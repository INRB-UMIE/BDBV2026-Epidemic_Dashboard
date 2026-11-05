// Current Snapshot summary rail.
//
// Summarises the other tabs for the focused health zone (engine.js's
// mapSelectedNom), or nationally when none is focused:
//   * headline counts       -- PAYLOAD.totals (national, = header tracker) /
//                              PAYLOAD.zone_data (zone), recency from
//                              PAYLOAD.confirmed_recency
//   * cases + positivity    -- PAYLOAD.snapshot_summary.*.curve (Trends tab data)
//   * spatial invasion rank -- PAYLOAD.invasion_risk (Spatial Risk tab)
//   * contact tracing       -- PAYLOAD.snapshot_summary.ct / zones[*].ct
//   * laboratories          -- PAYLOAD.snapshot_summary.labs (Surveillance tab)
//   * sequences             -- PAYLOAD.snapshot_summary.sequences /
//                              zone_data.genomic_sequence_count
//   * recent trend          -- last 14 complete days vs the 14 before, from
//                              the same curve as the chart
//   * reproduction number   -- PAYLOAD.rt (common/rt.py): national + provinces
//   * incoming mobility     -- PAYLOAD.flow_catalogs.flowminder_latest (the
//                              map's flow arrows)
//   * news feed             -- phrContext() (Public Health Context tab)
//
// engine.js calls SnapshotSummary.render(nom) from renderMapInfoBox(), i.e. on
// every selection change and language switch. This file also owns the
// map/rail split handle.
(function (global) {
  "use strict";

  var C = global.DashboardCharts;
  var S = (PAYLOAD && PAYLOAD.snapshot_summary) || {};
  var DAY = 86400000;
  var NEWS_INITIAL = 6;

  var COLOR_OBS = "#9e2b2b";   // same as trends.js / genomic DIST_OBS
  var COLOR_IMP = "#587e72";   // same as trends.js / genomic DIST_IMP
  var COLOR_POS = "#1B4671";
  var COLOR_POS_BAND = "rgba(27,70,113,0.13)";
  var COLOR_INCOMPLETE = "#9c968b";

  var current = null;

  // engine.js's Leaflet map is a top-level const (a global lexical binding,
  // not a window property -- window.map is the #map <div>).
  function invalidateMap() {
    if (typeof map !== "undefined" && map && map.invalidateSize) map.invalidateSize({ animate: false });
  }
  var newsFilter = "all";
  var newsExpanded = false;

  // engine.js's t() echoes the key on a miss; treat that as a miss.
  function tr(key, fallback) {
    var v = global.t ? global.t("ui.snap." + key) : null;
    return (v && v !== "ui.snap." + key && typeof v === "string") ? v : (fallback || key);
  }
  function trf(key, vars) {
    var s = tr(key);
    Object.keys(vars || {}).forEach(function (k) { s = s.split("{" + k + "}").join(String(vars[k])); });
    return s;
  }
  function esc(s) { return global.escHtml ? global.escHtml(s) : String(s == null ? "" : s); }
  function loc() { return global.localeTag ? global.localeTag() : "en-US"; }
  function num(v) { return v == null || !isFinite(v) ? "—" : Math.round(v).toLocaleString(loc()); }
  function pct(k, n, d) {
    if (!n) return "—";
    return (100 * k / n).toLocaleString(loc(), { maximumFractionDigits: d == null ? 1 : d, minimumFractionDigits: d == null ? 1 : d }) + "%";
  }
  function pctv(v, d) {
    return v == null || !isFinite(v) ? "—" : Number(v).toLocaleString(loc(), { maximumFractionDigits: d == null ? 1 : d, minimumFractionDigits: d == null ? 1 : d }) + "%";
  }
  // Day-month-year in both languages, matching the header's sitrep date.
  function dateLoc() { return loc() === "fr-FR" ? "fr-FR" : "en-GB"; }
  function fmtDate(iso) {
    if (!iso) return "—";
    var d = new Date(String(iso).slice(0, 10) + "T00:00:00Z");
    if (isNaN(d)) return String(iso);
    return d.toLocaleDateString(dateLoc(), { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  }
  function fmtShort(ms) {
    return new Date(ms).toLocaleDateString(dateLoc(), { day: "numeric", month: "short", timeZone: "UTC" });
  }
  function addDays(iso, n) { return new Date(C.dayMs(iso) + n * DAY).toISOString().slice(0, 10); }

  function card(id, title, body, opts) {
    opts = opts || {};
    return '<section class="snap-card' + (opts.wide ? " snap-wide" : "") + '" id="' + id + '">' +
      "<h3><span>" + esc(title) + "</span>" + (opts.asof ? '<span class="snap-asof">' + esc(opts.asof) + "</span>" : "") + "</h3>" +
      body + "</section>";
  }
  function tile(cls, value, label, sub) {
    return '<div class="snap-tile ' + cls + '"><span class="snap-tile-v">' + value + "</span>" +
      '<span class="snap-tile-l">' + esc(label) + "</span>" +
      (sub ? '<span class="snap-tile-s">' + esc(sub) + "</span>" : "") + "</div>";
  }

  // ── Headline tiles ─────────────────────────────────────────────────────
  function lastCaseDays(nom) {
    var r = PAYLOAD.confirmed_recency;
    if (!r || !r.days_by_nom || !r.days_by_nom[nom]) return null;
    var arr = r.days_by_nom[nom];
    return arr.length ? arr[arr.length - 1] : null;
  }

  function kpis(nom) {
    var h = '<div class="snap-kpis">';
    var sitrep = trf("kpi_sitrep", { date: PAYLOAD.asof || "—" });
    if (!nom) {
      var tot = PAYLOAD.totals || {};
      h += tile("t-cases", num(tot.global_confirmed_cases), tr("kpi_confirmed"), sitrep);
      h += tile("t-deaths", num(tot.global_confirmed_deaths), tr("kpi_deaths"), sitrep);
      h += tile("t-recovered", num(tot.global_recovered_cases), tr("kpi_recovered"), sitrep);
      var nt = (S.national || {}).testing;
      if (nt) h += tile("t-tests", num(nt.n), tr("kpi_tests"), trf("kpi_tests_sub", { pct: pct(nt.pos, nt.n) }));
      if (S.sequences != null) h += tile("t-seq", num(S.sequences), tr("kpi_seq"), trf("kpi_seq_sub", { date: fmtDate((S.asof || {}).sequences) }));
    } else {
      var z = ZONE_DATA[nom] || {};
      h += tile("t-cases", num(z.confirmed_cases || 0), tr("kpi_confirmed"), sitrep);
      h += tile("t-deaths", num(z.confirmed_deaths || 0), tr("kpi_deaths"), sitrep);
      var days = lastCaseDays(nom);
      var r = PAYLOAD.confirmed_recency || {};
      var lastDate = r.dates && r.dates.length ? r.dates[r.dates.length - 1] : null;
      var v = days == null || days < 0 ? tr("kpi_never") : (days === 0 ? tr("kpi_today") : trf("kpi_days_ago", { n: days }));
      h += tile("t-recency", '<span style="font-size:0.8em">' + esc(v) + "</span>", tr("kpi_last_case"),
                lastDate ? trf("kpi_last_case_sub", { date: fmtDate(lastDate) }) : "");
      var zt = ((S.zones || {})[nom] || {}).testing;
      h += tile("t-tests", num(zt ? zt.n : 0), tr("kpi_tests"), zt && zt.n ? trf("kpi_tests_sub", { pct: pct(zt.pos, zt.n) }) : "");
      h += tile("t-seq", num(z.genomic_sequence_count || 0), tr("kpi_seq"), trf("kpi_seq_sub", { date: fmtDate((S.asof || {}).sequences) }));
    }
    return h + "</div>";
  }

  // ── Cases + positivity chart ───────────────────────────────────────────
  function curveFor(nom) {
    if (!nom) return (S.national || {}).curve || null;
    return ((S.zones || {})[nom] || {}).curve || null;
  }

  function chartCard(nom) {
    var cv = curveFor(nom);
    var hasCases = cv && cv.obs && cv.obs.some(function (v, i) { return (v || 0) + ((cv.imp || [])[i] || 0) > 0; });
    var body;
    if (!hasCases) {
      body = '<p class="snap-empty">' + esc(tr("chart_empty")) + "</p>";
    } else {
      body = '<div class="snap-legend">' +
        '<span><i style="background:' + COLOR_OBS + '"></i>' + esc(tr("legend_obs")) + "</span>" +
        '<span><i style="background:' + COLOR_IMP + '"></i>' + esc(tr("legend_imp")) + "</span>" +
        (cv.pos ? '<span><i class="ln" style="background:' + COLOR_POS + '"></i>' + esc(tr("legend_pos")) + "</span>" : "") +
        (S.incomplete_from ? '<span><i style="background:' + COLOR_INCOMPLETE + ';opacity:.35"></i>' + esc(tr("legend_incomplete")) + "</span>" : "") +
        "</div>" +
        '<div class="snap-chart" id="snap-chart"></div>' +
        '<p class="snap-note">' + esc(tr("chart_note")) + "</p>";
    }
    return card("snap-curve", tr("chart_title"), body,
      { wide: true, asof: (S.asof || {}).cases ? trf("chart_asof", { date: fmtDate(S.asof.cases) }) : "" });
  }

  function drawChart(nom) {
    var host = document.getElementById("snap-chart");
    var cv = curveFor(nom);
    if (!host || !cv || !cv.obs) return;
    host.innerHTML = "";
    var W = Math.max(280, host.clientWidth || 600), H = host.clientHeight || 210;
    var svg = C.svgEl("svg", { viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none", role: "img", "aria-label": tr("chart_title") });
    host.appendChild(svg);

    var dates = cv.obs.map(function (_, i) { return addDays(cv.start, i); });
    var pos = cv.pos || null;
    // Trim leading/trailing all-zero days so a zone's curve fills the frame.
    var first = 0, last = dates.length - 1;
    while (first < last && !((cv.obs[first] || 0) + ((cv.imp || [])[first] || 0))) first++;
    var xStart = dates[first], xEnd = dates[last];
    if (pos && pos.dates.length) {
      if (pos.dates[pos.dates.length - 1] > xEnd) xEnd = pos.dates[pos.dates.length - 1];
    }
    if (S.asof && S.asof.cases && S.asof.cases > xEnd) xEnd = S.asof.cases;
    xStart = addDays(xStart, -2);

    var yMax = 1;
    cv.obs.forEach(function (v, i) { yMax = Math.max(yMax, (v || 0) + ((cv.imp || [])[i] || 0)); });
    var ticks = C.niceLinearTicks(yMax);
    yMax = ticks[ticks.length - 1] || yMax;

    var fr = C.frame(svg, {
      width: W, height: H, pad: { left: 36, right: pos ? 40 : 12, top: 8, bottom: 22 },
      xStart: xStart, xEnd: xEnd, yMax: yMax,
      fmtY: function (v) { return v.toLocaleString(loc()); }
    });
    C.shadeRegion(svg, fr, S.incomplete_from, COLOR_INCOMPLETE);
    C.stackedBars(svg, fr, dates, [
      { values: cv.obs, color: COLOR_OBS },
      { values: cv.imp || [], color: COLOR_IMP }
    ]);
    var posByDay = {};
    if (pos) {
      var sc = function (arr) { return arr.map(function (v) { return v == null ? null : Math.max(0, Math.min(1, v)) * fr.yMax; }); };
      C.ciBand(svg, fr, pos.dates, sc(pos.lo), sc(pos.hi), COLOR_POS_BAND);
      C.line(svg, fr, pos.dates, sc(pos.mean), COLOR_POS, 1.4);
      C.dualAxis(svg, fr, "", 100);
      pos.dates.forEach(function (d, i) { posByDay[d] = i; });
    }
    var idxOf = {};
    dates.forEach(function (d, i) { idxOf[d] = i; });
    C.tooltip(host, svg, fr, function (day) {
      var i = idxOf[day], j = posByDay[day];
      if (i == null && j == null) return null;
      var h = '<div class="dc-tip-d">' + esc(fmtDate(day)) + "</div>";
      if (i != null) {
        h += '<div><span class="dc-sw" style="background:' + COLOR_OBS + '"></span>' + num(cv.obs[i] || 0) + " " + esc(tr("tip_obs")) + "</div>";
        if (cv.imp && cv.imp[i]) h += '<div><span class="dc-sw" style="background:' + COLOR_IMP + '"></span>' + num(cv.imp[i]) + " " + esc(tr("tip_imp")) + "</div>";
      }
      if (j != null && pos.mean[j] != null) {
        h += '<div><span class="dc-sw" style="background:' + COLOR_POS + '"></span>' + esc(tr("tip_pos")) + " " + pctv(100 * pos.mean[j], 0) +
          (pos.lo[j] != null ? ' <span class="dc-tip-ci">(' + pctv(100 * pos.lo[j], 0) + "–" + pctv(100 * pos.hi[j], 0) + ")</span>" : "") + "</div>";
      }
      return h;
    });
  }

  // ── Spatial invasion risk ──────────────────────────────────────────────
  function riskCard(nom) {
    var ir = PAYLOAD.invasion_risk;
    var asof = "";
    if (!ir || !ir.zones) return card("snap-risk", tr("risk_title"), '<p class="snap-empty">' + esc(tr("no_data")) + "</p>");
    var zones = ir.zones;
    var ranked = Object.keys(zones).filter(function (k) { return zones[k].rr_nat_rank != null; });
    var total = ranked.length;
    if (ir.forecast_start_date) asof = trf("risk_window", { start: fmtDate(ir.forecast_start_date), end: fmtDate(ir.forecast_end_date) });
    var body = "";
    if (!nom) {
      var top = ranked.sort(function (a, b) { return zones[a].rr_nat_rank - zones[b].rr_nat_rank; }).slice(0, 5);
      body += '<p class="snap-tile-l" style="margin:0 0 4px">' + esc(tr("risk_top")) + "</p>";
      body += '<table class="snap-table"><tbody>' + top.map(function (k) {
        var z = zones[k];
        return "<tr><td class=\"num\" style=\"width:1.5em;text-align:left;color:#9c968b\">" + z.rr_nat_rank + "</td>" +
          '<td><button type="button" class="snap-inline" data-zone="' + esc(k) + '">' + esc(global.zoneDisplayName ? zoneDisplayName(k) : k) + "</button>" +
          '<span class="sub">' + esc(z.province || "") + "</span></td>" +
          '<td class="num">' + pctv(100 * z.p_case_invasion, 1) + "</td></tr>";
      }).join("") + "</tbody></table>";
      body += '<p class="snap-note">' + esc(tr("risk_prob")) + " · " + esc(trf("risk_rank_sub", {})) + "</p>";
    } else {
      var z = zones[nom];
      if (!z) {
        body += '<p class="snap-empty">' + esc(tr("risk_absent")) + "</p>";
      } else if (z.rr_nat_rank == null) {
        body += '<div class="snap-big" style="font-size:18px">' + esc(tr("risk_active")) + "</div>";
        body += '<p class="snap-note">' + esc(tr("risk_active_sub")) + "</p>";
      } else {
        body += '<div class="snap-big">' + esc(trf("risk_rank", { rank: z.rr_nat_rank, total: total })) + "</div>";
        body += '<p class="snap-note" style="margin-top:2px">' + esc(tr("risk_rank_sub")) + "</p>";
        body += '<div class="snap-bar" aria-hidden="true"><span style="width:' + Math.max(2, 100 * (1 - (z.rr_nat_rank - 1) / Math.max(1, total))) + '%;background:#6a4c93"></span></div>';
        body += '<dl class="snap-rows">' +
          "<dt>" + esc(tr("risk_prob")) + "</dt><dd>" + pctv(100 * z.p_case_invasion, 1) +
            (z.p_case_lo != null ? ' <span class="snap-tile-s">(' + pctv(100 * z.p_case_lo, 1) + "–" + pctv(100 * z.p_case_hi, 1) + ")</span>" : "") + "</dd>" +
          (z.priority_rank != null ? "<dt>" + esc(tr("risk_priority")) + "</dt><dd>" + num(z.priority_rank) + "</dd>" : "") +
          "</dl>";
      }
    }
    body += '<p style="margin:8px 0 0"><a class="snap-link-a" href="spatial-risk.html">' + esc(tr("risk_open")) + " →</a></p>";
    return card("snap-risk", tr("risk_title"), body, { asof: asof });
  }

  // ── Contact tracing ────────────────────────────────────────────────────
  function ctCard(nom) {
    var ct = S.ct;
    var asof = (S.asof || {}).ct ? trf("ct_asof", { date: fmtDate(S.asof.ct) }) : "";
    if (!ct || !ct.headline) return card("snap-ct", tr("ct_title"), '<p class="snap-empty">' + esc(tr("ct_none")) + "</p>", { asof: asof });
    var hl = ct.headline, nat = ct.national || {};
    var natFu = hl.fu_contacts ? 100 * hl.fu_complete / hl.fu_contacts : null;
    var body = "";
    function rows(r) {
      return '<dl class="snap-rows">' + r.map(function (x) { return "<dt>" + esc(x[0]) + "</dt><dd>" + x[1] + "</dd>"; }).join("") + "</dl>";
    }
    if (!nom) {
      body += '<div class="snap-big">' + pctv(natFu, 1) + " <small>" + esc(tr("ct_fu")) + "</small></div>";
      body += '<div class="snap-bar"><span style="width:' + (natFu || 0) + '%"></span></div>';
      body += rows([
        [tr("ct_contacts"), num(hl.contacts)],
        [tr("ct_fu_n"), num(hl.fu_complete) + " / " + num(hl.fu_contacts)],
        [tr("ct_known"), pctv(hl.prev_contact_pct, 1)],
        [tr("ct_source"), pctv(nat.pct_cases_source, 1)],
        [tr("ct_med"), num(nat.med_contacts)]
      ]);
    } else {
      var zc = ((S.zones || {})[nom] || {}).ct || null;
      var province = global.zoneProvince ? zoneProvince(nom) : null;
      var pr = province && ct.provinces ? ct.provinces[province] : null;
      if (zc && zc.fu_n) {
        var zfu = 100 * zc.fu_k / zc.fu_n;
        body += '<div class="snap-big">' + pctv(zfu, 1) + " <small>" + esc(tr("ct_fu")) + "</small></div>";
        body += '<div class="snap-bar"><span style="width:' + zfu + '%"></span></div>';
        var r = [[tr("ct_fu_n"), num(zc.fu_k) + " / " + num(zc.fu_n)]];
        if (zc.cases) {
          r.push([tr("ct_known"), pct(zc.prev_contact, zc.cases)]);
          r.push([tr("ct_source"), pct(zc.became_source, zc.cases)]);
        }
        body += rows(r);
        if (natFu != null) {
          body += '<p class="snap-note">' + esc(trf(zfu >= natFu ? "ct_above" : "ct_below", { pct: pctv(natFu, 1) })) + "</p>";
        }
      } else {
        body += '<p class="snap-note" style="margin-top:0">' + esc(tr("ct_zone_none")) + "</p>";
      }
      if (pr) {
        body += '<p class="snap-tile-l" style="margin:10px 0 0;font-weight:600">' + esc(trf("ct_province", { province: province })) + "</p>";
        body += rows([
          [tr("ct_contacts"), num(pr.contacts)],
          [tr("ct_fu"), pctv(pr.pct_fu_complete, 1)],
          [tr("ct_known"), pctv(pr.pct_cases_prev_contact, 1)],
          [tr("ct_source"), pctv(pr.pct_cases_source, 1)]
        ]);
      }
    }
    body += '<p style="margin:8px 0 0"><a class="snap-link-a" href="surveillance-testing.html">' + esc(tr("ct_open")) + " →</a></p>";
    return card("snap-ct", tr("ct_title"), body, { asof: asof });
  }

  // ── Laboratories ───────────────────────────────────────────────────────
  function labsCard(nom) {
    var labs = S.labs || [];
    var asof = (S.asof || {}).testing ? trf("chart_asof", { date: fmtDate(S.asof.testing) }) : "";
    if (!labs.length && !S.national) return card("snap-labs", tr("labs_title"), '<p class="snap-empty">' + esc(tr("no_data")) + "</p>", { wide: true, asof: asof });
    var list, lead = "";
    if (!nom) {
      list = labs;
      var nt = (S.national || {}).testing;
      if (nt) lead = trf("labs_national", { n: num(nt.n), pct: pct(nt.pos, nt.n) });
    } else {
      list = labs.filter(function (l) { return l.health_zone === nom; });
      var zt = ((S.zones || {})[nom] || {}).testing;
      if (zt) lead = trf("labs_residents", { n: num(zt.n), pct: pct(zt.pos, zt.n) });
    }
    var body = lead ? '<p class="snap-tile-l" style="margin:0 0 6px">' + esc(lead) + "</p>" : "";
    if (!list.length) {
      body += '<p class="snap-empty">' + esc(tr("labs_none")) + "</p>";
    } else {
      var rd = S.recent_days || 14;
      body += '<div class="snap-table-wrap"><table class="snap-table"><thead><tr>' +
        "<th>" + esc(tr("labs_col_lab")) + '</th><th class="num">' + esc(tr("labs_col_samples")) +
        '</th><th class="num">' + esc(tr("labs_col_pos")) + '</th><th class="num">' + esc(trf("labs_col_recent", { n: rd })) +
        '</th><th class="num">' + esc(tr("labs_col_last")) + "</th></tr></thead><tbody>" +
        list.map(function (l) {
          var where = l.health_zone && !nom ? '<span class="sub">' + esc(l.health_zone) + (l.province ? ", " + esc(l.province) : "") + "</span>" : "";
          return "<tr><td>" + esc(l.label) + where + "</td>" +
            '<td class="num">' + num(l.total_n) + "</td>" +
            '<td class="num">' + pct(l.total_pos, l.total_n) + "</td>" +
            '<td class="num">' + num(l.recent_n) + (l.recent_n ? '<span class="sub">' + pct(l.recent_pos, l.recent_n) + "</span>" : "") + "</td>" +
            '<td class="num">' + esc(l.last ? fmtShort(C.dayMs(l.last)) : "—") + "</td></tr>";
        }).join("") + "</tbody></table></div>";
      body += '<p class="snap-note">' + esc(trf("labs_note", { n: rd })) + "</p>";
    }
    return card("snap-labs", tr("labs_title"), body, { wide: true, asof: asof });
  }

  // ── News feed (Public Health Context) ──────────────────────────────────
  function newsItems(nom) {
    var ctx = global.phrContext ? phrContext() : { national: [], by_nom: {} };
    var rollups = ctx.national || [];
    var province = nom && global.zoneProvince ? zoneProvince(nom) : null;
    var items = rollups.filter(function (p) {
      if (p.scope === "national") return true;
      if (p.scope === "provincial") return nom ? (province && p.province === province) : true;
      return false;
    });
    if (nom) items = items.concat(((ctx.by_nom || {})[nom] || []).map(function (p) {
      return Object.assign({}, p, { scope: "zone" });
    }));
    return global.sortContextPillarsByDate ? sortContextPillarsByDate(items) : items;
  }

  function newsCard(nom) {
    var all = newsItems(nom);
    var counts = { national: 0, provincial: 0, zone: 0 };
    all.forEach(function (p) { if (counts[p.scope] != null) counts[p.scope]++; });
    if (newsFilter !== "all" && !counts[newsFilter]) newsFilter = "all";
    var items = newsFilter === "all" ? all : all.filter(function (p) { return p.scope === newsFilter; });
    var body = "";
    if (!all.length) {
      body = '<p class="snap-empty">' + esc(tr("news_none")) + "</p>";
    } else {
      var chips = [["all", tr("news_all"), all.length], ["national", tr("news_national"), counts.national],
                   ["provincial", tr("news_provincial"), counts.provincial], ["zone", tr("news_zone"), counts.zone]]
        .filter(function (c) { return c[0] === "all" || c[2] > 0; });
      body += '<div class="snap-filter" role="group" style="margin:0 0 10px">' + chips.map(function (c) {
        return '<button type="button" class="snap-chip' + (newsFilter === c[0] ? " active" : "") + '" data-news-filter="' + c[0] +
          '" aria-pressed="' + (newsFilter === c[0]) + '">' + esc(c[1]) + " (" + c[2] + ")</button>";
      }).join("") + "</div>";
      var shown = newsExpanded ? items : items.slice(0, NEWS_INITIAL);
      body += shown.map(function (p) { return renderContextPillarHtml(p); }).join("");
      if (items.length > NEWS_INITIAL) {
        body += '<button type="button" class="snap-link" data-news-toggle="1">' +
          esc(newsExpanded ? tr("news_less") : trf("news_more", { n: items.length })) + "</button>";
      }
    }
    return '<section class="snap-card snap-wide snap-news" id="snap-news"><h3><span>' + esc(tr("news_title")) + "</span></h3>" + body + "</section>";
  }

  // ── Recent trend (top of the rail) ─────────────────────────────────────
  // Last 14 COMPLETE days vs the 14 before, from the same onset curve as the
  // chart. "Complete" stops the day before S.incomplete_from: the last few
  // days of the line list are still filling in, and comparing them would
  // show a spurious fall every time.
  var TREND_DAYS = 14;
  var TREND_MIN_CASES = 5;   // below this in both windows, a % change is noise

  function sumCases(cv, fromIso, toIso) {
    var tot = 0;
    cv.obs.forEach(function (v, i) {
      var d = addDays(cv.start, i);
      if (d >= fromIso && d <= toIso) tot += (v || 0) + ((cv.imp || [])[i] || 0);
    });
    return tot;
  }
  function posAt(cv, iso) {
    // Latest rolling-positivity value on or before `iso`, within 3 days.
    if (!cv.pos) return null;
    var best = null;
    cv.pos.dates.forEach(function (d, i) {
      if (d <= iso && d >= addDays(iso, -3) && cv.pos.mean[i] != null) best = cv.pos.mean[i];
    });
    return best;
  }
  function arrow(delta, upIsBad) {
    if (delta == null || delta === 0) return '<span class="snap-trend-flat">→</span>';
    var bad = upIsBad ? delta > 0 : delta < 0;
    return '<span class="' + (bad ? "snap-trend-bad" : "snap-trend-good") + '">' + (delta > 0 ? "▲" : "▼") + "</span>";
  }

  function trendCard(nom) {
    var cv = curveFor(nom);
    var asofCases = (S.asof || {}).cases;
    if (nom && asofCases && (!cv || !cv.obs)) {
      // No onset-dated cases at all for this zone in the line list.
      return card("snap-trend", tr("trend_title"), '<div class="snap-trend-v">0</div><div class="snap-tile-l">' +
        esc(tr("trend_none")) + "</div>", { wide: true });
    }
    if (!cv || !cv.obs || !asofCases) {
      return card("snap-trend", tr("trend_title"), '<p class="snap-empty">' + esc(tr("chart_empty")) + "</p>", { wide: true });
    }
    var end = S.incomplete_from ? addDays(S.incomplete_from, -1) : asofCases;
    var curFrom = addDays(end, -(TREND_DAYS - 1));
    var prevTo = addDays(curFrom, -1), prevFrom = addDays(prevTo, -(TREND_DAYS - 1));
    var cur = sumCases(cv, curFrom, end), prev = sumCases(cv, prevFrom, prevTo);
    var range = trf("trend_range", { from: fmtShort(C.dayMs(curFrom)), to: fmtShort(C.dayMs(end)) });

    var casesHtml;
    if (!cur && !prev) {
      casesHtml = '<div class="snap-trend-v">0</div><div class="snap-tile-l">' + esc(tr("trend_none")) + "</div>";
    } else {
      var change = "";
      if (Math.max(cur, prev) >= TREND_MIN_CASES && prev > 0) {
        var pc = Math.round(100 * (cur - prev) / prev);
        change = " " + arrow(cur - prev, true) + " " + Math.abs(pc).toLocaleString(loc()) + "%";
      } else if (prev === 0 && cur > 0) {
        change = " " + arrow(1, true) + " " + esc(tr("trend_new"));
      } else {
        change = ' <span class="snap-tile-s">' + esc(tr("trend_few")) + "</span>";
      }
      casesHtml = '<div class="snap-trend-v">' + num(cur) + change + "</div>" +
        '<div class="snap-tile-l">' + esc(trf("trend_cases", { n: TREND_DAYS })) + " · " + esc(trf("trend_vs", { n: num(prev), n2: TREND_DAYS })) + "</div>";
    }

    var pNow = posAt(cv, end), pThen = posAt(cv, addDays(end, -TREND_DAYS));
    var posHtml = "";
    if (pNow != null) {
      var pts = pThen != null ? Math.round(100 * (pNow - pThen)) : null;
      posHtml = '<div class="snap-trend-item"><div class="snap-trend-v">' + pctv(100 * pNow, 0) +
        (pts != null ? " " + arrow(pts, true) + " " + Math.abs(pts) + " " + esc(tr("trend_points")) : "") + "</div>" +
        '<div class="snap-tile-l">' + esc(tr("trend_pos")) +
        (pThen != null ? " · " + esc(trf("trend_pos_vs", { pct: pctv(100 * pThen, 0) })) : "") + "</div></div>";
    }
    var body = '<div class="snap-trend"><div class="snap-trend-item">' + casesHtml + "</div>" + posHtml + "</div>" +
      '<p class="snap-note">' + esc(trf("trend_note", { date: fmtDate(S.incomplete_from || asofCases) })) + "</p>";
    return card("snap-trend", tr("trend_title"), body, { wide: true, asof: range });
  }

  // ── Top incoming mobility sources (Flowminder) ─────────────────────────
  // Same catalogue as the map's flow arrows. Zone view: where people coming
  // INTO this zone travel from, flagged by whether the origin has confirmed
  // cases. National view: the largest flows from zones with confirmed cases
  // into zones without any.
  var MOB_TOP = 5;
  function zoneCases(nom) { return ((ZONE_DATA[nom] || {}).confirmed_cases) || 0; }
  function zname(nom) { return global.zoneDisplayName ? zoneDisplayName(nom) : nom; }
  function mobilityPeriod() {
    var ym = String(PAYLOAD.flowminder_latest_yyyymm || "");
    if (!/^\d{6}$/.test(ym)) return "";
    var d = new Date(Date.UTC(+ym.slice(0, 4), +ym.slice(4, 6) - 1, 1));
    return "Flowminder, " + d.toLocaleDateString(dateLoc(), { month: "long", year: "numeric", timeZone: "UTC" });
  }
  function mobRow(nom, count, max, sub) {
    var cases = zoneCases(nom);
    return "<tr><td>" + '<button type="button" class="snap-inline" data-zone="' + esc(nom) + '">' + esc(zname(nom)) + "</button>" +
      '<span class="sub">' + sub + "</span>" +
      '<div class="snap-bar" style="margin:3px 0 0"><span style="width:' + Math.max(2, 100 * count / max) + '%;background:#2c7fb8"></span></div></td>' +
      '<td class="num">' + num(count) + "</td></tr>";
  }

  function mobilityCard(nom) {
    var cat = ((PAYLOAD.flow_catalogs || {}).flowminder_latest) || null;
    var asof = mobilityPeriod();
    if (!cat || !cat.in_by_dest) return card("snap-mob", tr("mob_title"), '<p class="snap-empty">' + esc(tr("no_data")) + "</p>", { asof: asof });
    var body = "";
    if (nom) {
      var ins = (cat.in_by_dest[nom] || []).slice().sort(function (a, b) { return b[1] - a[1]; });
      if (!ins.length) {
        body = '<p class="snap-empty">' + esc(tr("mob_none")) + "</p>";
      } else {
        var total = ins.reduce(function (a, p) { return a + (Number(p[1]) || 0); }, 0);
        var fromAffected = ins.reduce(function (a, p) { return a + (zoneCases(p[0]) > 0 ? (Number(p[1]) || 0) : 0); }, 0);
        var top = ins.slice(0, MOB_TOP), max = top[0][1] || 1;
        body += '<div class="snap-big">' + pct(fromAffected, total, 0) + " <small>" + esc(tr("mob_from_affected")) + "</small></div>";
        body += '<table class="snap-table" style="margin-top:6px"><tbody>' + top.map(function (p) {
          var c = zoneCases(p[0]);
          var sub = c > 0 ? '<span class="snap-case-tag">' + esc(trf("mob_cases", { n: num(c) })) + "</span>" : esc(tr("mob_no_cases"));
          return mobRow(p[0], p[1], max, sub);
        }).join("") + "</tbody></table>";
        body += '<p class="snap-note">' + esc(trf("mob_note_zone", { n: num(total), k: ins.length })) + "</p>";
      }
    } else {
      // Largest single flows from a case-reporting zone into a zone without cases.
      var edges = [];
      Object.keys(cat.out_by_origin || {}).forEach(function (o) {
        if (!(zoneCases(o) > 0)) return;
        (cat.out_by_origin[o] || []).forEach(function (p) {
          if (zoneCases(p[0]) > 0) return;
          edges.push([o, p[0], Number(p[1]) || 0]);
        });
      });
      edges.sort(function (a, b) { return b[2] - a[2]; });
      var topE = edges.slice(0, MOB_TOP);
      if (!topE.length) {
        body = '<p class="snap-empty">' + esc(tr("mob_none")) + "</p>";
      } else {
        var maxE = topE[0][2] || 1;
        body += '<p class="snap-tile-l" style="margin:0 0 4px">' + esc(tr("mob_national_lead")) + "</p>";
        body += '<table class="snap-table"><tbody>' + topE.map(function (e) {
          return mobRow(e[1], e[2], maxE, esc(trf("mob_from", { zone: zname(e[0]) })));
        }).join("") + "</tbody></table>";
        body += '<p class="snap-note">' + esc(tr("mob_note_national")) + "</p>";
      }
    }
    return card("snap-mob", tr("mob_title"), body, { asof: asof });
  }

  // ── Reproduction number (Rt) ───────────────────────────────────────────
  // PAYLOAD.rt (common/rt.py): national + province series. Left: current
  // national Rt with a sparkline; right: provinces ranked by their latest
  // estimate. A zone view highlights its province's row (there are no
  // zone-level estimates).
  var COLOR_RT = "#6a4c93", COLOR_RT_BAND = "rgba(106,76,147,0.16)";
  var RT_SPARK_DAYS = 90;

  function rtLatest(e) {
    if (!e || !e.dates || !e.dates.length) return null;
    for (var i = e.dates.length - 1; i >= 0; i--) {
      if (e.mean[i] != null) return { i: i, date: e.dates[i], mean: e.mean[i], lo: e.lo[i], hi: e.hi[i] };
    }
    return null;
  }
  // Status from the 95% interval, not the mean alone.
  function rtStatus(l) {
    if (!l || l.lo == null || l.hi == null) return { cls: "rt-unc", key: "rt_uncertain" };
    if (l.lo > 1) return { cls: "rt-up", key: "rt_growing" };
    if (l.hi < 1) return { cls: "rt-down", key: "rt_declining" };
    return { cls: "rt-unc", key: "rt_uncertain" };
  }
  function f2(v) { return v == null ? "–" : Number(v).toLocaleString(loc(), { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

  function rtCard(nom) {
    var rt = PAYLOAD.rt;
    if (!rt || !rt.national) {
      return card("snap-rt", tr("rt_title"), '<p class="snap-empty">' + esc(tr("no_data")) + "</p>", { wide: true });
    }
    var nat = rtLatest(rt.national);
    var st = rtStatus(nat);
    var then = null;
    if (nat) {
      var target = addDays(nat.date, -14);
      var j = rt.national.dates.indexOf(target);
      if (j >= 0) then = rt.national.mean[j];
    }
    var left = '<div class="snap-rt-nat">' +
      '<div class="snap-tile-l">' + esc(tr("rt_national")) + "</div>" +
      '<div class="snap-big">' + f2(nat && nat.mean) +
        ' <small>(' + f2(nat && nat.lo) + "–" + f2(nat && nat.hi) + ")</small></div>" +
      '<div><span class="snap-rt-chip ' + st.cls + '">' + esc(tr(st.key)) + "</span>" +
        (then != null ? ' <span class="snap-tile-s">' + esc(trf("rt_then", { v: f2(then) })) + "</span>" : "") + "</div>" +
      '<div class="snap-chart snap-rt-spark" id="snap-rt-spark"></div>' +
      "</div>";

    var province = nom && global.zoneProvince ? zoneProvince(nom) : null;
    var rows = Object.keys(rt.provinces || {}).map(function (p) {
      return { p: p, l: rtLatest(rt.provinces[p]) };
    }).filter(function (r) { return r.l; }).sort(function (a, b) { return b.l.mean - a.l.mean; });
    var right = '<div class="snap-rt-prov"><div class="snap-tile-l" style="margin-bottom:2px">' + esc(tr("rt_provinces")) + "</div>";
    if (!rows.length) {
      right += '<p class="snap-empty">' + esc(tr("no_data")) + "</p>";
    } else {
      right += '<table class="snap-table"><thead><tr><th>' + esc(tr("rt_col_province")) + '</th><th class="num">Rt</th><th class="num">' +
        esc(tr("rt_col_ci")) + "</th><th></th></tr></thead><tbody>" + rows.map(function (r, i) {
          var s2 = rtStatus(r.l);
          var stale = nat && r.l.date !== nat.date ? '<span class="sub">' + esc(trf("rt_asof_short", { date: fmtShort(C.dayMs(r.l.date)) })) + "</span>" : "";
          return '<tr' + (province === r.p ? ' class="snap-rt-here"' : "") + "><td>" + (i + 1) + ". " + esc(r.p) + stale + "</td>" +
            '<td class="num"><strong>' + f2(r.l.mean) + "</strong></td>" +
            '<td class="num">' + f2(r.l.lo) + "–" + f2(r.l.hi) + "</td>" +
            '<td><span class="snap-rt-chip ' + s2.cls + '">' + esc(tr(s2.key)) + "</span></td></tr>";
        }).join("") + "</tbody></table>";
    }
    if (nom) {
      var has = province && (rt.provinces || {})[province];
      right += '<p class="snap-note">' + esc(has ? trf("rt_zone_note", { province: province })
        : trf("rt_zone_none", { province: province || "—" })) + "</p>";
    }
    right += "</div>";
    var body = '<div class="snap-rt">' + left + right + "</div>" +
      '<p class="snap-note">' + esc(tr("rt_note")) + ' <a class="snap-link-a" href="trends.html">' + esc(tr("rt_open")) + " →</a></p>";
    var asof = nat ? trf("rt_asof", { date: fmtDate(nat.date), run: fmtDate(rt.run_date) }) : "";
    return card("snap-rt", tr("rt_title"), body, { wide: true, asof: asof });
  }

  function drawRtSpark() {
    var host = document.getElementById("snap-rt-spark");
    var e = PAYLOAD.rt && PAYLOAD.rt.national;
    if (!host || !e || !e.dates.length) return;
    host.innerHTML = "";
    var last = e.dates[e.dates.length - 1];
    var from = addDays(last, -RT_SPARK_DAYS);
    var idx = [];
    e.dates.forEach(function (d, i) { if (d >= from) idx.push(i); });
    var dates = idx.map(function (i) { return e.dates[i]; });
    var pick = function (arr) { return idx.map(function (i) { return arr[i]; }); };
    var lo = pick(e.lo), hi = pick(e.hi), mean = pick(e.mean);
    var W = Math.max(200, host.clientWidth || 300), H = host.clientHeight || 96;
    var svg = C.svgEl("svg", { viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none", role: "img", "aria-label": tr("rt_title") });
    host.appendChild(svg);
    var yMax = Math.max(2, Math.max.apply(null, hi.filter(function (v) { return v != null; }).concat([0])));
    var fr = C.frame(svg, {
      width: W, height: H, pad: { left: 26, right: 8, top: 6, bottom: 18 },
      xStart: dates[0], xEnd: last, yMax: yMax, allowFractional: true,
      fmtY: function (v) { return String(Math.round(v * 10) / 10); }
    });
    var y1 = fr.yToPx(1);
    svg.appendChild(C.svgEl("line", { x1: fr.left, x2: fr.right, y1: y1, y2: y1, stroke: "#2a2a27", "stroke-width": 1, "stroke-dasharray": "4,3", opacity: 0.5 }));
    C.ciBand(svg, fr, dates, lo, hi, COLOR_RT_BAND);
    C.line(svg, fr, dates, mean, COLOR_RT, 1.5);
    C.tooltip(host, svg, fr, function (day) {
      var i = dates.indexOf(day);
      if (i < 0 || mean[i] == null) return null;
      return '<div class="dc-tip-d">' + esc(fmtDate(day)) + "</div><div>Rt " + f2(mean[i]) +
        ' <span class="dc-tip-ci">(' + f2(lo[i]) + "–" + f2(hi[i]) + ")</span></div>";
    });
  }

  // ── Header ─────────────────────────────────────────────────────────────
  function header(nom) {
    var title = document.getElementById("snap-title");
    var sub = document.getElementById("snap-sub");
    var clear = document.getElementById("snap-clear");
    if (clear) { clear.hidden = !nom; clear.textContent = tr("back_national"); }
    if (!nom) {
      if (title) title.textContent = tr("national_title");
      if (sub) sub.textContent = tr("national_sub");
      return;
    }
    if (title) title.textContent = global.zoneDisplayName ? zoneDisplayName(nom) : nom;
    var z = ZONE_DATA[nom] || {};
    var bits = [];
    var province = global.zoneProvince ? zoneProvince(nom) : null;
    if (province) bits.push(trf("zone_sub_province", { province: province }));
    if (z.worldpop__pop_count__pop_count) bits.push(trf("zone_pop", { n: num(z.worldpop__pop_count__pop_count) }));
    if (z.grid3_healthsites__healthsite_count__healthsite_count != null) {
      bits.push(trf("zone_facilities", { n: num(z.grid3_healthsites__healthsite_count__healthsite_count) }));
    }
    if (sub) sub.textContent = bits.join(" · ");
  }

  function render(nom) {
    var body = document.getElementById("snap-body");
    if (!body) return;
    if (nom !== current) { newsFilter = "all"; newsExpanded = false; }
    var changed = nom !== current;
    current = nom || null;
    header(current);
    // Risk / contact tracing / mobility share one row container so they go
    // straight from a column to three across, never 2 + 1 (CSS .snap-trio).
    body.innerHTML = trendCard(current) + kpis(current) + chartCard(current) + rtCard(current) +
      '<div class="snap-trio">' + riskCard(current) + ctCard(current) + mobilityCard(current) + "</div>" +
      labsCard(current) + newsCard(current);
    drawChart(current);
    drawRtSpark();
    if (changed) {
      var panel = document.getElementById("snapshot-panel");
      if (panel) panel.scrollTop = 0;
    }
  }

  function rerenderNews() {
    var el = document.getElementById("snap-news");
    if (!el) return;
    var tmp = document.createElement("div");
    tmp.innerHTML = newsCard(current);
    el.replaceWith(tmp.firstChild);
  }

  // Delegated: the rail body is rebuilt on every render.
  (function wire() {
    var panel = document.getElementById("snapshot-panel");
    if (!panel) return;
    panel.addEventListener("click", function (e) {
      var el = e.target.closest ? e.target.closest("button") : null;
      if (!el || !panel.contains(el)) return;
      if (el.id === "snap-clear") { global.setMapSelection(null); return; }
      if (el.dataset.zone) { global.setMapSelection(el.dataset.zone); return; }
      if (el.dataset.newsFilter) { newsFilter = el.dataset.newsFilter; newsExpanded = false; rerenderNews(); return; }
      if (el.dataset.newsToggle) { newsExpanded = !newsExpanded; rerenderNews(); }
    });
  })();

  // ── Map / rail split (mirrors wireTrendsSplitUi in engine.js) ──────────
  (function wireSplit() {
    var handle = document.getElementById("snapshot-split-handle");
    var MIN = 30, MAX = 75, DEF = 58, KEY = "bdbv_snapshot_panel_width_pct";
    var redrawTimer = null;
    function clamp(p) { return Math.max(MIN, Math.min(MAX, p)); }
    function scheduleRedraw() {
      clearTimeout(redrawTimer);
      redrawTimer = setTimeout(function () { drawChart(current); drawRtSpark(); }, 120);
    }
    function apply(p, invalidate) {
      var v = clamp(p);
      document.documentElement.style.setProperty("--snapshot-panel-width", v + "%");
      if (handle) handle.setAttribute("aria-valuenow", String(Math.round(v)));
      try { localStorage.setItem(KEY, String(v)); } catch (e) {}
      if (invalidate) { invalidateMap(); scheduleRedraw(); }
      return v;
    }
    function stored() {
      try {
        var raw = localStorage.getItem(KEY);
        var n = raw == null || raw === "" ? DEF : Number(raw);
        return isFinite(n) ? n : DEF;
      } catch (e) { return DEF; }
    }
    apply(stored(), false);
    global.addEventListener("resize", scheduleRedraw);
    if (!handle) return;
    handle.setAttribute("aria-valuemin", String(MIN));
    handle.setAttribute("aria-valuemax", String(MAX));
    var dragging = false;
    function fromX(x) {
      var w = global.innerWidth || document.documentElement.clientWidth || 1;
      return clamp(((w - x) / w) * 100);
    }
    function move(e) {
      if (!dragging) return;
      if (e.cancelable) e.preventDefault();
      var x = e.touches && e.touches[0] ? e.touches[0].clientX : e.clientX;
      apply(fromX(x), false);
    }
    function up() {
      if (!dragging) return;
      dragging = false;
      document.body.classList.remove("snapshot-splitting");
      global.removeEventListener("mousemove", move);
      global.removeEventListener("mouseup", up);
      global.removeEventListener("touchmove", move);
      global.removeEventListener("touchend", up);
      global.removeEventListener("touchcancel", up);
      invalidateMap();
      drawChart(current);
      drawRtSpark();
    }
    function down(e) {
      dragging = true;
      document.body.classList.add("snapshot-splitting");
      var x = e.touches && e.touches[0] ? e.touches[0].clientX : e.clientX;
      apply(fromX(x), false);
      global.addEventListener("mousemove", move);
      global.addEventListener("mouseup", up);
      global.addEventListener("touchmove", move, { passive: false });
      global.addEventListener("touchend", up);
      global.addEventListener("touchcancel", up);
      if (e.cancelable) e.preventDefault();
    }
    handle.addEventListener("mousedown", down);
    handle.addEventListener("touchstart", down, { passive: false });
    handle.addEventListener("keydown", function (e) {
      var cur = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--snapshot-panel-width")) || DEF;
      if (e.key === "ArrowLeft") apply(cur + 2, true);
      else if (e.key === "ArrowRight") apply(cur - 2, true);
      else if (e.key === "Home") apply(DEF, true);
      else return;
      e.preventDefault();
    });
  })();

  // ── One compact map widget: LAYER + legend ─────────────────────────────
  // The shared markup (common/chrome.py) has #controls and #legend as two
  // floating panels. On Snapshot the map pane is narrower than the summary
  // rail, so the legend's body moves into #controls, under the layer select,
  // and #legend is hidden (CSS: body.snapshot-combined-legend). Nodes are moved,
  // not copied, so engine.js's updateLegend() keeps writing to the same ids.
  // #legend-title stays behind in the hidden #legend: the select already
  // names the layer.
  (function combineLayerAndLegend() {
    var controls = document.getElementById("controls");
    var legend = document.getElementById("legend");
    var select = document.getElementById("layer-select");
    var lbody = legend && legend.querySelector(".panel-body");
    if (!controls || !lbody || !select) return;
    var wrap = document.createElement("div");
    wrap.id = "controls-legend";
    while (lbody.firstChild) wrap.appendChild(lbody.firstChild);
    select.parentNode.insertBefore(wrap, select.nextSibling);
    document.body.classList.add("snapshot-combined-legend");
  })();

  global.SnapshotSummary = { render: render };
  // engine.js rendered before this file loaded; draw the initial state now,
  // and let Leaflet pick up the narrowed map pane.
  invalidateMap();
  render(typeof mapSelectedNom !== "undefined" ? mapSelectedNom : null);
})(window);
