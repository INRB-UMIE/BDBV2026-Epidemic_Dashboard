// Surveillance and Testing tab.
//
// Draws every card on surveillance-testing.html from PAYLOAD.surveillance
// (Scripts/common/surveillance.py), using the shared SVG primitives in
// charts.js -- the same idiom as the Trends tab, so charts resize, hover and
// translate the same way.
//
// The contact tracing panels re-draw the contact tracing report's Fig 3A-D and
// Fig 2A-B from its AGGREGATE tables; their rules (>= 20 cases/week for
// percentages, >= 10 contacts per zone-month, incomplete-week shading) are
// applied in surveillance.py or noted beside the code below. The palette
// follows the report (LSHTM theme) so the two read as one product.
(function (global) {
  "use strict";

  var C = global.DashboardCharts;
  if (!C) return;

  // --- palette (report: 03_figures.py) -------------------------------------------
  var INK = "#01454f", MAIN = "#1a8c99", ALERT = "#e0703f", MUTED = "#a3b9bc";
  var GOLD = "#c9a227", RED = "#a8322d", GREEN = "#5b8c5a", PURPLE = "#7a5c99", PINK = "#d17fa8";
  var BAR = "#a3b9bc", BAR_LIGHT = "#dce4e5", SHADE = "#9c968b";
  var ZONE_PAL = [INK, MAIN, ALERT, GOLD, PURPLE, RED, GREEN, MUTED, PINK,
                  "#3d6e8f", "#8a6d3b", "#4f9a7f"];
  var STEP_COL = {
    notified: MAIN, hospitalised: PURPLE, sample: INK, lab_result: GOLD,
    last_contact: GREEN, first_followed_up: RED, contacts_registered: ALERT
  };
  var PAD = { left: 40, right: 46, top: 12, bottom: 24 };
  var PAD_NOSEC = { left: 40, right: 14, top: 12, bottom: 24 };
  var DAY = 86400000;

  // --- payload ---------------------------------------------------------------------
  var _data;
  function data() {
    if (_data !== undefined) return _data;
    var el = document.getElementById("payload");
    try { _data = (JSON.parse(el.textContent) || {}).surveillance || null; } catch (e) { _data = null; }
    return _data;
  }
  function ct() { var d = data(); return d && d.contact_tracing; }
  function testing() { var d = data(); return d && d.testing; }

  // engine.js's t() echoes the key when a string is missing; treat that as a miss.
  function tr(key, fallback) {
    if (!global.t) return fallback;
    var v = global.t(key);
    return (v && v !== key) ? v : fallback;
  }
  function trf(key, fallback, vars) {
    var s = String(tr(key, fallback));
    Object.keys(vars || {}).forEach(function (k) { s = s.split("{" + k + "}").join(String(vars[k])); });
    return s;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function lang() { return document.documentElement.lang === "fr" ? "fr-FR" : "en-GB"; }
  function num(v) { return v == null ? "–" : Number(v).toLocaleString(lang()); }
  function pct(v, d) { return v == null ? "–" : Number(v).toFixed(d == null ? 1 : d) + "%"; }
  function iso(t) { return new Date(t).toISOString().slice(0, 10); }
  function addDays(isoDate, n) { return iso(C.dayMs(isoDate) + n * DAY); }
  function fmtDay(isoDate) {
    return new Date(C.dayMs(isoDate)).toLocaleDateString(lang(), { day: "numeric", month: "short", timeZone: "UTC" });
  }
  function fmtMonth(m) {
    return new Date(C.dayMs(m + "-15")).toLocaleDateString(lang(), { month: "long", year: "numeric", timeZone: "UTC" });
  }
  function weekLabel(monday) {
    return trf("ui.surv.week_of", "Week of {date}", { date: fmtDay(monday) });
  }
  function maxOf(arr) {
    var m = 0;
    (arr || []).forEach(function (v) { if (v != null && isFinite(v) && v > m) m = v; });
    return m;
  }
  // A secondary-axis maximum with a little headroom, on a 1/2/5 grid.
  function niceMax(v, floor) {
    v = Math.max(v || 0, floor || 0);
    if (v <= 0) return 1;
    var mag = Math.pow(10, Math.floor(Math.log10(v))), r = v / mag;
    var steps = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
    for (var i = 0; i < steps.length; i++) if (r <= steps[i]) return steps[i] * mag;
    return 10 * mag;
  }

  // --- DOM helpers --------------------------------------------------------------------
  function host(id) { return document.getElementById(id); }
  function newSvg(h) {
    var W = h.clientWidth || 480, H = h.clientHeight || 220;
    h.replaceChildren();
    var svg = C.svgEl("svg", { viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none" });
    return { svg: svg, W: W, H: H };
  }
  function empty(chartId, msg) {
    var h = host(chartId);
    if (!h) return;
    h.replaceChildren();
    var p = document.createElement("p");
    p.className = "surv-empty";
    p.textContent = msg || tr("ui.surv.no_data", "No data available for this panel yet.");
    h.appendChild(p);
  }
  function caption(cardId, text) {
    var el = host(cardId + "-caption");
    if (el) el.textContent = text || "";
  }
  function legendEl(cardId) { return host(cardId + "-legend"); }

  // A legend whose items can be toggled. items: [{id, label, color, dashed, on}]
  function toggleLegend(cardId, items, onToggle) {
    var el = legendEl(cardId);
    if (!el) return;
    el.replaceChildren();
    items.forEach(function (it) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "surv-chip" + (it.on === false ? " off" : "");
      b.setAttribute("aria-pressed", it.on === false ? "false" : "true");
      var sw = document.createElement("span");
      sw.className = "surv-sw" + (it.dashed ? " dashed" : "") + (it.bar ? " bar" : "");
      sw.style.setProperty("--sw", it.color);
      b.appendChild(sw);
      b.appendChild(document.createTextNode(it.label));
      if (onToggle) {
        b.addEventListener("click", function () { onToggle(it.id); });
      } else {
        b.disabled = true;
      }
      el.appendChild(b);
    });
  }
  function staticLegend(cardId, items) { toggleLegend(cardId, items, null); }

  // Map a hovered day onto the week (Monday ISO) containing it.
  function weekIndex(weeks, day) {
    for (var i = 0; i < weeks.length; i++) {
      if (day >= weeks[i] && day < addDays(weeks[i], 7)) return i;
    }
    return -1;
  }
  function mid(weeks) { return weeks.map(function (w) { return addDays(w, 3); }); }

  // Weekly bars + optional percentage line on a right-hand axis.
  //   o.weeks (Mondays), o.bars [{values, color, colorAt}], o.line {values, color}
  //   o.lineMax (secondary max), o.shadeFrom (ISO), o.tip(i) -> html, o.secName
  function weeklyChart(chartId, o) {
    var h = host(chartId);
    if (!h || !o.weeks.length) return false;
    var s = newSvg(h);
    var totals = o.weeks.map(function (_, i) {
      return o.bars.reduce(function (a, b) { return a + (b.values[i] || 0); }, 0);
    });
    var yMax = maxOf(totals);
    var fr = C.frame(s.svg, {
      width: s.W, height: s.H, pad: o.line ? PAD : PAD_NOSEC,
      xStart: o.weeks[0], xEnd: addDays(o.weeks[o.weeks.length - 1], 6), yMax: yMax
    });
    if (o.shadeFrom) C.shadeRegion(s.svg, fr, o.shadeFrom, SHADE);
    C.stackedBars(s.svg, fr, mid(o.weeks), o.bars, { barDays: 7 });
    if (o.line) {
      var secMax = o.lineMax || niceMax(maxOf(o.line.values));
      var scaled = o.line.values.map(function (v) { return v == null ? null : (v / secMax) * fr.yMax; });
      C.line(s.svg, fr, mid(o.weeks), scaled, o.line.color, 1.8);
      C.points(s.svg, fr, mid(o.weeks), scaled, o.line.color, 2.4, null);
      C.dualAxis(s.svg, fr, o.secName || "", secMax);
    }
    h.appendChild(s.svg);
    C.tooltip(h, s.svg, fr, function (day) {
      var i = weekIndex(o.weeks, day);
      return i < 0 ? null : o.tip(i);
    });
    return true;
  }

  // Weekly lines (optionally with IQR bands) on one axis.
  //   series: [{id, values, lo, hi, color, dashed}]
  function lineChart(chartId, o) {
    var h = host(chartId);
    if (!h || !o.xs.length) return false;
    var s = newSvg(h);
    var yMax = o.yMax || 0;
    if (!yMax) {
      o.series.forEach(function (sr) { yMax = Math.max(yMax, maxOf(sr.hi || sr.values)); });
    }
    var fr = C.frame(s.svg, {
      width: s.W, height: s.H, pad: PAD_NOSEC, xStart: o.xStart, xEnd: o.xEnd, yMax: yMax,
      fmtY: o.fmtY, xTicks: o.xTicks
    });
    if (o.shadeFrom) C.shadeRegion(s.svg, fr, o.shadeFrom, SHADE);
    o.series.forEach(function (sr) {
      var xs = sr.xs || o.xs;
      if (sr.lo && sr.hi) C.ciBand(s.svg, fr, xs, sr.lo, sr.hi, sr.band || "rgba(0,0,0,0.08)");
    });
    o.series.forEach(function (sr) {
      var xs = sr.xs || o.xs;
      // Gaps (null) break the line, unlike C.line, which joins across them:
      // a zone-month that is omitted must not be bridged by a straight line.
      var path = "", pen = false;
      xs.forEach(function (x, i) {
        var v = sr.values[i];
        if (v == null) { pen = false; return; }
        path += (pen ? "L" : "M") + fr.xToPx(C.dayMs(x)) + " " + fr.yToPx(v);
        pen = true;
      });
      if (!path) return;
      var g = C.svgEl("g", { "clip-path": "url(#" + fr.clipId + ")" });
      g.appendChild(C.svgEl("path", {
        d: path,
        fill: "none", stroke: sr.color, "stroke-width": sr.width || 1.6,
        "stroke-dasharray": sr.dashed ? "2,3" : "none", "stroke-linecap": "round"
      }));
      s.svg.appendChild(g);
      C.points(s.svg, fr, xs, sr.values, sr.color, sr.dashed ? 0 : 2.4, null);
    });
    h.appendChild(s.svg);
    C.tooltip(h, s.svg, fr, function (day) { return o.tip(day); });
    return true;
  }

  // --- headline + intro ------------------------------------------------------------
  function renderHeadline() {
    var el = host("surv-headline"), asof = host("surv-asof");
    var c = ct(), te = testing();
    if (asof) {
      var parts = [];
      if (c) parts.push(trf("ui.surv.asof_ct", "Contact tracing data cut: {date}", { date: fmtDay(c.data_cut) }));
      if (te) parts.push(trf("ui.surv.asof_testing", "Testing data: line list of {date}", { date: fmtDay(te.asof) }));
      asof.textContent = parts.join(" · ");
    }
    if (!el) return;
    el.replaceChildren();
    var h = c && c.headline;
    var tiles = [];
    if (h) {
      tiles.push([num(h.cases), tr("ui.surv.tile_cases", "confirmed cases")]);
      tiles.push([pct(100 * h.prev_contact_n / h.cases),
        trf("ui.surv.tile_known", "already known as contacts when notified ({n})", { n: num(h.prev_contact_n) })]);
      if (h.any_time_n != null) {
        tiles.push([pct(100 * h.any_time_n / h.cases),
          trf("ui.surv.tile_anytime", "on a contact list at any time ({n})", { n: num(h.any_time_n) })]);
      }
      tiles.push([num(h.contacts), trf("ui.surv.tile_contacts", "contacts listed for {n} source cases", { n: num(h.source_cases) })]);
      if (h.fu_contacts) {
        tiles.push([pct(100 * h.fu_complete / h.fu_contacts, 0),
          trf("ui.surv.tile_fu", "of {n} contacts fully followed up to day 21", { n: num(h.fu_contacts) })]);
      }
    }
    if (te && te.national) {
      var n = te.national;
      tiles.push([num(n.total_n), trf("ui.surv.tile_tests", "samples tested ({p} positive)",
        { p: pct(n.total_n ? 100 * n.total_pos / n.total_n : null) })]);
    }
    tiles.forEach(function (t) {
      var d = document.createElement("div");
      d.className = "surv-tile";
      d.innerHTML = '<span class="surv-tile-v">' + esc(t[0]) + '</span><span class="surv-tile-l">' + esc(t[1]) + "</span>";
      el.appendChild(d);
    });
    el.hidden = !tiles.length;
  }

  // --- Fig 3A / 3B: weekly CT coverage --------------------------------------------
  var ctScope = "national";
  function ctWeekly() {
    var c = ct();
    if (!c) return null;
    return ctScope === "national" ? c.weekly : (c.weekly_by_zone || {})[ctScope] || null;
  }
  function ctPlaceLabel() {
    return ctScope === "national" ? tr("ui.trends_scope_national", "National") : ctScope;
  }
  function fillCtScope() {
    var sel = host("surv-ct-scope"), c = ct();
    if (!sel || !c) return;
    var opts = [["national", tr("ui.trends_scope_national", "National")]];
    Object.keys(c.weekly_by_zone || {}).forEach(function (z) { opts.push([z, z]); });
    sel.innerHTML = opts.map(function (o) {
      return '<option value="' + esc(o[0]) + '"' + (o[0] === ctScope ? " selected" : "") + ">" + esc(o[1]) + "</option>";
    }).join("");
    sel.title = tr("ui.surv.ct_scope_title", "National, or one of the health zones with the most cases");
  }

  function renderKnown() {
    var c = ct(), w = ctWeekly();
    if (!w || !w.weeks.length) { empty("surv-ct-known-chart"); caption("surv-ct-known", ""); return; }
    var incompleteFrom = addDays(c.meta.last_full_week, 7);
    var ok = weeklyChart("surv-ct-known-chart", {
      weeks: w.weeks,
      bars: [{ values: w.new_cases, color: BAR,
               colorAt: function (i) { return w.weeks[i] >= incompleteFrom ? BAR_LIGHT : BAR; } }],
      line: { values: w.pct_prev_contact, color: ALERT },
      lineMax: niceMax(maxOf(w.pct_prev_contact), 1),
      secName: tr("ui.surv.axis_pct_known", "% known contact"),
      shadeFrom: incompleteFrom,
      tip: function (i) {
        return '<div class="dc-tip-d">' + esc(weekLabel(w.weeks[i])) + "</div>" +
          '<div><span class="dc-sw" style="background:' + BAR + '"></span>' +
          esc(tr("ui.surv.new_cases", "New cases")) + ": " + num(w.new_cases[i]) + "</div>" +
          '<div><span class="dc-sw" style="background:' + ALERT + '"></span>' +
          esc(tr("ui.surv.known_before", "Known contact before notification")) + ": " + num(w.prev_contact[i]) +
          (w.pct_prev_contact[i] != null ? " (" + pct(w.pct_prev_contact[i]) + ")" : "") + "</div>";
      }
    });
    staticLegend("surv-ct-known", [
      { label: tr("ui.surv.legend_new_cases", "New cases (week of notification)"), color: BAR, bar: true },
      { label: tr("ui.surv.legend_pct_known", "% known contact before notification (right axis)"), color: ALERT }
    ]);
    caption("surv-ct-known", ok ? trf("ui.surv.known_caption",
      "{place}. Percentages only for weeks with at least {min} cases. Shaded: incomplete weeks (after {date}).",
      { place: ctPlaceLabel(), min: c.meta.min_cases_per_week_lines || 20, date: fmtDay(addDays(c.meta.last_full_week, 6)) }) : "");
  }

  function renderSource() {
    var c = ct(), w = ctWeekly();
    if (!w || !w.weeks.length) { empty("surv-ct-source-chart"); caption("surv-ct-source", ""); return; }
    // Report Fig 3B shades from LAST_FULL_WEEK - 10 days: becoming a source case
    // needs contacts listed, which lags notification.
    var shadeFrom = addDays(c.meta.last_full_week, -10);
    var xs = mid(w.weeks);
    lineChart("surv-ct-source-chart", {
      xs: xs, xStart: w.weeks[0], xEnd: addDays(w.weeks[w.weeks.length - 1], 6),
      yMax: niceMax(maxOf(w.pct_became_source), 5),
      shadeFrom: shadeFrom,
      series: [{ values: w.pct_became_source, color: INK }],
      tip: function (day) {
        var i = weekIndex(w.weeks, day);
        if (i < 0) return null;
        return '<div class="dc-tip-d">' + esc(weekLabel(w.weeks[i])) + "</div><div>" +
          (w.pct_became_source[i] != null ? pct(w.pct_became_source[i]) + " · " : "") +
          num(w.became_source[i]) + " / " + num(w.new_cases[i]) + "</div>";
      }
    });
    legendEl("surv-ct-source").replaceChildren();
    caption("surv-ct-source", trf("ui.surv.source_caption",
      "{place}. % of new cases with at least one listed contact. Weeks with at least {min} cases; shaded: incomplete.",
      { place: ctPlaceLabel(), min: c.meta.min_cases_per_week_lines || 20 }));
  }

  // --- Fig 3C: follow-up visits ------------------------------------------------------
  function renderVisits() {
    var c = ct(), f = c && c.followup;
    if (!f || !f.weeks.length) { empty("surv-fu-visits-chart"); caption("surv-fu-visits", ""); return; }
    var incompleteFrom = addDays(c.meta.last_full_week, 7);
    weeklyChart("surv-fu-visits-chart", {
      weeks: f.weeks,
      bars: [{ values: f.visits, color: "#bfe0e3",
               colorAt: function (i) { return f.weeks[i] >= incompleteFrom ? LIGHT_TEAL : "#bfe0e3"; } }],
      line: { values: f.pct_result, color: ALERT }, lineMax: 100,
      secName: tr("ui.surv.axis_pct_result", "% with result"),
      shadeFrom: incompleteFrom,
      tip: function (i) {
        return '<div class="dc-tip-d">' + esc(weekLabel(f.weeks[i])) + "</div>" +
          "<div>" + esc(tr("ui.surv.visits", "Follow-up visits")) + ": " + num(f.visits[i]) + "</div>" +
          "<div>" + esc(tr("ui.surv.with_result", "With a result")) + ": " + pct(f.pct_result[i]) + "</div>";
      }
    });
    staticLegend("surv-fu-visits", [
      { label: tr("ui.surv.legend_visits", "Follow-up visits"), color: "#bfe0e3", bar: true },
      { label: tr("ui.surv.legend_pct_result", "% with a result recorded (right axis)"), color: ALERT }
    ]);
    caption("surv-fu-visits", tr("ui.surv.visits_caption", "National. Week of the follow-up visit. Shaded: incomplete weeks."));
  }
  var LIGHT_TEAL = "#e3f0f1";

  // --- Fig 3D: follow-up completeness by zone ------------------------------------------
  var fuShown = null;      // zone names currently drawn
  function fuColor(zone) {
    var f = ct().fu21;
    var all = (f.default_zones || []).concat(Object.keys(f.zones).filter(function (z) {
      return (f.default_zones || []).indexOf(z) < 0;
    }).sort());
    return ZONE_PAL[all.indexOf(zone) % ZONE_PAL.length];
  }
  function fillFuAdd() {
    var sel = host("surv-fu21-add"), c = ct(), f = c && c.fu21;
    if (!sel || !f) return;
    var rest = Object.keys(f.zones).filter(function (z) { return fuShown.indexOf(z) < 0; })
      .sort(function (a, b) { return f.zones[b].total - f.zones[a].total; });
    sel.innerHTML = '<option value="">' + esc(tr("ui.surv.add_zone", "Add a health zone…")) + "</option>" +
      rest.map(function (z) { return '<option value="' + esc(z) + '">' + esc(z) + " (" + num(f.zones[z].total) + ")</option>"; }).join("");
    sel.disabled = !rest.length;
  }
  function renderFu21() {
    var c = ct(), f = c && c.fu21;
    if (!f || !f.months.length) { empty("surv-fu21-chart"); caption("surv-fu21", ""); return; }
    if (!fuShown) fuShown = (f.default_zones || []).slice();
    var xs = f.months.map(function (m) { return m + "-15"; });
    var pctOf = function (k, n) { return k == null || !n ? null : Math.round(1000 * k / n) / 10; };
    var series = fuShown.filter(function (z) { return f.zones[z]; }).map(function (z) {
      var zz = f.zones[z];
      return { id: z, color: fuColor(z), values: zz.n.map(function (n, i) { return pctOf(zz.k[i], n); }) };
    });
    var nat = f.national ? f.national.n.map(function (n, i) { return pctOf(f.national.k[i], n); }) : null;
    if (nat) series.push({ id: "__all", color: INK, values: nat, dashed: true, width: 2.6 });
    var last = f.months[f.months.length - 1];
    lineChart("surv-fu21-chart", {
      xs: xs, xStart: f.months[0] + "-01", xEnd: addDays(last + "-01", 30), yMax: 100,
      series: series,
      fmtY: function (v) { return v + "%"; },
      xTicks: f.months.map(function (m) {
        return { iso: m + "-15", label: new Date(C.dayMs(m + "-15")).toLocaleDateString(lang(), { month: "short", timeZone: "UTC" }) };
      }),
      tip: function (day) {
        var m = day.slice(0, 7), i = f.months.indexOf(m);
        if (i < 0) return null;
        var rows = [];
        if (nat) rows.push([tr("ui.surv.all_zones", "All zones"), nat[i], f.national.k[i], f.national.n[i], INK]);
        fuShown.forEach(function (z) {
          var zz = f.zones[z];
          if (zz && zz.n[i] != null) rows.push([z, pctOf(zz.k[i], zz.n[i]), zz.k[i], zz.n[i], fuColor(z)]);
        });
        rows.sort(function (a, b) { return (b[1] || 0) - (a[1] || 0); });
        return '<div class="dc-tip-d">' + esc(fmtMonth(m)) + "</div>" + rows.map(function (r) {
          return '<div><span class="dc-sw" style="background:' + r[4] + '"></span>' + esc(r[0]) + ": " +
            pct(r[1], 0) + ' <span class="dc-tip-ci">(' + num(r[2]) + "/" + num(r[3]) + ")</span></div>";
        }).join("");
      }
    });
    var items = [{ id: "__all", label: tr("ui.surv.all_zones", "All zones"), color: INK, dashed: true }];
    fuShown.forEach(function (z) { items.push({ id: z, label: z, color: fuColor(z) }); });
    toggleLegend("surv-fu21", items, function (id) {
      if (id === "__all") return;
      fuShown = fuShown.filter(function (z) { return z !== id; });
      renderFu21();
      fillFuAdd();
    });
    var h = c.headline;
    caption("surv-fu21", trf("ui.surv.fu21_caption",
      "Overall {p} of {n} contacts. Month of first follow-up. Zone-months with fewer than {min} contacts not shown.",
      { p: h && h.fu_contacts ? pct(100 * h.fu_complete / h.fu_contacts, 0) : "–",
        n: num(h && h.fu_contacts), min: f.min_contacts }));
  }

  // --- Fig 2A: patient journey (horizontal) ------------------------------------------
  function renderJourney() {
    var c = ct(), steps = c && c.journey;
    var h = host("surv-journey-chart");
    if (!h) return;
    if (!steps || !steps.length) { empty("surv-journey-chart"); caption("surv-journey", ""); return; }
    var s = newSvg(h), svg = s.svg;
    // Narrow: labels sit ABOVE each bar instead of in a left gutter, which
    // would leave too little room for both the labels and the plot.
    var narrow = s.W < 520;
    var left = narrow ? 14 : 170, right = s.W - (narrow ? 12 : 150), top = narrow ? 14 : 8, bottom = s.H - 26;
    var xMax = Math.max(20, Math.ceil(maxOf(steps.map(function (st) { return st.q3; })) / 5) * 5 + 5);
    var xMin = Math.min(-1, Math.floor(Math.min.apply(null, steps.map(function (st) { return st.q1; }))));
    var xp = function (v) { return left + (v - xMin) / (xMax - xMin) * (right - left); };
    var rowH = (bottom - top) / steps.length;
    // grid + axis
    for (var v = 0; v <= xMax; v += 5) {
      svg.appendChild(C.svgEl("line", { x1: xp(v), y1: top, x2: xp(v), y2: bottom, stroke: "#eee" }));
      var tl = C.svgEl("text", { x: xp(v), y: bottom + 12, "font-size": 9, fill: "#9c968b", "text-anchor": "middle" });
      tl.textContent = String(v);
      svg.appendChild(tl);
    }
    svg.appendChild(C.svgEl("line", { x1: xp(0), y1: top, x2: xp(0), y2: bottom, stroke: INK, "stroke-width": 1 }));
    var xl = C.svgEl("text", { x: (left + right) / 2, y: s.H - 2, "font-size": 9, fill: "#9c968b", "text-anchor": "middle" });
    xl.textContent = tr("ui.surv.days_since_onset", "Days since symptom onset");
    svg.appendChild(xl);
    var tip = document.createElement("div");
    tip.className = "dc-tip";
    tip.style.display = "none";
    steps.forEach(function (st, i) {
      var y = top + rowH * (i + 0.5), col = STEP_COL[st.step] || INK;
      var label = tr("ui.surv.step_" + st.step, st.label);
      var g = C.svgEl("g", { class: "surv-journey-row" });
      g.appendChild(C.svgEl("rect", { x: 0, y: y - rowH / 2, width: s.W, height: rowH, fill: "transparent" }));
      g.appendChild(C.svgEl("rect", {
        x: xp(st.q1), y: y - 6, width: Math.max(2, xp(st.q3) - xp(st.q1)), height: 12, fill: col, "fill-opacity": 0.3
      }));
      g.appendChild(C.svgEl("circle", { cx: xp(st.median), cy: y, r: 5, fill: col, stroke: "#fff", "stroke-width": 1 }));
      var d = 4, mx = xp(st.mean);
      g.appendChild(C.svgEl("path", {
        d: "M" + mx + " " + (y - d) + "L" + (mx + d) + " " + y + "L" + mx + " " + (y + d) + "L" + (mx - d) + " " + y + "Z",
        fill: "#fff", stroke: col, "stroke-width": 1.5
      }));
      var lt = narrow
        ? C.svgEl("text", { x: left, y: y - 9, "font-size": 10, "font-weight": 700, fill: col, "text-anchor": "start" })
        : C.svgEl("text", { x: left - 8, y: y + 3, "font-size": 11, "font-weight": 700, fill: col, "text-anchor": "end" });
      lt.textContent = label + (st.source_only ? " *" : "") + (narrow
        ? "  ·  " + st.median + " (" + st.q1 + "–" + st.q3 + ")"
        : "");
      g.appendChild(lt);
      if (!narrow) {
        var rt = C.svgEl("text", { x: right + 8, y: y + 3, "font-size": 9.5, fill: "#5c574f" });
        rt.textContent = trf("ui.surv.journey_label", "median {m} (IQR {q1}–{q3})",
          { m: st.median, q1: st.q1, q3: st.q3 });
        g.appendChild(rt);
      }
      g.addEventListener("mousemove", function (ev) {
        var r = svg.getBoundingClientRect();
        tip.innerHTML = '<div class="dc-tip-d">' + esc(label) + "</div>" +
          "<div>" + esc(tr("ui.surv.median", "Median")) + ": " + st.median + " · IQR " + st.q1 + "–" + st.q3 + "</div>" +
          "<div>" + esc(tr("ui.surv.mean", "Mean")) + ": " + Number(st.mean).toFixed(1) + " · n = " + num(st.n) + "</div>";
        tip.style.display = "";
        tip.style.left = Math.min(ev.clientX - r.left + 10, r.width - 190) + "px";
        tip.style.top = (ev.clientY - r.top + 10) + "px";
      });
      g.addEventListener("mouseleave", function () { tip.style.display = "none"; });
      svg.appendChild(g);
    });
    h.appendChild(svg);
    h.appendChild(tip);
    var lg = legendEl("surv-journey");
    if (lg) {
      lg.innerHTML = '<span class="surv-key">● ' + esc(tr("ui.surv.median", "Median")) + "</span>" +
        '<span class="surv-key">◇ ' + esc(tr("ui.surv.mean", "Mean")) + "</span>" +
        '<span class="surv-key"><span class="surv-sw bar" style="--sw:rgba(1,69,79,0.3)"></span>' +
        esc(tr("ui.surv.iqr", "Interquartile range")) + "</span>";
    }
    caption("surv-journey", trf("ui.surv.journey_caption",
      "Confirmed cases with onset on or before {date}. * Source cases only. Delays outside 0–60 days excluded (−60 to 60 for contact steps).",
      { date: fmtDay(c.meta.onset_end) }));
  }

  // --- Fig 2B: delays by week of onset -----------------------------------------------
  var delayHidden = {};
  function renderDelays() {
    var c = ct(), dw = c && c.delays_weekly;
    var order = ["notified", "hospitalised", "lab_result", "contacts_registered"].filter(function (k) { return dw && dw[k]; });
    if (!order.length) { empty("surv-delays-chart"); caption("surv-delays", ""); return; }
    var weeks = {};
    order.forEach(function (k) { dw[k].weeks.forEach(function (w) { weeks[w] = true; }); });
    var wk = Object.keys(weeks).sort();
    var series = order.filter(function (k) { return !delayHidden[k]; }).map(function (k) {
      var col = STEP_COL[k];
      return { id: k, xs: mid(dw[k].weeks), values: dw[k].median, lo: dw[k].q1, hi: dw[k].q3,
               color: col, band: hexA(col, 0.15) };
    });
    lineChart("surv-delays-chart", {
      xs: mid(wk), xStart: wk[0], xEnd: addDays(wk[wk.length - 1], 6),
      yMax: Math.max(10, maxOf([].concat.apply([], series.map(function (s) { return s.hi; })))),
      series: series,
      tip: function (day) {
        var w = wk[weekIndex(wk, day)];
        if (!w) return null;
        var rows = order.filter(function (k) { return !delayHidden[k]; }).map(function (k) {
          var i = dw[k].weeks.indexOf(w);
          if (i < 0) return "";
          return '<div><span class="dc-sw" style="background:' + STEP_COL[k] + '"></span>' +
            esc(tr("ui.surv.delay_" + k, k)) + ": " + dw[k].median[i] +
            ' <span class="dc-tip-ci">(IQR ' + dw[k].q1[i] + "–" + dw[k].q3[i] + ", n=" + num(dw[k].n[i]) + ")</span></div>";
        }).join("");
        return rows ? '<div class="dc-tip-d">' + esc(weekLabel(w)) + "</div>" + rows : null;
      }
    });
    toggleLegend("surv-delays", order.map(function (k) {
      return { id: k, label: tr("ui.surv.delay_" + k, k), color: STEP_COL[k], on: !delayHidden[k] };
    }), function (id) { delayHidden[id] = !delayHidden[id]; renderDelays(); });
    caption("surv-delays", trf("ui.surv.delays_caption",
      "Days from onset (median, IQR). Onset weeks up to {date}; weeks with at least {min} cases.",
      { date: fmtDay(addDays(c.meta.onset_week_end, 6)), min: c.meta.min_cases_per_week_delays || 5 }));
  }
  function hexA(hex, a) {
    var n = parseInt(hex.slice(1), 16);
    return "rgba(" + (n >> 16 & 255) + "," + (n >> 8 & 255) + "," + (n & 255) + "," + a + ")";
  }

  // --- Testing: samples + positivity ---------------------------------------------------
  var testScope = "national";
  function testEntry() {
    var te = testing();
    if (!te) return null;
    if (testScope === "national") return te.national;
    var p = testScope.split(":"), kind = p[0], name = p.slice(1).join(":");
    return kind === "province" ? (te.provinces || {})[name] : (te.health_zones || {})[name];
  }
  function testPlace() {
    if (testScope === "national") return tr("ui.trends_scope_national", "National");
    return testScope.split(":").slice(1).join(":");
  }
  function fillTestScope() {
    var sel = host("surv-test-scope"), te = testing();
    if (!sel || !te) return;
    var byTotal = function (obj) {
      return Object.keys(obj || {}).sort(function (a, b) { return obj[b].total_n - obj[a].total_n; });
    };
    var html = '<option value="national">' + esc(tr("ui.trends_scope_national", "National")) + "</option>";
    html += '<optgroup label="' + esc(tr("ui.trends_scope_province", "Provincial")) + '">' +
      byTotal(te.provinces).map(function (p) { return '<option value="province:' + esc(p) + '">' + esc(p) + "</option>"; }).join("") + "</optgroup>";
    html += '<optgroup label="' + esc(tr("ui.trends_scope_health_zone", "Health Zone")) + '">' +
      byTotal(te.health_zones).map(function (z) { return '<option value="zone:' + esc(z) + '">' + esc(z) + "</option>"; }).join("") + "</optgroup>";
    sel.innerHTML = html;
    sel.value = testScope;
  }
  function renderTests() {
    var te = testing(), e = testEntry();
    var h = host("surv-tests-chart");
    if (!h) return;
    if (!e || !e.dates.length) { empty("surv-tests-chart"); caption("surv-tests", ""); return; }
    var s = newSvg(h);
    var neg = e.n.map(function (n, i) { return Math.max(0, n - e.pos[i]); });
    var fr = C.frame(s.svg, { width: s.W, height: s.H, pad: PAD,
      xStart: e.dates[0], xEnd: e.dates[e.dates.length - 1], yMax: maxOf(e.n) });
    C.shadeRegion(s.svg, fr, te.incomplete_from, SHADE);
    C.stackedBars(s.svg, fr, e.dates, [{ values: e.pos, color: INK }, { values: neg, color: BAR }]);
    var sc = function (v) { return v == null ? null : Math.min(1, Math.max(0, v)) * fr.yMax; };
    C.ciBand(s.svg, fr, e.dates, e.lo.map(sc), e.hi.map(sc), hexA(ALERT, 0.15));
    C.line(s.svg, fr, e.dates, e.mean.map(sc), ALERT, 1.6);
    C.dualAxis(s.svg, fr, tr("ui.surv.axis_positivity", "Positivity (%)"), 100);
    h.appendChild(s.svg);
    C.tooltip(h, s.svg, fr, function (day) {
      var i = e.dates.indexOf(day);
      if (i < 0) return null;
      return '<div class="dc-tip-d">' + esc(fmtDay(day)) + "</div>" +
        '<div><span class="dc-sw" style="background:' + INK + '"></span>' + esc(tr("ui.surv.positive", "Positive")) + ": " + num(e.pos[i]) + "</div>" +
        '<div><span class="dc-sw" style="background:' + BAR + '"></span>' + esc(tr("ui.surv.other_results", "Other results")) + ": " + num(neg[i]) + "</div>" +
        (e.mean[i] != null ? "<div>" + esc(tr("ui.surv.positivity_5d", "5-day positivity")) + ": " + pct(100 * e.mean[i]) +
          ' <span class="dc-tip-ci">(' + pct(100 * e.lo[i]) + "–" + pct(100 * e.hi[i]) + ")</span></div>" : "");
    });
    staticLegend("surv-tests", [
      { label: tr("ui.surv.positive", "Positive"), color: INK, bar: true },
      { label: tr("ui.surv.other_results", "Other results"), color: BAR, bar: true },
      { label: tr("ui.surv.legend_positivity", "5-day positivity, 95% CI (right axis)"), color: ALERT }
    ]);
    caption("surv-tests", trf("ui.surv.tests_caption",
      "{place}: {n} samples, {p} positive. By date of symptom onset. Shaded: last 7 days, reporting likely incomplete.",
      { place: testPlace(), n: num(e.total_n), p: pct(e.total_n ? 100 * e.total_pos / e.total_n : null) }));
  }

  // --- Labs: weekly throughput + table ---------------------------------------------------
  var LAB_TOP = 6, labHidden = {};
  function mondayOf(isoDate) {
    var t = C.dayMs(isoDate), dow = (new Date(t).getUTCDay() + 6) % 7;
    return iso(t - dow * DAY);
  }
  function renderLabs() {
    var te = testing(), labs = (te && te.labs) || [];
    if (!labs.length) { empty("surv-labs-chart"); caption("surv-labs", ""); renderLabTable([]); return; }
    var groups = labs.slice(0, LAB_TOP).map(function (l, i) {
      return { id: l.code, label: l.label, color: ZONE_PAL[i], labs: [l] };
    });
    if (labs.length > LAB_TOP) {
      groups.push({ id: "__other", label: tr("ui.surv.other_labs", "Other laboratories"), color: "#cfc9bd", labs: labs.slice(LAB_TOP) });
    }
    var weekSet = {};
    var byGroup = groups.map(function (g) {
      var m = {};
      g.labs.forEach(function (l) {
        l.dates.forEach(function (d, i) { var w = mondayOf(d); weekSet[w] = true; m[w] = (m[w] || 0) + l.n[i]; });
      });
      return m;
    });
    var weeks = Object.keys(weekSet).sort();
    // Fill gaps so every week between first and last has a slot.
    var all = [], w = weeks[0];
    while (w <= weeks[weeks.length - 1]) { all.push(w); w = addDays(w, 7); }
    var shown = groups.map(function (g, gi) { return { g: g, vals: all.map(function (wk) { return byGroup[gi][wk] || 0; }) }; })
      .filter(function (x) { return !labHidden[x.g.id]; });
    weeklyChart("surv-labs-chart", {
      weeks: all,
      bars: shown.map(function (x) { return { values: x.vals, color: x.g.color }; }),
      shadeFrom: mondayOf(te.incomplete_from),
      tip: function (i) {
        var rows = shown.filter(function (x) { return x.vals[i] > 0; }).map(function (x) {
          return '<div><span class="dc-sw" style="background:' + x.g.color + '"></span>' + esc(x.g.label) + ": " + num(x.vals[i]) + "</div>";
        });
        var tot = shown.reduce(function (a, x) { return a + x.vals[i]; }, 0);
        return '<div class="dc-tip-d">' + esc(weekLabel(all[i])) + " · " + num(tot) + "</div>" + rows.join("");
      }
    });
    toggleLegend("surv-labs", groups.map(function (g) {
      return { id: g.id, label: g.label, color: g.color, bar: true, on: !labHidden[g.id] };
    }), function (id) { labHidden[id] = !labHidden[id]; renderLabs(); });
    caption("surv-labs", tr("ui.surv.labs_caption", "By week of analysis. Shaded: most recent week, reporting likely incomplete."));
    renderLabTable(labs);
  }
  function renderLabTable(labs) {
    var el = host("surv-labs-table");
    if (!el) return;
    if (!labs.length) { el.replaceChildren(); return; }
    var head = [tr("ui.surv.col_lab", "Laboratory"), tr("ui.surv.col_location", "Location"),
      tr("ui.surv.col_samples", "Samples"), tr("ui.surv.col_positive", "Positive"),
      tr("ui.surv.col_positivity", "Positivity"), tr("ui.surv.col_first", "First analysis"),
      tr("ui.surv.col_last", "Latest analysis")];
    el.innerHTML = '<table class="surv-table"><thead><tr>' + head.map(function (x, i) {
      return "<th" + (i >= 2 && i <= 4 ? ' class="num"' : "") + ">" + esc(x) + "</th>";
    }).join("") + "</tr></thead><tbody>" + labs.map(function (l) {
      var loc = [l.health_zone, l.province].filter(Boolean).join(", ");
      return "<tr><td>" + esc(l.label) + (l.label !== l.code ? ' <span class="surv-muted">' + esc(l.code) + "</span>" : "") +
        "</td><td>" + esc(loc || "–") + '</td><td class="num">' + num(l.total_n) + '</td><td class="num">' + num(l.total_pos) +
        '</td><td class="num">' + pct(l.total_n ? 100 * l.total_pos / l.total_n : null) +
        "</td><td>" + esc(l.first ? fmtDay(l.first) : "–") + "</td><td>" + esc(l.last ? fmtDay(l.last) : "–") + "</td></tr>";
    }).join("") + "</tbody></table>";
  }

  // --- Province indicators table ----------------------------------------------------------
  function renderProvinceTable() {
    var el = host("surv-province-table"), c = ct();
    if (!el) return;
    var rows = (c && c.provinces) || [];
    if (!rows.length) { el.innerHTML = '<p class="surv-empty">' + esc(tr("ui.surv.no_data", "No data available for this panel yet.")) + "</p>"; return; }
    var all = rows.slice().sort(function (a, b) { return b.cases - a.cases; });
    if (c.national) all.push(Object.assign({}, c.national, { area: tr("ui.surv.total", "All provinces"), _total: true }));
    var head = [tr("ui.surv.col_province", "Province"), tr("ui.surv.col_cases", "Cases"),
      tr("ui.surv.col_pct_source", "% cases with contacts listed"), tr("ui.surv.col_pct_known", "% known contact before notification"),
      tr("ui.surv.col_sources", "Source cases"), tr("ui.surv.col_contacts", "Contacts"),
      tr("ui.surv.col_med_contacts", "Median contacts per source"), tr("ui.surv.col_fu", "% contacts fully followed up (95% CI)")];
    el.innerHTML = '<table class="surv-table"><thead><tr>' + head.map(function (x, i) {
      return "<th" + (i ? ' class="num"' : "") + ">" + esc(x) + "</th>";
    }).join("") + "</tr></thead><tbody>" + all.map(function (r) {
      var fu = r.pct_fu_complete == null ? "–" : pct(r.pct_fu_complete, 0) +
        (r.fu_lo != null ? ' <span class="surv-muted">(' + Math.round(r.fu_lo) + "–" + Math.round(r.fu_hi) + ")</span>" : "");
      return "<tr" + (r._total ? ' class="surv-total"' : "") + "><td>" + esc(r.area) + '</td><td class="num">' + num(r.cases) +
        '</td><td class="num">' + pct(r.pct_cases_source) + '</td><td class="num">' + pct(r.pct_cases_prev_contact) +
        '</td><td class="num">' + num(r.source_cases) + '</td><td class="num">' + num(r.contacts) +
        '</td><td class="num">' + (r.med_contacts == null ? "–" : num(r.med_contacts)) + '</td><td class="num">' + fu + "</td></tr>";
    }).join("") + "</tbody></table>";
    var cap = host("surv-province-caption");
    if (cap) cap.textContent = trf("ui.surv.province_caption",
      "Contact tracing data cut {date}. Follow-up: % of contacts with a result up to day 21 (Wilson 95% CI).", { date: fmtDay(c.data_cut) });
  }

  // --- orchestration -------------------------------------------------------------------------
  function renderAll() {
    if (!data()) {
      ["surv-ct-known", "surv-ct-source", "surv-fu-visits", "surv-fu21", "surv-journey", "surv-delays",
       "surv-tests", "surv-labs"].forEach(function (id) { empty(id + "-chart"); });
      renderProvinceTable();
      return;
    }
    renderHeadline();
    fillCtScope();
    renderKnown();
    renderSource();
    renderVisits();
    renderFu21();
    if (ct() && ct().fu21) fillFuAdd();
    renderJourney();
    renderDelays();
    fillTestScope();
    renderTests();
    renderLabs();
    renderProvinceTable();
  }

  function wire() {
    var sel = host("surv-ct-scope");
    if (sel) sel.addEventListener("change", function () { ctScope = sel.value || "national"; renderKnown(); renderSource(); });
    var ts = host("surv-test-scope");
    if (ts) ts.addEventListener("change", function () { testScope = ts.value || "national"; renderTests(); });
    var add = host("surv-fu21-add");
    if (add) add.addEventListener("change", function () {
      if (add.value && fuShown.indexOf(add.value) < 0) fuShown.push(add.value);
      renderFu21();
      fillFuAdd();
    });
    // Charts are drawn to a fixed viewBox; redraw when the layout width changes
    // (window resize, narrow/wide breakpoint) so text and bars keep their shape.
    var timer = null, lastW = 0;
    global.addEventListener("resize", function () {
      if (timer) global.clearTimeout(timer);
      timer = global.setTimeout(function () {
        var w = (host("surv-inner") || document.body).clientWidth;
        if (w !== lastW) { lastW = w; renderAll(); }
      }, 120);
    });
  }

  global.SurveillanceTab = { render: renderAll, refreshI18n: renderAll, _data: data };
  wire();
  renderAll();
})(window);
