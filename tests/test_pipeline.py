"""Tests de bout en bout sur données synthétiques (aucun accès réseau)."""

from __future__ import annotations

import json
from dataclasses import replace

import pandas as pd
import pytest

from radar.config import Config, load_config
from radar.features import build_training_set
from radar.synthetic import write_raw
from radar.transform import build_tables, extract_sirens, load_tables, parse_jugement


@pytest.fixture(scope="session")
def cfg(tmp_path_factory) -> Config:
    base = load_config()
    tmp = tmp_path_factory.mktemp("radar")
    raw = json.loads(json.dumps(base.raw))
    raw["paths"] = {"raw_dir": str(tmp / "raw"), "db": str(tmp / "radar.duckdb"), "model_dir": str(tmp / "models")}
    return replace(base, raw=raw)


@pytest.fixture(scope="session")
def built(cfg):
    pb, pr = write_raw(cfg, cfg.raw_dir, n_companies=2500, seed=7)
    counts = build_tables(cfg, pb, pr)
    return counts


def test_extract_sirens_formats():
    assert extract_sirens("123 456 789") == ["123456789"]
    assert extract_sirens(["123 456 789", "987654321"]) == ["123456789", "987654321"]
    assert extract_sirens(None) == []
    assert extract_sirens("RCS Paris 123 456 789") == ["123456789"]


def test_parse_jugement():
    nature, date = parse_jugement('{"nature": "Jugement d\'ouverture de liquidation", "date": "2024-03-01"}')
    assert "liquidation" in nature and date == "2024-03-01"
    assert parse_jugement(None) == (None, None)


def test_build_tables_ignore_les_clotures(cfg, built):
    procedures, bilans = load_tables(cfg)
    assert built["bilans"] > 0 and built["procedures"] > 0
    # Les jugements de clôture ne sont pas des ouvertures
    assert not procedures["nature"].str.contains("clôture", case=False).any()
    assert bilans["siren"].str.fullmatch(r"\d{9}").all()


def test_pas_de_fuite_temporelle(cfg, built):
    procedures, bilans = load_tables(cfg)
    df = build_training_set(bilans, procedures, cfg)
    assert df["defaillance"].between(0, 1).all()
    assert 0 < df["defaillance"].mean() < 0.5
    # Aucune entreprise déjà en procédure à la date d'observation
    first = procedures.groupby("siren")["date_ouverture"].min()
    already = df["siren"].map(first)
    assert not (already.notna() & (already <= df["date_observation"])).any()
    # Toute cible positive correspond à une ouverture dans la fenêtre
    horizon = pd.DateOffset(months=cfg.target["horizon_months"])
    pos = df[df["defaillance"] == 1].merge(procedures, on="siren")
    ok = (pos["date_ouverture"] > pos["date_observation"]) & (pos["date_ouverture"] <= pos["date_observation"] + horizon)
    assert ok.groupby([pos["siren"], pos["date_cloture"]]).any().all()


def test_entrainement_et_scoring(cfg, built):
    from radar.scoring import Scorer
    from radar.train import train

    procedures, bilans = load_tables(cfg)
    report = train(build_training_set(bilans, procedures, cfg), cfg)
    # Le signal simulé doit être retrouvé nettement mieux que le hasard
    assert report["metrics"]["lightgbm"]["roc_auc"] > 0.65

    from radar.store import DuckDBStore, FrameStore

    # Les deux accès aux données doivent donner le même score
    by_frame = Scorer(cfg, FrameStore(bilans, procedures), with_identity=False)
    scorer = Scorer(cfg, DuckDBStore(cfg.db_path), with_identity=False)
    one = bilans["siren"].iloc[0]
    assert by_frame.score(one).probabilite == scorer.score(one).probabilite
    assert set(scorer.store.sample_sirens()) == {"sain", "fragile", "procedure"}
    sain = bilans[~bilans["siren"].isin(procedures["siren"])]["siren"].iloc[0]
    r = scorer.score(sain)
    assert r.statut == "score" and 0 <= r.probabilite <= 1
    assert r.niveau in {"faible", "modéré", "élevé"} and len(r.facteurs) == 3

    # Chaque résultat porte une recommandation de conditions de paiement
    assert r.recommandation and r.recommandation["titre"]

    en_procedure = procedures["siren"].iloc[0]
    proc = scorer.score(en_procedure)
    assert proc.statut == "procedure_en_cours"
    assert proc.recommandation["titre"] == "N'accordez pas de délai"
    vide = scorer.score("000000001")
    assert vide.statut == "donnees_insuffisantes" and vide.recommandation is not None
