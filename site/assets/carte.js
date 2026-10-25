/* Carte de France animée des procédures collectives (GET /carte + contours des départements). */
(function () {
  "use strict";
  var svg = document.getElementById("fcarte");
  if (!svg) return;
  var API = (window.ACQUIT_API || "").replace(/\/$/, "");
  var calme = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var info = document.getElementById("finfo");
  var NS = "http://www.w3.org/2000/svg";
  function fr(x, d) { return x.toLocaleString("fr-FR", { maximumFractionDigits: d || 0 }); }

  function compter(el, cible) {
    if (calme) { el.textContent = fr(cible); return; }
    var t0 = performance.now(), D = 1800;
    (function pas(t) {
      var p = Math.min(1, (t - t0) / D), e = 1 - Math.pow(1 - p, 4);
      el.textContent = fr(Math.round(cible * e));
      if (p < 1) requestAnimationFrame(pas);
    })(t0);
  }

  function dessiner(geo, data) {
    var deps = data.departements || {};
    svg.setAttribute("viewBox", "-10 -10 " + (geo.w + 20) + " " + (geo.h + 20));
    // Échelle par quantiles (5 classes) : Paris ne doit pas écraser le reste du pays
    var valeurs = Object.keys(geo.dep).map(function (c) { return (deps[c] || {}).n || 0; }).sort(function (a, b) { return a - b; });
    function q(p) { return valeurs[Math.floor(p * (valeurs.length - 1))]; }
    var seuils = [q(0.2), q(0.4), q(0.6), q(0.8)];
    function classe(n) { var k = 0; while (k < 4 && n > seuils[k]) k++; return k; }

    // Ordre d'apparition : une onde qui part de Paris
    var paris = geo.dep["75"] ? geo.dep["75"].c : [geo.w / 2, geo.h / 3];
    var codes = Object.keys(geo.dep);
    var dmax = 0;
    codes.forEach(function (c) { var p = geo.dep[c].c; dmax = Math.max(dmax, Math.hypot(p[0] - paris[0], p[1] - paris[1])); });

    var groupe = document.createElementNS(NS, "g");
    codes.forEach(function (code) {
      var d = geo.dep[code], v = deps[code] || {};
      var path = document.createElementNS(NS, "path");
      path.setAttribute("d", d.d);
      path.setAttribute("class", "dep c" + classe(v.n || 0));
      path.setAttribute("tabindex", "0");
      var dist = Math.hypot(d.c[0] - paris[0], d.c[1] - paris[1]) / dmax;
      path.style.transitionDelay = calme ? "0ms" : Math.round(dist * 1400) + "ms";
      function montrer() {
        var ev = v.evolution_pct;
        info.innerHTML = "<b>" + d.n + " (" + code + ")</b><span>" + fr(v.n || 0) + " jugements d'ouverture en 12 mois</span>" +
          (ev == null ? "" : '<span class="' + (ev > 0 ? "hausse" : "baisse") + '">' + (ev > 0 ? "+" : "") + fr(ev, 1) + " % sur un an</span>");
        info.hidden = false;
        groupe.appendChild(path);  // au premier plan pour que le contour se voie
      }
      path.addEventListener("mouseenter", montrer);
      path.addEventListener("focus", montrer);
      path.addEventListener("click", montrer);
      groupe.appendChild(path);
    });
    svg.appendChild(groupe);

    // Halos sur les 5 départements les plus touchés
    codes.slice().sort(function (a, b) { return ((deps[b] || {}).n || 0) - ((deps[a] || {}).n || 0); }).slice(0, 5).forEach(function (c, i) {
      var p = geo.dep[c].c, halo = document.createElementNS(NS, "circle");
      halo.setAttribute("cx", p[0]); halo.setAttribute("cy", p[1]); halo.setAttribute("r", 9);
      halo.setAttribute("class", "halo");
      halo.style.animationDelay = (1.6 + i * 0.35) + "s";
      svg.appendChild(halo);
    });

    // Légende
    var bornes = [0].concat(seuils);
    document.getElementById("flegende").innerHTML = "<span>Jugements d'ouverture sur 12 mois</span>" + [0, 1, 2, 3, 4].map(function (k) {
      var lib = k < 4 ? fr(bornes[k]) + "–" + fr(seuils[k]) : "> " + fr(seuils[3]);
      return '<i class="c' + k + '"></i><small>' + lib + "</small>";
    }).join("");

    // Courbe mensuelle (24 mois)
    var m = data.mensuel || [], fm = document.getElementById("fmois");
    if (m.length > 2) {
      var max = Math.max.apply(null, m.map(function (x) { return x.n; }));
      var min = Math.min.apply(null, m.map(function (x) { return x.n; }));
      var pts = m.map(function (x, i) { return [i * 300 / (m.length - 1), 56 - 50 * (x.n - min) / Math.max(1, max - min)]; });
      var dd = pts.map(function (p, i) { return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" ");
      fm.innerHTML = '<path class="aire" d="' + dd + ' L300 60 L0 60 Z"/><path class="ligne" d="' + dd + '" pathLength="1"/>';
    }

    // Chiffres
    var total = document.getElementById("ftotal");
    var ev = data.evolution_pct, fevol = document.getElementById("fevol");
    if (ev != null) fevol.innerHTML = '<span class="' + (ev > 0 ? "hausse" : "baisse") + '">' + (ev > 0 ? "+" : "") + fr(ev, 1) + " %</span> par rapport aux 12 mois précédents";

    // Lancement de l'animation quand la carte devient visible
    function lancer() {
      svg.parentNode.classList.add("vivante");
      document.querySelector(".radar-france").classList.add("vivante");
      compter(total, data.total || 0);
    }
    if ("IntersectionObserver" in window && !calme) {
      var obs = new IntersectionObserver(function (es) {
        if (es[0].isIntersecting) { obs.disconnect(); lancer(); }
      }, { threshold: 0.3 });
      obs.observe(svg);
    } else lancer();
  }

  Promise.all([
    fetch("assets/carte-france.json?v=1").then(function (r) { return r.json(); }),
    fetch(API + "/carte").then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
  ]).then(function (res) { dessiner(res[0], res[1]); })
    .catch(function () { var s = document.querySelector(".radar-france"); if (s) s.hidden = true; });
})();
