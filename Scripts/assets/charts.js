// Shared runtime-SVG chart primitives.
//
// Extracted from genomic.js so trends.js can build on the same drawing idiom
// (hand-rolled SVG via createElementNS -- this project has no charting
// library). genomic.js still carries its own copy of these; migrating it onto
// this module and deleting that copy is a tracked follow-up.
//
// Everything here is pure drawing: no page state, no payload knowledge.
(function (global) {
  "use strict";

  var SVNS = "http://www.w3.org/2000/svg";

  // Unique per chart instance: a Trends page renders 4 cards plus up to 20 lab
  // charts in one document, and duplicate clipPath ids would cross-clip.
  var clipSeq = 0;

  function svgEl(name, attrs) {
    var n = document.createElementNS(SVNS, name);
    for (var k in attrs) n.setAttribute(k, String(attrs[k]));
    return n;
  }

  // Tick steps of 1/2/5 x 10^n, always starting at 0.
  function niceLinearTicks(max, allowFractional) {
    max = Math.max(allowFractional ? 1e-9 : 1, max);
    var raw = max / 4, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    var step = mag;
    if (raw / mag >= 5) step = 5 * mag; else if (raw / mag >= 2) step = 2 * mag;
    if (!allowFractional) step = Math.max(1, Math.round(step));
    var ticks = [];
    for (var v = 0; v <= max + step * 0.001; v += step) ticks.push(v);
    return ticks;
  }

  function dayMs(iso) { return Date.parse(iso + "T00:00:00Z"); }
  function fmtDay(t) {
    return new Date(t).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
  }

  // A plot frame: pixel scales plus the axes/gridlines drawn into `svg`.
  // xStart/xEnd are ISO dates and define the SHARED range -- pass the same
  // pair to every card of one selection or they will disagree about time.
  function frame(svg, opts) {
    var W = opts.width, H = opts.height, pad = opts.pad;
    var t0 = dayMs(opts.xStart), t1 = dayMs(opts.xEnd);
    var span = (t1 - t0) || 86400000;
    var left = pad.left, right = W - pad.right, baseY = H - pad.bottom;
    var xToPx = function (t) { return left + ((t - t0) / span) * (right - left); };
    var pxToDate = function (px) { return t0 + ((px - left) / (right - left)) * span; };
    var yMax = Math.max(opts.yMax, opts.allowFractional ? 1e-9 : 1);
    var yToPx = function (v) { return baseY - (v / yMax) * (baseY - pad.top); };

    var ticks = niceLinearTicks(yMax, opts.allowFractional);
    ticks.forEach(function (v) {
      var y = yToPx(v);
      svg.appendChild(svgEl("line", { x1: left, y1: y, x2: right, y2: y, stroke: "#eee", "stroke-width": 1 }));
      var lbl = svgEl("text", { x: left - 4, y: y + 3, "font-size": 9, fill: "#9c968b", "text-anchor": "end" });
      lbl.textContent = opts.fmtY ? opts.fmtY(v) : String(v);
      svg.appendChild(lbl);
    });

    svg.appendChild(svgEl("line", { x1: left, y1: baseY, x2: right, y2: baseY, stroke: "#c9c7c2", "stroke-width": 1 }));
    var nT = Math.max(2, Math.min(6, Math.floor((right - left) / 80)));
    for (var i = 0; i <= nT; i++) {
      var t = t0 + (span * i) / nT, x = xToPx(t);
      svg.appendChild(svgEl("line", { x1: x, y1: baseY, x2: x, y2: baseY + 3, stroke: "#c9c7c2", "stroke-width": 1 }));
      var xl = svgEl("text", { x: x, y: baseY + 13, "font-size": 9, fill: "#9c968b", "text-anchor": "middle" });
      xl.textContent = fmtDay(t);
      svg.appendChild(xl);
    }

    var pxPerDay = Math.abs(xToPx(t0 + 86400000) - xToPx(t0));

    // Clip marks to the plot gutter so a bar centred on the axis start/end
    // doesn't overhang the edge by half a bar width. Axis lines, ticks, tick
    // labels and dualAxis labels are drawn above (or via dualAxis, separately)
    // and are intentionally NOT inside this clip.
    var clipId = "dc-clip-" + (++clipSeq);
    var clip = svgEl("clipPath", { id: clipId });
    clip.appendChild(svgEl("rect", {
      x: left, y: pad.top, width: Math.max(0, right - left), height: Math.max(0, baseY - pad.top)
    }));
    svg.appendChild(clip);

    return {
      xToPx: xToPx, pxToDate: pxToDate, yToPx: yToPx, yMax: yMax,
      left: left, right: right, top: pad.top, baseY: baseY,
      barW: Math.max(1, pxPerDay - 1), ticks: ticks, clipId: clipId
    };
  }

  // Shaded band from `fromIso` to the right edge, drawn BENEATH the data
  // (call before the marks). Used for the incomplete-reporting window.
  function shadeRegion(svg, fr, fromIso, fill) {
    if (!fromIso) return;
    var x = Math.max(fr.left, Math.min(fr.right, fr.xToPx(dayMs(fromIso))));
    if (x >= fr.right) return;
    var g = svgEl("g", { "clip-path": "url(#" + fr.clipId + ")" });
    g.appendChild(svgEl("rect", {
      x: x, y: fr.top, width: fr.right - x, height: fr.baseY - fr.top,
      fill: fill, "fill-opacity": 0.25
    }));
    svg.appendChild(g);
  }

  // Stacked bars. `series` is [{values:[], color}] drawn bottom-up.
  function stackedBars(svg, fr, dates, series) {
    var g = svgEl("g", { "clip-path": "url(#" + fr.clipId + ")" });
    dates.forEach(function (iso, i) {
      var acc = 0;
      series.forEach(function (s) {
        var v = s.values[i] || 0;
        if (v <= 0) return;
        var yTop = fr.yToPx(acc + v), yBot = fr.yToPx(acc);
        g.appendChild(svgEl("rect", {
          x: fr.xToPx(dayMs(iso)) - fr.barW / 2, y: yTop,
          width: fr.barW, height: Math.max(0, yBot - yTop), fill: s.color
        }));
        acc += v;
      });
    });
    svg.appendChild(g);
  }

  function pathFor(fr, dates, values) {
    var d = "";
    dates.forEach(function (iso, i) {
      var v = values[i];
      if (v === null || v === undefined) return;
      d += (d ? "L" : "M") + fr.xToPx(dayMs(iso)) + " " + fr.yToPx(v);
    });
    return d;
  }

  // Confidence band. Straight across gaps, matching geom_ribbon.
  function ciBand(svg, fr, dates, lo, hi, fill) {
    var up = "", down = [];
    dates.forEach(function (iso, i) {
      if (hi[i] === null || hi[i] === undefined) return;
      if (lo[i] === null || lo[i] === undefined) return;
      up += (up ? "L" : "M") + fr.xToPx(dayMs(iso)) + " " + fr.yToPx(hi[i]);
      down.push(fr.xToPx(dayMs(iso)) + " " + fr.yToPx(lo[i]));
    });
    if (!up) return;
    down.reverse();
    var g = svgEl("g", { "clip-path": "url(#" + fr.clipId + ")" });
    g.appendChild(svgEl("path", {
      d: up + "L" + down.join("L") + "Z", fill: fill, "fill-opacity": 0.35, stroke: "none"
    }));
    svg.appendChild(g);
  }

  function line(svg, fr, dates, values, color, width) {
    var d = pathFor(fr, dates, values);
    if (!d) return;
    var g = svgEl("g", { "clip-path": "url(#" + fr.clipId + ")" });
    g.appendChild(svgEl("path", { d: d, fill: "none", stroke: color, "stroke-width": width || 0.9 }));
    svg.appendChild(g);
  }

  // `filter(i)` selects which indices get a dot (the deaths chart plots points
  // only where daily_deaths > 0).
  function points(svg, fr, dates, values, color, r, filter) {
    var g = svgEl("g", { "clip-path": "url(#" + fr.clipId + ")" });
    dates.forEach(function (iso, i) {
      if (filter && !filter(i)) return;
      var v = values[i];
      if (v === null || v === undefined) return;
      g.appendChild(svgEl("circle", {
        cx: fr.xToPx(dayMs(iso)), cy: fr.yToPx(v), r: r || 1.8, fill: color, stroke: "none"
      }));
    });
    svg.appendChild(g);
  }

  // Dashed vertical marker plus a label (the lab charts' "Earliest Sample").
  function markerLine(svg, fr, iso, color, label) {
    if (!iso) return;
    var x = fr.xToPx(dayMs(iso));
    if (x < fr.left || x > fr.right) return;
    var g = svgEl("g", { "clip-path": "url(#" + fr.clipId + ")" });
    g.appendChild(svgEl("line", {
      x1: x, y1: fr.top, x2: x, y2: fr.baseY,
      stroke: color, "stroke-width": 1, "stroke-dasharray": "3,2"
    }));
    if (label) {
      var txt = svgEl("text", { x: x + 3, y: fr.top + 9, "font-size": 8, fill: color });
      txt.textContent = label;
      g.appendChild(txt);
    }
    svg.appendChild(g);
  }

  // Right-hand axis that RELABELS the same pixel range -- it never moves a
  // mark. `fmt` maps a primary-axis value to its secondary-axis label.
  function dualAxis(svg, fr, name, fmt) {
    fr.ticks.forEach(function (v) {
      var y = fr.yToPx(v);
      var lbl = svgEl("text", { x: fr.right + 4, y: y + 3, "font-size": 9, fill: "#9c968b", "text-anchor": "start" });
      lbl.textContent = fmt(v);
      svg.appendChild(lbl);
    });
    if (!name) return;
    var cy = (fr.top + fr.baseY) / 2;
    var t = svgEl("text", {
      x: fr.right + 16, y: cy, "font-size": 9, fill: "#9c968b",
      "text-anchor": "middle", transform: "rotate(90 " + (fr.right + 16) + " " + cy + ")"
    });
    t.textContent = name;
    svg.appendChild(t);
  }

  // Hover tooltip. `resolve(iso)` returns HTML, or null to hide.
  function tooltip(host, svg, fr, resolve) {
    var tip = document.createElement("div");
    tip.className = "dc-tip";
    tip.style.display = "none";
    host.appendChild(tip);
    svg.addEventListener("mousemove", function (ev) {
      var r = svg.getBoundingClientRect();
      if (!r.width) { tip.style.display = "none"; return; }
      var mx = (ev.clientX - r.left) * (svg.viewBox.baseVal.width / r.width);
      if (mx < fr.left || mx > fr.right) { tip.style.display = "none"; return; }
      var iso = new Date(fr.pxToDate(mx)).toISOString().slice(0, 10);
      var html = resolve(iso);
      if (!html) { tip.style.display = "none"; return; }
      tip.innerHTML = html;
      tip.style.display = "";
      tip.style.left = Math.min(mx + 8, fr.right - 110) + "px";
      tip.style.top = (fr.top + 4) + "px";
    });
    svg.addEventListener("mouseleave", function () { tip.style.display = "none"; });
  }

  global.DashboardCharts = {
    svgEl: svgEl, niceLinearTicks: niceLinearTicks, dayMs: dayMs, fmtDay: fmtDay,
    frame: frame, shadeRegion: shadeRegion, stackedBars: stackedBars,
    ciBand: ciBand, line: line, points: points, markerLine: markerLine,
    dualAxis: dualAxis, tooltip: tooltip
  };
})(window);
