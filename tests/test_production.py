"""Settings, the real-list requirement, auth, limits, headers, metrics, health, the screening log
and migrations."""
import hashlib
import importlib
import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sancscreen import db, ops

KEY = "sancscreen_" + "x" * 40
HASHED = {f"sha256:{hashlib.sha256(KEY.encode()).hexdigest()}": {"user": "pay-hub", "role": "screener"}}
NS = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML"
SDN = f"""<?xml version="1.0" standalone="yes"?>
<sdnList xmlns="{NS}">
  <sdnEntry><uid>36</uid><lastName>AEROCARIBBEAN AIRLINES</lastName><sdnType>Entity</sdnType>
    <programList><program>CUBA</program></programList>
    <addressList><address><country>Cuba</country></address></addressList></sdnEntry>
  <sdnEntry><uid>7</uid><firstName>Viktor</firstName><lastName>BOUT</lastName><sdnType>Individual</sdnType>
    <programList><program>SDGT</program></programList>
    <dateOfBirthList><dateOfBirthItem><dateOfBirth>13 Jan 1967</dateOfBirth></dateOfBirthItem></dateOfBirthList></sdnEntry>
</sdnList>"""
BOMB = """<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>
<sdnList><sdnEntry><uid>1</uid><lastName>&lol2;</lastName><sdnType>Entity</sdnType></sdnEntry></sdnList>"""


@pytest.fixture
def sdn_file(tmp_path):
    f = tmp_path / "SDN.XML"
    f.write_text(SDN, encoding="utf-8")
    return str(f)


def boot(monkeypatch, **env):
    for k in [k for k in os.environ if k.startswith("SANCSCREEN_")]:
        monkeypatch.delenv(k)
    for k, v in env.items():
        monkeypatch.setenv(f"SANCSCREEN_{k}", v)
    import sancscreen.api as api

    return importlib.reload(api)


def prod(sdn_file, **over):
    env = {"ENV": "production", "API_KEYS": json.dumps(HASHED), "DATABASE_URL": "sqlite://", "SDN_XML": sdn_file}
    env.update(over)
    return {k: v for k, v in env.items() if v is not None}


@pytest.mark.parametrize("change, message", [
    ({"SANCSCREEN_API_KEYS": None}, "API keys"),
    ({"SANCSCREEN_DATABASE_URL": None}, "DATABASE_URL"),
    ({"SANCSCREEN_API_KEYS": json.dumps({KEY: {"user": "p", "role": "screener"}})}, "sha256"),
    ({"SANCSCREEN_API_KEYS": json.dumps({"sha256:" + "0" * 64: {"user": "x", "role": "root"}})}, "roles"),
    ({"SANCSCREEN_CORS_ORIGINS": "*"}, "CORS"),
    ({"SANCSCREEN_ENV": "prod"}, "development or production"),
])
def test_production_settings_refused(change, message):
    env = {"SANCSCREEN_ENV": "production", "SANCSCREEN_API_KEYS": json.dumps(HASHED), "SANCSCREEN_DATABASE_URL": "sqlite://"}
    env.update(change)
    with pytest.raises(ops.ConfigError, match=message):
        ops.load_settings({k: v for k, v in env.items() if v is not None})


def test_production_needs_the_real_list(monkeypatch, sdn_file, tmp_path):
    with pytest.raises(ops.ConfigError, match="SDN_XML"):
        boot(monkeypatch, **prod(None))
    with pytest.raises(ops.ConfigError, match="cannot load"):
        boot(monkeypatch, **prod(str(tmp_path / "missing.xml")))
    bomb = tmp_path / "bomb.xml"
    bomb.write_text(BOMB, encoding="utf-8")
    with pytest.raises(ops.ConfigError, match="cannot load"):  # defusedxml refuses entity expansion
        boot(monkeypatch, **prod(str(bomb)))

    api = boot(monkeypatch, **prod(sdn_file))
    c = TestClient(api.app)
    h = {"x-api-key": KEY}
    r = c.post("/screen", json={"name": "Viktor Bout", "entity_type": "individual", "dob": "1967-01-13"}, headers=h)
    body = r.json()
    assert r.status_code == 200 and body["decision"] == "BLOCK" and body["best_watchlist_match"]["sdn_id"] == "OFAC-7"
    assert body["list_version"].startswith("sha256:") and body["screening_id"]
    assert c.post("/screen", json={"name": "Priya Sharma", "entity_type": "individual"}, headers=h).json()["decision"] == "CLEAR"
    # the toy ownership graph is not used with a real list
    assert c.post("/ubo/check", json={"entity": "UBO-SHELL-01"}, headers=h).status_code == 404
    assert c.get("/readyz").json()["checks"] == {"database": True, "watchlist": True}


def test_no_public_bind_without_keys():
    with pytest.raises(ops.ConfigError, match="without API keys"):
        ops.load_settings({"SANCSCREEN_HOST": "0.0.0.0"})


def test_serve_exits_with_a_readable_error():
    env = {k: v for k, v in os.environ.items() if not k.startswith("SANCSCREEN_")}
    r = subprocess.run([sys.executable, "-m", "sancscreen", "serve", "--host", "0.0.0.0"], env=env,
                       capture_output=True, text=True, timeout=60, check=False)
    assert r.returncode != 0 and "without API keys" in r.stderr


def test_roles_decide_what_a_key_may_do(monkeypatch):
    keys = {"k-pay": {"user": "pay-hub", "role": "screener"}, "k-view": {"user": "vic", "role": "viewer"},
            "k-an": {"user": "asha", "role": "analyst"}, "k-mon": {"user": "prom", "role": "monitor"}}
    c = TestClient(boot(monkeypatch, API_KEYS=json.dumps(keys)).app)
    party = {"name": "John Smith"}
    assert c.post("/screen", json=party).status_code == 401
    assert c.post("/screen", json=party, headers={"x-api-key": "k-pay"}).status_code == 200
    assert c.get("/screenings", headers={"x-api-key": "k-pay"}).status_code == 403
    assert c.post("/screen", json=party, headers={"x-api-key": "k-view"}).status_code == 403
    assert c.get("/screenings", headers={"authorization": "Bearer k-view"}).status_code == 200
    assert c.post("/screenings/x/review", json={"status": "cleared", "note": "ok"}, headers={"x-api-key": "k-view"}).status_code == 403
    assert c.get("/metrics", headers={"x-api-key": "k-an"}).status_code == 403
    m = c.get("/metrics", headers={"x-api-key": "k-mon"})
    assert m.status_code == 200 and 'sancscreen_decisions_total{decision="CLEAR"}' in m.text


def test_screenings_are_logged_reviewed_and_survive_a_restart(monkeypatch, tmp_path):
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'log.db'}"
    c = TestClient(boot(monkeypatch, DATABASE_URL=url).app)
    hit = c.post("/screen", json={"name": "Сергей Лавров", "dob": "1950-03-21", "query_id": "WIRE-9"}).json()
    clear = c.post("/screen", json={"name": "Priya Sharma", "entity_type": "individual"}).json()
    assert hit["decision"] == "BLOCK" and clear["decision"] == "CLEAR"
    rev = c.post(f"/screenings/{hit['screening_id']}/review", json={"status": "confirmed", "note": "same DOB, PEP list"})
    assert rev.status_code == 200 and rev.json()["status"] == "confirmed"
    assert c.post("/screenings/nope/review", json={"status": "cleared", "note": "xx"}).status_code == 404

    c = TestClient(boot(monkeypatch, DATABASE_URL=url).app)  # restart
    got = c.get(f"/screenings/{hit['screening_id']}").json()
    assert got["status"] == "confirmed" and got["query_id"] == "WIRE-9" and got["list_version"] == "demo"
    assert got["reviews"][0]["reviewer"] == "demo" and got["result"]["decision"] == "BLOCK"
    assert c.get(f"/screenings/{clear['screening_id']}").json()["status"] == "cleared"  # CLEARs start closed
    assert any(s["id"] == hit["screening_id"] for s in c.get("/screenings", params={"decision": "BLOCK"}).json()["screenings"])


def test_watchlist_is_paged(monkeypatch):
    c = TestClient(boot(monkeypatch).app)
    page = c.get("/watchlist", params={"offset": 2, "limit": 3}).json()
    assert len(page["watchlist"]) == 3 and page["watchlist_count"] > 3 and page["offset"] == 2
    assert c.get("/watchlist", params={"limit": 5000}).status_code == 422


def test_rate_limit_and_body_cap(monkeypatch):
    c = TestClient(boot(monkeypatch, RATE_LIMIT="3", MAX_BODY_BYTES="500").app)
    codes = [c.post("/screen", json={"name": "John Smith"}).status_code for _ in range(5)]
    assert codes[:3] == [200] * 3 and codes[3:] == [429, 429]
    assert int(c.get("/screenings").headers["retry-after"]) >= 1
    c = TestClient(boot(monkeypatch, MAX_BODY_BYTES="500").app)
    assert c.post("/screen", json={"name": "x" * 100, "identifier": "y" * 600}).status_code == 413

    def chunks():
        for _ in range(10):
            yield b"a" * 100

    assert c.post("/screen", content=chunks(), headers={"content-type": "application/json"}).status_code == 413


def test_headers_errors_and_health(monkeypatch):
    api = boot(monkeypatch)

    @api.app.get("/boom")
    def boom():
        raise RuntimeError("secret detail: Viktor Bout passport 1234")

    c = TestClient(api.app)
    r = c.post("/screen", json={"name": "John Smith"}, headers={"x-request-id": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123" and r.headers["content-security-policy"] == ops.API_CSP
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"
    crash = c.get("/boom")
    assert crash.status_code == 500 and "passport" not in crash.text and crash.json()["request_id"]
    bad = c.post("/screen", json={"name": "Jane Roe", "dob": "13/01/1967", "identifier": "PASS-998877"})
    assert bad.status_code == 422 and "13/01/1967" not in bad.text and "PASS-998877" not in bad.text
    nf = c.post("/ubo/check", json={"entity": "Secret Holdings Ltd"})
    assert nf.status_code == 404 and "Secret" not in nf.text
    assert c.get("/healthz").json() == {"status": "ok"}
    monkeypatch.setattr(api.log_store.db, "connect", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
    rz = c.get("/readyz")
    assert rz.status_code == 503 and rz.json()["checks"]["database"] is False and "db down" not in rz.text


def test_migrations_apply_once(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    eng = db.engine(url)
    assert db.migrate(eng) == ["001_init.sql"] and db.migrate(eng) == []
    with eng.connect() as c:
        tables = {r[0] for r in c.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))}
    assert {"screenings", "screening_reviews", "schema_migrations"} <= tables
    env = {**{k: v for k, v in os.environ.items() if not k.startswith("SANCSCREEN_")}, "SANCSCREEN_DATABASE_URL": url}
    out = subprocess.run([sys.executable, "-m", "sancscreen", "migrate"], env=env, capture_output=True, text=True,
                         timeout=60, check=False)
    assert out.returncode == 0 and "up to date" in out.stdout
