"""Espace client (V0, semaine 1) : configuration publique, page et « Mon secteur »."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from radar import api, espace

CARTE = {
    "periode": {"debut": "2025-11-01", "fin": "2026-10-31"},
    "total": 1000, "evolution_pct": -0.4,
    "departements": {"94": {"n": 120, "evolution_pct": -8.0}, "75": {"n": 300, "evolution_pct": 6.2},
                     "13": {"n": 200, "evolution_pct": 1.0}, "2A": {"n": 10, "evolution_pct": None}},
    "mois": [f"2025-{m:02d}" for m in range(1, 13)] + [f"2026-{m:02d}" for m in range(1, 13)],
    "series": {"94": list(range(24))},
    "source": "BODACC",
}


@pytest.fixture
def client():
    return TestClient(api.app)


def test_config_absente_puis_presente(client, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    assert client.get("/espace/config").status_code == 503
    monkeypatch.setenv("SUPABASE_URL", "https://exemple.supabase.co/")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_ne_doit_jamais_sortir")
    r = client.get("/espace/config")
    assert r.status_code == 200
    assert r.json() == {"supabase_url": "https://exemple.supabase.co", "supabase_publishable_key": "sb_publishable_test"}
    assert "sb_secret" not in r.text


def test_page_espace_et_non_indexee(client):
    r = client.get("/espace")
    assert r.status_code == 200 and "Mon secteur" in r.text and "noindex" in r.text
    assert client.get("/espace.html", follow_redirects=False).headers["location"] == "/espace"
    assert "Disallow: /espace" in client.get("/robots.txt").text


@pytest.mark.parametrize("evo,code", [(-8.0, "respire"), (6.2, "tension"), (1.0, "stable"), (None, "inconnu"),
                                      (-5.0, "respire"), (5.0, "tension")])
def test_verdict(evo, code):
    assert espace.verdict(evo)["code"] == code


def test_secteur_douze_derniers_mois():
    s = espace.secteur(CARTE, "94")
    assert s["n_12_mois"] == 120 and s["verdict"]["code"] == "respire"
    assert s["mois"] == CARTE["mois"][-12:] and s["serie"] == list(range(12, 24))
    assert s["france"] == {"n_12_mois": 1000, "evolution_pct": -0.4}
    assert espace.secteur(CARTE, "99") is None


def test_route_secteur(client, monkeypatch):
    from radar import carte
    monkeypatch.setattr(carte, "carte", lambda cfg: CARTE)
    assert client.get("/secteur/94").json()["verdict"]["code"] == "respire"
    assert client.get("/secteur/2a").json()["verdict"]["code"] == "inconnu"
    assert client.get("/secteur/xx").status_code == 422
    assert client.get("/secteur/48").status_code == 404
