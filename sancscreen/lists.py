"""
Curated Synthetic SDN Watchlist, Multi-Hop Corporate UBO Ownership Graph,
and 300 Benchmark SWIFT Wire Transfers.

Covers:
(a) Exact matches (Latin SDN names with/without honorifics & corporate suffixes)
(b) Devanagari (Hindi), Arabic, and Cyrillic script transliterations
(c) Reordered name tokens & cross-dialect phonetic spelling variants
(d) 2-hop and 3-hop UBO shell companies (aggregate SDN ownership >= 50% under OFAC rule)
(e) Hard negatives:
    - Innocent customers sharing names with sanctioned individuals but with distinct DOB/Country
    - Legitimate companies sharing generic corporate boilerplate words ("Oil Company OJSC",
      "Global Trading LLC", "General Aviation Co")
    - Companies with < 50% sanctioned ownership (e.g. 35% and 12% SDN stake)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sancscreen.matcher import SDNEntry
from sancscreen.ubo import GraphNode, OwnershipEdge, UBOGraphEngine


@dataclass
class WireTransferCase:
    """A labeled benchmark SWIFT MT103 / ISO-20022 pacs.008 wire screening test case."""
    wire_id: str
    category: str  # "exact_match" | "cross_script" | "phonetic_reordered" | "ubo_shell" | "hard_negative"
    party_name: str
    entity_type: str
    dob: Optional[str]
    country: Optional[str]
    identifier: Optional[str]
    amount_usd: float
    should_block: bool
    expected_sdn_or_ubo_id: Optional[str] = None
    notes: str = ""


def get_default_watchlist() -> List[SDNEntry]:
    """Return the curated 20-entry multi-jurisdictional SDN watchlist."""
    return [
        SDNEntry(
            sdn_id="SDN-001",
            name="Viktor Anatolyevich But",
            entity_type="individual",
            program="OFAC-SDN-TRANSNATIONAL",
            aliases=["Viktor But", "Victor Bout", "Viktor Anatolievich Bout"],
            dob="1967-01-13",
            countries=["RU", "TJ"],
            identifiers=["RU7788991", "P9910234"],
            remarks="International arms trafficking network.",
        ),
        SDNEntry(
            sdn_id="SDN-002",
            name="Tariq Al-Rashid",
            entity_type="individual",
            program="OFAC-SYRIA",
            aliases=["Tarek Al Rasheed", "Tariq ibn Rashid"],
            dob="1968-04-12",
            countries=["SY", "IQ"],
            identifiers=["SY9928172"],
            remarks="Sanctioned illicit finance facilitator.",
        ),
        SDNEntry(
            sdn_id="SDN-003",
            name="Muammar Al-Qaddafi",
            entity_type="individual",
            program="UN-LY-1970",
            aliases=["Moammar Gaddafi", "Muammar Kadhafi", "Mouammar Al Gathafi"],
            dob="1942-06-07",
            countries=["LY"],
            identifiers=["LY0011223"],
            remarks="Frozen regime assets.",
        ),
        SDNEntry(
            sdn_id="SDN-004",
            name="Qasim Suleimani",
            entity_type="individual",
            program="OFAC-IRAN-SDGT",
            aliases=["Qasem Soleimani", "Qasim Sulaymani"],
            dob="1957-03-11",
            countries=["IR"],
            identifiers=["IR5544332"],
            remarks="IRGC-QF designation.",
        ),
        SDNEntry(
            sdn_id="SDN-005",
            name="Sergei Viktorovich Lavrov",
            entity_type="individual",
            program="OFAC-RUSSIA-EO14024",
            aliases=["Sergei Lavrov", "Sergey Lavrov"],
            dob="1950-03-21",
            countries=["RU"],
            identifiers=["RU1002003"],
            remarks="Senior government official.",
        ),
        SDNEntry(
            sdn_id="SDN-006",
            name="Yevgeny Viktorovich Prigozhin",
            entity_type="individual",
            program="OFAC-RUSSIA-EO14024",
            aliases=["Yevgeny Prigozhin", "Evgeny Prigozhin"],
            dob="1961-06-01",
            countries=["RU"],
            identifiers=["RU6611229"],
            remarks="Paramilitary & resource network.",
        ),
        SDNEntry(
            sdn_id="SDN-007",
            name="Oleg Vladimirovich Deripaska",
            entity_type="individual",
            program="OFAC-RUSSIA-EO13662",
            aliases=["Oleg Deripaska"],
            dob="1968-01-02",
            countries=["RU", "CY"],
            identifiers=["RU8844112"],
            remarks="Industrial conglomerate beneficial owner.",
        ),
        SDNEntry(
            sdn_id="SDN-008",
            name="Aleksandr Grigoryevich Lukashenko",
            entity_type="individual",
            program="OFAC-BELARUS",
            aliases=["Aleksandr Lukashenko", "Alexander Lukashenko", "Aliaksandr Lukashenka"],
            dob="1954-08-30",
            countries=["BY"],
            identifiers=["BY0000101"],
            remarks="Belarus sanctions program.",
        ),
        SDNEntry(
            sdn_id="SDN-009",
            name="Hassan Nasrallah",
            entity_type="individual",
            program="OFAC-SDGT",
            aliases=["Sayyid Hassan Nasrallah", "Hasan Nasrallah"],
            dob="1960-08-31",
            countries=["LB"],
            identifiers=["LB3399110"],
            remarks="SDGT leadership designation.",
        ),
        SDNEntry(
            sdn_id="SDN-010",
            name="Bashar Al-Assad",
            entity_type="individual",
            program="OFAC-SYRIA",
            aliases=["Bashar Hafez Al Assad", "Bachar El Assad"],
            dob="1965-09-11",
            countries=["SY"],
            identifiers=["SY0001965"],
            remarks="Syria sanctions regime.",
        ),
        SDNEntry(
            sdn_id="SDN-011",
            name="Mohammed Ibrahim Al-Masri",
            entity_type="individual",
            program="OFAC-SDGT",
            aliases=["Muhammad Ibrahim Al Masri", "Mohamed Al-Masri"],
            dob="1963-07-19",
            countries=["EG", "PS"],
            identifiers=["EG7712300"],
            remarks="Designated militant operative.",
        ),
        SDNEntry(
            sdn_id="SDN-012",
            name="Ahmed Abdullah Al-Baghdadi",
            entity_type="individual",
            program="UN-1267-ISIL",
            aliases=["Ahmad Abdulla Al Baghdadi", "Ahmed Al-Baghdadi"],
            dob="1971-05-04",
            countries=["IQ"],
            identifiers=["IQ8823411"],
            remarks="UN Security Council 1267 list.",
        ),
        SDNEntry(
            sdn_id="SDN-013",
            name="Dmitry Anatolyevich Medvedev",
            entity_type="individual",
            program="OFAC-RUSSIA-EO14024",
            aliases=["Dmitry Medvedev", "Dmitri Medvedev"],
            dob="1965-09-14",
            countries=["RU"],
            identifiers=["RU2020303"],
            remarks="Senior security council official.",
        ),
        SDNEntry(
            sdn_id="SDN-014",
            name="Rami Makhlouf",
            entity_type="individual",
            program="OFAC-SYRIA",
            aliases=["Rami Mohammad Makhlouf"],
            dob="1969-07-10",
            countries=["SY", "CY"],
            identifiers=["SY4455667"],
            remarks="Regime commercial holding network.",
        ),
        SDNEntry(
            sdn_id="SDN-015",
            name="Ramzan Akhmadovich Kadyrov",
            entity_type="individual",
            program="OFAC-MAGNITSKY",
            aliases=["Ramzan Kadyrov"],
            dob="1976-10-05",
            countries=["RU"],
            identifiers=["RU9900112"],
            remarks="Global Magnitsky designation.",
        ),
        SDNEntry(
            sdn_id="SDN-016",
            name="Al-Noor Global Trading LLC",
            entity_type="entity",
            program="OFAC-SYRIA",
            aliases=["Sharikah Al Noor Lil Tijarah", "Al Noor Trading LLC"],
            dob=None,
            countries=["SY", "AE"],
            identifiers=["LEI549300NOOR001"],
            remarks="Sanctioned front trading house.",
        ),
        SDNEntry(
            sdn_id="SDN-017",
            name="Rosneft Oil Company OJSC",
            entity_type="entity",
            program="OFAC-SSI-EO13662",
            aliases=["PAO NK Rosneft", "Rosneft"],
            dob=None,
            countries=["RU"],
            identifiers=["LEI253400ROSNEFT"],
            remarks="Sectoral & blocking sanctions.",
        ),
        SDNEntry(
            sdn_id="SDN-018",
            name="Mahan Air General Aviation Co",
            entity_type="entity",
            program="OFAC-IRAN-SDGT",
            aliases=["Mahan Airlines", "Mahan Air"],
            dob=None,
            countries=["IR"],
            identifiers=["BICMAHANIRTH"],
            remarks="Sanctioned aviation carrier.",
        ),
        SDNEntry(
            sdn_id="SDN-019",
            name="Korea Ryonbong General Corporation",
            entity_type="entity",
            program="OFAC-DPRK-WMD",
            aliases=["Ryonbong General Corp"],
            dob=None,
            countries=["KP"],
            identifiers=["KP9900881"],
            remarks="WMD proliferation procurement entity.",
        ),
        SDNEntry(
            sdn_id="SDN-020",
            name="Gazprombank JSC",
            entity_type="entity",
            program="OFAC-RUSSIA-EO14024",
            aliases=["GPB Bank JSC", "Gazprombank"],
            dob=None,
            countries=["RU"],
            identifiers=["BICGAZPRUMM"],
            remarks="Sanctioned financial institution.",
        ),
    ]


def build_default_ubo_graph() -> UBOGraphEngine:
    """
    Build the corporate beneficial ownership graph with:
    - 5 multi-hop OFAC 50%-rule blocked shell companies (aggregate SDN ownership >= 50%)
    - 1 minority SDN exposure company (35% SDN stake -> EDD 25% flagged, NOT OFAC 50% blocked)
    - 1 low SDN exposure company (12% SDN stake -> CLEAR)
    - 1 completely clean company (0% SDN stake -> CLEAR)
    - Circular cross-holding edges to verify cycle-safe traversal
    """
    nodes = [
        # Root Sanctioned SDN Owners
        GraphNode("SDN-001", "Viktor Anatolyevich But", "individual", "RU", True, "SDN-001", "OFAC-SDN-TRANSNATIONAL"),
        GraphNode("SDN-002", "Tariq Al-Rashid", "individual", "SY", True, "SDN-002", "OFAC-SYRIA"),
        GraphNode("SDN-004", "Qasim Suleimani", "individual", "IR", True, "SDN-004", "OFAC-IRAN-SDGT"),
        GraphNode("SDN-006", "Yevgeny Viktorovich Prigozhin", "individual", "RU", True, "SDN-006", "OFAC-RUSSIA-EO14024"),
        GraphNode("SDN-007", "Oleg Vladimirovich Deripaska", "individual", "RU", True, "SDN-007", "OFAC-RUSSIA-EO13662"),
        GraphNode("SDN-014", "Rami Makhlouf", "individual", "SY", True, "SDN-014", "OFAC-SYRIA"),
        GraphNode("SDN-017", "Rosneft Oil Company OJSC", "entity", "RU", True, "SDN-017", "OFAC-SSI-EO13662"),

        # Non-Sanctioned Institutional / Private Co-Investors
        GraphNode("CLEAN-OWNER-01", "Anatolia Maritime Pension Fund", "entity", "TR", False),
        GraphNode("CLEAN-OWNER-02", "Temasek Sovereign Tech Ventures", "entity", "SG", False),
        GraphNode("CLEAN-OWNER-03", "Zurich Cantonal Private Equity AG", "entity", "CH", False),

        # Intermediate Holding Layer (Tier 1 & Tier 2)
        GraphNode("HOLD-01", "Caspian Venture Holdings Ltd", "shell_company", "CY", False),
        GraphNode("HOLD-02", "Neva Industrial Investments LLC", "shell_company", "AE", False),
        GraphNode("HOLD-03", "Levant Oasis Capital Ltd", "shell_company", "LB", False),
        GraphNode("HOLD-04", "Phoenicia Energy Partners SA", "shell_company", "PA", False),
        GraphNode("HOLD-05", "Steppe Aero Holdings Ltd", "shell_company", "SC", False),
        GraphNode("HOLD-06", "Ural Freight Ventures Corp", "shell_company", "CY", False),
        GraphNode("HOLD-07", "Damascus Crown Investments LLC", "shell_company", "SY", False),
        GraphNode("HOLD-08", "Hormuz Star Trading Co", "shell_company", "IR", False),
        GraphNode("HOLD-09", "Baltic Terminal Alpha BV", "shell_company", "NL", False),
        GraphNode("HOLD-10", "Arctic Fleet Management Ltd", "shell_company", "MT", False),

        # Target Operational / Shell Entities Appearing on SWIFT Wire Transfers
        # 1) 2-hop Joint SDN Shell: Deripaska (60%*50%=30%) + Prigozhin (50%*50%=25%) = 55% >= 50%
        GraphNode("UBO-SHELL-01", "Blue Horizon Maritime Logistics Ltd", "shell_company", "VG", False),
        # 2) 3-hop Deep Chain Shell: Tariq Al-Rashid (90%*70%*90% = 56.7% >= 50%)
        GraphNode("UBO-SHELL-02", "Aegean Star Petrotech FZE", "shell_company", "AE", False),
        # 3) 3-hop + 2-hop Multi-SDN Shell: Viktor But (80%*80%*50%=32%) + Rami Makhlouf (50%*40%=20%) = 52% >= 50%
        GraphNode("UBO-SHELL-03", "Vostok Meridian Chartering GmbH", "shell_company", "CH", False),
        # 4) 2-hop Single-SDN Shell: Qasim Suleimani (80%*80% = 64% >= 50%)
        GraphNode("UBO-SHELL-04", "Saffron Gulf Petrochemicals DMCC", "shell_company", "AE", False),
        # 5) 2-hop Corporate SDN + Cycle Shell: Rosneft (75%*80% = 60% >= 50%)
        GraphNode("UBO-SHELL-05", "Nordic Baltic Bunker Services AS", "shell_company", "EE", False),

        # Non-Blocked Minority SDN Exposure Entities (< 50% OFAC threshold)
        # 6) 35% SDN ownership (Deripaska 35% + Anatolia Pension Fund 65%) -> < 50% (EDD 25% only, not OFAC blocked)
        GraphNode("UBO-MIN-01", "Emerald Bosporus Shipping Co", "entity", "TR", False),
        # 7) 12% SDN ownership (HOLD-01 20% -> 60%*20% = 12% Deripaska, Zurich Equity 80%) -> CLEAR
        GraphNode("UBO-MIN-02", "Helvetia Alpine Precision AG", "entity", "CH", False),
        # 8) 0% SDN ownership -> CLEAR
        GraphNode("UBO-CLEAN-01", "Pacific Rim Semiconductor Corp", "entity", "SG", False),
    ]

    edges = [
        # Shell 1: Blue Horizon Maritime Logistics Ltd (30% + 25% = 55%)
        OwnershipEdge("SDN-007", "HOLD-01", 0.60),
        OwnershipEdge("SDN-006", "HOLD-02", 0.50),
        OwnershipEdge("HOLD-01", "UBO-SHELL-01", 0.50),
        OwnershipEdge("HOLD-02", "UBO-SHELL-01", 0.50),

        # Shell 2: Aegean Star Petrotech FZE (90% * 70% * 90% = 56.7%)
        OwnershipEdge("SDN-002", "HOLD-03", 0.90),
        OwnershipEdge("HOLD-03", "HOLD-04", 0.70),
        OwnershipEdge("HOLD-04", "UBO-SHELL-02", 0.90),

        # Shell 3: Vostok Meridian Chartering GmbH (80%*80%*50% + 50%*40% = 32% + 20% = 52%)
        OwnershipEdge("SDN-001", "HOLD-05", 0.80),
        OwnershipEdge("HOLD-05", "HOLD-06", 0.80),
        OwnershipEdge("HOLD-06", "UBO-SHELL-03", 0.50),
        OwnershipEdge("SDN-014", "HOLD-07", 0.50),
        OwnershipEdge("HOLD-07", "UBO-SHELL-03", 0.40),

        # Shell 4: Saffron Gulf Petrochemicals DMCC (80% * 80% = 64%)
        OwnershipEdge("SDN-004", "HOLD-08", 0.80),
        OwnershipEdge("HOLD-08", "UBO-SHELL-04", 0.80),

        # Shell 5: Nordic Baltic Bunker Services AS (75% * 80% = 60%) + circular cross-holding
        OwnershipEdge("SDN-017", "HOLD-09", 0.75),
        OwnershipEdge("HOLD-09", "UBO-SHELL-05", 0.80),
        # Circular cross-holding between HOLD-09 and HOLD-10 to test cycle safety
        OwnershipEdge("HOLD-09", "HOLD-10", 0.10),
        OwnershipEdge("HOLD-10", "HOLD-09", 0.10),

        # Minority SDN Entity 1: Emerald Bosporus Shipping Co (35% SDN < 50%)
        OwnershipEdge("SDN-007", "UBO-MIN-01", 0.35),
        OwnershipEdge("CLEAN-OWNER-01", "UBO-MIN-01", 0.65),

        # Minority SDN Entity 2: Helvetia Alpine Precision AG (60% * 20% = 12% SDN < 25%)
        OwnershipEdge("HOLD-01", "UBO-MIN-02", 0.20),
        OwnershipEdge("CLEAN-OWNER-03", "UBO-MIN-02", 0.80),

        # Clean Entity: Pacific Rim Semiconductor Corp (0% SDN)
        OwnershipEdge("CLEAN-OWNER-02", "UBO-CLEAN-01", 1.00),
    ]

    return UBOGraphEngine(nodes=nodes, edges=edges, max_depth=6)


def generate_benchmark_wires() -> List[WireTransferCase]:
    """
    Generate exactly 300 labeled test wire transfers across all 5 categories:
    - Category A: exact_match (30 wires, positive)
    - Category B: cross_script (45 wires, positive)
    - Category C: phonetic_reordered (45 wires, positive)
    - Category D: ubo_shell (30 wires, positive)
    - Category E: hard_negative (150 wires, negative)
    Total = 300 wires (150 positive, 150 negative).
    """
    cases: List[WireTransferCase] = []
    idx = 1

    def add_case(
        category: str,
        party_name: str,
        entity_type: str,
        dob: Optional[str],
        country: Optional[str],
        identifier: Optional[str],
        amount_usd: float,
        should_block: bool,
        expected_id: Optional[str],
        notes: str,
    ) -> None:
        nonlocal idx
        cases.append(
            WireTransferCase(
                wire_id=f"WIRE-{idx:04d}",
                category=category,
                party_name=party_name,
                entity_type=entity_type,
                dob=dob,
                country=country,
                identifier=identifier,
                amount_usd=amount_usd,
                should_block=should_block,
                expected_sdn_or_ubo_id=expected_id,
                notes=notes,
            )
        )
        idx += 1

    # -----------------------------------------------------------------------
    # (a) Category A: Exact & Affix-Normalized Latin Matches (30 wires)
    # -----------------------------------------------------------------------
    exact_templates = [
        ("Viktor Anatolyevich But", "individual", "1967-01-13", "RU", "RU7788991", "SDN-001"),
        ("Tariq Al-Rashid", "individual", "1968-04-12", "SY", "SY9928172", "SDN-002"),
        ("Muammar Al-Qaddafi", "individual", "1942-06-07", "LY", None, "SDN-003"),
        ("Qasim Suleimani", "individual", "1957-03-11", "IR", "IR5544332", "SDN-004"),
        ("Sergei Viktorovich Lavrov", "individual", "1950-03-21", "RU", None, "SDN-005"),
        ("Yevgeny Viktorovich Prigozhin", "individual", "1961-06-01", "RU", None, "SDN-006"),
        ("Oleg Vladimirovich Deripaska", "individual", "1968-01-02", "RU", "RU8844112", "SDN-007"),
        ("Aleksandr Grigoryevich Lukashenko", "individual", "1954-08-30", "BY", None, "SDN-008"),
        ("Hassan Nasrallah", "individual", "1960-08-31", "LB", None, "SDN-009"),
        ("Bashar Al-Assad", "individual", "1965-09-11", "SY", None, "SDN-010"),
        ("Mohammed Ibrahim Al-Masri", "individual", "1963-07-19", "EG", None, "SDN-011"),
        ("Ahmed Abdullah Al-Baghdadi", "individual", "1971-05-04", "IQ", None, "SDN-012"),
        ("Dmitry Anatolyevich Medvedev", "individual", "1965-09-14", "RU", None, "SDN-013"),
        ("Rami Makhlouf", "individual", "1969-07-10", "SY", None, "SDN-014"),
        ("Ramzan Akhmadovich Kadyrov", "individual", "1976-10-05", "RU", None, "SDN-015"),
        ("Al-Noor Global Trading LLC", "entity", None, "SY", "LEI549300NOOR001", "SDN-016"),
        ("Rosneft Oil Company OJSC", "entity", None, "RU", "LEI253400ROSNEFT", "SDN-017"),
        ("Mahan Air General Aviation Co", "entity", None, "IR", "BICMAHANIRTH", "SDN-018"),
        ("Korea Ryonbong General Corporation", "entity", None, "KP", None, "SDN-019"),
        ("Gazprombank JSC", "entity", None, "RU", "BICGAZPRUMM", "SDN-020"),
        ("Mr. Viktor Anatolyevich But", "individual", "1967-01-13", "RU", None, "SDN-001"),
        ("Sheikh Tariq Al-Rashid", "individual", "1968-04-12", "SY", None, "SDN-002"),
        ("Gen. Qasim Suleimani", "individual", "1957-03-11", "IR", None, "SDN-004"),
        ("Dr. Bashar Al-Assad", "individual", "1965-09-11", "SY", None, "SDN-010"),
        ("Mr. Oleg Vladimirovich Deripaska", "individual", "1968-01-02", "CY", None, "SDN-007"),
        ("Shri Rami Makhlouf", "individual", "1969-07-10", "SY", None, "SDN-014"),
        ("Col. Ramzan Akhmadovich Kadyrov", "individual", "1976-10-05", "RU", None, "SDN-015"),
        ("Al-Noor Global Trading Limited", "entity", None, "AE", None, "SDN-016"),
        ("Rosneft Oil Company PJSC", "entity", None, "RU", None, "SDN-017"),
        ("Gazprombank OOO", "entity", None, "RU", None, "SDN-020"),
    ]
    for i, (nm, etype, dob, ctry, ident, sdn_id) in enumerate(exact_templates):
        add_case(
            "exact_match", nm, etype, dob, ctry, ident,
            125_000.0 + i * 5_000.0, True, sdn_id, "Exact or honorific-prefixed SDN name"
        )

    # -----------------------------------------------------------------------
    # (b) Category B: Multi-Script Transliterations (45 wires: Hindi, Arabic, Cyrillic)
    # -----------------------------------------------------------------------
    script_templates = [
        # Devanagari (Hindi) - 15 cases
        ("विक्टर बुट", "individual", "1967-01-13", "RU", None, "SDN-001", "Devanagari Viktor But"),
        ("श्री विक्टर बुट", "individual", "1967-01-13", "RU", None, "SDN-001", "Devanagari with Shri honorific"),
        ("तारिक अल रशीद", "individual", "1968-04-12", "SY", None, "SDN-002", "Devanagari Tariq Al-Rashid"),
        ("शेख तारिक अल रशीद", "individual", "1968-04-12", "SY", None, "SDN-002", "Devanagari Sheikh Tariq Al-Rashid"),
        ("कासिम सुलेमानी", "individual", "1957-03-11", "IR", None, "SDN-004", "Devanagari Qasim Suleimani"),
        ("क़ासिम सुलेमानी", "individual", "1957-03-11", "IR", None, "SDN-004", "Devanagari Nukta Qasim Suleimani"),
        ("सर्गेई लावरोव", "individual", "1950-03-21", "RU", None, "SDN-005", "Devanagari Sergei Lavrov"),
        ("येवगेनी प्रिगोज़िन", "individual", "1961-06-01", "RU", None, "SDN-006", "Devanagari Yevgeny Prigozhin"),
        ("ओलेग देरिपास्का", "individual", "1968-01-02", "RU", None, "SDN-007", "Devanagari Oleg Deripaska"),
        ("अलेक्जेंडर लुकाशेंको", "individual", "1954-08-30", "BY", None, "SDN-008", "Devanagari Aleksandr Lukashenko"),
        ("हसन नसरल्लाह", "individual", "1960-08-31", "LB", None, "SDN-009", "Devanagari Hassan Nasrallah"),
        ("बशर अल असद", "individual", "1965-09-11", "SY", None, "SDN-010", "Devanagari Bashar Al-Assad"),
        ("मोहम्मद इब्राहिम अल मसरी", "individual", "1963-07-19", "EG", None, "SDN-011", "Devanagari Mohammed Ibrahim Al-Masri"),
        ("अहमद अब्दुल्ला अल बगदादी", "individual", "1971-05-04", "IQ", None, "SDN-012", "Devanagari Ahmed Abdullah Al-Baghdadi"),
        ("रामी मखलूफ", "individual", "1969-07-10", "SY", None, "SDN-014", "Devanagari Rami Makhlouf"),

        # Arabic - 15 cases
        ("طارق الرشيد", "individual", "1968-04-12", "SY", None, "SDN-002", "Arabic Tariq Al-Rashid"),
        ("الشيخ طارق الرشيد", "individual", "1968-04-12", "SY", None, "SDN-002", "Arabic Sheikh Tariq Al-Rashid"),
        ("طارق بن رشيد", "individual", "1968-04-12", "SY", None, "SDN-002", "Arabic Tariq bin Rashid"),
        ("معمر القذافي", "individual", "1942-06-07", "LY", None, "SDN-003", "Arabic Muammar Al-Qaddafi"),
        ("قاسم سليماني", "individual", "1957-03-11", "IR", None, "SDN-004", "Arabic Qasim Suleimani"),
        ("حسن نصر الله", "individual", "1960-08-31", "LB", None, "SDN-009", "Arabic Hassan Nasrallah"),
        ("حسن نصرالله", "individual", "1960-08-31", "LB", None, "SDN-009", "Arabic compound Hassan Nasrallah"),
        ("بشار الأسد", "individual", "1965-09-11", "SY", None, "SDN-010", "Arabic Bashar Al-Assad"),
        ("بشار الاسد", "individual", "1965-09-11", "SY", None, "SDN-010", "Arabic unhamzated Bashar Al-Assad"),
        ("محمد إبراهيم المصري", "individual", "1963-07-19", "EG", None, "SDN-011", "Arabic Mohammed Ibrahim Al-Masri"),
        ("محمد ابراهيم المصري", "individual", "1963-07-19", "EG", None, "SDN-011", "Arabic unhamzated Mohammed Ibrahim Al-Masri"),
        ("أحمد عبدالله البغدادي", "individual", "1971-05-04", "IQ", None, "SDN-012", "Arabic Ahmed Abdullah Al-Baghdadi"),
        ("فيكتور بوت", "individual", "1967-01-13", "RU", None, "SDN-001", "Arabic Viktor But"),
        ("سيرغي لافروف", "individual", "1950-03-21", "RU", None, "SDN-005", "Arabic Sergei Lavrov"),
        ("شركة النور للتجارة", "entity", None, "SY", None, "SDN-016", "Arabic Al-Noor Trading Company"),

        # Cyrillic - 15 cases
        ("Виктор Бут", "individual", "1967-01-13", "RU", None, "SDN-001", "Cyrillic Viktor But"),
        ("Виктор Анатольевич Бут", "individual", "1967-01-13", "RU", None, "SDN-001", "Cyrillic full Viktor Anatolyevich But"),
        ("Бут Виктор Анатольевич", "individual", "1967-01-13", "RU", None, "SDN-001", "Cyrillic reordered But Viktor"),
        ("Сергей Лавров", "individual", "1950-03-21", "RU", None, "SDN-005", "Cyrillic Sergei Lavrov"),
        ("Сергей Викторович Лавров", "individual", "1950-03-21", "RU", None, "SDN-005", "Cyrillic full Sergei Viktorovich Lavrov"),
        ("Евгений Пригожин", "individual", "1961-06-01", "RU", None, "SDN-006", "Cyrillic Yevgeny Prigozhin"),
        ("Пригожин Евгений Викторович", "individual", "1961-06-01", "RU", None, "SDN-006", "Cyrillic reordered Prigozhin"),
        ("Олег Дерипаска", "individual", "1968-01-02", "RU", None, "SDN-007", "Cyrillic Oleg Deripaska"),
        ("Дерипаска Олег Владимирович", "individual", "1968-01-02", "RU", None, "SDN-007", "Cyrillic reordered Deripaska"),
        ("Александр Лукашенко", "individual", "1954-08-30", "BY", None, "SDN-008", "Cyrillic Aleksandr Lukashenko"),
        ("Лукашенко Александр Григорьевич", "individual", "1954-08-30", "BY", None, "SDN-008", "Cyrillic reordered Lukashenko"),
        ("Дмитрий Медведев", "individual", "1965-09-14", "RU", None, "SDN-013", "Cyrillic Dmitry Medvedev"),
        ("Рамзан Кадыров", "individual", "1976-10-05", "RU", None, "SDN-015", "Cyrillic Ramzan Kadyrov"),
        ("ПАО НК Роснефть", "entity", None, "RU", None, "SDN-017", "Cyrillic PAO NK Rosneft"),
        ("Газпромбанк АО", "entity", None, "RU", None, "SDN-020", "Cyrillic Gazprombank AO"),
    ]
    for i, (nm, etype, dob, ctry, ident, sdn_id, note) in enumerate(script_templates):
        add_case(
            "cross_script", nm, etype, dob, ctry, ident,
            210_000.0 + i * 3_500.0, True, sdn_id, note
        )

    # -----------------------------------------------------------------------
    # (c) Category C: Reordered Tokens & Cross-Dialect Phonetic Variants (45 wires)
    # -----------------------------------------------------------------------
    phonetic_templates = [
        ("But, Viktor Anatolyevich", "individual", "1967-01-13", "RU", None, "SDN-001", "Surname-first Viktor But"),
        ("Bout, Victor", "individual", "1967-01-13", "RU", None, "SDN-001", "French/English spelling Victor Bout"),
        ("Victor A. Bout", "individual", "1967-01-13", "RU", None, "SDN-001", "Middle initial + Bout variant"),
        ("Al-Rasheed, Tarek", "individual", "1968-04-12", "SY", None, "SDN-002", "Reordered + ee/k phonetic variant"),
        ("Rashid, Sheikh Tarik Bin", "individual", "1968-04-12", "SY", None, "SDN-002", "Tarik + Bin + Sheikh reordered"),
        ("Tarek El-Rachid", "individual", "1968-04-12", "SY", None, "SDN-002", "North African French transliteration"),
        ("Gaddafi, Moammar", "individual", "1942-06-07", "LY", None, "SDN-003", "Gaddafi dialectal Qaf variant"),
        ("Kadhafi, Muammar", "individual", "1942-06-07", "LY", None, "SDN-003", "Kadhafi French transliteration"),
        ("Al-Qadhafi, Mouammar", "individual", "1942-06-07", "LY", None, "SDN-003", "Qadhafi variant"),
        ("Soleimani, Qasem", "individual", "1957-03-11", "IR", None, "SDN-004", "Persian o/e vowel transliteration"),
        ("Sulaymani, Gen. Kasim", "individual", "1957-03-11", "IR", None, "SDN-004", "Kasim Sulaymani K/ay variant"),
        ("Qassim Soleymani", "individual", "1957-03-11", "IR", None, "SDN-004", "Double-s + ey variant"),
        ("Lavrov, Sergey Viktorovich", "individual", "1950-03-21", "RU", None, "SDN-005", "Reordered Sergey Lavrov"),
        ("Sergey V. Lavrov", "individual", "1950-03-21", "RU", None, "SDN-005", "Initial + ey variant"),
        ("Sergii Lavrov", "individual", "1950-03-21", "RU", None, "SDN-005", "Ukrainian/Slavic Sergii spelling"),
        ("Prigozhin, Evgeny Viktorovich", "individual", "1961-06-01", "RU", None, "SDN-006", "Evgeny without initial Y"),
        ("Evgenii Prigozhin", "individual", "1961-06-01", "RU", None, "SDN-006", "Evgenii double-i transliteration"),
        ("Prigozhyn, Yevgeniy", "individual", "1961-06-01", "RU", None, "SDN-006", "Y-vowel phonetic variant"),
        ("Deripaska, Oleg Vladimirovich", "individual", "1968-01-02", "RU", None, "SDN-007", "Reordered Oleg Deripaska"),
        ("Oleh V. Derypaska", "individual", "1968-01-02", "CY", None, "SDN-007", "Derypaska y-vowel variant"),
        ("Lukashenko, Alexander", "individual", "1954-08-30", "BY", None, "SDN-008", "Alexander x-variant reordered"),
        ("Lukashenka, Aliaksandr", "individual", "1954-08-30", "BY", None, "SDN-008", "Belarusian national orthography"),
        ("Oleksandr Lukashenko", "individual", "1954-08-30", "BY", None, "SDN-008", "Slavic Oleksandr variant"),
        ("Nasrallah, Sayyid Hasan", "individual", "1960-08-31", "LB", None, "SDN-009", "Single-s Hasan reordered"),
        ("Hassan Nasralla", "individual", "1960-08-31", "LB", None, "SDN-009", "Dropped trailing silent h"),
        ("Assad, Bashar Hafez Al", "individual", "1965-09-11", "SY", None, "SDN-010", "Reordered Bashar Al-Assad"),
        ("Bachar El-Asad", "individual", "1965-09-11", "SY", None, "SDN-010", "French ch + single-s Asad"),
        ("Al-Masri, Muhammad Ibrahim", "individual", "1963-07-19", "EG", None, "SDN-011", "Muhammad variant reordered"),
        ("Mohamed Ebrahim El-Masry", "individual", "1963-07-19", "EG", None, "SDN-011", "Mohamed Ebrahim Masry variant"),
        ("Muhammed I. Al-Masri", "individual", "1963-07-19", "PS", None, "SDN-011", "Muhammed with middle initial"),
        ("Al-Baghdadi, Ahmad Abdulla", "individual", "1971-05-04", "IQ", None, "SDN-012", "Ahmad Abdulla reordered"),
        ("Ahmed Abdallah Baghdady", "individual", "1971-05-04", "IQ", None, "SDN-012", "Abdallah + Baghdady y-ending"),
        ("Medvedev, Dmitri Anatolyevich", "individual", "1965-09-14", "RU", None, "SDN-013", "Dmitri i-ending reordered"),
        ("Dmitriy A. Medvedev", "individual", "1965-09-14", "RU", None, "SDN-013", "Dmitriy iy-ending"),
        ("Makhlouf, Rami Mohammad", "individual", "1969-07-10", "SY", None, "SDN-014", "Reordered Rami Makhlouf"),
        ("Ramy Makhluf", "individual", "1969-07-10", "SY", None, "SDN-014", "Ramy Makhluf u-vowel variant"),
        ("Kadyrov, Ramzan Akhmadovich", "individual", "1976-10-05", "RU", None, "SDN-015", "Reordered Ramzan Kadyrov"),
        ("Ramzan Ahmadovich Kadirov", "individual", "1976-10-05", "RU", None, "SDN-015", "Kadirov i-vowel + kh->h variant"),
        ("Trading Global Al-Noor LLC", "entity", None, "SY", None, "SDN-016", "Reordered entity tokens"),
        ("Sharikah Al-Nour Lil-Tijara", "entity", None, "AE", None, "SDN-016", "Transliterated Arabic alias variant"),
        ("Oil Company Rosneft OJSC", "entity", None, "RU", None, "SDN-017", "Reordered Rosneft tokens"),
        ("Aviation General Mahan Air Co", "entity", None, "IR", None, "SDN-018", "Reordered Mahan Air tokens"),
        ("Ryonbong Korea General Corp", "entity", None, "KP", None, "SDN-019", "Reordered Korea Ryonbong"),
        ("V. A. But", "individual", "1967-01-13", "RU", "RU7788991", "SDN-001", "Initials + exact passport ID match"),
        ("T. Al-Rashid", "individual", "1968-04-12", "SY", "SY9928172", "SDN-002", "Initial + exact passport ID match"),
    ]
    for i, (nm, etype, dob, ctry, ident, sdn_id, note) in enumerate(phonetic_templates):
        add_case(
            "phonetic_reordered", nm, etype, dob, ctry, ident,
            180_000.0 + i * 4_200.0, True, sdn_id, note
        )

    # -----------------------------------------------------------------------
    # (d) Category D: Multi-Hop OFAC 50%-Rule UBO Shell Companies (30 wires)
    # -----------------------------------------------------------------------
    ubo_shell_templates = [
        # Shell 1: Blue Horizon Maritime Logistics Ltd (Deripaska 30% + Prigozhin 25% = 55%)
        ("Blue Horizon Maritime Logistics Ltd", "VG", "UBO-SHELL-01", "2-hop joint SDN shell (30% + 25% = 55%)"),
        ("Blue Horizon Maritime Logistics Limited", "VG", "UBO-SHELL-01", "2-hop joint SDN shell (Limited suffix)"),
        ("Blue Horizon Maritime Logistics", "VG", "UBO-SHELL-01", "2-hop joint SDN shell (no suffix)"),
        ("BLUE HORIZON MARITIME LOGISTICS LTD", "CY", "UBO-SHELL-01", "2-hop joint SDN shell (uppercase)"),
        ("Blue Horizon Maritime Logistics LLC", "AE", "UBO-SHELL-01", "2-hop joint SDN shell (LLC suffix)"),
        ("Logistics Maritime Blue Horizon Ltd", "VG", "UBO-SHELL-01", "2-hop joint SDN shell (reordered tokens)"),

        # Shell 2: Aegean Star Petrotech FZE (Tariq Al-Rashid 90%*70%*90% = 56.7% 3-hop)
        ("Aegean Star Petrotech FZE", "AE", "UBO-SHELL-02", "3-hop deep chain SDN shell (56.7%)"),
        ("Aegean Star Petrotech FZCO", "AE", "UBO-SHELL-02", "3-hop deep chain SDN shell (FZCO suffix)"),
        ("Aegean Star Petrotech", "AE", "UBO-SHELL-02", "3-hop deep chain SDN shell (no suffix)"),
        ("AEGEAN STAR PETROTECH FZE", "AE", "UBO-SHELL-02", "3-hop deep chain SDN shell (uppercase)"),
        ("Aegean Star Petrotech LLC", "SY", "UBO-SHELL-02", "3-hop deep chain SDN shell (LLC suffix)"),
        ("Petrotech Aegean Star FZE", "AE", "UBO-SHELL-02", "3-hop deep chain SDN shell (reordered)"),

        # Shell 3: Vostok Meridian Chartering GmbH (Viktor But 32% + Rami Makhlouf 20% = 52% 3-hop)
        ("Vostok Meridian Chartering GmbH", "CH", "UBO-SHELL-03", "3-hop multi-SDN shell (32% + 20% = 52%)"),
        ("Vostok Meridian Chartering AG", "CH", "UBO-SHELL-03", "3-hop multi-SDN shell (AG suffix)"),
        ("Vostok Meridian Chartering", "CH", "UBO-SHELL-03", "3-hop multi-SDN shell (no suffix)"),
        ("VOSTOK MERIDIAN CHARTERING GMBH", "CH", "UBO-SHELL-03", "3-hop multi-SDN shell (uppercase)"),
        ("Vostok Meridian Chartering Ltd", "CY", "UBO-SHELL-03", "3-hop multi-SDN shell (Ltd suffix)"),
        ("Chartering Vostok Meridian GmbH", "CH", "UBO-SHELL-03", "3-hop multi-SDN shell (reordered)"),

        # Shell 4: Saffron Gulf Petrochemicals DMCC (Qasim Suleimani 80%*80% = 64% 2-hop)
        ("Saffron Gulf Petrochemicals DMCC", "AE", "UBO-SHELL-04", "2-hop single SDN shell (64%)"),
        ("Saffron Gulf Petrochemicals FZE", "AE", "UBO-SHELL-04", "2-hop single SDN shell (FZE suffix)"),
        ("Saffron Gulf Petrochemicals", "AE", "UBO-SHELL-04", "2-hop single SDN shell (no suffix)"),
        ("SAFFRON GULF PETROCHEMICALS DMCC", "AE", "UBO-SHELL-04", "2-hop single SDN shell (uppercase)"),
        ("Saffron Gulf Petrochemicals LLC", "IR", "UBO-SHELL-04", "2-hop single SDN shell (LLC suffix)"),
        ("Petrochemicals Saffron Gulf DMCC", "AE", "UBO-SHELL-04", "2-hop single SDN shell (reordered)"),

        # Shell 5: Nordic Baltic Bunker Services AS (Rosneft 75%*80% = 60% 2-hop + cycle)
        ("Nordic Baltic Bunker Services AS", "EE", "UBO-SHELL-05", "2-hop corporate SDN shell with cycle (60%)"),
        ("Nordic Baltic Bunker Services Ltd", "EE", "UBO-SHELL-05", "2-hop corporate SDN shell (Ltd suffix)"),
        ("Nordic Baltic Bunker Services", "EE", "UBO-SHELL-05", "2-hop corporate SDN shell (no suffix)"),
        ("NORDIC BALTIC BUNKER SERVICES AS", "EE", "UBO-SHELL-05", "2-hop corporate SDN shell (uppercase)"),
        ("Nordic Baltic Bunker Services BV", "NL", "UBO-SHELL-05", "2-hop corporate SDN shell (BV suffix)"),
        ("Bunker Services Nordic Baltic AS", "EE", "UBO-SHELL-05", "2-hop corporate SDN shell (reordered)"),
    ]
    for i, (nm, ctry, ubo_id, note) in enumerate(ubo_shell_templates):
        add_case(
            "ubo_shell", nm, "entity", None, ctry, None,
            950_000.0 + i * 25_000.0, True, ubo_id, note
        )

    # -----------------------------------------------------------------------
    # (e) Category E: Hard Negatives & Clean Wires (150 wires, should_block=False)
    # -----------------------------------------------------------------------
    # Sub-group E1 (50 wires): Innocent customers sharing names with sanctioned individuals
    # but having completely distinct DOB (>= 20 years younger/older) & non-matching Country/Passport!
    innocent_homonyms = [
        ("Tariq Al-Rashid", "1994-11-23", "JO", "JO4410928", "Innocent Jordanian engineer born 1994 (SDN born 1968)"),
        ("Tariq Al-Rashid", "1991-06-15", "AE", "AE8821034", "Innocent UAE resident born 1991 (SDN born 1968)"),
        ("Tarek Al-Rashid", "1989-02-19", "SA", "SA7712091", "Innocent Saudi merchant born 1989 (SDN born 1968)"),
        ("Mohammed Ibrahim Al-Masri", "1995-08-12", "JO", "JO1192834", "Innocent Jordanian student born 1995 (SDN born 1963)"),
        ("Mohammed Ibrahim Al-Masri", "1988-03-29", "AE", "AE5519201", "Innocent Dubai pharmacist born 1988 (SDN born 1963)"),
        ("Muhammad Ibrahim Al-Masri", "1992-10-04", "KW", "KW3301928", "Innocent Kuwaiti resident born 1992 (SDN born 1963)"),
        ("Ahmed Abdullah Al-Baghdadi", "1996-01-17", "OM", "OM9918273", "Innocent Omani citizen born 1996 (SDN born 1971)"),
        ("Ahmed Abdullah Al-Baghdadi", "1993-07-22", "BH", "BH6617289", "Innocent Bahraini accountant born 1993 (SDN born 1971)"),
        ("Sergei Lavrov", "1992-05-14", "DE", "DE8817263", "Innocent German software developer born 1992 (SDN born 1950)"),
        ("Sergey Lavrov", "1989-11-08", "US", "US4491827", "Innocent US resident born 1989 (SDN born 1950)"),
        ("Viktor But", "1997-04-03", "PL", "PL3381726", "Innocent Polish citizen born 1997 (SDN born 1967)"),
        ("Victor Bout", "1993-09-19", "FR", "FR2291837", "Innocent French citizen born 1993 (SDN born 1967)"),
        ("Hassan Nasrallah", "1994-12-11", "CA", "CA7718293", "Innocent Canadian citizen born 1994 (SDN born 1960)"),
        ("Hasan Nasrallah", "1990-02-28", "AU", "AU6619283", "Innocent Australian physician born 1990 (SDN born 1960)"),
        ("Dmitry Medvedev", "1995-06-30", "IL", "IL5518290", "Innocent Israeli citizen born 1995 (SDN born 1965)"),
        ("Dmitri Medvedev", "1991-01-15", "GB", "GB9918234", "Innocent UK analyst born 1991 (SDN born 1965)"),
        ("Oleg Deripaska", "1996-08-21", "US", "US1182934", "Innocent US student born 1996 (SDN born 1968)"),
        ("Rami Makhlouf", "1995-03-09", "FR", "FR6612983", "Innocent French architect born 1995 (SDN born 1969)"),
        ("Bashar Al-Assad", "1993-10-27", "SE", "SE4491823", "Innocent Swedish resident born 1993 (SDN born 1965)"),
        ("Aleksandr Lukashenko", "1994-07-14", "LT", "LT8819204", "Innocent Lithuanian citizen born 1994 (SDN born 1954)"),
        ("Yevgeny Prigozhin", "1996-11-02", "EE", "EE7712390", "Innocent Estonian citizen born 1996 (SDN born 1961)"),
        ("Ramzan Kadyrov", "1998-05-19", "KZ", "KZ3319284", "Innocent Kazakh athlete born 1998 (SDN born 1976)"),
        ("Qasim Suleimani", "1992-09-01", "TR", "TR9918271", "Innocent Turkish citizen born 1992 (SDN born 1957)"),
        ("Mohammed Ibrahim", "1985-04-10", "IN", "IN7781920", "Common given names Mohammed Ibrahim in India"),
        ("Ahmed Abdullah", "1987-12-05", "MY", "MY6619281", "Common given names Ahmed Abdullah in Malaysia"),
    ]
    # Expand the 25 templates into 50 wires (2 transaction amounts/dates each)
    for round_idx in range(2):
        for i, (nm, dob, ctry, ident, note) in enumerate(innocent_homonyms):
            add_case(
                "hard_negative", nm, "individual", dob, ctry, ident,
                4_500.0 + (round_idx * 25 + i) * 350.0, False, None, note
            )

    # Sub-group E2 (40 wires): Corporate boilerplate overlaps that fool naive Levenshtein
    # (share long generic substrings like "Oil Company OJSC", "Global Trading LLC",
    # "General Aviation Co", "General Corporation")
    corporate_hard_negatives = [
        ("Rostov Oil Company OJSC", "RU", "Shares 'Oil Company OJSC' with Rosneft Oil Company OJSC"),
        ("Rossiya Oil Company OJSC", "RU", "Shares 'Oil Company OJSC' with Rosneft Oil Company OJSC"),
        ("Romashka Oil Company OJSC", "KZ", "Shares 'Oil Company OJSC' with Rosneft Oil Company OJSC"),
        ("Rosenergo Oil Company OJSC", "RU", "Shares 'Oil Company OJSC' with Rosneft Oil Company OJSC"),
        ("Maharaja Air General Aviation Co", "IN", "Shares 'Air General Aviation Co' with Mahan Air General Aviation Co"),
        ("Mahaba Air General Aviation Co", "AE", "Shares 'Air General Aviation Co' with Mahan Air General Aviation Co"),
        ("Mahogany Air General Aviation Co", "SG", "Shares 'Air General Aviation Co' with Mahan Air General Aviation Co"),
        ("Maharani Air General Aviation Co", "IN", "Shares 'Air General Aviation Co' with Mahan Air General Aviation Co"),
        ("Al-Manar Global Trading LLC", "AE", "Shares 'Al-... Global Trading LLC' with Al-Noor Global Trading LLC"),
        ("Al-Nahda Global Trading LLC", "OM", "Shares 'Al-... Global Trading LLC' with Al-Noor Global Trading LLC"),
        ("Al-Nيل Global Trading LLC", "EG", "Shares 'Al-... Global Trading LLC' with Al-Noor Global Trading LLC"),
        ("Al-Nasr Global Trading LLC", "QA", "Shares 'Al-... Global Trading LLC' with Al-Noor Global Trading LLC"),
        ("Al-Naeem Global Trading LLC", "BH", "Shares 'Al-... Global Trading LLC' with Al-Noor Global Trading LLC"),
        ("Korea Daesong General Corporation", "KR", "Shares 'Korea ... General Corporation' with Korea Ryonbong"),
        ("Korea Halla General Corporation", "KR", "Shares 'Korea ... General Corporation' with Korea Ryonbong"),
        ("Korea Kumgang General Corporation", "KR", "Shares 'Korea ... General Corporation' with Korea Ryonbong"),
        ("Korea Taedong General Corporation", "KR", "Shares 'Korea ... General Corporation' with Korea Ryonbong"),
        ("Gazstroibank JSC", "KZ", "Shares 'Gaz...bank JSC' with Gazprombank JSC"),
        ("Gazinvestbank JSC", "AM", "Shares 'Gaz...bank JSC' with Gazprombank JSC"),
        ("Gazenergobank JSC", "UZ", "Shares 'Gaz...bank JSC' with Gazprombank JSC"),
    ]
    for round_idx in range(2):
        for i, (nm, ctry, note) in enumerate(corporate_hard_negatives):
            add_case(
                "hard_negative", nm, "entity", None, ctry, None,
                65_000.0 + (round_idx * 20 + i) * 1_500.0, False, None, note
            )

    # Sub-group E3 (25 wires): Minority UBO exposure (< 50% OFAC threshold)
    # 35% SDN stake (Emerald Bosporus Shipping Co) and 12% SDN stake (Helvetia Alpine Precision AG)
    minority_ubo_templates = [
        ("Emerald Bosporus Shipping Co", "TR", "35% SDN ownership (< 50% OFAC blocking threshold)"),
        ("Emerald Bosporus Shipping Ltd", "TR", "35% SDN ownership (< 50% OFAC blocking threshold)"),
        ("Emerald Bosporus Shipping Company", "TR", "35% SDN ownership (< 50% OFAC blocking threshold)"),
        ("Helvetia Alpine Precision AG", "CH", "12% indirect SDN ownership (< 25% EDD & < 50% OFAC)"),
        ("Helvetia Alpine Precision GmbH", "CH", "12% indirect SDN ownership (< 25% EDD & < 50% OFAC)"),
    ]
    for round_idx in range(5):
        for i, (nm, ctry, note) in enumerate(minority_ubo_templates):
            add_case(
                "hard_negative", nm, "entity", None, ctry, None,
                140_000.0 + (round_idx * 5 + i) * 3_000.0, False, None, note
            )

    # Sub-group E4 (35 wires): Standard clean international commercial & retail wires
    clean_wires = [
        ("Pacific Rim Semiconductor Corp", "entity", None, "SG", "0% SDN UBO verified clean entity"),
        ("Rajesh Kumar Sharma", "individual", "1982-05-19", "IN", "Clean retail wire"),
        ("Smt. Priya Darshini Nair", "individual", "1990-11-04", "IN", "Clean retail wire"),
        ("Siemens Energy Solutions GmbH", "entity", None, "DE", "Clean industrial corporate wire"),
        ("Tata Consultancy Services Ltd", "entity", None, "IN", "Clean IT services wire"),
        ("Nippon Yusen Kabushiki Kaisha", "entity", None, "JP", "Clean maritime shipping wire"),
        ("Maersk Line Container Logistics BV", "entity", None, "NL", "Clean container shipping wire"),
        ("Bajaj Finserv Treasury Ltd", "entity", None, "IN", "Clean financial services wire"),
        ("Larsen & Toubro Hydrocarbon Engineering", "entity", None, "IN", "Clean engineering wire"),
        ("Emirates SkyCargo Logistics FZE", "entity", None, "AE", "Clean air cargo wire"),
        ("Orascom Construction Industries SAE", "entity", None, "EG", "Clean construction wire"),
        ("Sabanci Industrial Holdings AS", "entity", None, "TR", "Clean holding company wire"),
        ("Keppel Offshore & Marine Ltd", "entity", None, "SG", "Clean marine engineering wire"),
        ("posco International Trading Corp", "entity", None, "KR", "Clean Korean trading wire"),
        ("Sumitomo Chemical Asia Pte Ltd", "entity", None, "SG", "Clean chemical wire"),
        ("Carlos Eduardo Mendoza", "individual", "1979-03-14", "MX", "Clean individual wire"),
        ("Jean-Pierre Laurent", "individual", "1975-08-29", "FR", "Clean individual wire"),
        ("Hiroshi Takahashi", "individual", "1984-01-22", "JP", "Clean individual wire"),
        ("Fatima Al-Zahra Mansouri", "individual", "1991-07-16", "MA", "Clean Moroccan wire"),
        ("Kofi Mensah Osei", "individual", "1986-09-03", "GH", "Clean Ghanaian wire"),
        ("Adebayo Oluwaseun Balogun", "individual", "1988-02-11", "NG", "Clean Nigerian wire"),
        ("Chen Wei Ming", "individual", "1980-12-25", "TW", "Clean Taiwanese wire"),
        ("Park Ji-Hoon", "individual", "1993-04-08", "KR", "Clean Korean wire"),
        ("Svetlana Ivanovna Morozova", "individual", "1987-06-19", "KZ", "Clean Kazakh wire"),
        ("Lukas Maximilian Weber", "individual", "1983-10-30", "AT", "Clean Austrian wire"),
        ("Nordea Corporate Markets AB", "entity", None, "SE", "Clean Nordic banking wire"),
        ("Standard Chartered Trade Services", "entity", None, "GB", "Clean trade finance wire"),
        ("DBS Vickers Securities Pte Ltd", "entity", None, "SG", "Clean brokerage wire"),
        ("Macquarie Infrastructure Partners", "entity", None, "AU", "Clean infrastructure wire"),
        ("Brookfield Renewable Power Inc", "entity", None, "CA", "Clean energy wire"),
        ("Petrobras International Braspetro BV", "entity", None, "BR", "Clean energy wire"),
        ("Sasol Synfuels International Pty", "entity", None, "ZA", "Clean energy wire"),
        ("Cemex Latam Holdings SA", "entity", None, "CO", "Clean materials wire"),
        ("Infosys Finacle Digital Banking", "entity", None, "IN", "Clean fintech wire"),
        ("Wipro Enterprises Pvt Ltd", "entity", None, "IN", "Clean enterprise wire"),
    ]
    for i, (nm, etype, dob, ctry, note) in enumerate(clean_wires):
        add_case(
            "hard_negative", nm, etype, dob, ctry, None,
            32_000.0 + i * 2_100.0, False, None, note
        )

    assert len(cases) == 300, f"Expected 300 benchmark wires, got {len(cases)}"
    return cases
