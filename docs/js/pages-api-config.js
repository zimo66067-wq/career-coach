/*
 * API origin selection.
 *
 * Vercel production and Preview deployments call their own API so Preview
 * tests exercise the code being reviewed. GitHub Pages uses the production
 * Vercel API. An explicit value injected before this file always wins.
 */
(function () {
  if (window.DUMATE_API_BASE) return;
  var loc = window.location || {};
  var hostname = String(loc.hostname || "");
  var isVercel = /\.vercel\.app$/i.test(hostname);
  window.DUMATE_API_BASE = isVercel && loc.origin
    ? loc.origin
    : "https://career-coach-omega-three.vercel.app";
})();
