// Clinical Symptoms tab.
//
// Draws the cards on clinical-symptoms.html from PAYLOAD.clinical
// (Scripts/common/clinical.py), which holds BDBV2026-Processing_Code step 9's
// summary tables. Counts below meta.min_cell_count arrive as null with a
// suppression flag and are shown as "<N", never as zero. Owns its own state
// (area, toggles); engine.js only calls ClinicalTab.refreshI18n() on a
// language switch.
(function (global) {
  "use strict";

  var C = global.DashboardCharts;
  var INK = "#01454f", MAIN = "#1a8c99", ALERT = "#e0703f", MUTED = "#a3b9bc";
  var GOLD = "#c9a227", RED = "#a8322d", PURPLE = "#7a5c99", GREY = "#9c968b";
  var FEMALE = PURPLE, FEMALE_DARK = "#4b3563", MALE = MAIN, MALE_DARK = INK;
  var AGE_PAL = ["#b9d7da", "#6eacb3", "#2a7d89", INK, GOLD, ALERT];
  var GROUP_COL = {
    female: FEMALE, male: MALE, alive: MAIN, deceased: RED
  };
  var SVGNS = "http://www.w3.org/2000/svg";

  // --- payload / i18n ----------------------------------------------------------------
  var _data;
  function data() {
    if (_data !== undefined) return _data;
    var el = document.getElementById("payload");
    try { _data = (JSON.parse(el.textContent) || {}).clinical || null; } catch (e) { _data = null; }
    return _data;
  }
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
  function lang() { return document.documentElement.lang === "fr" ? "fr" : "en"; }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function num(v) { return v == null ? "–" : Number(v).toLocaleString(lang() === "fr" ? "fr-FR" : "en-GB"); }
  function minCell() { var d = data(); return (d && d.meta && d.meta.min_cell_count) || 10; }
  function hidden() { return "<" + minCell(); }
  function host(id) { return document.getElementById(id); }

  // --- small SVG helpers --------------------------------------------------------------
  function svg(w, h) {
    var s = C.svgEl("svg", { viewBox: "0 0 " + w + " " + h, width: "100%", height: h, role: "img" });
    s.style.display = "block";
    return s;
  }
  function el(tag, attrs, text, tip) {
    var e = C.svgEl(tag, attrs);
    if (text != null) e.textContent = text;
    if (tip) {
      var t = document.createElementNS(SVGNS, "title");
      t.textContent = tip;
      e.appendChild(t);
    }
    return e;
  }
  function empty(chartId, msg) {
    var h = host(chartId);
    if (!h) return;
    h.replaceChildren();
    var p = document.createElement("p");
    p.className = "surv-empty";
    p.textContent = msg || tr("ui.clin.no_data", "No data available for this panel yet.");
    h.appendChild(p);
  }
  function caption(cardId, text) { var e = host(cardId + "-caption"); if (e) e.textContent = text || ""; }
  function legend(cardId, items) {
    var e = host(cardId + "-legend");
    if (!e) return;
    e.replaceChildren();
    items.forEach(function (it) {
      var b = document.createElement("span");
      b.className = "surv-chip";
      var sw = document.createElement("span");
      sw.className = "surv-sw" + (it.bar ? " bar" : "");
      sw.style.setProperty("--sw", it.color);
      b.appendChild(sw);
      b.appendChild(document.createTextNode(it.label));
      e.appendChild(b);
    });
  }
  // A row of mutually exclusive buttons. opts: [{id, label}]
  function toggle(groupId, opts, current, onPick) {
    var g = host(groupId);
    if (!g) return;
    g.replaceChildren();
    opts.forEach(function (o) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "surv-chip clin-opt" + (o.id === current ? " on" : "");
      b.setAttribute("aria-pressed", o.id === current ? "true" : "false");
      b.textContent = o.label;
      b.addEventListener("click", function () { onPick(o.id); });
      g.appendChild(b);
    });
  }

  // Gridline values whose top is at least `max` (niceLinearTicks can stop
  // just below it, which would let the tallest bar run off the chart).
  function axisTicks(max) {
    var t = (C.niceLinearTicks ? C.niceLinearTicks(max) : [0, max]).slice();
    var step = t.length > 1 ? t[1] - t[0] : max;
    while (t[t.length - 1] < max) t.push(t[t.length - 1] + step);
    return t;
  }

  // --- state --------------------------------------------------------------------------
  var scope = "national", symBy = "all", losBy = "all";
  function locData() {
    var d = data();
    return d && d.locations ? d.locations[scope] || d.locations.national : null;
  }
  function placeName() {
    var L = locData();
    return scope === "national" || !L ? tr("ui.trends_scope_national", "National") : L.label;
  }
  function fillScope() {
    var sel = host("clin-scope"), d = data();
    if (!sel || !d) return;
    var keys = Object.keys(d.locations || {});
    var provs = keys.filter(function (k) { return k.indexOf("province:") === 0; }).sort();
    var html = '<option value="national">' + esc(tr("ui.trends_scope_national", "National")) + "</option>";
    if (provs.length) {
      html += '<optgroup label="' + esc(tr("ui.trends_scope_province", "Provincial")) + '">' +
        provs.map(function (k) { return '<option value="' + esc(k) + '">' + esc(d.locations[k].label) + "</option>"; }).join("") +
        "</optgroup>";
    }
    sel.innerHTML = html;
    if (!d.locations[scope]) scope = "national";
    sel.value = scope;
  }

  // --- headline -----------------------------------------------------------------------
  function fmtDate(iso) {
    if (!iso) return "";
    return new Date(iso + "T00:00:00Z").toLocaleDateString(lang() === "fr" ? "fr-FR" : "en-GB",
      { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  }
  function pctOf(n, d) { return n == null || !d ? null : Math.round(1000 * n / d) / 10; }
  function renderHeadline() {
    var e = host("clin-headline"), d = data(), L = locData(), asof = host("clin-asof");
    if (asof) asof.textContent = d ? trf("ui.clin.asof", "Line list of {date}", { date: fmtDate(d.asof) }) : "";
    if (!e) return;
    e.replaceChildren();
    if (!L) { e.hidden = true; return; }
    var s = L.summary || {}, tiles = [];
    var v = function (n) { return n == null ? hidden() : num(n); };
    tiles.push([v(s.n_cases), tr("ui.clin.tile_cases", "confirmed cases")]);
    var ps = pctOf(s.n_symptoms_recorded, s.n_cases);
    tiles.push([ps == null ? "–" : ps + "%", trf("ui.clin.tile_symptoms", "with symptoms recorded ({n})", { n: v(s.n_symptoms_recorded) })]);
    var ph = pctOf(s.n_hospitalised, s.n_cases);
    tiles.push([ph == null ? "–" : ph + "%", trf("ui.clin.tile_hosp", "admitted to hospital ({n})", { n: v(s.n_hospitalised) })]);
    if (s.los_median != null) {
      tiles.push([s.los_median + " " + tr("ui.clin.days", "days"),
        trf("ui.clin.tile_los", "median hospital stay (IQR {lo}–{hi})", { lo: s.los_q25, hi: s.los_q75 })]);
    }
    if (s.onset_admit_median != null) {
      tiles.push([s.onset_admit_median + " " + tr("ui.clin.days", "days"),
        trf("ui.clin.tile_onset_admit", "median from symptom onset to admission (IQR {lo}–{hi})", { lo: s.onset_admit_q25, hi: s.onset_admit_q75 })]);
    }
    var pd = pctOf(s.n_dead_at_sampling, s.n_cases);
    tiles.push([pd == null ? "–" : pd + "%", trf("ui.clin.tile_dead", "already dead when sampled ({n})", { n: v(s.n_dead_at_sampling) })]);
    tiles.push([v(s.n_health_workers), tr("ui.clin.tile_hcw", "health workers infected")]);
    tiles.forEach(function (t) {
      var div = document.createElement("div");
      div.className = "surv-tile";
      div.innerHTML = '<span class="surv-tile-v">' + esc(t[0]) + '</span><span class="surv-tile-l">' + esc(t[1]) + "</span>";
      e.appendChild(div);
    });
    e.hidden = false;
  }

  // --- symptoms -----------------------------------------------------------------------
  function symLabel(code) {
    var d = data(), l = d.labels[code] || {};
    var name = (lang() === "fr" ? l.fr : l.en) || code;
    return l.confirmed === false ? name + " *" : name;
  }
  function groupLabel(bd, g) {
    if (bd === "age_group") return trf("ui.clin.age_years", "{g} yrs", { g: g });
    if (bd === "sex") return g === "female" ? tr("ui.clin.female", "Female") : tr("ui.clin.male", "Male");
    if (bd === "status_at_sampling") return g === "alive" ? tr("ui.clin.alive", "Alive at sampling") : tr("ui.clin.dead", "Dead at sampling");
    return tr("ui.clin.all_cases", "All cases");
  }
  function renderSymptoms() {
    var d = data(), L = locData(), h = host("clin-symptoms-chart");
    toggle("clin-sym-by", [
      { id: "all", label: tr("ui.clin.by_all", "All") },
      { id: "age_group", label: tr("ui.clin.by_age", "By age") },
      { id: "sex", label: tr("ui.clin.by_sex", "By sex") },
      { id: "status_at_sampling", label: tr("ui.clin.by_status", "Alive / dead at sampling") }
    ], symBy, function (id) { symBy = id; renderSymptoms(); });
    if (!h) return;
    var bd = L && L.symptoms && L.symptoms[symBy];
    if (!bd) { empty("clin-symptoms-chart"); caption("clin-symptoms", ""); legend("clin-symptoms", []); return; }
    var groups = symBy === "age_group" ? (d.meta.symptom_age_groups || Object.keys(bd)).filter(function (g) { return bd[g]; })
      : Object.keys(bd);
    // Rows: codes with something to show in at least one group.
    var rows = [];
    d.order.forEach(function (code, i) {
      var any = groups.some(function (g) { return bd[g].s[i] || (bd[g].n[i] || 0) > 0; });
      if (any) rows.push(i);
    });
    var W = h.clientWidth || 640, labelW = Math.min(230, Math.max(150, W * 0.3)), right = 46;
    var rowH = symBy === "all" ? 20 : 22, top = 18, H = top + rows.length * rowH + 8;
    var s = svg(W, H), x0 = labelW, x1 = W - right;
    var xMax = 0;
    groups.forEach(function (g) { rows.forEach(function (i) { if (bd[g].pct[i] != null) xMax = Math.max(xMax, bd[g].pct[i]); }); });
    xMax = Math.min(100, Math.max(10, Math.ceil(xMax / 10) * 10));
    var xp = function (v) { return x0 + (v / xMax) * (x1 - x0); };
    for (var t = 0; t <= xMax; t += (xMax > 50 ? 20 : 10)) {
      s.appendChild(el("line", { x1: xp(t), x2: xp(t), y1: top - 4, y2: H - 6, stroke: "#eee" }));
      s.appendChild(el("text", { x: xp(t), y: 10, "font-size": 9, fill: GREY, "text-anchor": "middle" }, t + "%"));
    }
    var colOf = function (g, gi) {
      return symBy === "age_group" ? AGE_PAL[gi % AGE_PAL.length] : (GROUP_COL[g] || INK);
    };
    rows.forEach(function (i, r) {
      var y = top + r * rowH + rowH / 2, code = d.order[i];
      var full = symLabel(code), maxCh = Math.floor((labelW - 12) / 6.1);
      var shown = full.length > maxCh ? full.slice(0, Math.max(4, maxCh - 1)).replace(/\s+$/, "") + "…" : full;
      s.appendChild(el("text", { x: labelW - 8, y: y + 3.5, "font-size": 11, fill: "#2a2a27", "text-anchor": "end" },
        shown, shown !== full ? full : null));
      if (symBy === "all") {
        var e = bd.all, p = e.pct[i];
        if (e.s[i]) {
          s.appendChild(el("text", { x: x0 + 4, y: y + 3.5, "font-size": 10, fill: GREY }, hidden(),
            trf("ui.clin.suppressed_tip", "Fewer than {n} cases: hidden", { n: minCell() })));
        } else if (p != null) {
          s.appendChild(el("rect", { x: x0, y: y - rowH * 0.32, width: Math.max(1, xp(p) - x0), height: rowH * 0.64, fill: MAIN, rx: 1 },
            null, symLabel(code) + ": " + p + "% (" + num(e.n[i]) + " / " + num(e.den) + ")"));
          s.appendChild(el("text", { x: xp(p) + 4, y: y + 3.5, "font-size": 10, fill: "#5c574f" }, p.toFixed(1) + "%"));
        }
      } else {
        var vals = [];
        groups.forEach(function (g, gi) { if (bd[g].pct[i] != null) vals.push(bd[g].pct[i]); });
        if (vals.length > 1) {
          s.appendChild(el("line", { x1: xp(Math.min.apply(null, vals)), x2: xp(Math.max.apply(null, vals)), y1: y, y2: y,
            stroke: "#d6d2c9", "stroke-width": 2 }));
        }
        groups.forEach(function (g, gi) {
          var e = bd[g], p = e.pct[i];
          if (p == null) return;
          s.appendChild(el("circle", { cx: xp(p), cy: y, r: 4.2, fill: colOf(g, gi), stroke: "#fff", "stroke-width": 1 },
            null, symLabel(code) + " – " + groupLabel(symBy, g) + ": " + p + "% (" + num(e.n[i]) + " / " + num(e.den) + ")"));
        });
      }
    });
    h.replaceChildren(s);
    h.style.height = "auto";
    if (symBy === "all") legend("clin-symptoms", []);
    else legend("clin-symptoms", groups.map(function (g, gi) {
      var den = bd[g].den;
      return { label: groupLabel(symBy, g) + " (n=" + (den == null ? hidden() : num(den)) + ")", color: colOf(g, gi) };
    }));
    var den = bd.all ? bd.all.den : null;
    var text = trf("ui.clin.symptoms_caption",
      "{place}. % of confirmed cases with at least one symptom recorded{n}. Hover for counts. Not shown: counts under {min}.",
      { place: placeName(), n: symBy === "all" && den != null ? " (n=" + num(den) + ")" : "", min: minCell() });
    if (d.meta.unconfirmed_symptom_codes && d.meta.unconfirmed_symptom_codes.length) {
      text += " " + tr("ui.clin.unconfirmed_note", "* Symptom code not yet identified; shown as recorded.");
    }
    if (symBy === "status_at_sampling") {
      text += " " + tr("ui.clin.status_note", "Symptoms are recorded less often for people who were dead at sampling.");
    }
    caption("clin-symptoms", text);
  }

  // --- length of stay -----------------------------------------------------------------
  function renderLos() {
    var L = locData(), h = host("clin-los-chart");
    toggle("clin-los-by", [
      { id: "all", label: tr("ui.clin.by_all", "All") },
      { id: "alive", label: tr("ui.clin.alive", "Alive at sampling") },
      { id: "deceased", label: tr("ui.clin.dead", "Dead at sampling") }
    ], losBy, function (id) { losBy = id; renderLos(); });
    if (!h) return;
    var e = L && L.los && L.los[losBy];
    var total = e ? e.n.reduce(function (a, v) { return a + (v || 0); }, 0) : 0;
    if (!e || (!total && !e.s.some(Boolean))) { empty("clin-los-chart"); caption("clin-los", ""); return; }
    var W = h.clientWidth || 420, H = h.clientHeight || 220, pad = { l: 36, r: 8, t: 10, b: 34 };
    var s = svg(W, H), n = e.bins.length, bw = (W - pad.l - pad.r) / n;
    var yMax = Math.max(1, Math.max.apply(null, e.n.map(function (v) { return v || 0; })));
    var ticks = axisTicks(yMax);
    yMax = ticks[ticks.length - 1];
    var yp = function (v) { return H - pad.b - (v / yMax) * (H - pad.t - pad.b); };
    ticks.forEach(function (v) {
      s.appendChild(el("line", { x1: pad.l, x2: W - pad.r, y1: yp(v), y2: yp(v), stroke: "#eee" }));
      s.appendChild(el("text", { x: pad.l - 4, y: yp(v) + 3, "font-size": 9, fill: GREY, "text-anchor": "end" }, num(v)));
    });
    e.bins.forEach(function (b, i) {
      var x = pad.l + i * bw + 2, w = bw - 4;
      if (e.s[i]) {
        s.appendChild(el("text", { x: x + w / 2, y: H - pad.b - 4, "font-size": 9, fill: GREY, "text-anchor": "middle" }, hidden()));
      } else if (e.n[i] != null) {
        s.appendChild(el("rect", { x: x, y: yp(e.n[i]), width: w, height: H - pad.b - yp(e.n[i]),
          fill: losBy === "deceased" ? RED : MAIN }, null, b + " " + tr("ui.clin.days", "days") + ": " + num(e.n[i])));
      }
      // Narrow bars: label every other one (always the last) so labels don't run together.
      var every = bw < 34 ? 2 : 1;
      if (i % every === 0 || i === e.bins.length - 1) {
        s.appendChild(el("text", { x: x + w / 2, y: H - pad.b + 12, "font-size": 9, fill: GREY, "text-anchor": "middle" }, b));
      }
    });
    s.appendChild(el("text", { x: (pad.l + W - pad.r) / 2, y: H - 4, "font-size": 9, fill: GREY, "text-anchor": "middle" },
      tr("ui.clin.los_axis", "Days in hospital")));
    h.replaceChildren(s);
    legend("clin-los", []);
    var sm = L.summary || {};
    caption("clin-los", trf("ui.clin.los_caption",
      "{place}: {n} stays with admission and discharge dates. Median {med} days (IQR {lo}–{hi}) across all stays. The last bar covers {last} days. The discharge date does not say whether the patient recovered or died.",
      { place: placeName(), n: num(total), last: e.bins[e.bins.length - 1], med: sm.los_median == null ? "–" : sm.los_median,
        lo: sm.los_q25 == null ? "–" : sm.los_q25, hi: sm.los_q75 == null ? "–" : sm.los_q75 }));
  }

  // --- age pyramid --------------------------------------------------------------------
  function renderPyramid() {
    var L = locData(), h = host("clin-pyramid-chart"), py = L && L.pyramid;
    if (!h) return;
    if (!py || !py.bands.length) { empty("clin-pyramid-chart"); caption("clin-pyramid", ""); return; }
    var W = h.clientWidth || 420, H = h.clientHeight || 220, mid = W / 2, gap = 30, pad = { t: 6, b: 18 };
    var s = svg(W, H), n = py.bands.length, rowH = (H - pad.t - pad.b) / n;
    var max = 1;
    py.female.concat(py.male).forEach(function (v) { if (v != null && v > max) max = v; });
    var half = mid - gap - 6, sc = function (v) { return (v / max) * half; };
    // Oldest band on top.
    for (var i = 0; i < n; i++) {
      var y = pad.t + (n - 1 - i) * rowH, bh = rowH * 0.78;
      s.appendChild(el("text", { x: mid, y: y + bh / 2 + 3.5, "font-size": 9.5, fill: "#5c574f", "text-anchor": "middle" }, py.bands[i]));
      [["female", -1, FEMALE, FEMALE_DARK], ["male", 1, MALE, MALE_DARK]].forEach(function (cfg) {
        var sx = cfg[0], dir = cfg[1], v = py[sx][i], dv = py[sx + "_dead"][i], sup = py["s_" + sx][i];
        var x0 = dir < 0 ? mid - gap : mid + gap;
        if (v == null) {
          if (sup) s.appendChild(el("text", { x: x0 + dir * 4, y: y + bh / 2 + 3.5, "font-size": 9, fill: GREY,
            "text-anchor": dir < 0 ? "end" : "start" }, hidden()));
          return;
        }
        var w = sc(v), tip = (sx === "female" ? tr("ui.clin.female", "Female") : tr("ui.clin.male", "Male")) +
          ", " + py.bands[i] + ": " + num(v) + " · " + tr("ui.clin.dead", "Dead at sampling") + ": " + (dv == null ? hidden() : num(dv));
        s.appendChild(el("rect", { x: dir < 0 ? x0 - w : x0, y: y, width: w, height: bh, fill: cfg[2] }, null, tip));
        if (dv != null && dv > 0) {
          var dw = sc(dv);
          s.appendChild(el("rect", { x: dir < 0 ? x0 - dw : x0, y: y, width: dw, height: bh, fill: cfg[3] }, null, tip));
        }
      });
    }
    s.appendChild(el("text", { x: mid - gap, y: H - 4, "font-size": 9.5, fill: FEMALE, "text-anchor": "end" }, "← " + tr("ui.clin.female", "Female")));
    s.appendChild(el("text", { x: mid + gap, y: H - 4, "font-size": 9.5, fill: MALE }, tr("ui.clin.male", "Male") + " →"));
    h.replaceChildren(s);
    legend("clin-pyramid", [
      { label: tr("ui.clin.legend_cases", "Cases"), color: MUTED, bar: true },
      { label: tr("ui.clin.dead", "Dead at sampling"), color: "#4a4a4a", bar: true }
    ]);
    caption("clin-pyramid", trf("ui.clin.pyramid_caption",
      "{place}. Confirmed cases by age (years) and sex; darker: dead at sampling. Hover for counts. Not shown: counts under {min}.",
      { place: placeName(), min: minCell() }));
  }

  // --- health workers -----------------------------------------------------------------
  function fmtMonth(m) {
    var d = new Date(m + "-15T00:00:00Z");
    return d.toLocaleDateString(lang() === "fr" ? "fr-FR" : "en-GB", { month: "short", year: "2-digit", timeZone: "UTC" });
  }
  function renderHcw() {
    var L = locData(), h = host("clin-hcw-chart"), hw = L && L.hcw;
    if (!h) return;
    if (!hw || !hw.months.length) { empty("clin-hcw-chart"); caption("clin-hcw", ""); return; }
    var W = h.clientWidth || 640, H = h.clientHeight || 220, pad = { l: 36, r: 8, t: 16, b: 22 };
    var s = svg(W, H), n = hw.months.length, bw = (W - pad.l - pad.r) / n;
    var yMax = Math.max(1, Math.max.apply(null, hw.n.map(function (v) { return v || 0; })));
    var ticks = axisTicks(yMax);
    yMax = ticks[ticks.length - 1];
    var yp = function (v) { return H - pad.b - (v / yMax) * (H - pad.t - pad.b); };
    ticks.forEach(function (v) {
      s.appendChild(el("line", { x1: pad.l, x2: W - pad.r, y1: yp(v), y2: yp(v), stroke: "#eee" }));
      s.appendChild(el("text", { x: pad.l - 4, y: yp(v) + 3, "font-size": 9, fill: GREY, "text-anchor": "end" }, num(v)));
    });
    hw.months.forEach(function (m, i) {
      var x = pad.l + i * bw + bw * 0.15, w = bw * 0.7;
      if (hw.s[i]) {
        s.appendChild(el("text", { x: x + w / 2, y: H - pad.b - 4, "font-size": 9, fill: GREY, "text-anchor": "middle" }, hidden()));
      } else if (hw.n[i] != null) {
        s.appendChild(el("rect", { x: x, y: yp(hw.n[i]), width: w, height: H - pad.b - yp(hw.n[i]), fill: INK },
          null, fmtMonth(m) + ": " + num(hw.n[i])));
        if (hw.n[i] > 0) s.appendChild(el("text", { x: x + w / 2, y: yp(hw.n[i]) - 3, "font-size": 9, fill: "#5c574f", "text-anchor": "middle" }, num(hw.n[i])));
      }
      s.appendChild(el("text", { x: x + w / 2, y: H - 6, "font-size": 9, fill: GREY, "text-anchor": "middle" }, fmtMonth(m)));
    });
    h.replaceChildren(s);
    legend("clin-hcw", []);
    var roleName = { nurse: tr("ui.clin.role_nurse", "Nurses"), doctor: tr("ui.clin.role_doctor", "Doctors"), other: tr("ui.clin.role_other", "Other / unspecified role") };
    var roles = ["nurse", "doctor", "other"].map(function (r) {
      var v = hw.roles[r];
      return roleName[r] + ": " + (hw.roles_s[r] ? hidden() : (v == null ? "–" : num(v)));
    }).join(" · ");
    var latest = hw.months[hw.months.length - 1];
    caption("clin-hcw", trf("ui.clin.hcw_caption",
      "{place}. By month of symptom onset ({latest} is not complete yet). {roles}. Not shown: counts under {min}.",
      { place: placeName(), latest: fmtMonth(latest), roles: roles, min: minCell() }));
  }

  // --- orchestration ------------------------------------------------------------------
  function renderAll() {
    if (!data()) {
      ["clin-symptoms", "clin-los", "clin-pyramid", "clin-hcw"].forEach(function (id) { empty(id + "-chart"); });
      var hl = host("clin-headline"); if (hl) hl.hidden = true;
      return;
    }
    fillScope();
    renderHeadline();
    renderSymptoms();
    renderLos();
    renderPyramid();
    renderHcw();
  }

  function wire() {
    var sel = host("clin-scope");
    if (sel) sel.addEventListener("change", function () { scope = sel.value || "national"; renderAll(); });
    var timer = null, lastW = 0;
    global.addEventListener("resize", function () {
      if (timer) global.clearTimeout(timer);
      timer = global.setTimeout(function () {
        var w = (host("clin-inner") || document.body).clientWidth;
        if (w !== lastW) { lastW = w; renderAll(); }
      }, 120);
    });
  }

  global.ClinicalTab = { render: renderAll, refreshI18n: renderAll, _data: data };
  wire();
  renderAll();
})(window);
