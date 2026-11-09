"""Espace client : configuration publique et « Mon secteur ».

La connexion et le profil passent directement par Supabase (clé publique +
Row Level Security) ; l'API ne fait ici que deux choses :
- donner au navigateur l'adresse du projet Supabase et sa clé publique ;
- traduire les données BODACC de la carte en un verdict lisible pour un département.
"""

from __future__ import annotations

import os

SEUIL_PCT = 5.0  # en deçà de ±5 % sur un an, on parle de stabilité


def config_publique() -> dict | None:
    """URL du projet et clé publique (publishable) : publiques par nature, jamais la clé secrète."""
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    cle = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
    if not url.startswith("https://") or not cle:
        return None
    return {"supabase_url": url, "supabase_publishable_key": cle}


def verdict(evolution_pct: float | None) -> dict:
    if evolution_pct is None:
        return {"code": "inconnu", "libelle": "Pas assez de données",
                "conseil": "Nous n'avons pas assez d'historique pour ce département."}
    if evolution_pct <= -SEUIL_PCT:
        return {"code": "respire", "libelle": "Ça respire",
                "conseil": "Moins d'entreprises en difficulté qu'il y a un an : le terrain se raffermit."}
    if evolution_pct >= SEUIL_PCT:
        return {"code": "tension", "libelle": "Sous tension",
                "conseil": "Plus de défaillances qu'il y a un an : vérifiez vos nouveaux clients "
                           "professionnels et demandez un acompte."}
    return {"code": "stable", "libelle": "Stable",
            "conseil": "Peu de changement sur un an. Restez attentif aux délais de paiement."}


def secteur(carte: dict, departement: str) -> dict | None:
    """Résumé d'un département à partir du résultat de radar.carte.calculer()."""
    d = carte.get("departements", {}).get(departement)
    if d is None:
        return None
    mois = carte.get("mois") or []
    serie = (carte.get("series") or {}).get(departement) or []
    return {
        "departement": departement,
        "n_12_mois": d["n"],
        "evolution_pct": d.get("evolution_pct"),
        "france": {"n_12_mois": carte.get("total"), "evolution_pct": carte.get("evolution_pct")},
        "verdict": verdict(d.get("evolution_pct")),
        "mois": mois[-12:],
        "serie": serie[-12:],
        "periode": carte.get("periode"),
        "source": carte.get("source"),
    }
