"""Normalisation des données brutes en deux tables propres.

- ``procedures`` : une ligne par (siren, date d'ouverture de procédure collective)
- ``bilans``     : une ligne par (siren, date de clôture) avec les ratios
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import duckdb
import pandas as pd

from .config import Config

_SIREN_RE = re.compile(r"\d{9}")


def extract_sirens(registre) -> list[str]:
    """Extrait les SIREN d'un champ `registre` (formats hétérogènes)."""
    if registre is None or (isinstance(registre, float) and pd.isna(registre)):
        return []
    if isinstance(registre, (list, tuple)):
        text = " ".join(str(x) for x in registre)
    else:
        text = str(registre)
    # "123 456 789" -> "123456789" ; on ne colle que les groupes de chiffres
    compact = re.sub(r"(?<=\d) (?=\d)", "", text)
    return sorted(set(_SIREN_RE.findall(compact)))


def parse_jugement(raw) -> tuple[str | None, str | None]:
    """Retourne (nature, date) depuis le champ JSON `jugement`."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, None
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (ValueError, TypeError):
        return str(raw), None
    nature = data.get("nature") or data.get("famille")
    return nature, data.get("date")


def normalize_procedures(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Une ligne par SIREN et date d'ouverture d'une procédure collective."""
    col = cfg.bodacc["columns"]
    keywords = [k.lower() for k in cfg.target["opening_keywords"]]

    rows = []
    for registre, parution, jugement in zip(
        df[col["registre"]], df[col["date_parution"]], df[col["jugement"]]
    ):
        nature, date_jug = parse_jugement(jugement)
        if nature and not any(k in nature.lower() for k in keywords):
            continue  # clôtures, plans, modifications... : pas une ouverture
        date = pd.to_datetime(date_jug or parution, errors="coerce")
        if pd.isna(date):
            continue
        for siren in extract_sirens(registre):
            rows.append((siren, date.normalize(), nature))

    out = pd.DataFrame(rows, columns=["siren", "date_ouverture", "nature"])
    # Première ouverture connue par SIREN et par date
    return out.drop_duplicates(["siren", "date_ouverture"]).reset_index(drop=True)


def normalize_bilans(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Une ligne par SIREN et date de clôture, ratios renommés."""
    col = cfg.ratios["columns"]
    feats = cfg.ratios["features"]
    keep = {col["siren"]: "siren", col["date_cloture"]: "date_cloture", col["type_bilan"]: "type_bilan"}
    keep.update({v: k for k, v in feats.items()})

    present = [c for c in keep if c in df.columns]
    out = df[present].rename(columns=keep).copy()
    for name in feats:  # colonnes absentes : variable manquante, pas d'erreur
        if name not in out.columns:
            out[name] = float("nan")

    out["siren"] = out["siren"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(9)
    out["date_cloture"] = pd.to_datetime(out["date_cloture"], errors="coerce")
    out = out.dropna(subset=["date_cloture"])
    for name in feats:
        out[name] = pd.to_numeric(out[name], errors="coerce")

    # Si plusieurs types de bilan pour une même clôture, on garde le plus complet
    out["_n"] = out[list(feats)].notna().sum(axis=1)
    out = (
        out.sort_values(["siren", "date_cloture", "_n"], ascending=[True, True, False])
        .drop_duplicates(["siren", "date_cloture"])
        .drop(columns="_n")
        .reset_index(drop=True)
    )
    return out


def build_tables(cfg: Config, bodacc_path: Path, ratios_path: Path) -> dict[str, int]:
    """Lit les fichiers bruts, normalise et écrit les tables dans DuckDB."""
    bodacc = pd.read_parquet(bodacc_path)
    ratios = pd.read_parquet(ratios_path)
    procedures = normalize_procedures(bodacc, cfg)
    bilans = normalize_bilans(ratios, cfg)

    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(cfg.db_path)) as con:
        # Tri et index par SIREN : l'API lit un SIREN à la fois
        con.execute("CREATE OR REPLACE TABLE procedures AS SELECT * FROM procedures ORDER BY siren")
        con.execute("CREATE OR REPLACE TABLE bilans AS SELECT * FROM bilans ORDER BY siren, date_cloture")
        con.execute("CREATE INDEX idx_procedures_siren ON procedures (siren)")
        con.execute("CREATE INDEX idx_bilans_siren ON bilans (siren)")
    return {"procedures": len(procedures), "bilans": len(bilans)}


def load_tables(cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    with duckdb.connect(str(cfg.db_path), read_only=True) as con:
        return con.execute("SELECT * FROM procedures").df(), con.execute("SELECT * FROM bilans").df()
