"""
OFAC 50% Rule and Beneficial-Ownership Exposure Graph Engine.

Models a directed weighted shareholding graph W_{u -> v} in [0, 1].

- Blocking follows OFAC's 2014 guidance: an entity is blocked when blocked persons together
  hold 50% or more of it, where "blocked persons" includes entities already blocked under the
  same rule. Only holdings by blocked persons count; a stake held through an entity that is not
  itself blocked does not pass through. Computed as a fixpoint, so cross-holdings are safe.
- Exposure is the proportional look-through stake (products along every simple path from a
  listed person, summed). It is not a legal test, but an entity with 25% or more exposure
  (the EU AMLD beneficial-ownership level) is sent to enhanced due diligence. The threshold
  is configurable; India's PML Rules have used 10% for companies since 2023.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sancscreen.phonetics import normalize_tokens, transliterate


@dataclass
class GraphNode:
    """Represents a person or corporate entity in the ownership graph."""
    node_id: str
    name: str
    node_type: str = "entity"  # "individual" | "entity" | "shell_company"
    jurisdiction: str = "XX"
    is_sanctioned: bool = False
    sdn_id: Optional[str] = None
    program: Optional[str] = None


@dataclass
class OwnershipEdge:
    """Directed shareholding link: owner_id owns `share` (in [0, 1]) of target_id."""
    owner_id: str
    target_id: str
    share: float  # 0.0 to 1.0 (e.g. 0.60 = 60% equity stake)


@dataclass
class OwnershipPath:
    """Traces a single k-hop ownership chain from a sanctioned SDN root to a target company."""
    sdn_node_id: str
    sdn_name: str
    sdn_id: Optional[str]
    target_node_id: str
    target_name: str
    hop_count: int
    node_chain: List[str]
    name_chain: List[str]
    edge_shares: List[float]
    effective_share: float


@dataclass
class UBOResult:
    """Complete beneficial ownership risk assessment for a target corporate entity."""
    target_node_id: str
    target_name: str
    jurisdiction: str
    direct_sdn_match: bool
    aggregate_sdn_ownership: float  # Proportional look-through exposure to listed persons in [0, 1]
    blocked_owner_share: float      # Share held directly by blocked persons (the OFAC 50% test)
    ofac_50_rule_blocked: bool      # True if blocked persons hold >= 50%
    edd_25_rule_flagged: bool       # True if blocked, or exposure / blocked share >= the EDD threshold
    max_hop_depth: int
    sanctioned_owners: List[Dict[str, Any]] = field(default_factory=list)
    ownership_paths: List[OwnershipPath] = field(default_factory=list)
    risk_status: str = "CLEAR"      # "BLOCK_OFAC_50", "EDD_UBO_25", "LOW_SDN_EXPOSURE", "CLEAR"


class UBOGraphEngine:
    """
    Transitive Beneficial Ownership (UBO) Graph Engine supporting cycle-safe simple-path
    aggregation and truncated Neumann series matrix power evaluation E = sum_{k=1}^D W^k.
    """

    def __init__(
        self,
        nodes: Sequence[GraphNode] = (),
        edges: Sequence[OwnershipEdge] = (),
        max_depth: int = 6,
        ofac_threshold: float = 0.50,
        edd_threshold: float = 0.25,
    ) -> None:
        self.max_depth: int = max_depth
        self.ofac_threshold: float = ofac_threshold
        self.edd_threshold: float = edd_threshold
        self.nodes: Dict[str, GraphNode] = {}
        self.adj: Dict[str, List[OwnershipEdge]] = {}
        self.rev_adj: Dict[str, List[OwnershipEdge]] = {}
        self._name_to_node_id: Dict[str, str] = {}
        self._token_key_to_node_id: Dict[str, str] = {}
        self._sorted_token_key_to_node_id: Dict[str, str] = {}

        for n in nodes:
            self.add_node(n)
        for e in edges:
            self.add_edge(e)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.node_id] = node
        self.adj.setdefault(node.node_id, [])
        self.rev_adj.setdefault(node.node_id, [])

        norm_name = transliterate(node.name).strip().lower()
        if norm_name:
            self._name_to_node_id[norm_name] = node.node_id

        toks = normalize_tokens(node.name, strip_affixes=True)
        tok_key = " ".join(toks)
        if tok_key:
            self._token_key_to_node_id[tok_key] = node.node_id
            self._sorted_token_key_to_node_id[" ".join(sorted(toks))] = node.node_id

    def add_edge(self, edge: OwnershipEdge) -> None:
        if edge.share <= 0.0 or edge.share > 1.0:
            raise ValueError(f"Ownership share must be in (0, 1], got {edge.share}")
        if edge.owner_id not in self.nodes:
            self.add_node(GraphNode(node_id=edge.owner_id, name=edge.owner_id))
        if edge.target_id not in self.nodes:
            self.add_node(GraphNode(node_id=edge.target_id, name=edge.target_id))

        self.adj[edge.owner_id].append(edge)
        self.rev_adj[edge.target_id].append(edge)

    def resolve_node_id(self, identifier_or_name: str) -> Optional[str]:
        """Resolve either a graph node_id or a company/entity name to its canonical node_id."""
        if not identifier_or_name:
            return None
        if identifier_or_name in self.nodes:
            return identifier_or_name

        norm = transliterate(identifier_or_name).strip().lower()
        if norm in self._name_to_node_id:
            return self._name_to_node_id[norm]

        toks = normalize_tokens(identifier_or_name, strip_affixes=True)
        tok_key = " ".join(toks)
        if tok_key in self._token_key_to_node_id:
            return self._token_key_to_node_id[tok_key]

        sorted_key = " ".join(sorted(toks))
        if sorted_key in self._sorted_token_key_to_node_id:
            return self._sorted_token_key_to_node_id[sorted_key]

        return None

    def compute_matrix_power_sum(self, depth: Optional[int] = None) -> Tuple[List[str], List[List[float]]]:
        """
        Explicitly compute the truncated Neumann power series E = sum_{k=1}^D W^k
        over the ownership adjacency matrix W.
        Returns (ordered_node_ids, E_matrix).
        """
        d_max = depth if depth is not None else self.max_depth
        node_ids = sorted(self.nodes.keys())
        idx_map = {nid: i for i, nid in enumerate(node_ids)}
        n = len(node_ids)

        # Build W (n x n)
        W = [[0.0] * n for _ in range(n)]
        for u_id, edge_list in self.adj.items():
            u_idx = idx_map[u_id]
            for e in edge_list:
                v_idx = idx_map[e.target_id]
                W[u_idx][v_idx] += e.share

        # E = sum_{k=1}^{d_max} W^k
        E = [[W[i][j] for j in range(n)] for i in range(n)]
        W_power = [[W[i][j] for j in range(n)] for i in range(n)]

        for _ in range(2, d_max + 1):
            nxt = [[0.0] * n for _ in range(n)]
            for i in range(n):
                for k in range(n):
                    if W_power[i][k] == 0.0:
                        continue
                    wik = W_power[i][k]
                    for j in range(n):
                        if W[k][j] != 0.0:
                            nxt[i][j] += wik * W[k][j]
            W_power = nxt
            for i in range(n):
                for j in range(n):
                    E[i][j] += W_power[i][j]

        return node_ids, E

    def _enumerate_sanctioned_paths_to(self, target_id: str) -> List[OwnershipPath]:
        """
        Traverse upstream ownership links (reverse DFS, cycle-safe) from `target_id`
        up to `self.max_depth` hops to find all simple paths starting at a sanctioned node.
        """
        paths: List[OwnershipPath] = []
        target_node = self.nodes[target_id]

        # Stack holds: (current_node_id, node_chain_from_cur_to_target, edge_shares_from_cur_to_target, visited_set)
        stack: List[Tuple[str, List[str], List[float], Set[str]]] = [
            (target_id, [target_id], [], {target_id})
        ]

        while stack:
            curr_id, chain, shares, visited = stack.pop()
            hop_len = len(shares)

            if hop_len >= 1:
                curr_node = self.nodes[curr_id]
                if curr_node.is_sanctioned:
                    eff = 1.0
                    for s in shares:
                        eff *= s
                    paths.append(
                        OwnershipPath(
                            sdn_node_id=curr_node.node_id,
                            sdn_name=curr_node.name,
                            sdn_id=curr_node.sdn_id,
                            target_node_id=target_id,
                            target_name=target_node.name,
                            hop_count=hop_len,
                            node_chain=list(chain),
                            name_chain=[self.nodes[nid].name for nid in chain],
                            edge_shares=list(shares),
                            effective_share=round(eff, 6),
                        )
                    )

            if hop_len >= self.max_depth:
                continue

            for in_edge in self.rev_adj.get(curr_id, []):
                owner_id = in_edge.owner_id
                if owner_id in visited:
                    # Cycle prevention: never traverse the same node twice on a single path
                    continue
                stack.append(
                    (
                        owner_id,
                        [owner_id] + chain,
                        [in_edge.share] + shares,
                        visited | {owner_id},
                    )
                )

        paths.sort(key=lambda p: (p.effective_share, -p.hop_count), reverse=True)
        return paths

    def _blocked_share(self, node_id: str, blocked: Set[str]) -> float:
        return min(1.0, sum(e.share for e in self.rev_adj.get(node_id, []) if e.owner_id in blocked))

    def ofac_blocked_set(self) -> Set[str]:
        """
        Fixpoint of the OFAC 50% rule: start from the listed nodes and keep adding any entity
        that blocked nodes hold 50% or more of, until nothing changes.
        """
        blocked = {nid for nid, n in self.nodes.items() if n.is_sanctioned}
        changed = True
        while changed:
            changed = False
            for nid in self.nodes:
                if nid not in blocked and self._blocked_share(nid, blocked) >= self.ofac_threshold - 1e-9:
                    blocked.add(nid)
                    changed = True
        return blocked

    def evaluate_entity(self, identifier_or_name: str) -> Optional[UBOResult]:
        """
        Compute full transitive UBO sanctions exposure for a target entity (by node_id or name).
        Returns None if the entity is not present in the corporate ownership graph.
        """
        node_id = self.resolve_node_id(identifier_or_name)
        if node_id is None:
            return None

        target_node = self.nodes[node_id]
        paths = self._enumerate_sanctioned_paths_to(node_id)

        # Group effective ownership by each distinct sanctioned Ultimate Beneficial Owner
        by_sdn: Dict[str, Dict[str, Any]] = {}
        for p in paths:
            entry = by_sdn.setdefault(
                p.sdn_node_id,
                {
                    "sdn_node_id": p.sdn_node_id,
                    "sdn_name": p.sdn_name,
                    "sdn_id": p.sdn_id,
                    "effective_ownership": 0.0,
                    "min_hops": p.hop_count,
                    "max_hops": p.hop_count,
                    "path_count": 0,
                },
            )
            entry["effective_ownership"] = round(
                min(1.0, entry["effective_ownership"] + p.effective_share), 6
            )
            entry["min_hops"] = min(entry["min_hops"], p.hop_count)
            entry["max_hops"] = max(entry["max_hops"], p.hop_count)
            entry["path_count"] += 1

        sanctioned_owners = sorted(
            by_sdn.values(), key=lambda x: x["effective_ownership"], reverse=True
        )

        # Total proportional transitive ownership E = sum_{s in SDN} E_{s -> target}
        prop_total = min(1.0, sum(item["effective_ownership"] for item in sanctioned_owners))
        if target_node.is_sanctioned:
            prop_total = 1.0

        blocked = self.ofac_blocked_set()
        blocked_share = 1.0 if target_node.is_sanctioned else self._blocked_share(node_id, blocked)
        ofac_blocked = node_id in blocked
        edd_flagged = ofac_blocked or max(prop_total, blocked_share) >= (self.edd_threshold - 1e-9)

        if ofac_blocked:
            risk_status = "BLOCK_OFAC_50"
        elif edd_flagged:
            risk_status = "EDD_UBO_25"
        elif prop_total > 0.0:
            risk_status = "LOW_SDN_EXPOSURE"
        else:
            risk_status = "CLEAR"

        max_hops = max((p.hop_count for p in paths), default=0)

        return UBOResult(
            target_node_id=node_id,
            target_name=target_node.name,
            jurisdiction=target_node.jurisdiction,
            direct_sdn_match=target_node.is_sanctioned,
            aggregate_sdn_ownership=round(prop_total, 4),
            blocked_owner_share=round(blocked_share, 4),
            ofac_50_rule_blocked=ofac_blocked,
            edd_25_rule_flagged=edd_flagged,
            max_hop_depth=max_hops,
            sanctioned_owners=sanctioned_owners,
            ownership_paths=paths,
            risk_status=risk_status,
        )

    def scan_all_entities(self) -> List[UBOResult]:
        """Evaluate every non-individual entity in the graph and return sorted UBO assessments."""
        results: List[UBOResult] = []
        for nid, node in self.nodes.items():
            if node.node_type in ("entity", "shell_company"):
                res = self.evaluate_entity(nid)
                if res is not None:
                    results.append(res)
        results.sort(
            key=lambda r: (
                r.ofac_50_rule_blocked,
                r.edd_25_rule_flagged,
                r.aggregate_sdn_ownership,
            ),
            reverse=True,
        )
        return results
