"""Construction du jeu d'entraînement sans fuite d'information.

Pour chaque bilan (siren, date de clôture) :

- date d'observation ``t = clôture + délai de dépôt`` : c'est le premier jour
  où un utilisateur réel aurait pu voir ces comptes ;
- cible = 1 si une procédure collective s'ouvre dans ``]t, t + horizon]`` ;
- on écarte les bilans d'entreprises déjà en procédure avant ``t``
  (le risque est alors connu, il n'y a rien à prédire).

Variables : ratios du dernier bilan, évolution du chiffre d'affaires par
rapport au bilan précédent, nombre de bilans connus (proxy d'ancienneté).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config

EXTRA_FEATURES = ["evolution_ca", "nb_bilans"]


def add_history_features(bilans: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les variables calculées à partir de l'historique des bilans."""
    b = bilans.sort_values(["siren", "date_cloture"]).copy()
    prev_ca = b.groupby("siren")["chiffre_affaires"].shift(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        evo = (b["chiffre_affaires"] - prev_ca) / prev_ca.abs()
    b["evolution_ca"] = evo.replace([np.inf, -np.inf], np.nan).clip(-1, 5)
    b["nb_bilans"] = b.groupby("siren").cumcount() + 1
    return b


def model_features(cfg: Config) -> list[str]:
    return cfg.feature_names + EXTRA_FEATURES


def build_training_set(bilans: pd.DataFrame, procedures: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    lag = pd.DateOffset(months=cfg.target["observation_lag_months"])
    horizon = pd.DateOffset(months=cfg.target["horizon_months"])

    b = add_history_features(bilans)
    b["date_observation"] = b["date_cloture"] + lag
    b["fin_horizon"] = b["date_observation"] + horizon

    # Dernière date où la cible est connue : la dernière procédure publiée, sans jamais dépasser
    # aujourd'hui moins un mois (délai de publication au BODACC). Au-delà, une absence de
    # procédure ne veut rien dire : ces bilans sont exclus.
    cap = pd.Timestamp.now().normalize() - pd.DateOffset(months=1)
    last_proc = procedures["date_ouverture"].max() if len(procedures) else cap
    last_known = min(last_proc, cap)
    b = b[b["fin_horizon"] <= last_known]

    first_proc = procedures.groupby("siren")["date_ouverture"].min()
    proc = procedures[["siren", "date_ouverture"]]

    merged = b.merge(proc, on="siren", how="left")
    in_window = (merged["date_ouverture"] > merged["date_observation"]) & (
        merged["date_ouverture"] <= merged["fin_horizon"]
    )
    merged["_hit"] = in_window
    target = merged.groupby(["siren", "date_cloture"])["_hit"].any().rename("defaillance").reset_index()
    b = b.merge(target, on=["siren", "date_cloture"], how="left")
    b["defaillance"] = b["defaillance"].fillna(False).astype(int)

    # Entreprises déjà en procédure au moment de l'observation : exclues
    already = b["siren"].map(first_proc)
    b = b[~(already.notna() & (already <= b["date_observation"]))]

    b["annee_observation"] = b["date_observation"].dt.year
    cols = ["siren", "date_cloture", "date_observation", "annee_observation", *model_features(cfg), "defaillance"]
    return b[cols].reset_index(drop=True)


def latest_features(bilans: pd.DataFrame, siren: str, cfg: Config) -> pd.Series | None:
    """Variables du bilan le plus récent d'un SIREN (pour le scoring)."""
    b = bilans[bilans["siren"] == siren]
    if b.empty:
        return None
    # La base de service contient déjà ces variables, précalculées sur tout l'historique
    if not set(EXTRA_FEATURES) <= set(b.columns):
        b = add_history_features(b)
    return b.sort_values("date_cloture").iloc[-1]
