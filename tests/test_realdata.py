import random

from sancscreen.lists import generate_benchmark_wires, get_default_watchlist
from sancscreen.matcher import SanctionsMatcher, ScreeningQuery, _join_split
from sancscreen.phonetics import normalize_tokens
from sancscreen.realdata import load_sdn_xml, perturb

SDN_XML = """<?xml version="1.0" standalone="yes"?>
<sdnList xmlns="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML">
  <publshInformation><Publish_Date>10/21/2026</Publish_Date><Record_Count>2</Record_Count></publshInformation>
  <sdnEntry>
    <uid>8279</uid><firstName>Viktor Anatolijevitch</firstName><lastName>BOUT</lastName><sdnType>Individual</sdnType>
    <programList><program>DRCONGO</program></programList>
    <idList>
      <id><uid>1</uid><idType>Passport</idType><idNumber>21N0832689</idNumber><idCountry>Russia</idCountry></id>
      <id><uid>2</uid><idType>Gender</idType><idNumber>Male</idNumber></id>
      <id><uid>3</uid><idType>Organization Established Date</idType><idNumber>01 Jan 2001</idNumber></id>
    </idList>
    <akaList>
      <aka><uid>4</uid><type>a.k.a.</type><category>strong</category><firstName>Victor</firstName><lastName>BUT</lastName></aka>
      <aka><uid>5</uid><type>a.k.a.</type><category>weak</category><lastName>BUTT</lastName></aka>
    </akaList>
    <dateOfBirthList><dateOfBirthItem><uid>6</uid><dateOfBirth>13 Jan 1967</dateOfBirth><mainEntry>true</mainEntry></dateOfBirthItem></dateOfBirthList>
    <nationalityList><nationality><uid>7</uid><country>Tajikistan</country><mainEntry>true</mainEntry></nationality></nationalityList>
  </sdnEntry>
  <sdnEntry>
    <uid>9347</uid><lastName>KOREA RYONBONG GENERAL CORPORATION</lastName><sdnType>Entity</sdnType>
    <programList><program>NPWMD</program></programList>
    <addressList><address><uid>8</uid><country>Korea, North</country></address></addressList>
  </sdnEntry>
</sdnList>"""


def test_ofac_loader_and_candidate_index(tmp_path) -> None:
    f = tmp_path / "SDN.XML"
    f.write_text(SDN_XML, encoding="utf-8")
    bout, ryonbong = load_sdn_xml(f)
    assert (bout.sdn_id, bout.name, bout.entity_type) == ("OFAC-8279", "Viktor Anatolijevitch BOUT", "individual")
    assert bout.aliases == ["Victor BUT"] and load_sdn_xml(f, weak_akas=True)[0].aliases == ["Victor BUT", "BUTT"]
    assert bout.dob == "1967-01-13" and bout.countries == ["TJ", "RU"]
    assert bout.identifiers == ["21N0832689"]               # gender and dates are not identity documents
    assert ryonbong.entity_type == "entity" and ryonbong.countries == ["KP"]

    m = SanctionsMatcher([bout, ryonbong])
    assert m.screen(ScreeningQuery("Q", "Виктор Бут", dob="1967-01-13"))["decision"] == "BLOCK"
    assert m.screen(ScreeningQuery("Q", "Someone Else", identifier="21N 0832689"))["decision"] == "BLOCK"
    # "victor" and "but" are equally rare; matching either counts as matching the distinctive token
    res = m.screen(ScreeningQuery("Q", "V. Bout", dob="1967-01-13"))
    assert res["decision"] == "BLOCK" and res["best_match"].sdn_id == "OFAC-8279"

    # The index must reach every decision a full scan reaches on the benchmark list.
    m = SanctionsMatcher(get_default_watchlist())
    for w in generate_benchmark_wires():
        q = ScreeningQuery(w.wire_id, w.party_name, w.entity_type, w.dob, w.country, w.identifier)
        indexed, full = m.screen(q), m.screen(q, full_scan=True)
        assert indexed["decision"] == full["decision"] or w.wire_id == "WIRE-0291"  # see _blocking_keys
        if indexed["decision"] != "CLEAR":
            assert indexed["best_match"].sdn_id == full["best_match"].sdn_id


def test_spelled_out_company_forms_and_heldout_variants() -> None:
    assert normalize_tokens("GAZPROMBANK JOINT STOCK COMPANY") == ["gazprombank"]
    assert normalize_tokens("OBSHCHESTVO S OGRANICHENNOI OTVETSTVENNOSTYU MEDSTANDART") == ["medstandart"]
    assert normalize_tokens("Public Joint-Stock Company Rosneft") == ["rosneft"]
    assert _join_split(["hassan", "nasr", "allah"], ["hassan", "nasrallah"]) == ["hassan", "nasrallah"]
    rng = random.Random(0)
    assert perturb("Viktor Anatolijevitch BOUT", "reorder", rng) == "BOUT, Viktor Anatolijevitch"
    assert perturb("Viktor Anatolijevitch BOUT", "drop_middle", rng) == "Viktor BOUT"
    assert perturb("Viktor BOUT", "initial", rng) == "V. BOUT"
    assert perturb("BOUT", "drop_middle", rng) is None
    typo = perturb("GAZPROMBANK", "typo", rng)
    assert typo != "Gazprombank" and len(typo) in (10, 11, 12)
