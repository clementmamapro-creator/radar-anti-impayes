"""Sonde ponctuelle : syntaxes d'agrégation BODACC (Opendatasoft) pour la carte."""
import json, httpx
B = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales"
essais = {
  "sans_filtre_jugement": "familleavis='collective' and dateparution>=date'2025-10-01'",
  "like_pct": "familleavis='collective' and dateparution>=date'2025-10-01' and jugement like '%ouverture%'",
  "like_etoile": "familleavis='collective' and dateparution>=date'2025-10-01' and jugement like \"*ouverture*\"",
  "search": "familleavis='collective' and dateparution>=date'2025-10-01' and search(jugement, \"ouverture\")",
}
out = {}
for k, w in essais.items():
    r = httpx.get(B + "/records", params={"select": "numerodepartement, count(*) as n", "where": w,
                  "group_by": "numerodepartement", "order_by": "n desc", "limit": 5}, timeout=60)
    out[k] = {"status": r.status_code, "body": r.text[:600]}
r = httpx.get(B + "/records", params={"where": "familleavis='collective'", "limit": 1, "order_by": "dateparution desc"}, timeout=60)
out["exemple"] = r.text[:2500]
r = httpx.get(B + "/records", params={"select": "year(dateparution) as an, month(dateparution) as mois, count(*) as n",
              "where": "familleavis='collective' and dateparution>=date'2024-10-01'", "group_by": "an, mois", "limit": 30}, timeout=60)
out["mensuel"] = {"status": r.status_code, "body": r.text[:800]}
print(json.dumps(out, ensure_ascii=False, indent=1))
