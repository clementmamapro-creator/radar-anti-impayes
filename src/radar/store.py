"""Accès aux données d'un SIREN, sans charger toute la base en mémoire."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import duckdb
import pandas as pd


class Store(Protocol):
    def procedures_for(self, siren: str) -> pd.DataFrame: ...
    def bilans_for(self, siren: str) -> pd.DataFrame: ...
    def sample_sirens(self) -> dict[str, list[str]]: ...


class DuckDBStore:
    """Lecture seule, une requête indexée par SIREN."""

    def __init__(self, db_path: Path):
        self.con = duckdb.connect(str(db_path), read_only=True)

    def _query(self, sql: str, siren: str) -> pd.DataFrame:
        # Un curseur par requête : la connexion est partagée entre les threads de l'API
        return self.con.cursor().execute(sql, [siren]).df()

    def procedures_for(self, siren: str) -> pd.DataFrame:
        return self._query("SELECT * FROM procedures WHERE siren = ?", siren)

    def bilans_for(self, siren: str) -> pd.DataFrame:
        return self._query("SELECT * FROM bilans WHERE siren = ? ORDER BY date_cloture", siren)

    def sample_sirens(self) -> dict[str, list[str]]:
        cur = self.con.cursor()
        latest = """
            SELECT b.* FROM bilans b
            WHERE b.siren NOT IN (SELECT siren FROM procedures)
            QUALIFY row_number() OVER (PARTITION BY b.siren ORDER BY b.date_cloture DESC) = 1
        """
        low = cur.execute(f"SELECT siren FROM ({latest}) ORDER BY taux_endettement ASC LIMIT 1").fetchall()
        high = cur.execute(f"SELECT siren FROM ({latest}) ORDER BY taux_endettement DESC LIMIT 1").fetchall()
        proc = cur.execute("SELECT min(siren) FROM procedures").fetchall()
        return {"sain": [r[0] for r in low], "fragile": [r[0] for r in high], "procedure": [r[0] for r in proc if r[0]]}


class FrameStore:
    """Même interface sur des DataFrames (tests et notebooks)."""

    def __init__(self, bilans: pd.DataFrame, procedures: pd.DataFrame):
        self.bilans = bilans
        self.procedures = procedures

    def procedures_for(self, siren: str) -> pd.DataFrame:
        return self.procedures[self.procedures["siren"] == siren]

    def bilans_for(self, siren: str) -> pd.DataFrame:
        return self.bilans[self.bilans["siren"] == siren].sort_values("date_cloture")

    def sample_sirens(self) -> dict[str, list[str]]:
        last = self.bilans.sort_values("date_cloture").groupby("siren").tail(1)
        healthy = last[~last["siren"].isin(self.procedures["siren"])].sort_values("taux_endettement")
        return {
            "sain": healthy["siren"].head(1).tolist(),
            "fragile": healthy["siren"].tail(1).tolist(),
            "procedure": sorted(self.procedures["siren"])[:1],
        }
