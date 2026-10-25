/* Acquit — confort de lecture : en-tête fixe, barre de progression, retour en haut,
   apparition douce des blocs et repérage de la section en cours. */
(function () {
  "use strict";
  var doc = document.documentElement;
  var calme = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var entete = document.querySelector(".entete");

  // Barre de progression de lecture, sous l'en-tête
  var barre = document.createElement("div");
  barre.className = "progression";
  barre.setAttribute("aria-hidden", "true");
  if (entete) entete.appendChild(barre);

  // Bouton « retour en haut »
  var haut = document.createElement("button");
  haut.type = "button";
  haut.className = "retour-haut";
  haut.setAttribute("aria-label", "Revenir en haut de la page");
  haut.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  haut.addEventListener("click", function () { window.scrollTo({ top: 0, behavior: calme ? "auto" : "smooth" }); });
  document.body.appendChild(haut);

  var attente = false;
  function majDefilement() {
    attente = false;
    var y = window.scrollY || doc.scrollTop;
    var max = doc.scrollHeight - window.innerHeight;
    if (entete) entete.classList.toggle("defile", y > 8);
    barre.style.transform = "scaleX(" + (max > 0 ? Math.min(1, y / max) : 0) + ")";
    haut.classList.toggle("visible", y > 700);
  }
  window.addEventListener("scroll", function () {
    if (!attente) { attente = true; window.requestAnimationFrame(majDefilement); }
  }, { passive: true });
  majDefilement();

  if (!("IntersectionObserver" in window)) return;

  // Apparition douce des blocs au fil de la lecture
  if (!calme) {
    var blocs = document.querySelectorAll(
      ".section h2, .section .intro, .moments li, .methode > div, .tarif, .faq details, .chat, main.texte > *"
    );
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("visible"); obs.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    blocs.forEach(function (b, i) {
      b.classList.add("revele");
      b.style.transitionDelay = (i % 3) * 70 + "ms";
      obs.observe(b);
    });
  }

  // Lien du menu correspondant à la section en cours de lecture
  var liens = {};
  document.querySelectorAll('.nav a[href^="#"]').forEach(function (a) { liens[a.getAttribute("href").slice(1)] = a; });
  var spy = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      var a = liens[e.target.id];
      if (!a) return;
      if (e.isIntersecting) {
        Object.keys(liens).forEach(function (k) { liens[k].classList.remove("actif"); });
        a.classList.add("actif");
      }
    });
  }, { rootMargin: "-45% 0px -50% 0px" });
  Object.keys(liens).forEach(function (id) { var s = document.getElementById(id); if (s) spy.observe(s); });
})();
