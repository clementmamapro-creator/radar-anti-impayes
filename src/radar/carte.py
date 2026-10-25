"""Carte des défaillances : jugements d'ouverture de procédures collectives
publiés au BODACC, par département, sur les 12 derniers mois.

Calculé à la volée par l'API d'agrégation Opendatasoft du BODACC (quelques
requêtes légères), puis gardé en mémoire 12 heures : la carte reste à jour
sans alourdir le pipeline ni la base de service.
"""

from __future__ import annotations

import datetime as dt
import threading
import time

import httpx

from .config import Config

DUREE_CACHE_S = 12 * 3600
FILTRE = "familleavis='collective' and jugement like '%ouverture%'"
_cache: dict = {}
_verrou = threading.Lock()


def _records(cfg: Config, params: dict) -> list[dict]:
    b = cfg.bodacc
    url = f"{b['base_url']}/catalog/datasets/{b['dataset']}/records"
    r = httpx.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("results") or []


def _par_departement(cfg: Config, debut: dt.date, fin: dt.date) -> dict[str, int]:
    rows = _records(cfg, {
        "select": "numerodepartement, count(*) as n",
        "where": f"{FILTRE} and dateparution>=date'{debut}' and dateparution<date'{fin}'",
        "group_by": "numerodepartement", "limit": 200,
    })
    return {r["numerodepartement"]: r["n"] for r in rows if r.get("numerodepartement")}


def _mensuel(cfg: Config, debut: dt.date, fin: dt.date) -> list[dict]:
    rows = _records(cfg, {
        "select": "count(*) as n",
        "where": f"{FILTRE} and dateparution>=date'{debut}' and dateparution<date'{fin}'",
        "group_by": "date_format(dateparution, 'yyyy-MM') as mois", "order_by": "mois", "limit": 100,
    })
    return [{"mois": r["mois"], "n": r["n"]} for r in rows if r.get("mois")]


def calculer(cfg: Config, aujourd_hui: dt.date | None = None) -> dict:
    j = aujourd_hui or dt.date.today()
    fin = j.replace(day=1)                       # mois complets uniquement
    debut = (fin - dt.timedelta(days=365)).replace(day=1)
    avant = (debut - dt.timedelta(days=365)).replace(day=1)
    actuel = _par_departement(cfg, debut, fin)
    precedent = _par_departement(cfg, avant, debut)
    departements = {
        d: {"n": n, "evolution_pct": round(100 * (n - precedent[d]) / precedent[d], 1) if precedent.get(d) else None}
        for d, n in actuel.items()
    }
    try:
        mensuel = _mensuel(cfg, avant, fin)
    except httpx.HTTPError:
        mensuel = []
    total, total_prec = sum(actuel.values()), sum(precedent.values())
    return {
        "periode": {"debut": str(debut), "fin": str(fin - dt.timedelta(days=1))},
        "total": total,
        "evolution_pct": round(100 * (total - total_prec) / total_prec, 1) if total_prec else None,
        "departements": departements,
        "mensuel": mensuel,
        "source": "BODACC (DILA), jugements d'ouverture de procédures collectives, Licence Ouverte",
        "calcule_le": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def carte(cfg: Config) -> dict | None:
    """Résultat en cache ; recalculé au plus toutes les 12 heures, l'ancien est gardé en cas d'échec."""
    with _verrou:
        if _cache and time.time() - _cache["t"] < DUREE_CACHE_S:
            return _cache["data"]
        try:
            data = calculer(cfg)
            _cache.update(t=time.time(), data=data)
        except (httpx.HTTPError, ValueError, KeyError):
            pass
        return _cache.get("data")
