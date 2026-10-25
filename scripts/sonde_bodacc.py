"""Sonde ponctuelle : état du site en production et requête mensuelle par département (BODACC)."""
import json, httpx
B = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales/records"
out = {}
for chemin in ("/metriques", "/carte"):
    try:
        r = httpx.get("https://acquit-solutions.fr" + chemin, timeout=90)
        d = r.json()
        out[chemin] = {"status": r.status_code, "commit": (d.get("service") or {}).get("commit"),
                       "total": d.get("total"), "evolution": d.get("evolution_pct"), "mensuel": len(d.get("mensuel") or []),
                       "departements": len(d.get("departements") or {})}
    except Exception as e:
        out[chemin] = repr(e)
r = httpx.get(B, params={"select": "count(*) as n",
              "where": "familleavis='collective' and jugement like '%ouverture%' and dateparution>=date'2024-10-01' and dateparution<date'2026-10-01'",
              "group_by": "numerodepartement, date_format(dateparution, 'yyyy-MM') as mois", "limit": -1}, timeout=120)
out["dep_mois"] = {"status": r.status_code, "lignes": len(r.json().get("results") or []) if r.status_code == 200 else None, "debut": r.text[:400]}
print(json.dumps(out, ensure_ascii=False, indent=1))
