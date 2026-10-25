/* Page « Sous le capot » : architecture interactive et métriques en direct (GET /metriques). */
(function () {
  "use strict";
  var API = (window.ACQUIT_API || "").replace(/\/$/, "");
  var calme = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var nf = new Intl.NumberFormat("fr-FR");
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function fr(x, d) { return x == null ? "–" : x.toLocaleString("fr-FR", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }); }
  function compact(n) {
    if (n == null) return "–";
    if (n >= 1e6) return fr(n / 1e6, 1) + " M";
    if (n >= 1e4) return fr(Math.round(n / 1e3)) + " k";
    return nf.format(n);
  }
  function ms(x) { return x == null ? "–" : x >= 1000 ? fr(x / 1000, 1) + " s" : fr(x, x < 100 ? 1 : 0) + " ms"; }
  function duree(s) {
    if (s == null) return "–";
    var j = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
    return j ? j + " j " + h + " h" : h ? h + " h " + m + " min" : m + " min";
  }

  // Valeur affichée avec un compteur qui défile jusqu'au nombre (une seule fois par clé)
  var deja = {};
  function poser(k, texte, nombre, format) {
    $$('[data-k="' + k + '"]').forEach(function (el) {
      if (nombre == null || calme || deja[k]) { el.textContent = texte; return; }
      deja[k] = true;
      var t0 = performance.now(), D = 1100;
      (function pas(t) {
        var p = Math.min(1, (t - t0) / D), e = 1 - Math.pow(1 - p, 3);
        el.textContent = p < 1 ? format(nombre * e) : texte;
        if (p < 1) requestAnimationFrame(pas);
      })(t0);
    });
  }

  // ---- Architecture : détail de la brique choisie ----
  var detail = $("#archi-detail");
  $$(".noeud").forEach(function (n) {
    function montrer() {
      $$(".noeud.actif").forEach(function (x) { x.classList.remove("actif"); });
      n.classList.add("actif");
      detail.innerHTML = "<b>" + n.querySelector("b").textContent + "</b> · " + n.dataset.d;
    }
    n.addEventListener("mouseenter", montrer);
    n.addEventListener("focus", montrer);
    n.addEventListener("click", montrer);
  });

  // ---- Courbe : barres de requêtes et ligne de latence p95 ----
  function courbe(minutes) {
    var svg = $("#courbe");
    if (!svg || !minutes || !minutes.length) return;
    var W = 600, H = 160, pad = 6, n = minutes.length, bw = W / n;
    var maxR = Math.max.apply(null, minutes.map(function (m) { return m.requetes; }).concat([1]));
    var lat = minutes.map(function (m) { return m.p95_ms; });
    var maxL = Math.max.apply(null, lat.filter(function (x) { return x != null; }).concat([10]));
    var h = "";
    minutes.forEach(function (m, i) {
      var bh = (H - 2 * pad) * m.requetes / maxR;
      h += '<rect class="b" x="' + (i * bw + 2).toFixed(1) + '" y="' + (H - pad - bh).toFixed(1) + '" width="' + (bw - 4).toFixed(1) + '" height="' + bh.toFixed(1) + '" rx="2"><title>' + m.requetes + " requêtes</title></rect>";
    });
    var pts = [];
    lat.forEach(function (v, i) { if (v != null) pts.push([(i + 0.5) * bw, H - pad - (H - 2 * pad) * v / maxL]); });
    if (pts.length > 1) {
      var d = pts.map(function (p, i) { return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" ");
      h += '<path class="l" d="' + d + '" pathLength="1"/>';
      var last = pts[pts.length - 1];
      h += '<circle class="pt" cx="' + last[0].toFixed(1) + '" cy="' + last[1].toFixed(1) + '" r="4"/>';
    } else if (pts.length === 1) {
      h += '<circle class="pt" cx="' + pts[0][0].toFixed(1) + '" cy="' + pts[0][1].toFixed(1) + '" r="4"/>';
    }
    var lm = $("#lmax");
    if (lm) lm.textContent = "max " + fr(maxL) + " ms · " + maxR + " req/min";
    svg.innerHTML = h;
  }

  function jauge(id, pct) { var e = $("#" + id); if (e) e.style.width = Math.max(2, Math.min(100, pct || 0)) + "%"; }

  function anneau(nom, v) {
    var el = $('.anneau[data-a="' + nom + '"]');
    if (!el || v == null) return;
    var c = 2 * Math.PI * 50;
    var arc = el.querySelector(".arc");
    arc.style.strokeDasharray = c;
    arc.style.strokeDashoffset = c * (1 - v);
    el.querySelector("b").textContent = fr(v * 100) + " %";
  }

  var modeleAffiche = false;
  function modele(m, a, donnees) {
    if (modeleAffiche) return;
    modeleAffiche = true;
    poser("train", compact(m.lignes_entrainement));
    poser("test", compact(m.lignes_test));
    poser("auc2", fr(m.roc_auc, 3));
    poser("ref", fr(m.reference_auc, 3));
    // échelle 0,5 (hasard) -> 1 (parfait)
    function largeur(x) { return x == null ? 0 : Math.max(0, (x - 0.5) / 0.5 * 100); }
    var wa = $('[data-w="auc"]'), wr = $('[data-w="ref"]');
    if (wa) wa.style.width = largeur(m.roc_auc) + "%";
    if (wr) wr.style.width = largeur(m.reference_auc) + "%";
    var niv = m.niveaux || {};
    var ordre = [["faible", "Faible"], ["modéré", "Modéré"], ["élevé", "Élevé"]];
    var max = Math.max.apply(null, ordre.map(function (o) { return (niv[o[0]] || {}).taux_defaillance_observe || 0; }).concat([0.01]));
    $("#niveaux").innerHTML = ordre.map(function (o) {
      var d = niv[o[0]] || {};
      var t = d.taux_defaillance_observe;
      return '<div class="niv niv-' + o[0].normalize("NFD").replace(/[̀-ͯ]/g, "") + '"><span>' + o[1] + "</span><i><em style=\"--w:" + (t ? (t / max * 100).toFixed(1) : 0) + '%"></em></i><b>' + (t == null ? "–" : fr(t * 100, 1) + " %") + "</b><small>" + (d.part_entreprises == null ? "" : fr(d.part_entreprises * 100, 1) + " % des entreprises") + "</small></div>";
    }).join("");
    anneau("reussite", a.test_reussite_at5);
    anneau("rappel", a.test_rappel_at5);
    anneau("fidelite", a.taux_fidelite);
    poser("llm", a.modele || "–");
    poser("articles", donnees.corpus_articles == null ? "–" : String(donnees.corpus_articles));
  }

  function afficher(d) {
    var t = d.trafic || {}, l = t.latence_ms || {}, s = d.service || {}, c = d.cache || {}, m = d.modele || {}, a = d.assistant || {}, donnees = d.donnees || {};
    poser("p95", l.p95 == null ? "–" : fr(l.p95) + " ms", l.p95, function (x) { return fr(x) + " ms"; });
    poser("req", nf.format(t.requetes || 0), t.requetes, function (x) { return nf.format(Math.round(x)); });
    poser("entreprises", compact(donnees.bilans), donnees.bilans, compact);
    poser("auc", fr(m.roc_auc, 3), m.roc_auc, function (x) { return fr(x, 3); });
    poser("rag", a.test_reussite_at5 == null ? "–" : fr(a.test_reussite_at5 * 100) + " %", a.test_reussite_at5 && a.test_reussite_at5 * 100, function (x) { return fr(x) + " %"; });
    poser("p50", ms(l.p50));
    poser("p95b", ms(l.p95));
    poser("p99", ms(l.p99));
    poser("err", fr(t.erreurs_pct, 1) + " %");
    poser("mem", fr(s.memoire_mo) + " Mo / 512");
    jauge("jmem", s.memoire_mo / 512 * 100);
    poser("cpu", fr(s.cpu_pct) + " %");
    jauge("jcpu", s.cpu_pct / 50 * 100);  // l'instance dispose d'une demi-unité de CPU
    poser("cache", c.taux_pct == null ? "pas encore sollicité" : fr(c.taux_pct) + " % de succès");
    jauge("jcache", c.taux_pct);
    poser("instance", s.instance || "");
    poser("uptime", duree(s.en_service_s));
    poser("version", (s.version || "–") + (s.commit ? " (" + s.commit + ")" : ""));
    var routes = t.par_route || [];
    $("#routes").innerHTML = routes.length ? routes.map(function (r) {
      return "<tr><td><code>" + r.route.replace(/[<>&]/g, "") + "</code></td><td>" + nf.format(r.requetes) + "</td><td>" + ms(r.p50_ms) + "</td><td>" + ms(r.p95_ms) + "</td></tr>";
    }).join("") : '<tr><td colspan="4">Aucune requête d\'API ces 15 dernières minutes. Vérifiez une entreprise ou posez une question à l\'assistant, puis revenez ici.</td></tr>';
    courbe(t.minutes);
    modele(m, a, donnees);
    $("#maj").textContent = "Dernière mesure : " + new Date().toLocaleTimeString("fr-FR");
    document.body.classList.add("capot-pret");
  }

  function charger() {
    if (document.hidden) return;
    fetch(API + "/metriques", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(afficher)
      .catch(function () { $("#maj").textContent = "Mesures momentanément indisponibles."; });
  }
  charger();
  setInterval(charger, 5000);
  document.addEventListener("visibilitychange", charger);
})();

/* Test de charge : avant / après le cache des scores (fichiers publiés avec le site) */
(function () {
  "use strict";
  var svg = document.getElementById("cgraph");
  if (!svg) return;
  function lire(f) { return fetch("assets/" + f + "?v=2").then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }); }
  function fr(x, d) { return x == null ? "–" : x.toLocaleString("fr-FR", { maximumFractionDigits: d || 0 }); }
  Promise.all([lire("charge-avant.json"), lire("charge-apres.json")]).then(function (res) {
    var avant = res[0], apres = res[1];
    if (!avant) return;
    var paliers = avant.paliers.map(function (p) { return p.utilisateurs_simultanes; });
    var max = Math.max.apply(null, [avant].concat(apres ? [apres] : []).map(function (r) { return r.debit_max_rps; }));
    var W = 600, H = 220, g = 34, bas = H - 26, n = paliers.length, pas = (W - g) / n, bw = apres ? pas * 0.34 : pas * 0.5;
    var h = "";
    [0.25, 0.5, 0.75, 1].forEach(function (t) {
      var y = bas - (bas - 14) * t;
      h += '<line class="grille" x1="' + g + '" x2="' + W + '" y1="' + y + '" y2="' + y + '"/><text class="axe" x="' + (g - 6) + '" y="' + (y + 4) + '" text-anchor="end">' + fr(max * t) + "</text>";
    });
    paliers.forEach(function (u, i) {
      var x0 = g + i * pas + pas / 2;
      [[avant, "avant", apres ? -bw / 2 - 2 : 0], [apres, "apres", bw / 2 + 2]].forEach(function (s) {
        if (!s[0]) return;
        var p = s[0].paliers[i];
        if (!p) return;
        var hh = (bas - 14) * p.debit_rps / max, x = x0 + s[2] - bw / 2;
        h += '<rect class="' + s[1] + '" x="' + x.toFixed(1) + '" y="' + (bas - hh).toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + hh.toFixed(1) + '" rx="3"><title>' + u + " utilisateurs : " + fr(p.debit_rps, 1) + " req/s, médiane " + fr(p.p50_ms) + " ms</title></rect>";
      });
      h += '<text class="axe" x="' + x0 + '" y="' + (H - 8) + '" text-anchor="middle">' + u + "</text>";
    });
    svg.innerHTML = h;
    document.querySelectorAll('[data-c="avant"]').forEach(function (e) { e.textContent = fr(avant.debit_max_rps); });
    if (apres) {
      var gain = apres.debit_max_rps / avant.debit_max_rps;
      var p40a = avant.paliers[avant.paliers.length - 1], p40b = apres.paliers[apres.paliers.length - 1];
      document.querySelectorAll('[data-c="apres"]').forEach(function (e) {
        e.textContent = fr(apres.debit_max_rps) + " req/s, soit ×" + fr(gain, 1) + " ; à " + p40b.utilisateurs_simultanes +
          " utilisateurs, la latence médiane passe de " + fr(p40a.p50_ms) + " à " + fr(p40b.p50_ms) + " ms, sans aucune erreur";
      });
    }
  });
})();
