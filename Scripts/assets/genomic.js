// Genomic Epidemiology tab — Phase 3 seam skeleton.
// Reads the page-scoped `genomic` payload slice and renders placeholder content
// into the rail, proving data flows through the contribution seam end-to-end.
// Shaped as a mount()/unmount() tab module for SPA-readiness; real panels,
// coordinator, and shared-map integration come in later phases.
(function () {
  "use strict";

  function setText(id, t) { var e = document.getElementById(id); if (e) e.textContent = t; }

  // Active toggle = accent colour + light band shade, set inline `!important` so it
  // beats the brand theme layer's `!important` button rules. Cleared when off.
  function applyToggleStyle(btn, on, color, band) {
    if (!btn) return;
    btn.classList.toggle("active", on);
    if (on) {
      btn.style.setProperty("color", color, "important");
      btn.style.setProperty("border-color", color, "important");
      btn.style.setProperty("background", band, "important");
    } else {
      btn.style.removeProperty("color");
      btn.style.removeProperty("border-color");
      btn.style.removeProperty("background");
    }
    btn.setAttribute("aria-pressed", String(on));
  }

  function readGenomic() {
    var el = document.getElementById("payload");
    if (!el) return null;
    try { return (JSON.parse(el.textContent) || {}).genomic || null; } catch (e) { return null; }
  }

  // Terracotta accent for the tree's own toolbar toggles (Legend / Node Bars /
  // Tip Labels), matching the rail's warm accent.
  var TREE_ACCENT = "#9b7d4e", TREE_ACCENT_BAND = "rgba(155,125,78,0.16)";

  // --- Phylogeny (PearTree) --------------------------------------------------
  // A defined categorical zone palette (Phase 0: passed at embed init via
  // settings.annotationPalettes, the only per-zone colour hook the bundle exposes).
  // Kelly-style maximally-distinct hues, all legible on the light tree canvas; the
  // same map drives the legend, so tips and legend can never disagree. Cycled if a
  // future tree carries >COLOURS zones (16 here covers the current 16).
  var ZONE_COLOURS = [
    "#BE0032", "#0067A5", "#008856", "#F38400", "#875692", "#F6A600",
    "#E68FAC", "#654522", "#848482", "#604E97", "#B3446C", "#882D17",
    "#8DB600", "#E25822", "#2B3D26", "#C2B280"
  ];

  function realZone(z) { return (z && z !== "null") ? z : null; }
  function up(s) { return (s || "").toUpperCase().trim(); }

  // {map: {zone->hex}, order: [zone…] by descending tip count, counts: {zone->n}}.
  // Ordering by count gives the most-sampled zones the leading (most separable) hues.
  function buildZonePalette(tips) {
    var counts = {};
    (tips || []).forEach(function (t) {
      var z = realZone(t.health_zone);
      if (z) counts[z] = (counts[z] || 0) + 1;
    });
    var order = Object.keys(counts).sort(function (a, b) {
      return counts[b] - counts[a] || (a < b ? -1 : 1);
    });
    var map = {};
    order.forEach(function (z, i) { map[z] = ZONE_COLOURS[i % ZONE_COLOURS.length]; });
    return { map: map, order: order, counts: counts };
  }

  function renderZoneLegend(pal) {
    var box = document.getElementById("gen-tree-legend-box");
    if (!box) return;
    box.replaceChildren();
    pal.order.forEach(function (z) {
      var row = document.createElement("div"); row.className = "gen-legend-row";
      var sw = document.createElement("span"); sw.className = "gen-legend-sw";
      sw.style.background = pal.map[z];
      var lb = document.createElement("span"); lb.className = "gen-legend-lb";
      lb.textContent = z + " (" + pal.counts[z] + ")";
      row.appendChild(sw); row.appendChild(lb); box.appendChild(row);
    });
  }

  var TREE_PAD_LEFT = 20, TREE_PAD_RIGHT = 20;

  // Embeds the phylogeny via the global PearTree bundle. Returns the tree instance
  // (async, via a Promise) or null if the bundle/data is missing. The coordinator
  // (Phase 5b) consumes the returned instance for tip selection + view-lock.
  function createTreePanel(containerId, genomic) {
    var host = document.getElementById(containerId);
    if (!host) return Promise.resolve(null);
    if (!window.PearTreeEmbed) { host.textContent = "Phylogeny renderer failed to load."; return Promise.resolve(null); }
    if (!genomic || !genomic.tree) { host.textContent = "No phylogeny data."; return Promise.resolve(null); }

    var meta = genomic.meta || {};
    var pal = buildZonePalette(genomic.tips || []);
    renderZoneLegend(pal);
    host.textContent = "";   // drop the "Loading…" placeholder before embedding

    return window.PearTreeEmbed.embed({
      container: containerId,
      tree: genomic.tree,           // inline NEXUS text (Phase 0: the `tree` key; no fetch)
      filename: "Ituri.ptree",
      height: "100%",               // fill the card's tree area (which is sized in CSS)
      ui: {
        theme: "light",
        // Keep-list of toolbar sections; the omitted editing groups (annotations,
        // colour, order, rotate, reroot, hideShow, navigation) stay hidden.
        toolbarSections: ["fileOps", "nodeInfo", "zoom", "filter", "panels"]
      },
      settings: {
        theme: "O'Toole",                    // light built-in palette (branch/tip/axis/bg)
        tipLabelShow: "health_zone",         // annotation-keyed → init-only setting
        tipColourBy: "health_zone",          // colour tips by zone…
        annotationPalettes: { health_zone: pal.map },   // …with OUR defined palette
        axisShow: "time",
        axisDateAnnotation: "date",
        axisDateFormat: "dd MMM yyyy",
        axisMajorInterval: "auto",
        axisMinorInterval: "auto",
        axisMajorLabelFormat: "component",
        axisMinorLabelFormat: "component",
        nodeBarsEnabled: "on",               // 95% HPD internal-node age bars, on by default
        nodeBarsWidth: "3",
        // Yellow selection highlight (matches the map's selected marker); init-only keys.
        selectedTipFillColor: "#f2c84b", selectedTipStrokeColor: "#9a7a16",
        selectedTipStrokeWidth: "2", selectedTipStrokeOpacity: "1",
        selectedTipFillOpacity: "0.65", selectedTipGrowthFactor: "1.9", selectedTipMinSize: "6",
        selectedNodeFillColor: "#f2c84b", selectedNodeStrokeColor: "#9a7a16",
        selectedNodeStrokeWidth: "2", selectedNodeStrokeOpacity: "1",
        selectedNodeFillOpacity: "0.65", selectedNodeGrowthFactor: "1.9", selectedNodeMinSize: "6",
        tipHoverFillColor: "#5b86b3", tipHoverStrokeColor: "#33567a",
        // Alignment-critical geometry (kept regardless of theme).
        paddingLeft: String(TREE_PAD_LEFT), paddingRight: String(TREE_PAD_RIGHT),
        rootStubLength: "0", rootStemPct: "0"
      }
    }).then(function (tree) {
      // Marker/label sizes: applyTheme drives these, so push them AFTER the theme.
      // (applySettings key for the tip-label font is `fontSize`, not tipLabelFontSize.)
      var SHAPE_SIZES = { nodeSize: "3", tipSize: "4", fontSize: "10" };
      tree.applySettings(SHAPE_SIZES);
      tree.onTreeLoad(function () { tree.fitToWindow(); tree.applySettings(SHAPE_SIZES); });

      // Swallow PearTree's double-click "drill into subtree" gesture (no embed opt for
      // it) on the canvas, in the capture phase before its own handler runs.
      host.addEventListener("dblclick", function (e) {
        if (e.target && e.target.id === "tree-canvas") { e.stopPropagation(); e.preventDefault(); }
      }, true);

      // Wheel over the tree: scroll the RAIL when the tree is fitted, but let
      // PearTree PAN the tree when it's zoomed in. PearTree pans vertically on the
      // wheel and preventDefaults it (trapping the rail scroll), and its drag-pan
      // needs Space held — so when fitted we intercept in the capture phase and stop
      // propagation (native rail scroll proceeds), and when zoomed in we let the
      // event reach PearTree so there's a way to move around. Zoom is only driven by
      // the toolbar buttons (wheel-zoom never reaches PearTree while fitted), so we
      // track the zoom level from their clicks.
      var zoomLevel = 0;   // 0 = fitted; > 0 = zoomed in
      function bindZoom(id, delta) {
        var b = document.getElementById(id);
        if (b) b.addEventListener("click", function () {
          zoomLevel = delta === 0 ? 0 : Math.max(0, zoomLevel + delta);
        });
      }
      bindZoom("btn-zoom-in", 1);
      bindZoom("btn-zoom-out", -1);
      bindZoom("btn-fit", 0);           // "Fit all" → back to fitted
      host.addEventListener("wheel", function (e) {
        if (zoomLevel <= 0) e.stopPropagation();   // fitted → rail scrolls; zoomed → PearTree pans
      }, true);

      wireTreeToggles(tree, pal);
      return makeTreeApi(tree, meta);
    }).catch(function (err) {
      host.textContent = "Phylogeny failed to render.";
      if (window.console) console.warn("[genomic] tree embed failed:", err);
      return null;
    });
  }

  // App-facing wrapper over the raw PearTree instance (mirrors the source
  // tree-panel's returned interface). PearTree's setSelection keys on internal
  // node ids, so tips are selected via the `accession` annotation (== leaf name),
  // additively. The view/band methods seed the Ne/distribution coupling (Phase 5b
  // increment 2). `_raw` is kept for debugging.
  function makeTreeApi(tree, meta) {
    return {
      _raw: tree,
      selectByNames: function (names) {
        (names || []).forEach(function (nm, i) { tree.selectByAnnotation("accession", nm, { additive: i > 0 }); });
      },
      clear: function () { tree.setSelection([]); },
      onSelect: function (cb) { return tree.onNodeSelect(cb); },
      onViewChange: function (cb) { return tree.onViewChange(cb); },
      getViewTransform: function () { return tree.getViewTransform ? tree.getViewTransform() : null; },
      meta: meta
    };
  }

  // The three header toggles. Legend drives OUR legend box; Node Bars / Tip Labels
  // drive PearTree's internal selects (applySettings can't push those to the renderer
  // at runtime), dispatching the change each re-renders on.
  function wireTreeToggles(tree, pal) {
    var legendOn = false;
    var legendBtn = document.getElementById("gen-tree-legend");
    var legendBox = document.getElementById("gen-tree-legend-box");
    // Pin the legend just below PearTree's toolbar (whose height changes as it
    // wraps on a narrow rail) and cap its height to the canvas area so it scrolls.
    function positionLegend() {
      if (!legendBox || legendBox.hidden) return;
      var cc = document.getElementById("canvas-container");
      var wrap = legendBox.parentElement;
      if (!cc || !wrap) return;
      var ccr = cc.getBoundingClientRect(), wr = wrap.getBoundingClientRect();
      legendBox.style.top = Math.round(ccr.top - wr.top + 4) + "px";
      legendBox.style.maxHeight = Math.max(60, Math.round(ccr.height - 8)) + "px";
    }
    function setLegend(on) {
      legendOn = on;
      if (legendBox) legendBox.hidden = !on;
      applyToggleStyle(legendBtn, on, TREE_ACCENT, TREE_ACCENT_BAND);
      if (on) positionLegend();
    }
    applyToggleStyle(legendBtn, false, TREE_ACCENT, TREE_ACCENT_BAND);
    if (legendBtn) legendBtn.addEventListener("click", function (e) { e.preventDefault(); setLegend(!legendOn); });
    // Reposition when the toolbar re-wraps (rail resize) or the tree relays out.
    if (window.ResizeObserver) {
      var tb = document.getElementById("gen-tree-body");
      if (tb) new ResizeObserver(function () { positionLegend(); }).observe(tb);
    }

    function driveSelect(id, value) {
      var sel = document.getElementById(id);
      if (!sel) return;
      sel.value = value;
      sel.dispatchEvent(new Event("change", { bubbles: true }));
    }

    var nodeBarsOn = true;
    var nodeBarsBtn = document.getElementById("gen-tree-nodebars");
    function setNodeBars(on) { nodeBarsOn = on; driveSelect("node-bars-show", on ? "on" : "off"); applyToggleStyle(nodeBarsBtn, on, TREE_ACCENT, TREE_ACCENT_BAND); }
    applyToggleStyle(nodeBarsBtn, true, TREE_ACCENT, TREE_ACCENT_BAND);
    if (nodeBarsBtn) nodeBarsBtn.addEventListener("click", function (e) { e.preventDefault(); setNodeBars(!nodeBarsOn); });

    var tipLabelsOn = true;
    var tipLabelsBtn = document.getElementById("gen-tree-tiplabels");
    function setTipLabels(on) { tipLabelsOn = on; driveSelect("tip-label-show", on ? "health_zone" : "off"); applyToggleStyle(tipLabelsBtn, on, TREE_ACCENT, TREE_ACCENT_BAND); }
    applyToggleStyle(tipLabelsBtn, true, TREE_ACCENT, TREE_ACCENT_BAND);
    if (tipLabelsBtn) tipLabelsBtn.addEventListener("click", function (e) { e.preventDefault(); setTipLabels(!tipLabelsOn); });
  }

  // --- log-Y helpers (ported verbatim from the source log-scale.js) ---
  function niceLogRange(lo, hi) {
    if (!(lo > 0) || !(hi > 0)) return [1, 10];
    var a = Math.pow(10, Math.floor(Math.log10(Math.min(lo, hi))));
    var b = Math.pow(10, Math.ceil(Math.log10(Math.max(lo, hi))));
    if (b <= a) b = a * 10;
    return [a, b];
  }
  function logTicks(min, max) {
    var lo = Math.round(Math.log10(min)), hi = Math.round(Math.log10(max)), ticks = [];
    for (var d = lo; d <= hi; d++) ticks.push(Math.pow(10, d));
    return ticks;
  }
  function fmtNe(v) { return v >= 1 ? String(Math.round(v)) : String(v); }
  var SVNS = "http://www.w3.org/2000/svg";
  function svgEl(name, attrs) {
    var n = document.createElementNS(SVNS, name);
    for (var k in attrs) n.setAttribute(k, String(attrs[k]));
    return n;
  }
  var NE_PAD = { left: 42, right: 14, top: 30, bottom: 22 };
  var TIP_MARK_Y = 12;   // shared horizontal lane for tip-count circles (above the plot)
  function fmtDay(t) { return new Date(t).toLocaleDateString("en-GB", { day: "numeric", month: "short" }); }

  function tipMarkerRadius(n, maxN) {
    return Math.max(3, Math.min(10, 3 + 7 * Math.sqrt(n / Math.max(1, maxN))));
  }

  // Parse setMarkers input → [{t: ms, n: count}]. Accepts date strings, a
  // date→count map, or [{date,n}] objects.
  function normalizeTipMarkers(datesOrCounts) {
    var counts = {};
    if (Array.isArray(datesOrCounts)) {
      datesOrCounts.forEach(function (d) {
        if (d && typeof d === "object" && d.date != null) {
          var key = String(d.date).slice(0, 10);
          counts[key] = (counts[key] || 0) + (d.n || 1);
        } else if (d != null) {
          var ds = String(d).slice(0, 10);
          counts[ds] = (counts[ds] || 0) + 1;
        }
      });
    } else if (datesOrCounts && typeof datesOrCounts === "object") {
      Object.keys(datesOrCounts).forEach(function (d) {
        counts[String(d).slice(0, 10)] = +datesOrCounts[d] || 0;
      });
    }
    return Object.keys(counts).map(function (d) {
      return { t: +new Date(d), n: counts[d] };
    }).filter(function (m) { return isFinite(m.t) && m.n > 0; });
  }

  // Circles on a single top lane + dashed drop-lines into the plot (upper region only).
  function drawTipMarkers(svg, markers, xToPx, xLeft, xRight, lineBot) {
    if (!markers || !markers.length) return;
    var maxMark = 1;
    markers.forEach(function (m) { if (m.n > maxMark) maxMark = m.n; });
    markers.forEach(function (m) {
      var x = xToPx(m.t);
      if (x < xLeft - 1 || x > xRight + 1) return;
      svg.appendChild(svgEl("line", {
        x1: x, y1: TIP_MARK_Y, x2: x, y2: lineBot,
        stroke: "#c79a1a", "stroke-width": 1, "stroke-dasharray": "3,2", opacity: 0.75
      }));
      var r = tipMarkerRadius(m.n, maxMark);
      svg.appendChild(svgEl("circle", {
        cx: x, cy: TIP_MARK_Y, r: r,
        fill: "#f2c84b", stroke: "#9a7a16", "stroke-width": 1.2, opacity: 0.95
      }));
      if (m.n > 1) {
        var nl = svgEl("text", {
          x: x, y: TIP_MARK_Y + 3, "font-size": 8, fill: "#5a4a10",
          "text-anchor": "middle", "font-weight": "700", style: "pointer-events:none"
        });
        nl.textContent = String(m.n);
        svg.appendChild(nl);
      }
    });
  }

  // Renders the Ne panel into #gen-ne-body. Static calendar-X (root->mostRecent);
  // tree-lock/brush/markers are added with the coordinator in a later phase.
  function renderNePanel(genomic) {
    var host = document.getElementById("gen-ne-body");
    if (!host) return;
    var noteEl = document.getElementById("gen-ne-stale-note");
    if (noteEl) {
      if (genomic && genomic.ne_stale_note) {
        noteEl.textContent = genomic.ne_stale_note;
        noteEl.hidden = false;
      } else {
        noteEl.textContent = "";
        noteEl.hidden = true;
      }
    }
    var sg = genomic.skygrid, ex = genomic.exponential;
    if (!sg && !ex) { host.textContent = "No Ne data"; return; }
    var meta = sg || ex;
    var datasets = [
      sg && { key: "skygrid", label: "SkyGrid", color: "#587e72", band: "rgba(88,126,114,0.15)", btnId: "gen-ne-skygrid", data: sg },
      ex && { key: "exp", label: "Exp", color: "#7c1d1d", band: "rgba(124,29,29,0.12)", btnId: "gen-ne-exp", data: ex }
    ].filter(Boolean);
    datasets.forEach(function (ds) {
      ds.pts = ds.data.points.map(function (p) { return { t: +new Date(p.date), med: p.neMedian, lo: p.neLower, hi: p.neUpper }; });
      ds.visible = true;
    });

    // Anchor the x-axis to the TREE's root/mostRecent (meta.json), NOT the SkyGrid
    // product's own rootDate — the tree transform maps the tree's root→offsetX, and
    // SkyGrid/exponential rootDate can differ by days, which would offset the lock
    // (and misalign the markers vs. the distribution panel, which uses the tree meta).
    var tmeta = genomic.meta || {};
    var xMin = +new Date(tmeta.rootDate || meta.rootDate), xMax = +new Date(tmeta.mostRecentDate || meta.mostRecentDate);
    var transform = null;      // tree view transform (x-axis lock); null = static span
    var markerCounts = [];     // [{t,n}] selected-tip counts → top-lane circles
    var tip = document.createElement("div"); tip.className = "ne-tip"; tip.style.display = "none";

    function yDomain() {
      var los = [], his = [];
      datasets.filter(function (d) { return d.visible; }).forEach(function (d) {
        d.pts.forEach(function (p) { if (p.t >= xMin && p.t <= xMax) { if (p.lo > 0) los.push(p.lo); his.push(p.hi); } });
      });
      if (!los.length) return [1, 10];
      return niceLogRange(Math.min.apply(null, los), Math.max.apply(null, his));
    }

    function render() {
      var W = host.clientWidth || 320, H = host.clientHeight || 180;
      var yd = yDomain(), yMin = yd[0], yMax = yd[1];
      // Date→x anchored to the tree's live transform when present (locks the x-axis
      // to the phylogeny, so panning/zooming the tree tracks here), else the panel's
      // own root→mostRecent span. offsetX = root px; +maxX·scaleX = mostRecent px.
      var x0 = transform ? transform.offsetX : NE_PAD.left;
      var x1 = transform ? (transform.offsetX + transform.maxX * transform.scaleX) : (W - NE_PAD.right);
      var span = (xMax - xMin) || 1, dx = (x1 - x0) || 1;
      var xToPx = function (t) { return x0 + ((t - xMin) / span) * dx; };
      var pxToDate = function (px) { return xMin + ((px - x0) / dx) * span; };
      var yOf = function (ne) {
        var lo = Math.log10(yMin), hi = Math.log10(yMax), v = Math.log10(Math.max(ne, Number.MIN_VALUE));
        return (H - NE_PAD.bottom) - ((v - lo) / (hi - lo)) * ((H - NE_PAD.bottom) - NE_PAD.top);
      };
      host.replaceChildren();
      var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none" });
      // Clip drawing to the plot gutter so an x-locked ribbon/marker doesn't spill
      // past the axes when the tree is panned or zoomed.
      var clip = svgEl("clipPath", { id: "gen-ne-clip" });
      clip.appendChild(svgEl("rect", { x: NE_PAD.left, y: NE_PAD.top, width: Math.max(0, W - NE_PAD.left - NE_PAD.right), height: Math.max(0, H - NE_PAD.top - NE_PAD.bottom) }));
      svg.appendChild(clip);

      logTicks(yMin, yMax).forEach(function (tk) {
        var y = yOf(tk);
        svg.appendChild(svgEl("line", { x1: NE_PAD.left, y1: y, x2: W - NE_PAD.right, y2: y, stroke: "#eee", "stroke-width": 1 }));
        var lbl = svgEl("text", { x: NE_PAD.left - 4, y: y + 3, "font-size": 9, fill: "#9c968b", "text-anchor": "end" });
        lbl.textContent = fmtNe(tk); svg.appendChild(lbl);
      });

      var baseY = H - NE_PAD.bottom;
      svg.appendChild(svgEl("line", { x1: NE_PAD.left, y1: baseY, x2: W - NE_PAD.right, y2: baseY, stroke: "#c9c7c2", "stroke-width": 1 }));
      // x ticks from the visible date range (tracks the lock).
      var dL = pxToDate(NE_PAD.left), dR = pxToDate(W - NE_PAD.right);
      var nT = Math.max(2, Math.min(6, Math.floor((W - NE_PAD.left) / 80)));
      for (var i = 0; i <= nT; i++) {
        var t = dL + ((dR - dL) * i) / nT, x = xToPx(t);
        if (x < NE_PAD.left - 1 || x > W - NE_PAD.right + 1) continue;
        svg.appendChild(svgEl("line", { x1: x, y1: baseY, x2: x, y2: baseY + 3, stroke: "#c9c7c2", "stroke-width": 1 }));
        var xl = svgEl("text", { x: x, y: baseY + 13, "font-size": 9, fill: "#9c968b", "text-anchor": "middle" });
        xl.textContent = fmtDay(t); svg.appendChild(xl);
      }

      var gdata = svgEl("g", { "clip-path": "url(#gen-ne-clip)" });
      datasets.forEach(function (ds) {
        if (!ds.visible) return;
        var d = "";
        ds.pts.forEach(function (p, i) { d += (i ? "L" : "M") + xToPx(p.t) + "," + yOf(p.hi) + " "; });
        for (var j = ds.pts.length - 1; j >= 0; j--) d += "L" + xToPx(ds.pts[j].t) + "," + yOf(ds.pts[j].lo) + " ";
        gdata.appendChild(svgEl("path", { d: d + "Z", fill: ds.band, stroke: "none" }));
        var m = "";
        ds.pts.forEach(function (p, i) { m += (i ? "L" : "M") + xToPx(p.t) + "," + yOf(p.med) + " "; });
        gdata.appendChild(svgEl("path", { d: m, fill: "none", stroke: ds.color, "stroke-width": 1.6 }));
      });
      svg.appendChild(gdata);

      // Tip markers: circles on the top lane; dashed lines through the plot.
      drawTipMarkers(svg, markerCounts, xToPx, NE_PAD.left, W - NE_PAD.right, baseY);

      host.appendChild(svg);
      host.appendChild(tip);

      svg.addEventListener("mousemove", function (ev) {
        var mx = ev.clientX - host.getBoundingClientRect().left;
        var vis = datasets.filter(function (d) { return d.visible; });
        if (!vis.length || mx < NE_PAD.left || mx > W - NE_PAD.right) { tip.style.display = "none"; return; }
        var dateMs = pxToDate(mx), html = '<div class="ne-tip-d">' + fmtDay(dateMs) + "</div>";
        vis.forEach(function (ds) {
          var best = null, bd = Infinity;
          ds.pts.forEach(function (p) { var dd = Math.abs(p.t - dateMs); if (dd < bd) { bd = dd; best = p; } });
          if (best) html += '<div><span style="color:' + ds.color + '">' + ds.label + "</span> <b>" + best.med.toPrecision(3) + "</b> " +
            '<span class="ne-tip-ci">(' + best.lo.toPrecision(2) + "–" + best.hi.toPrecision(2) + ")</span></div>";
        });
        tip.innerHTML = html; tip.style.display = ""; tip.style.left = Math.min(mx + 8, W - 130) + "px"; tip.style.top = (NE_PAD.top + 4) + "px";
      });
      svg.addEventListener("mouseleave", function () { tip.style.display = "none"; });
    }

    datasets.forEach(function (ds) {
      var btn = document.getElementById(ds.btnId);
      if (!btn) return;
      function reflect() { applyToggleStyle(btn, ds.visible, ds.color, ds.band); }
      reflect();
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        var visCount = datasets.filter(function (d) { return d.visible; }).length;
        if (ds.visible && visCount <= 1) return;   // keep at least one visible
        ds.visible = !ds.visible;
        reflect();
        render();
      });
    });

    if (window.ResizeObserver) { new ResizeObserver(render).observe(host); }
    render();
    // Reject the pre-layout/degenerate transform PearTree reports before its first
    // fitToWindow (root≈mostRecent, ~1px wide) — it would squash the whole date axis
    // to one pixel. Require a meaningful root→mostRecent pixel span.
    function isUsableTransform(t) {
      return !!(t && isFinite(t.offsetX) && isFinite(t.scaleX) && isFinite(t.maxX) && t.maxX > 0 && (t.maxX * t.scaleX) > 30);
    }
    return {
      setTransform: function (t) { transform = isUsableTransform(t) ? t : null; render(); },
      setMarkers: function (datesOrCounts) { markerCounts = normalizeTipMarkers(datesOrCounts); render(); }
    };
  }

  var DIST_PAD = { left: 36, right: 42, top: 36, bottom: 22 };
  var DIST_OBS = "#9e2b2b", DIST_IMP = "#587e72";
  var STRATA = [
    { key: "mongbwalu", label: "Mongbwalu", color: "#c45c26" },
    { key: "bunia_rwampara", label: "Bunia / Rwampara", color: "#3d6b8a" },
    { key: "other", label: "Other", color: "#8a8578" }
  ];
  var PCT_COLOR = "#2a2a27";

  function stratumKey(zone) {
    var z = up(realZone(zone) || "");
    if (z === "MONGBWALU" || z === "MONGBALU" || z === "MONGWALU" || z === "MUNGWALU") return "mongbwalu";
    if (z === "BUNIA" || z === "RWAMPARA") return "bunia_rwampara";
    return "other";
  }

  function emptyStrata() {
    return { mongbwalu: 0, bunia_rwampara: 0, other: 0 };
  }

  function niceLinearTicks(max) {
    max = Math.max(1, max);
    var raw = max / 4, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    var step = mag; if (raw / mag >= 5) step = 5 * mag; else if (raw / mag >= 2) step = 2 * mag;
    step = Math.max(1, Math.round(step));
    var ticks = []; for (var v = 0; v <= max + step * 0.001; v += step) ticks.push(v);
    return ticks;
  }

  function nicePctTicks(max) {
    max = Math.max(10, max);
    var step = max <= 25 ? 5 : max <= 50 ? 10 : 25;
    var ticks = [];
    for (var v = 0; v <= max + 0.001; v += step) ticks.push(v);
    return ticks;
  }

  // Dual-axis cases (up) / genomes (down) panel, stratified by epicentre groups,
  // with a top axis for daily sequencing coverage (genomes / confirmed cases %).
  function renderDistPanel(genomic) {
    var host = document.getElementById("gen-dist-body");
    if (!host) return;
    var od = genomic.onset_distribution;
    if (!od || !od.dates || !od.dates.length) { host.textContent = "No sample-distribution data"; return; }
    var beyondFrom = od.beyond_tree_from ? +new Date(od.beyond_tree_from) : Infinity;
    var meta = genomic.meta || {};
    var treeMin = +new Date(meta.rootDate), treeMax = +new Date(meta.mostRecentDate);
    var showImputed = true, showBeyond = false;
    var transform = null;
    var markerCounts = [];   // [{t: ms, n: tipCount}] — upper (cases) half only

    var byZoneUpper = {};
    Object.keys(od.by_zone || {}).forEach(function (z) { byZoneUpper[up(z)] = { nom: z, series: od.by_zone[z] }; });

    // Genome counts by tip date × stratum (from the embedded phylogeny tips).
    var genomeByDate = {};
    (genomic.tips || []).forEach(function (t) {
      var d = (t.date || "").slice(0, 10);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return;
      var sk = stratumKey(t.health_zone);
      var bucket = genomeByDate[d] || (genomeByDate[d] = emptyStrata());
      bucket[sk] += 1;
    });

    var scopeZones = [];
    function dayCasesByStratum(dateStr) {
      var out = emptyStrata();
      var zoneKeys = scopeZones.length
        ? scopeZones.map(function (z) { return up(z); })
        : Object.keys(byZoneUpper);
      zoneKeys.forEach(function (uk) {
        var entry = byZoneUpper[uk];
        if (!entry) return;
        var c = entry.series[dateStr];
        if (!c) return;
        var n = (c.observed || 0) + (showImputed ? (c.imputed || 0) : 0);
        if (!n) return;
        out[stratumKey(entry.nom)] += n;
      });
      return out;
    }

    function dayGenomesByStratum(dateStr) {
      var g = genomeByDate[dateStr] || emptyStrata();
      if (!scopeZones.length) return { mongbwalu: g.mongbwalu, bunia_rwampara: g.bunia_rwampara, other: g.other };
      // When scoped, only count genomes from selected zones (re-bucket from tips).
      var out = emptyStrata();
      var allow = {};
      scopeZones.forEach(function (z) { allow[up(z)] = 1; });
      (genomic.tips || []).forEach(function (t) {
        var d = (t.date || "").slice(0, 10);
        if (d !== dateStr) return;
        var z = realZone(t.health_zone);
        if (!z || !allow[up(z)]) return;
        out[stratumKey(z)] += 1;
      });
      return out;
    }

    var allDates = od.dates.slice();
    Object.keys(genomeByDate).forEach(function (d) {
      if (allDates.indexOf(d) < 0) allDates.push(d);
    });
    allDates.sort();

    var days = [];
    function rebuildDays() {
      days = allDates.map(function (d) {
        var cases = dayCasesByStratum(d);
        var genomes = dayGenomesByStratum(d);
        var caseTot = cases.mongbwalu + cases.bunia_rwampara + cases.other;
        var genTot = genomes.mongbwalu + genomes.bunia_rwampara + genomes.other;
        return {
          t: +new Date(d), ds: d,
          cases: cases, genomes: genomes,
          caseTot: caseTot, genTot: genTot,
          pct: caseTot > 0 ? (100 * genTot) / caseTot : null
        };
      });
    }
    rebuildDays();
    var tip = document.createElement("div"); tip.className = "ne-tip"; tip.style.display = "none";
    var locked = function () { return !!(transform && isFinite(treeMin) && isFinite(treeMax) && !showBeyond); };

    function render() {
      var W = host.clientWidth || 320, H = host.clientHeight || 260;
      var vis = days.filter(function (d) { return showBeyond || d.t <= beyondFrom; });
      if (!vis.length) vis = days;
      var lk = locked();
      var aMin = lk ? treeMin : Math.min.apply(null, vis.map(function (d) { return d.t; }));
      var aMax = lk ? treeMax : Math.max.apply(null, vis.map(function (d) { return d.t; }));
      var x0 = lk ? transform.offsetX : DIST_PAD.left;
      var x1 = lk ? (transform.offsetX + transform.maxX * transform.scaleX) : (W - DIST_PAD.right);
      var span = (aMax - aMin) || 1, dxp = (x1 - x0) || 1;
      var xToPx = function (t) { return x0 + ((t - aMin) / span) * dxp; };
      var pxToDate = function (px) { return aMin + ((px - x0) / dxp) * span; };
      var yMaxCases = Math.max(1, Math.max.apply(null, vis.map(function (d) { return d.caseTot; }).concat([0])));
      var yMaxGenomes = Math.max(1, Math.max.apply(null, vis.map(function (d) { return d.genTot; }).concat([0])));
      var pctMax = 100;   // fixed 0–100% coverage axis
      var midY = Math.round((DIST_PAD.top + (H - DIST_PAD.bottom)) / 2);
      var halfH = midY - DIST_PAD.top;
      var yCase = function (v) { return midY - (v / yMaxCases) * halfH; };
      var yGen = function (v) { return midY + (v / yMaxGenomes) * halfH; };
      var yPct = function (v) { return DIST_PAD.top + halfH - (Math.min(Math.max(v, 0), pctMax) / pctMax) * halfH; };
      var pxPerDay = Math.abs(xToPx(aMin + 86400000) - xToPx(aMin));
      var barW = Math.max(1, pxPerDay - 1);

      host.replaceChildren();
      var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none" });
      var clip = svgEl("clipPath", { id: "gen-dist-clip" });
      clip.appendChild(svgEl("rect", {
        x: DIST_PAD.left, y: DIST_PAD.top,
        width: Math.max(0, W - DIST_PAD.left - DIST_PAD.right),
        height: Math.max(0, H - DIST_PAD.top - DIST_PAD.bottom)
      }));
      svg.appendChild(clip);

      if (showBeyond && isFinite(beyondFrom)) {
        var bx = Math.max(DIST_PAD.left, Math.min(W - DIST_PAD.right, xToPx(beyondFrom)));
        if (bx < W - DIST_PAD.right) {
          svg.appendChild(svgEl("rect", {
            x: bx, y: DIST_PAD.top, width: Math.max(0, (W - DIST_PAD.right) - bx),
            height: H - DIST_PAD.top - DIST_PAD.bottom, fill: "rgba(0,0,0,0.04)"
          }));
          var blab = svgEl("text", { x: bx + 3, y: DIST_PAD.top + 9, "font-size": 8, fill: "#9c968b" });
          blab.textContent = "beyond tree"; svg.appendChild(blab);
        }
      }

      // Left count axes: cases↑ and genomes↓ use independent scales.
      niceLinearTicks(yMaxCases).forEach(function (v) {
        if (v === 0) return;
        var yc = yCase(v);
        svg.appendChild(svgEl("line", { x1: DIST_PAD.left, y1: yc, x2: W - DIST_PAD.right, y2: yc, stroke: "#eee", "stroke-width": 1 }));
        var lc = svgEl("text", { x: DIST_PAD.left - 4, y: yc + 3, "font-size": 9, fill: "#9c968b", "text-anchor": "end" });
        lc.textContent = String(v); svg.appendChild(lc);
      });
      niceLinearTicks(yMaxGenomes).forEach(function (v) {
        if (v === 0) return;
        var yg = yGen(v);
        svg.appendChild(svgEl("line", { x1: DIST_PAD.left, y1: yg, x2: W - DIST_PAD.right, y2: yg, stroke: "#eee", "stroke-width": 1 }));
        var lg = svgEl("text", { x: DIST_PAD.left - 4, y: yg + 3, "font-size": 9, fill: "#9c968b", "text-anchor": "end" });
        lg.textContent = String(v); svg.appendChild(lg);
      });
      var zeroLbl = svgEl("text", { x: DIST_PAD.left - 4, y: midY + 3, "font-size": 9, fill: "#9c968b", "text-anchor": "end" });
      zeroLbl.textContent = "0"; svg.appendChild(zeroLbl);

      // Top/right % axis fixed at 0–100%.
      nicePctTicks(pctMax).forEach(function (v) {
        var y = yPct(v);
        var rl = svgEl("text", { x: W - DIST_PAD.right + 4, y: y + 3, "font-size": 9, fill: PCT_COLOR, "text-anchor": "start" });
        rl.textContent = v + "%"; svg.appendChild(rl);
      });
      var pctTitle = svgEl("text", { x: W - DIST_PAD.right + 4, y: DIST_PAD.top - 10, "font-size": 8, fill: PCT_COLOR, "text-anchor": "start" });
      pctTitle.textContent = "genomes/cases"; svg.appendChild(pctTitle);

      svg.appendChild(svgEl("line", { x1: DIST_PAD.left, y1: midY, x2: W - DIST_PAD.right, y2: midY, stroke: "#c9c7c2", "stroke-width": 1 }));
      var caseAxis = svgEl("text", { x: DIST_PAD.left + 2, y: DIST_PAD.top + 10, "font-size": 8, fill: "#9c968b" });
      caseAxis.textContent = "cases ↑"; svg.appendChild(caseAxis);
      var genAxis = svgEl("text", { x: DIST_PAD.left + 2, y: H - DIST_PAD.bottom - 4, "font-size": 8, fill: "#9c968b" });
      genAxis.textContent = "genomes ↓"; svg.appendChild(genAxis);

      var dL = pxToDate(DIST_PAD.left), dR = pxToDate(W - DIST_PAD.right);
      var nT = Math.max(2, Math.min(6, Math.floor((W - DIST_PAD.left) / 80)));
      for (var i = 0; i <= nT; i++) {
        var t = dL + ((dR - dL) * i) / nT, x = xToPx(t);
        if (x < DIST_PAD.left - 1 || x > W - DIST_PAD.right + 1) continue;
        svg.appendChild(svgEl("line", { x1: x, y1: midY, x2: x, y2: midY + 3, stroke: "#c9c7c2", "stroke-width": 1 }));
        var xl = svgEl("text", { x: x, y: H - 6, "font-size": 9, fill: "#9c968b", "text-anchor": "middle" });
        xl.textContent = fmtDay(t); svg.appendChild(xl);
      }

      var gbars = svgEl("g", { "clip-path": "url(#gen-dist-clip)" });
      vis.forEach(function (d) {
        var x = xToPx(d.t) - barW / 2;
        var stack = 0;
        STRATA.forEach(function (s) {
          var n = d.cases[s.key] || 0;
          if (n <= 0) return;
          var yTop = yCase(stack + n), yBase = yCase(stack);
          gbars.appendChild(svgEl("rect", { x: x, y: yTop, width: barW, height: Math.max(0, yBase - yTop), fill: s.color, opacity: 0.92 }));
          stack += n;
        });
        stack = 0;
        STRATA.forEach(function (s) {
          var n = d.genomes[s.key] || 0;
          if (n <= 0) return;
          var yTop = yGen(stack), yBot = yGen(stack + n);
          gbars.appendChild(svgEl("rect", { x: x, y: yTop, width: barW, height: Math.max(0, yBot - yTop), fill: s.color, opacity: 0.55 }));
          stack += n;
        });
      });
      svg.appendChild(gbars);

      // Sequencing % polyline (clipped).
      var gline = svgEl("g", { "clip-path": "url(#gen-dist-clip)" });
      var path = "";
      vis.forEach(function (d) {
        if (d.pct == null) return;
        var x = xToPx(d.t), y = yPct(Math.min(d.pct, pctMax));
        path += (path ? " L " : "M ") + x + " " + y;
      });
      if (path) {
        gline.appendChild(svgEl("path", { d: path, fill: "none", stroke: PCT_COLOR, "stroke-width": 1.5, "stroke-dasharray": "3,2", opacity: 0.9 }));
      }
      svg.appendChild(gline);

      // Tip markers on a dedicated top lane (not over the bars); dashed lines
      // drop into the upper (cases) half only — never into the genomes half.
      drawTipMarkers(svg, markerCounts, xToPx, DIST_PAD.left, W - DIST_PAD.right, midY);
      host.appendChild(svg); host.appendChild(tip);

      svg.addEventListener("mousemove", function (ev) {
        var mx = ev.clientX - host.getBoundingClientRect().left;
        var best = null, bd = Infinity;
        vis.forEach(function (d) { var dd = Math.abs(xToPx(d.t) - mx); if (dd < bd) { bd = dd; best = d; } });
        if (!best || bd > Math.max(barW, 8)) { tip.style.display = "none"; return; }
        var html = '<div class="ne-tip-d">' + fmtDay(best.t) + "</div>" +
          "<div>cases <b>" + best.caseTot + "</b> · genomes <b>" + best.genTot + "</b></div>";
        if (best.pct != null) html += "<div>coverage <b>" + best.pct.toFixed(0) + "%</b></div>";
        STRATA.forEach(function (s) {
          var c = best.cases[s.key] || 0, g = best.genomes[s.key] || 0;
          if (!c && !g) return;
          html += '<div><span style="color:' + s.color + '">' + s.label + "</span> c " + c + " / g " + g + "</div>";
        });
        tip.innerHTML = html; tip.style.display = "";
        tip.style.left = Math.min(mx + 8, W - 140) + "px"; tip.style.top = (DIST_PAD.top + 4) + "px";
      });
      svg.addEventListener("mouseleave", function () { tip.style.display = "none"; });
    }

    var impBtn = document.getElementById("gen-dist-imputed");
    applyToggleStyle(impBtn, showImputed, DIST_IMP, "rgba(88,126,114,0.15)");
    if (impBtn) impBtn.addEventListener("click", function (e) {
      e.preventDefault(); showImputed = !showImputed;
      applyToggleStyle(impBtn, showImputed, DIST_IMP, "rgba(88,126,114,0.15)");
      rebuildDays(); render();
    });

    var beyBtn = document.getElementById("gen-dist-beyond");
    applyToggleStyle(beyBtn, showBeyond, "#9b7d4e", "rgba(155,125,78,0.12)");
    if (beyBtn) beyBtn.addEventListener("click", function (e) {
      e.preventDefault(); showBeyond = !showBeyond;
      applyToggleStyle(beyBtn, showBeyond, "#9b7d4e", "rgba(155,125,78,0.12)");
      render();
    });

    if (window.ResizeObserver) { new ResizeObserver(render).observe(host); }
    render();
    function isUsableTransform(t) {
      return !!(t && isFinite(t.offsetX) && isFinite(t.scaleX) && isFinite(t.maxX) && t.maxX > 0 && (t.maxX * t.scaleX) > 30);
    }
    return {
      setTransform: function (t) { transform = isUsableTransform(t) ? t : null; render(); },
      setMarkers: function (datesOrCounts) { markerCounts = normalizeTipMarkers(datesOrCounts); render(); },
      setZones: function (zones) { scopeZones = (zones || []).slice(); rebuildDays(); render(); }
    };
  }

  var CORR_PAD = { left: 42, right: 14, top: 14, bottom: 28 };
  var CORR_OK = "#3d6b8a", CORR_LOW = "#c45c26", CORR_SEL = "#f2c84b";

  // Scatter: confirmed cases vs genomes per health zone; flag low sequencing coverage.
  // Clicking a point selects that health zone on the map + phylogeny (via coordinator).
  function renderCorrPanel(genomic) {
    var host = document.getElementById("gen-corr-body");
    if (!host) return;
    var od = genomic.onset_distribution || {};
    var byZone = od.by_zone || {};
    var tips = genomic.tips || [];
    if (!Object.keys(byZone).length && !tips.length) {
      host.textContent = "No zone-level case/genome data";
      return;
    }

    var genomes = {};
    tips.forEach(function (t) {
      var z = realZone(t.health_zone);
      if (!z) return;
      genomes[z] = (genomes[z] || 0) + 1;
    });

    var rows = [];
    var allZones = {};
    Object.keys(byZone).forEach(function (z) { allZones[z] = 1; });
    Object.keys(genomes).forEach(function (z) { allZones[z] = 1; });
    Object.keys(allZones).forEach(function (z) {
      var series = byZone[z] || {};
      var cases = 0;
      Object.keys(series).forEach(function (d) {
        cases += (series[d].observed || 0) + (series[d].imputed || 0);
      });
      var g = genomes[z] || 0;
      if (cases <= 0 && g <= 0) return;
      rows.push({ zone: z, cases: cases, genomes: g, coverage: cases > 0 ? g / cases : null });
    });
    if (!rows.length) { host.textContent = "No zone-level case/genome data"; return; }

    var totC = rows.reduce(function (s, r) { return s + r.cases; }, 0);
    var totG = rows.reduce(function (s, r) { return s + r.genomes; }, 0);
    var natRate = totC > 0 ? totG / totC : 0;
    rows.forEach(function (r) {
      r.expected = r.cases * natRate;
      r.low = r.cases >= 3 && r.coverage != null && r.coverage < Math.max(0.01, natRate * 0.5);
    });
    rows.sort(function (a, b) { return (b.low - a.low) || (b.cases - a.cases); });

    var tip = document.createElement("div"); tip.className = "ne-tip"; tip.style.display = "none";
    var selectedUpper = null;   // currently highlighted zone (UPPER)
    var zoneClickCb = null;
    var layout = null;          // last render's xToPx/yToPx for hit-testing

    function hitRow(mx, my) {
      if (!layout) return null;
      var best = null, bd = Infinity;
      rows.forEach(function (r) {
        var dx = layout.xToPx(r.cases) - mx, dy = layout.yToPx(r.genomes) - my;
        var dd = Math.sqrt(dx * dx + dy * dy);
        if (dd < bd) { bd = dd; best = r; }
      });
      return (best && bd <= 12) ? best : null;
    }

    function render() {
      var W = host.clientWidth || 320, H = host.clientHeight || 220;
      var xMax = Math.max(1, Math.max.apply(null, rows.map(function (r) { return r.cases; })));
      var yMax = Math.max(1, Math.max.apply(null, rows.map(function (r) { return r.genomes; })));
      xMax = Math.ceil(xMax * 1.05); yMax = Math.ceil(yMax * 1.05);
      var xToPx = function (v) { return CORR_PAD.left + (v / xMax) * (W - CORR_PAD.left - CORR_PAD.right); };
      var yToPx = function (v) { return (H - CORR_PAD.bottom) - (v / yMax) * (H - CORR_PAD.top - CORR_PAD.bottom); };
      layout = { xToPx: xToPx, yToPx: yToPx, W: W, H: H };

      host.replaceChildren();
      var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none", style: "cursor:default" });

      niceLinearTicks(xMax).forEach(function (v) {
        var x = xToPx(v);
        svg.appendChild(svgEl("line", { x1: x, y1: CORR_PAD.top, x2: x, y2: H - CORR_PAD.bottom, stroke: "#eee", "stroke-width": 1 }));
        var lbl = svgEl("text", { x: x, y: H - 8, "font-size": 9, fill: "#9c968b", "text-anchor": "middle" });
        lbl.textContent = String(v); svg.appendChild(lbl);
      });
      niceLinearTicks(yMax).forEach(function (v) {
        var y = yToPx(v);
        svg.appendChild(svgEl("line", { x1: CORR_PAD.left, y1: y, x2: W - CORR_PAD.right, y2: y, stroke: "#eee", "stroke-width": 1 }));
        var lbl = svgEl("text", { x: CORR_PAD.left - 4, y: y + 3, "font-size": 9, fill: "#9c968b", "text-anchor": "end" });
        lbl.textContent = String(v); svg.appendChild(lbl);
      });

      svg.appendChild(svgEl("line", {
        x1: CORR_PAD.left, y1: H - CORR_PAD.bottom, x2: W - CORR_PAD.right, y2: H - CORR_PAD.bottom,
        stroke: "#c9c7c2", "stroke-width": 1
      }));
      svg.appendChild(svgEl("line", {
        x1: CORR_PAD.left, y1: CORR_PAD.top, x2: CORR_PAD.left, y2: H - CORR_PAD.bottom,
        stroke: "#c9c7c2", "stroke-width": 1
      }));
      var xlab = svgEl("text", { x: (CORR_PAD.left + W - CORR_PAD.right) / 2, y: H - 1, "font-size": 9, fill: "#9c968b", "text-anchor": "middle" });
      xlab.textContent = "confirmed cases"; svg.appendChild(xlab);
      var ylab = svgEl("text", {
        x: 11, y: (CORR_PAD.top + H - CORR_PAD.bottom) / 2, "font-size": 9, fill: "#9c968b",
        "text-anchor": "middle", transform: "rotate(-90 11 " + ((CORR_PAD.top + H - CORR_PAD.bottom) / 2) + ")"
      });
      ylab.textContent = "genomes"; svg.appendChild(ylab);

      if (natRate > 0) {
        var xEnd = Math.min(xMax, yMax / natRate);
        var yEnd = xEnd * natRate;
        svg.appendChild(svgEl("line", {
          x1: xToPx(0), y1: yToPx(0), x2: xToPx(xEnd), y2: yToPx(yEnd),
          stroke: "#9c968b", "stroke-width": 1, "stroke-dasharray": "4,3", opacity: 0.9
        }));
        var ref = svgEl("text", { x: xToPx(xEnd * 0.7), y: yToPx(yEnd * 0.7) - 4, "font-size": 8, fill: "#9c968b" });
        ref.textContent = "national rate"; svg.appendChild(ref);
      }

      rows.forEach(function (r) {
        var cx = xToPx(r.cases), cy = yToPx(r.genomes);
        var selected = selectedUpper && up(r.zone) === selectedUpper;
        var circle = svgEl("circle", {
          cx: cx, cy: cy,
          r: selected ? 7 : (r.low ? 5 : 3.5),
          fill: selected ? CORR_SEL : (r.low ? CORR_LOW : CORR_OK),
          opacity: selected ? 1 : (r.low ? 0.95 : 0.75),
          stroke: selected ? "#9a7a16" : (r.low ? "#7a3410" : "none"),
          "stroke-width": selected || r.low ? 1.5 : 0,
          "data-zone": r.zone,
          style: "cursor:pointer"
        });
        circle.addEventListener("click", function (ev) {
          ev.stopPropagation();
          if (zoneClickCb) zoneClickCb(r.zone);
        });
        svg.appendChild(circle);
        if (r.low || selected) {
          var lab = svgEl("text", {
            x: cx + 6, y: cy - 4, "font-size": 8,
            fill: selected ? "#9a7a16" : CORR_LOW, style: "pointer-events:none"
          });
          lab.textContent = r.zone; svg.appendChild(lab);
        }
      });

      var legend = svgEl("text", { x: W - CORR_PAD.right, y: CORR_PAD.top + 8, "font-size": 8, fill: CORR_LOW, "text-anchor": "end" });
      legend.textContent = "● low genome coverage · click a point to select"; svg.appendChild(legend);

      host.appendChild(svg); host.appendChild(tip);
      svg.addEventListener("mousemove", function (ev) {
        var rect = host.getBoundingClientRect();
        var mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
        var best = hitRow(mx, my);
        svg.style.cursor = best ? "pointer" : "default";
        if (!best) { tip.style.display = "none"; return; }
        var cov = best.coverage == null ? "—" : (100 * best.coverage).toFixed(0) + "%";
        tip.innerHTML = '<div class="ne-tip-d">' + best.zone + "</div>" +
          "<div>cases <b>" + best.cases + "</b></div>" +
          "<div>genomes <b>" + best.genomes + "</b></div>" +
          "<div>coverage <b>" + cov + "</b>" + (best.low ? " · low" : "") + "</div>" +
          '<div style="color:#9c968b;margin-top:2px">click to select on map/tree</div>';
        tip.style.display = "";
        tip.style.left = Math.min(mx + 8, W - 130) + "px";
        tip.style.top = Math.max(4, my - 40) + "px";
      });
      svg.addEventListener("mouseleave", function () { tip.style.display = "none"; svg.style.cursor = "default"; });
    }

    if (window.ResizeObserver) { new ResizeObserver(render).observe(host); }
    render();
    return {
      refresh: render,
      // Mirror distPanel.setZones: [] clears; one or more zones highlights the first match.
      setZones: function (zones) {
        var z = (zones && zones.length) ? zones[0] : null;
        selectedUpper = z ? up(z) : null;
        render();
      },
      onZoneClick: function (cb) { zoneClickCb = cb; }
    };
  }

  // --- Genomic-local coordinator ---------------------------------------------
  // Ports coordinator.js's selection contract into the tab (design §4): the active
  // selection is a ZONE's tip-set, chosen from a genome marker OR a zone polygon on
  // the shared map; clicking the same source again deselects (activeKey). A direct
  // tree click selects a clade and reflects its zones back onto the map. ALL tip
  // logic lives here; engine.js only exposes generic zone-level hooks.

  function startCoordinator(tree, hooks, tips, nePanel, distPanel, corrPanel) {
    // zone (UPPER) -> tip accessions/ids, for highlighting a zone's tips.
    var zoneToTips = {};
    (tips || []).forEach(function (t) {
      var z = realZone(t.health_zone);
      if (!z) return;
      var k = up(z);
      (zoneToTips[k] = zoneToTips[k] || []).push(t.id);
    });
    // Canonical zone spelling (as the map knows it) for highlightZones, keyed
    // upper-case; falls back to the tip's own spelling if a zone has no marker.
    var nomByUpper = {};
    (hooks.genomeMarkers || []).forEach(function (g) { if (g.nom) nomByUpper[up(g.nom)] = g.nom; });
    function zoneNom(z) { return nomByUpper[up(z)] || z; }

    var zoneSelecting = false;   // true while a marker/zone/corr click drives the selection
    var programmatic = false;    // true while WE mutate the tree (vs. a direct tree click)
    var activeKey = null;        // key of the current map-initiated selection (toggle-deselect)

    function clearAll() {
      activeKey = null;
      programmatic = true;
      tree.clear();              // onSelect (normal path) clears the map highlight
      programmatic = false;
      if (corrPanel && corrPanel.setZones) corrPanel.setZones([]);
    }

    // marker OR polygon OR correlation point → select that zone's tips; click again → clear.
    // opts.toggle === false suppresses that clear: the search box empties after
    // every pick, so a user searching the same zone twice would otherwise
    // DEselect it while the map still zoomed straight to it.
    function selectZone(nom, opts) {
      var key = "zone:" + up(nom);
      var toggle = !(opts && opts.toggle === false);
      if (toggle && key === activeKey) { clearAll(); return; }
      activeKey = key;
      var names = zoneToTips[up(nom)] || [];
      zoneSelecting = true;
      programmatic = true;
      tree.clear();                                  // drop any prior tip selection
      if (names.length) tree.selectByNames(names);   // highlight this zone's tips
      programmatic = false;
      zoneSelecting = false;
      hooks.highlightZones([zoneNom(nom)]);          // outline the zone + its marker
      // Scope the cases panel to this zone directly (not via the tree round-trip), so
      // it works even for a zone with confirmed cases but no genome tips.
      if (distPanel && distPanel.setZones) distPanel.setZones([zoneNom(nom)]);
      if (corrPanel && corrPanel.setZones) corrPanel.setZones([zoneNom(nom)]);
    }

    hooks.onMarkerClick(function (nom, opts) { selectZone(nom, opts); });
    hooks.onZoneClick(function (nom, opts) { selectZone(nom, opts); });
    hooks.onBackgroundClick(function () { clearAll(); });
    if (corrPanel && corrPanel.onZoneClick) {
      corrPanel.onZoneClick(function (nom) { selectZone(nom); });
    }

    // tree selection → (1) date markers on Ne/distribution (any selection source),
    // (2) map zone highlight (except when a marker/zone click already did it).
    tree.onSelect(function (ev) {
      var selected = (ev && ev.selected) || [];
      var dateCounts = {}, zoneSet = {};
      selected.forEach(function (n) {
        var a = n.annotations || {};
        if (a.date) dateCounts[a.date] = (dateCounts[a.date] || 0) + 1;
        var z = realZone(a.health_zone);
        if (z) zoneSet[zoneNom(z)] = true;
      });
      if (nePanel) nePanel.setMarkers(dateCounts);
      if (distPanel) distPanel.setMarkers(dateCounts);
      if (zoneSelecting) return;                     // marker/zone/corr click already drove map + cases scope
      if (!programmatic) activeKey = null;           // a direct tree click isn't a toggle target
      var zoneList = Object.keys(zoneSet);
      hooks.highlightZones(zoneList);
      // Direct tree/clade selection (or a clear) re-scopes the cases panel to the union
      // of the selected tips' zones; an empty selection restores the national series.
      if (distPanel && distPanel.setZones) distPanel.setZones(zoneList);
      if (corrPanel && corrPanel.setZones) corrPanel.setZones(zoneList);
    });

    // x-axis lock: keep the Ne panel's time axis aligned with the tree's live view
    // transform. Seed with the current transform, then track pan/zoom — coalesced to
    // one update per frame (onViewChange fires a tweened burst during zoom, Phase 0).
    var raf = window.requestAnimationFrame || function (f) { return setTimeout(f, 16); };
    function pushTransform() {
      var t = tree.getViewTransform && tree.getViewTransform();
      if (!t) return;
      if (nePanel) nePanel.setTransform(t);
      if (distPanel && distPanel.setTransform) distPanel.setTransform(t);
    }
    if (nePanel || distPanel) pushTransform();
    // PearTree's first fitToWindow lands slightly AFTER embed resolves, and it emits
    // neither onViewChange nor a host resize for it, so the seed above can catch the
    // pre-layout (degenerate) transform. Re-read a few times over ~1s so the settled
    // transform reaches the panels (they ignore the degenerate one until then).
    [60, 200, 500, 1000].forEach(function (ms) { setTimeout(pushTransform, ms); });
    var rafPending = false;
    tree.onViewChange(function () {
      if (rafPending) return;
      rafPending = true;
      raf(function () { rafPending = false; pushTransform(); });
    });
    // PearTree refits (and changes its X transform) when its container resizes but
    // does NOT emit onViewChange for that, so on the drag-resizable rail the lock
    // would go stale. Re-read the tree's transform after any tree-host resize
    // (rAF-deferred so PearTree's own refit lands first).
    if (window.ResizeObserver && (nePanel || distPanel)) {
      var treeHost = document.getElementById("gen-tree-body");
      if (treeHost) new ResizeObserver(function () { raf(pushTransform); }).observe(treeHost);
    }

    return { clearSelection: clearAll, selectZone: selectZone };
  }

  function createGenomicTab(ctx) {
    var data = (ctx && ctx.data) || {};
    var treeApi = null;   // resolved PearTree instance (async); consumed by the coordinator
    var coordinator = null;
    return {
      mount: function () {
        var nePanel = renderNePanel(data);
        var distPanel = renderDistPanel(data);
        var corrPanel = renderCorrPanel(data);
        this.treePromise = createTreePanel("gen-tree-body", data).then(function (t) {
          treeApi = t;
          var hooks = window.__bdbvMapHooks;
          if (t && hooks) {
            coordinator = startCoordinator(t, hooks, data.tips || [], nePanel, distPanel, corrPanel);
          }
          return t;
        });
      },
      getTree: function () { return treeApi; },
      getCoordinator: function () { return coordinator; },
      unmount: function () {
        if (coordinator) coordinator.clearSelection();
        setText("gen-tree-body", "");
      }
    };
  }

  // Drag-to-resize the right rail. Session-only: the width is NOT persisted, so a
  // reload snaps back to the CSS default width (this panel rebuilds its contents
  // each load, so a predictable default reads better than a remembered width).
  // Clamped to a sensible range.
  var MIN_W = 320;
  function maxW() { return Math.round(window.innerWidth * 0.7); }
  // PearTree re-fits its tree + time-axis on a window "resize", but its own
  // container ResizeObserver doesn't fire for this embed, so a rail drag alone
  // leaves the phylogeny at the old width. Nudge it with a synthetic resize on
  // every width change. mousemove is already frame-throttled, so this matches how
  // PearTree behaves under a real window-resize drag.
  function applyWidth(px) {
    var panel = document.getElementById("genomic-panel");
    if (!panel) return;
    px = Math.max(MIN_W, Math.min(maxW(), px));
    panel.style.width = px + "px";
    publishPanelWidth(px);
    window.dispatchEvent(new Event("resize"));
  }
  // #genomic-panel OVERLAYS a full-width #map (unlike the Trends and Spatial
  // Risk rails, which narrow #map itself), so dashboard.css needs its width to
  // clamp #zone-search to the visible map strip. The width is an inline px
  // style, unreachable from CSS, so the single writer publishes it as a custom
  // property in the same breath -- the two cannot drift.
  function publishPanelWidth(px) {
    document.documentElement.style.setProperty("--genomic-panel-width", px + "px");
  }
  function initResize() {
    var panel = document.getElementById("genomic-panel");
    var handle = document.getElementById("genomic-resize");
    if (!panel || !handle) return;

    // The starting width comes from the stylesheet (min(634px, 70vw)), not
    // from applyWidth(), so seed the custom property from the live geometry.
    publishPanelWidth(panel.offsetWidth);

    var dragging = false;
    function onMove(e) {
      if (!dragging) return;
      applyWidth(window.innerWidth - e.clientX);   // rail hugs the right edge
      e.preventDefault();
    }
    function onUp() {
      if (!dragging) return;
      dragging = false;
      document.body.classList.remove("genomic-resizing");
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    }
    handle.addEventListener("mousedown", function (e) {
      dragging = true;
      document.body.classList.add("genomic-resizing");
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
      e.preventDefault();
    });
    // Keyboard resize for accessibility (± 20px on arrow keys).
    handle.addEventListener("keydown", function (e) {
      var cur = parseInt(panel.style.width, 10) || panel.getBoundingClientRect().width;
      if (e.key === "ArrowLeft") { applyWidth(cur + 20); e.preventDefault(); }
      else if (e.key === "ArrowRight") { applyWidth(cur - 20); e.preventDefault(); }
    });
  }

  function boot() {
    if (document.body.getAttribute("data-initial-view") !== "genomic-epidemiology") return;
    var tab = createGenomicTab({ data: readGenomic() });
    tab.mount();
    initResize();
    window.__genomicTab = tab;   // exposed for later engine/coordinator integration
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
