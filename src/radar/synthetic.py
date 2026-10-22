"""Données synthétiques au format exact des fichiers bruts.

Sert aux tests, à la CI et aux démonstrations hors ligne. Les noms de
colonnes et formats (SIREN espacés, jugement en JSON texte, plusieurs
types de bilan) reproduisent ceux des sources réelles, pour que tout le
pipeline soit exercé. Le risque de défaillance dépend des ratios
(endettement, liquidité, rentabilité) : un modèle doit pouvoir le retrouver.

Ces données sont FICTIVES : aucun résultat obtenu dessus ne décrit
des entreprises réelles.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config


def generate(cfg: Config, n_companies: int = 6000, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    rc = cfg.ratios["columns"]
    rf = cfg.ratios["features"]
    bc = cfg.bodacc["columns"]

    sirens = [f"{900000000 + i:09d}" for i in range(n_companies)]
    # Santé latente de chaque entreprise (plus bas = plus fragile)
    health = rng.normal(0, 1, n_companies)

    ratio_rows, bodacc_rows = [], []
    for siren, h in zip(sirens, health):
        first_year = int(rng.integers(2016, 2022))
        n_years = int(rng.integers(2, 2025 - first_year + 1))
        ca = float(np.exp(rng.normal(13, 1.2)))  # CA initial, ~ 450 k€ médian
        failed = False
        for k in range(n_years):
            year = first_year + k
            if failed:
                break
            h_t = h + rng.normal(0, 0.35)  # la santé varie d'une année à l'autre
            ca *= float(np.exp(0.05 + 0.12 * h_t + rng.normal(0, 0.15)))
            row = {
                rc["siren"]: siren,
                rc["date_cloture"]: f"{year}-12-31",
                rc["type_bilan"]: "C" if rng.random() < 0.85 else "S",
                rf["chiffre_affaires"]: round(ca, 0),
                rf["marge_ebe"]: 0.08 + 0.05 * h_t + rng.normal(0, 0.03),
                rf["resultat_net"]: round(ca * (0.03 + 0.04 * h_t + rng.normal(0, 0.02)), 0),
                rf["taux_endettement"]: max(0.0, 0.9 - 0.45 * h_t + rng.normal(0, 0.25)),
                rf["ratio_liquidite"]: max(0.05, 1.3 + 0.4 * h_t + rng.normal(0, 0.25)),
                rf["autonomie_financiere"]: 0.35 + 0.12 * h_t + rng.normal(0, 0.08),
                rf["caf_sur_ca"]: 0.06 + 0.04 * h_t + rng.normal(0, 0.02),
                rf["capacite_remboursement"]: max(0.0, 3.0 - 1.2 * h_t + rng.normal(0, 0.8)),
                rf["couverture_interets"]: 6 + 3 * h_t + rng.normal(0, 2),
                rf["credit_clients_jours"]: max(0.0, 55 - 10 * h_t + rng.normal(0, 12)),
                rf["credit_fournisseurs_jours"]: max(0.0, 60 - 12 * h_t + rng.normal(0, 12)),
                rf["poids_bfr_sur_ca"]: 0.12 - 0.04 * h_t + rng.normal(0, 0.05),
            }
            # Données manquantes, comme dans la réalité (comptes partiels)
            for key in (rf["couverture_interets"], rf["credit_fournisseurs_jours"], rf["poids_bfr_sur_ca"]):
                if rng.random() < 0.2:
                    row[key] = None
            ratio_rows.append(row)

            # Probabilité de défaillance l'année suivant l'observation
            logit = -4.0 - 1.6 * h_t
            if rng.random() < 1 / (1 + np.exp(-logit)):
                failed = True
                # Ouverture entre 8 et 18 mois après la clôture (après dépôt des comptes)
                date = pd.Timestamp(f"{year}-12-31") + pd.Timedelta(days=int(rng.integers(245, 545)))
                nature = rng.choice(
                    [
                        "Jugement d'ouverture d'une procédure de redressement judiciaire",
                        "Jugement d'ouverture d'une procédure de liquidation judiciaire",
                        "Jugement d'ouverture d'une procédure de sauvegarde",
                    ],
                    p=[0.4, 0.5, 0.1],
                )
                spaced = f"{siren[:3]} {siren[3:6]} {siren[6:]}"
                bodacc_rows.append(
                    {
                        bc["registre"]: spaced,
                        bc["date_parution"]: (date + pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
                        bc["famille"]: "Procédures collectives",
                        bc["jugement"]: json.dumps(
                            {"type": "initial", "famille": "Jugement d'ouverture", "nature": nature,
                             "date": date.strftime("%Y-%m-%d")},
                            ensure_ascii=False,
                        ),
                    }
                )
                # Bruit réaliste : un jugement de clôture plus tard (doit être ignoré)
                if rng.random() < 0.5:
                    later = date + pd.Timedelta(days=int(rng.integers(200, 600)))
                    bodacc_rows.append(
                        {
                            bc["registre"]: spaced,
                            bc["date_parution"]: later.strftime("%Y-%m-%d"),
                            bc["famille"]: "Procédures collectives",
                            bc["jugement"]: json.dumps(
                                {"type": "initial", "famille": "Jugement de clôture",
                                 "nature": "Jugement de clôture pour insuffisance d'actif",
                                 "date": later.strftime("%Y-%m-%d")},
                                ensure_ascii=False,
                            ),
                        }
                    )

    return pd.DataFrame(bodacc_rows), pd.DataFrame(ratio_rows)


def write_raw(cfg: Config, out_dir: Path, **kwargs) -> tuple[Path, Path]:
    bodacc, ratios = generate(cfg, **kwargs)
    out_dir.mkdir(parents=True, exist_ok=True)
    pb, pr = out_dir / "bodacc_collectives.parquet", out_dir / "ratios.parquet"
    bodacc.to_parquet(pb, index=False)
    ratios.to_parquet(pr, index=False)
    return pb, pr
