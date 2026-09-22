// Epidemiological Trends charts.
//
// Draws the four cards from PAYLOAD.trends using the shared primitives in
// charts.js. Owns NO state: engine.js keeps the scope/selection and the map,
// and calls TrendsCharts.render({scope, key}).
//
// Every constant and rule here is transcribed from the generator at
// BDBV2026-Processing_Code@main; see the spec's section 6 before changing any
// of it. Colours, stacking order and captions are contractual.
(function (global) {
  "use strict";

  var C = global.DashboardCharts;

  var COLOR_OBS = "#b23b2e";        // Confirmed (Observed Onset)
  var COLOR_IMP = "#f1ccc6";        // Confirmed (Imputed Onset)
  var COLOR_POSITIVITY = "#5b86b3";
  var COLOR_DEATHS = "#7c1d1d";
  var COLOR_SAMPLES = "#9c968b";
  var COLOR_INCOMPLETE = "#9c968b";
  var COLOR_INK = "#2a2a27";
  var PAD = { left: 42, right: 46, top: 12, bottom: 26 };

  function readTrends() {
    var el = document.getElementById("payload");
    if (!el) return null;
    try { return (JSON.parse(el.textContent) || {}).trends || null; } catch (e) { return null; }
  }
  var _cache;
  function trends() { if (_cache === undefined) _cache = readTrends(); return _cache; }

  function tr(key, fallback) {
    return (global.t ? global.t(key) : null) || fallback;
  }

  // Resolve one family's entry for the current selection.
  function pick(family, scope, key) {
    var d = trends();
    if (!d || !d[family]) return null;
    if (scope === "national") return d[family].national || null;
    if (!key) return null;
    if (scope === "province") return (d[family].provinces || {})[key] || null;
    if (scope === "health_zone") return (d[family].health_zones || {})[key] || null;
    return null;
  }

  // The SHARED date range for this selection (spec 6.6). All three spatial
  // cards use it so they cannot disagree about time.
  function xLimits(scope, key) {
    var d = trends();
    if (!d || !d.x_limits) return null;
    var scale = scope === "national" ? "national" : (scope === "province" ? "province" : "healthzone");
    var name = scope === "national" ? "national" : key;
    return name ? (d.x_limits[scale] || {})[name] || null : null;
  }

  // Expand a {start, <array>} entry into explicit ISO dates.
  function isoSeq(start, n) {
    var out = [], t = C.dayMs(start), i;
    for (i = 0; i < n; i++) out.push(new Date(t + i * 86400000).toISOString().slice(0, 10));
    return out;
  }

  function newSvg(host, W, H) {
    host.replaceChildren();
    return C.svgEl("svg", { viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none" });
  }

  function size(host) {
    return { W: host.clientWidth || 320, H: host.clientHeight || 190 };
  }

  // --- Card 1: confirmed cases ----------------------------------------------
  function renderCases(host, scope, key) {
    var d = trends(), entry = pick("cases", scope, key), lim = xLimits(scope, key);
    if (!entry || !lim) return false;
    var dates = isoSeq(entry.start, entry.obs.length);
    var dim = size(host), svg = newSvg(host, dim.W, dim.H);
    var yMax = 0, i;
    for (i = 0; i < dates.length; i++) yMax = Math.max(yMax, entry.obs[i] + entry.imp[i]);

    var fr = C.frame(svg, {
      width: dim.W, height: dim.H, pad: PAD,
      xStart: lim.start, xEnd: lim.end, yMax: yMax
    });
    C.shadeRegion(svg, fr, d.incomplete_from, COLOR_INCOMPLETE);
    C.stackedBars(svg, fr, dates, [
      { values: entry.obs, color: COLOR_OBS },   // observed at the BOTTOM
      { values: entry.imp, color: COLOR_IMP }
    ]);
    host.appendChild(svg);

    C.tooltip(host, svg, fr, function (iso) {
      var i = dates.indexOf(iso);
      if (i < 0) return null;
      return '<div class="dc-tip-d">' + C.fmtDay(C.dayMs(iso)) + "</div>" +
        '<div><span class="dc-sw" style="background:' + COLOR_OBS + '"></span>' +
        tr("ui.trends_series_observed", "Confirmed (Observed Onset)") + ": " + entry.obs[i] + "</div>" +
        '<div><span class="dc-sw" style="background:' + COLOR_IMP + '"></span>' +
        tr("ui.trends_series_imputed", "Confirmed (Imputed Onset)") + ": " + entry.imp[i] + "</div>";
    });
    return true;
  }

  global.TrendsCharts = {
    _renderCases: renderCases,
    _trends: trends,
    _xLimits: xLimits,
    _pick: pick,
    _isoSeq: isoSeq
  };
})(window);
