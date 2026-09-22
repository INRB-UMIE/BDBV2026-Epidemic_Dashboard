// Epidemiological Trends charts.
//
// Draws the four cards from PAYLOAD.trends using the shared primitives in
// charts.js. Owns NO state: engine.js keeps the scope/selection and the map,
// and calls TrendsCharts.render({scope, key}).
//
// Every constant and rule here is transcribed from the generator at
// BDBV2026-Processing_Code@main; see the spec's section 6 before changing any
// of it. Values, series, dates, gaps, stacking order, ranges and label text
// are contractual; colours and chart furniture follow the Genomic
// Epidemiology tab (genomic.js) instead of the R/ggplot SVGs -- see the
// palette block below.
(function (global) {
  "use strict";

  var C = global.DashboardCharts;

  // Palette follows the Genomic Epidemiology tab (genomic.js), not the R SVGs.
  // The genomic "Confirmed positive cases" panel plots the SAME observed/imputed
  // quantity as the cases card below, so both use DIST_OBS/DIST_IMP and cannot
  // disagree about what a colour means.
  var COLOR_OBS = "#9e2b2b";                          // genomic DIST_OBS
  var COLOR_IMP = "#587e72";                          // genomic DIST_IMP
  var COLOR_POSITIVITY = "#587e72";                   // genomic SkyGrid idiom
  var COLOR_POSITIVITY_BAND = "rgba(88,126,114,0.15)";
  var COLOR_DEATHS = "#7c1d1d";                       // genomic Ne "Exp" series
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

  // --- Card 2: cumulative deaths --------------------------------------------
  function renderDeaths(host, scope, key) {
    var d = trends(), entry = pick("deaths", scope, key), lim = xLimits(scope, key);
    if (!entry || !lim) return false;
    var dates = isoSeq(entry.start, entry.cum.length);
    var dim = size(host), svg = newSvg(host, dim.W, dim.H);
    var yMax = Math.max.apply(null, entry.cum.concat([0]));

    var fr = C.frame(svg, {
      width: dim.W, height: dim.H, pad: PAD,
      xStart: lim.start, xEnd: lim.end, yMax: yMax
    });
    C.shadeRegion(svg, fr, d.incomplete_from, COLOR_INCOMPLETE);
    C.line(svg, fr, dates, entry.cum, COLOR_DEATHS, 1.6);
    // Points ONLY on days with a death reported -- a point every day would
    // imply an event on days where none occurred.
    C.points(svg, fr, dates, entry.cum, COLOR_DEATHS, 2, function (i) {
      return entry.daily[i] > 0;
    });
    host.appendChild(svg);

    C.tooltip(host, svg, fr, function (iso) {
      var i = dates.indexOf(iso);
      if (i < 0) return null;
      return '<div class="dc-tip-d">' + C.fmtDay(C.dayMs(iso)) + "</div>" +
        "<div>" + tr("ui.trends_axis_deaths", "Cumulative Deaths") + ": " + entry.cum[i] + "</div>" +
        (entry.daily[i] > 0 ? '<div class="dc-tip-ci">+' + entry.daily[i] + "</div>" : "");
    });
    return true;
  }

  function clampPct(v) {
    if (v === null || v === undefined) return null;
    return Math.min(1, Math.max(0, v)) * 100;    // clamp then x100
  }

  // --- Card 3: rolling positivity -------------------------------------------
  function renderPositivity(host, scope, key) {
    var d = trends(), entry = pick("positivity", scope, key), lim = xLimits(scope, key);
    if (!entry || !entry.dates.length || !lim) return false;
    // SPARSE on purpose: entry.dates has real gaps and the line runs straight
    // across them. Do NOT densify this.
    var dates = entry.dates;
    var mean = entry.mean.map(clampPct);
    var lo = entry.lo.map(clampPct);
    var hi = entry.hi.map(clampPct);
    var dim = size(host), svg = newSvg(host, dim.W, dim.H);
    var finite = hi.filter(function (v) { return v !== null; });
    var yMax = Math.max.apply(null, finite.concat([0]));

    var fr = C.frame(svg, {
      width: dim.W, height: dim.H, pad: PAD,
      xStart: lim.start, xEnd: lim.end, yMax: yMax   // lower bound pinned at 0
    });
    C.shadeRegion(svg, fr, d.incomplete_from, COLOR_INCOMPLETE);
    // The band's alpha lives in COLOR_POSITIVITY_BAND itself; ciBand sets no
    // opacity of its own, matching genomic.js's Ne band.
    C.ciBand(svg, fr, dates, lo, hi, COLOR_POSITIVITY_BAND);
    C.line(svg, fr, dates, mean, COLOR_POSITIVITY, 1.6);
    C.points(svg, fr, dates, mean, COLOR_POSITIVITY, 2, null);
    host.appendChild(svg);

    C.tooltip(host, svg, fr, function (iso) {
      var i = dates.indexOf(iso);
      if (i < 0) return null;
      return '<div class="dc-tip-d">' + C.fmtDay(C.dayMs(iso)) + "</div>" +
        "<div>" + mean[i].toFixed(1) + "%" +
        ' <span class="dc-tip-ci">(' + lo[i].toFixed(1) + "–" + hi[i].toFixed(1) + "%)</span></div>";
    });
    return true;
  }

  // Normalises a place name for cross-dataset matching (zone naming drifts
  // between feeds). Mirrors engine.js's normalizeLabLocationKey.
  function normLoc(s) {
    return String(s || "")
      .normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/\([^)]*\)/g, "")
      .replace(/[^a-z0-9]+/gi, " ")
      .trim().toLowerCase();
  }

  function labsForSelection(scope, key) {
    var d = trends();
    var labs = (d && d.labs) || [];
    if (scope === "national") return labs;
    if (!key) return [];
    var field = scope === "health_zone" ? "health_zone" : "province";
    var want = normLoc(key);
    return labs.filter(function (l) { return l[field] && normLoc(l[field]) === want; });
  }

  // --- Card 4: one chart per laboratory -------------------------------------
  function renderLab(host, lab) {
    var d = trends(), lim = d && d.lab_x;
    if (!lim) return false;
    var dates = lab.dates;
    var dim = size(host), svg = newSvg(host, dim.W, dim.H);
    var maxTotal = lab.max_total;

    var fr = C.frame(svg, {
      width: dim.W, height: dim.H, pad: PAD,
      xStart: lim.start, xEnd: lim.end, yMax: maxTotal
    });
    C.shadeRegion(svg, fr, d.incomplete_from, COLOR_INCOMPLETE);
    C.stackedBars(svg, fr, dates, [{ values: lab.n, color: COLOR_SAMPLES }]);

    // Positivity scaled onto the SAME primary axis by * max_total, exactly as
    // the source does.
    var sc = function (v) {
      if (v === null || v === undefined) return null;
      return Math.min(1, Math.max(0, v)) * maxTotal;
    };
    // Same opaque-fill reasoning as renderPositivity: ciBand's own
    // fill-opacity:0.35 is the only opacity applied here.
    C.ciBand(svg, fr, dates, lab.lo.map(sc), lab.hi.map(sc), COLOR_POSITIVITY_BAND);
    C.line(svg, fr, dates, lab.mean.map(sc), COLOR_POSITIVITY, 1.6);
    C.points(svg, fr, dates, lab.mean.map(sc), COLOR_POSITIVITY, 2, null);
    C.markerLine(svg, fr, lab.earliest, COLOR_INK,
      tr("ui.trends_lab_earliest", "Earliest Sample: ") + (lab.earliest || ""));

    // Secondary axis relabelled 0-100. The source emits a 0-1 proportion under
    // a "(%)" label; this is a LABEL change only -- every mark above is placed
    // on the primary axis, so nothing moves.
    C.dualAxis(svg, fr, tr("ui.trends_axis_positivity", "Sample Positivity (%)"), 100);
    host.appendChild(svg);

    C.tooltip(host, svg, fr, function (iso) {
      var i = dates.indexOf(iso);
      if (i < 0) return null;
      return '<div class="dc-tip-d">' + C.fmtDay(C.dayMs(iso)) + "</div>" +
        "<div>" + tr("ui.trends_axis_samples", "Samples Analysed") + ": " + lab.n[i] + "</div>" +
        "<div>" + (Math.min(1, Math.max(0, lab.mean[i])) * 100).toFixed(1) + "%</div>";
    });
    return true;
  }

  global.TrendsCharts = {
    _renderCases: renderCases,
    _renderDeaths: renderDeaths,
    _renderPositivity: renderPositivity,
    _renderLab: renderLab,
    _labsForSelection: labsForSelection,
    _trends: trends,
    _xLimits: xLimits,
    _pick: pick,
    _isoSeq: isoSeq
  };
})(window);
