"""Scoring d'un SIREN et explication en langage clair."""

from __future__ import annotations

import warnings
from dataclasses import asdict, dataclass, field
from functools import cached_property

import httpx
import joblib
import numpy as np
import pandas as pd
import shap

from .config import Config
from .features import latest_features

# SHAP signale un changement de format de sortie déjà géré dans `explain`
warnings.filterwarnings("ignore", message="LightGBM binary classifier with TreeExplainer")

LABELS = {
    "chiffre_affaires": "le chiffre d'affaires",
    "marge_ebe": "la marge d'exploitation (EBE)",
    "resultat_net": "le résultat net",
    "taux_endettement": "le taux d'endettement",
    "ratio_liquidite": "la liquidité (capacité à payer à court terme)",
    "autonomie_financiere": "l'autonomie financière",
    "caf_sur_ca": "la capacité d'autofinancement",
    "capacite_remboursement": "la capacité de remboursement de la dette",
    "couverture_interets": "la couverture des intérêts",
    "credit_clients_jours": "le délai de paiement de ses propres clients",
    "credit_fournisseurs_jours": "le délai de paiement de ses fournisseurs",
    "poids_bfr_sur_ca": "le besoin en fonds de roulement",
    "evolution_ca": "l'évolution du chiffre d'affaires",
    "nb_bilans": "l'ancienneté des comptes publiés",
}

DISCLAIMER = (
    "Risque estimé à partir des données publiques (comptes déposés, BODACC). "
    "Ce score est une aide à la décision, pas un jugement sur l'entreprise."
)

RAPPEL_LEGAL = (
    "Entre professionnels, le délai de paiement ne peut dépasser 60 jours après l'émission "
    "de la facture, ou 45 jours fin de mois."
)

# Recommandation de conditions de paiement par situation (version 1, à valider avec des artisans)
RECOMMANDATIONS = {
    "faible": {
        "titre": "Conditions habituelles",
        "texte": "Rien d'inquiétant dans les comptes publiés. Un paiement à 30 jours est raisonnable.",
    },
    "modéré": {
        "titre": "Demandez un acompte",
        "texte": "Demandez un acompte d'environ 30 % à la signature et un paiement du solde à 15 jours.",
    },
    "élevé": {
        "titre": "Sécurisez le paiement",
        "texte": "Demandez 50 % à la commande et le solde à la livraison, avant toute avance de matériel.",
    },
    "procedure_en_cours": {
        "titre": "N'accordez pas de délai",
        "texte": "Une procédure collective est en cours : exigez le paiement intégral avant de commencer.",
    },
    "donnees_insuffisantes": {
        "titre": "Restez prudent",
        "texte": "Cette entreprise ne publie pas ses comptes. Un acompte reste prudent, surtout si elle est récente.",
    },
}


@dataclass
class Facteur:
    variable: str
    libelle: str
    valeur: float | None
    effet: str  # "augmente" ou "réduit" le risque
    poids: float
    position: str | None = None  # "au-dessus" ou "en dessous" de la médiane, None si inconnue
    phrase: str = ""


@dataclass
class Resultat:
    siren: str
    statut: str  # "score", "procedure_en_cours", "donnees_insuffisantes"
    probabilite: float | None = None
    niveau: str | None = None
    date_dernier_bilan: str | None = None
    facteurs: list[Facteur] = field(default_factory=list)
    procedures: list[dict] = field(default_factory=list)
    identite: dict | None = None
    recommandation: dict | None = None
    rappel_legal: str = RAPPEL_LEGAL
    avertissement: str = DISCLAIMER

    def __post_init__(self) -> None:
        if self.recommandation is None:
            key = self.niveau if self.statut == "score" else self.statut
            self.recommandation = RECOMMANDATIONS.get(key)

    def to_dict(self) -> dict:
        return asdict(self)


def level_for(p: float, levels: dict) -> str:
    if p < levels["faible"]:
        return "faible"
    if p < levels["modere"]:
        return "modéré"
    return "élevé"


# Caches mémoire bornés : évitent de réinterroger l'API publique pour les mêmes recherches.
# Seules les réponses réussies sont gardées, pour qu'une panne passagère ne se fige pas.
_CACHE_MAX = 2000
_search_cache: dict[tuple[str, int], list[dict]] = {}
_identity_cache: dict[str, dict] = {}


def _remember(cache: dict, key, value) -> None:
    if len(cache) >= _CACHE_MAX:
        cache.pop(next(iter(cache)))
    cache[key] = value


def search_companies(cfg: Config, query: str, limit: int = 6, timeout: float = 5.0) -> list[dict]:
    """Suggestions d'entreprises par nom (API Recherche d'entreprises). Liste vide en cas d'échec."""
    key = (query.strip().lower(), limit)
    if key in _search_cache:
        return _search_cache[key]
    try:
        r = httpx.get(
            f"{cfg.entreprises['base_url']}/search",
            params={"q": query, "per_page": limit, "etat_administratif": "A"},
            timeout=timeout,
        )
        r.raise_for_status()
        results = r.json().get("results") or []
    except (httpx.HTTPError, ValueError):
        return []
    out = []
    for e in results:
        siege = e.get("siege") or {}
        out.append({
            "siren": e.get("siren"),
            "nom": e.get("nom_raison_sociale") or e.get("nom_complet"),
            "ville": siege.get("libelle_commune"),
            "code_postal": siege.get("code_postal"),
        })
    out = [x for x in out if x["siren"]]
    _remember(_search_cache, key, out)
    return out


def fetch_identity(cfg: Config, siren: str, timeout: float = 5.0) -> dict | None:
    """Nom, activité et date de création via l'API Recherche d'entreprises (facultatif)."""
    if siren in _identity_cache:
        return _identity_cache[siren]
    try:
        r = httpx.get(f"{cfg.entreprises['base_url']}/search", params={"q": siren, "per_page": 1}, timeout=timeout)
        r.raise_for_status()
        res = r.json().get("results") or []
    except (httpx.HTTPError, ValueError):
        return None
    if not res or res[0].get("siren") != siren:
        return None
    e = res[0]
    ident = {
        "nom": e.get("nom_raison_sociale") or e.get("nom_complet"),
        "activite": e.get("activite_principale"),
        "date_creation": e.get("date_creation"),
        "etat": e.get("etat_administratif"),
    }
    _remember(_identity_cache, siren, ident)
    return ident


class Scorer:
    """Score un SIREN.

    `store` fournit les données d'un SIREN à la fois (voir `radar.store`) :
    en production, une requête DuckDB ; en test, des DataFrames en mémoire.
    Rien n'est chargé en entier, pour tenir dans 512 Mo de RAM.
    """

    def __init__(self, cfg: Config, store, with_identity: bool = True):
        self.cfg = cfg
        self.store = store
        self.with_identity = with_identity
        bundle = joblib.load(cfg.model_dir / "model.joblib")
        self.calibrated = bundle["calibrated"]
        self.booster = bundle["booster"]
        self.features = bundle["features"]
        self.levels = bundle["levels"]
        self.medians = bundle.get("medians", {})

    @cached_property
    def explainer(self) -> shap.TreeExplainer:
        return shap.TreeExplainer(self.booster)

    def explain(self, x: pd.DataFrame, top: int = 3) -> list[Facteur]:
        values = self.explainer.shap_values(x)
        if isinstance(values, list):  # anciennes versions : une matrice par classe
            values = values[1]
        contrib = np.asarray(values)[0]
        order = np.argsort(-np.abs(contrib))[:top]
        out = []
        for i in order:
            name = self.features[i]
            v = x.iloc[0, i]
            label = LABELS.get(name, name)
            effet = "augmente" if contrib[i] > 0 else "réduit"
            med = self.medians.get(name)
            if pd.isna(v):
                position = None
                phrase = f"{label[0].upper()}{label[1:]} : non publié, ce qui {effet} le risque."
            else:
                position = "au-dessus" if med is None or v >= med else "en dessous"
                phrase = (
                    f"{label[0].upper()}{label[1:]} : {position} de la médiane des entreprises, "
                    f"ce qui {effet} le risque."
                )
            out.append(Facteur(
                variable=name,
                libelle=label,
                valeur=None if pd.isna(v) else round(float(v), 4),
                effet=effet,
                poids=round(float(contrib[i]), 4),
                position=position,
                phrase=phrase,
            ))
        return out

    def score(self, siren: str) -> Resultat:
        siren = "".join(c for c in siren if c.isdigit()).zfill(9)
        procs = self.store.procedures_for(siren).sort_values("date_ouverture")
        proc_list = [
            {"date": pd.Timestamp(d).strftime("%Y-%m-%d"), "nature": n}
            for d, n in zip(procs["date_ouverture"], procs["nature"])
        ]
        ident = fetch_identity(self.cfg, siren) if self.with_identity else None

        last = latest_features(self.store.bilans_for(siren), siren, self.cfg)
        if proc_list and (last is None or pd.Timestamp(proc_list[-1]["date"]) > last["date_cloture"]):
            return Resultat(siren, "procedure_en_cours", niveau="élevé", procedures=proc_list, identite=ident)
        if last is None:
            return Resultat(siren, "donnees_insuffisantes", procedures=proc_list, identite=ident)

        x = pd.DataFrame([last[self.features].astype(float).to_numpy()], columns=self.features)
        p = float(self.calibrated.predict_proba(x)[0, 1])
        return Resultat(
            siren=siren,
            statut="score",
            probabilite=round(p, 4),
            niveau=level_for(p, self.levels),
            date_dernier_bilan=last["date_cloture"].strftime("%Y-%m-%d"),
            facteurs=self.explain(x),
            procedures=proc_list,
            identite=ident,
        )
