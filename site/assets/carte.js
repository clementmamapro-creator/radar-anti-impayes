/* Carte de France animée des procédures collectives (GET /carte + contours des départements).
   Deux vues : les 12 derniers mois (cumul), ou un mois précis que l'on fait défiler (lecture). */
(function () {
  "use strict";
  var svg = document.getElementById("fcarte");
  if (!svg) return;
  var API = (window.ACQUIT_API || "").replace(/\/$/, "");
  var calme = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var info = document.getElementById("finfo");
  var NS = "http://www.w3.org/2000/svg";
  var MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
  function fr(x, d) { return (x || 0).toLocaleString("fr-FR", { maximumFractionDigits: d || 0 }); }
  function libMois(m) { var p = m.split("-"); return MOIS[+p[1] - 1] + " " + p[0]; }

  function compter(el, cible, D) {
    var depart = parseInt((el.textContent || "0").replace(/\D/g, ""), 10) || 0;
    if (calme) { el.textContent = fr(cible); return; }
    var t0 = performance.now();
    D = D || 1800;
    (function pas(t) {
      var p = Math.min(1, (t - t0) / D), e = 1 - Math.pow(1 - p, 4);
      el.textContent = fr(Math.round(depart + (cible - depart) * e));
      if (p < 1) requestAnimationFrame(pas);
    })(t0);
  }

  function quantiles(valeurs) {
    var v = valeurs.slice().sort(function (a, b) { return a - b; });
    function q(p) { return v[Math.floor(p * (v.length - 1))]; }
    return [q(0.2), q(0.4), q(0.6), q(0.8)];
  }
  function classe(n, s) { var k = 0; while (k < 4 && n > s[k]) k++; return k; }

  function sparkline(serie, idx) {
    if (!serie || serie.length < 2) return "";
    var max = Math.max.apply(null, serie.concat([1])), W = 200, H = 44;
    var pts = serie.map(function (v, i) { return [i * W / (serie.length - 1), H - 4 - (H - 8) * v / max]; });
    var d = pts.map(function (p, i) { return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" ");
    var h = '<svg class="spark" viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none"><path class="spark-aire" d="' + d + " L" + W + " " + H + " L0 " + H + ' Z"/><path class="spark-ligne" d="' + d + '"/>';
    if (idx != null && pts[idx]) h += '<circle cx="' + pts[idx][0].toFixed(1) + '" cy="' + pts[idx][1].toFixed(1) + '" r="3.5"/>';
    return h + "</svg>";
  }

  function dessiner(geo, data) {
    var deps = data.departements || {}, series = data.series || {}, mois = data.mois || [];
    var codes = Object.keys(geo.dep);
    svg.setAttribute("viewBox", "-10 -10 " + (geo.w + 20) + " " + (geo.h + 20));

    // Échelles par quantiles (Paris ne doit pas écraser le reste du pays) :
    // une pour le cumul sur 12 mois, une commune à tous les mois pour la lecture
    var seuilsAn = quantiles(codes.map(function (c) { return (deps[c] || {}).n || 0; }));
    var tousMois = [];
    codes.forEach(function (c) { (series[c] || []).forEach(function (v) { tousMois.push(v); }); });
    var seuilsMois = tousMois.length ? quantiles(tousMois) : seuilsAn;

    var etat = { idx: null, survol: null };  // idx null = 12 derniers mois
    var chemins = {};

    function valeur(code) {
      return etat.idx == null ? ((deps[code] || {}).n || 0) : ((series[code] || [])[etat.idx] || 0);
    }

    function montrer(code) {
      etat.survol = code;
      var d = geo.dep[code], v = deps[code] || {}, ev = v.evolution_pct;
      var periode = etat.idx == null ? "en 12 mois" : "en " + libMois(mois[etat.idx]);
      info.innerHTML = "<b>" + d.n + " (" + code + ")</b><span><strong>" + fr(valeur(code)) + "</strong> jugements d'ouverture " + periode + "</span>" +
        (ev == null ? "" : '<span class="' + (ev > 0 ? "hausse" : "baisse") + '">' + (ev > 0 ? "+" : "") + fr(ev, 1) + " % sur un an</span>") +
        sparkline(series[code], etat.idx) +
        (mois.length ? '<small>' + libMois(mois[0]) + " → " + libMois(mois[mois.length - 1]) + "</small>" : "");
      info.hidden = false;
    }

    // Sur ordinateur, l'info-bulle suit la souris et ne bloque jamais les clics (pointer-events: none).
    // Sur écran tactile, elle s'affiche sous la carte et se ferme en touchant ailleurs.
    // Détection au premier mouvement réel de souris (fiable aussi sur les PC à écran tactile)
    var souris = false;
    var zone = svg.parentNode;
    zone.addEventListener("pointermove", function (e) {
      if (e.pointerType === "mouse" && !souris) { souris = true; info.classList.add("flottante"); }
      suivre(e);
    });
    zone.addEventListener("pointerleave", function (e) { if (e.pointerType === "mouse") cacher(); });
    function suivre(e) {
      if (!souris || info.hidden) return;
      var r = zone.getBoundingClientRect(), w = info.offsetWidth, h = info.offsetHeight;
      var x = e.clientX - r.left + 18, y = e.clientY - r.top + 18;
      if (x + w > r.width) x = e.clientX - r.left - w - 18;   // bascule à gauche du curseur près du bord
      if (y + h > r.height) y = e.clientY - r.top - h - 18;
      info.style.transform = "translate(" + Math.max(0, x) + "px," + Math.max(0, y) + "px)";
    }
    function cacher() {
      if (!souris) return;
      etat.survol = null;
      info.hidden = true;
    }
    document.addEventListener("click", function (e) {
      if (!zone.contains(e.target) || e.target === svg) { etat.survol = null; info.hidden = true; }
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") { etat.survol = null; info.hidden = true; } });

    function colorer() {
      var s = etat.idx == null ? seuilsAn : seuilsMois;
      codes.forEach(function (c) { chemins[c].setAttribute("class", "dep c" + classe(valeur(c), s)); });
      var bornes = [0].concat(s);
      document.getElementById("flegende").innerHTML = "<span>Jugements d'ouverture " + (etat.idx == null ? "sur 12 mois" : "par mois") + "</span>" +
        [0, 1, 2, 3, 4].map(function (k) {
          var lib = k < 4 ? fr(bornes[k]) + "–" + fr(s[k]) : "> " + fr(s[3]);
          return '<i class="c' + k + '"></i><small>' + lib + "</small>";
        }).join("");
      if (etat.survol) montrer(etat.survol);
    }

    // Onde d'apparition depuis Paris
    var paris = geo.dep["75"] ? geo.dep["75"].c : [geo.w / 2, geo.h / 3], dmax = 0;
    codes.forEach(function (c) { var p = geo.dep[c].c; dmax = Math.max(dmax, Math.hypot(p[0] - paris[0], p[1] - paris[1])); });
    var groupe = document.createElementNS(NS, "g");
    codes.forEach(function (code) {
      var d = geo.dep[code], path = document.createElementNS(NS, "path");
      path.setAttribute("d", d.d);
      path.setAttribute("tabindex", "0");
      path.setAttribute("aria-label", d.n);
      var dist = Math.hypot(d.c[0] - paris[0], d.c[1] - paris[1]) / dmax;
      path.style.transitionDelay = calme ? "0ms" : Math.round(dist * 1400) + "ms";
      function survol() { montrer(code); groupe.appendChild(path); }
      path.addEventListener("mouseenter", survol);
      path.addEventListener("focus", survol);
      path.addEventListener("click", function (e) { e.stopPropagation(); survol(); suivre(e); });
      path.addEventListener("blur", cacher);
      chemins[code] = path;
      groupe.appendChild(path);
    });
    svg.appendChild(groupe);
    // Après l'apparition, les changements de couleur doivent être immédiats (lecture fluide)
    setTimeout(function () { codes.forEach(function (c) { chemins[c].style.transitionDelay = "0ms"; }); }, 2600);

    codes.slice().sort(function (a, b) { return ((deps[b] || {}).n || 0) - ((deps[a] || {}).n || 0); }).slice(0, 5).forEach(function (c, i) {
      var p = geo.dep[c].c, halo = document.createElementNS(NS, "circle");
      halo.setAttribute("cx", p[0]); halo.setAttribute("cy", p[1]); halo.setAttribute("r", 9);
      halo.setAttribute("class", "halo");
      halo.style.animationDelay = (1.6 + i * 0.35) + "s";
      svg.appendChild(halo);
    });
    colorer();

    // Courbe nationale (24 mois) avec repère du mois affiché
    var m = data.mensuel || [], fm = document.getElementById("fmois"), repere = null;
    if (m.length > 2) {
      var max = Math.max.apply(null, m.map(function (x) { return x.n; }));
      var min = Math.min.apply(null, m.map(function (x) { return x.n; }));
      var pts = m.map(function (x, i) { return [i * 300 / (m.length - 1), 56 - 50 * (x.n - min) / Math.max(1, max - min)]; });
      var dd = pts.map(function (p, i) { return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" ");
      fm.innerHTML = '<path class="aire" d="' + dd + ' L300 60 L0 60 Z"/><path class="ligne" d="' + dd + '" pathLength="1"/><circle class="repere" r="4" cx="-10" cy="-10"/>';
      repere = function (i) {
        var c = fm.querySelector(".repere");
        if (i == null) { c.classList.remove("vu"); return; }
        c.classList.add("vu");
        c.setAttribute("cx", pts[i][0]); c.setAttribute("cy", pts[i][1]);
      };
    }

    // Lecteur : bouton lecture + curseur des mois
    var lecteur = document.getElementById("flecteur"), btn = document.getElementById("fplay"),
        curseur = document.getElementById("fcurseur"), lib = document.getElementById("fmoislib"),
        total = document.getElementById("ftotal"), totalLib = document.getElementById("ftotallib"),
        an = document.getElementById("fan"), minuterie = null;
    var totalLibAn = totalLib ? totalLib.textContent : "";
    if (mois.length && lecteur) {
      lecteur.hidden = false;
      curseur.max = mois.length - 1;
      curseur.value = mois.length - 1;
    }
    function aller(i) {
      etat.idx = i;
      colorer();
      if (repere) repere(i);
      if (i == null) {
        lib.textContent = "12 derniers mois";
        compter(total, data.total || 0, 500);
        totalLib.textContent = totalLibAn;
        an.classList.add("actif");
      } else {
        curseur.value = i;
        lib.textContent = libMois(mois[i]);
        compter(total, (m[i] || {}).n || 0, 350);
        totalLib.textContent = "jugements d'ouverture publiés au BODACC en " + libMois(mois[i]);
        an.classList.remove("actif");
      }
    }
    function stop() { clearInterval(minuterie); minuterie = null; btn.classList.remove("lecture"); btn.setAttribute("aria-label", "Lire l'évolution mois par mois"); }
    function jouer() {
      if (minuterie) { stop(); return; }
      btn.classList.add("lecture");
      btn.setAttribute("aria-label", "Mettre en pause");
      var i = etat.idx == null || etat.idx >= mois.length - 1 ? 0 : etat.idx + 1;
      aller(i);
      minuterie = setInterval(function () {
        if (etat.idx >= mois.length - 1) { stop(); return; }
        aller(etat.idx + 1);
      }, 650);
    }
    if (btn) {
      btn.addEventListener("click", jouer);
      curseur.addEventListener("input", function () { stop(); aller(+curseur.value); });
      an.addEventListener("click", function () { stop(); curseur.value = mois.length - 1; aller(null); });
    }

    var ev = data.evolution_pct, fevol = document.getElementById("fevol");
    if (ev != null) fevol.innerHTML = '<span class="' + (ev > 0 ? "hausse" : "baisse") + '">' + (ev > 0 ? "+" : "") + fr(ev, 1) + " %</span> par rapport aux 12 mois précédents";

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
