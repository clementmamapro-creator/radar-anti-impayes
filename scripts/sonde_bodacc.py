"""Sonde ponctuelle : redirections et poids des pages en production (diagnostic Search Console)."""
import json, httpx
out = {}
urls = ["http://acquit-solutions.fr/", "https://www.acquit-solutions.fr/", "http://www.acquit-solutions.fr/",
        "https://acquit-solutions.fr/", "https://acquit-solutions.fr/index.html", "https://acquit-solutions.fr/a-propos.html",
        "https://acquit-solutions.fr/a-propos/", "https://acquit-solutions.fr/penalites-de-retard",
        "https://acquit-solutions.onrender.com/", "https://acquit-solutions.fr/sitemap.xml"]
with httpx.Client(timeout=60, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"}) as c:
    for u in urls:
        try:
            r = c.get(u)
            out[u] = {"status": r.status_code, "vers": r.headers.get("location"), "octets": len(r.content),
                      "type": r.headers.get("content-type"), "cache": r.headers.get("cache-control"),
                      "gzip": r.headers.get("content-encoding")}
        except Exception as e:
            out[u] = repr(e)
print(json.dumps(out, ensure_ascii=False, indent=1))
