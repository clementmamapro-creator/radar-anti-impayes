"""Sonde ponctuelle : vérifie en production les pages et fichiers publics du site."""
import json, httpx
B = "https://acquit-solutions.fr"
out = {}
with httpx.Client(timeout=60, follow_redirects=False) as c:
    for chemin in ("/", "/penalites-de-retard", "/a-propos", "/a-propos.html", "/sous-le-capot", "/robots.txt",
                   "/sitemap.xml", "/llms.txt", "/adresse-inexistante", "/carte", "/metriques"):
        try:
            r = c.get(B + chemin)
            info = {"status": r.status_code, "octets": len(r.content)}
            if r.status_code in (301, 302):
                info["vers"] = r.headers.get("location")
            if chemin == "/metriques":
                info["commit"] = r.json()["service"]["commit"]
            if chemin == "/carte":
                d = r.json(); info.update(total=d.get("total"), series=len(d.get("series") or {}), mois=len(d.get("mois") or []))
            out[chemin] = info
        except Exception as e:
            out[chemin] = repr(e)
print(json.dumps(out, ensure_ascii=False, indent=1))
