// Reports tab.
//
// Draws the report cards on reports.html from PAYLOAD.reports
// (Scripts/common/reports.py): one section per folder of the reports repo,
// newest report first. A report that exists in both languages is one card with
// a button per language; the button matching the dashboard language is
// highlighted. engine.js calls ReportsTab.refreshI18n() on a language switch.
(function (global) {
  "use strict";

  var LANGS = [["en", "English"], ["fr", "Français"]];

  var _data;
  function data() {
    if (_data !== undefined) return _data;
    var el = document.getElementById("payload");
    try { _data = (JSON.parse(el.textContent) || {}).reports || null; } catch (e) { _data = null; }
    return _data;
  }
  function tr(key, fallback) {
    if (!global.t) return fallback;
    var v = global.t(key);
    return (v && v !== key) ? v : fallback;
  }
  function lang() { return document.documentElement.lang === "fr" ? "fr" : "en"; }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function locale() { return lang() === "fr" ? "fr-FR" : "en-GB"; }

  function fmtDate(iso) {
    var d = new Date(iso + "T00:00:00Z");
    if (isNaN(d)) return iso;
    return d.toLocaleDateString(locale(), { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  }
  function fmtSize(bytes) {
    if (!bytes) return "";
    var mb = bytes / 1048576;
    if (mb >= 1) return mb.toLocaleString(locale(), { maximumFractionDigits: 1 }) + " MB";
    return Math.max(1, Math.round(bytes / 1024)).toLocaleString(locale()) + " KB";
  }
  function folderLabel(id) {
    return tr("ui.reports.folders." + id, id.replace(/_/g, " "));
  }

  function card(report, isLatest) {
    var cur = lang(), files = report.files || {};
    var main = files[cur] || files.en || files.fr || {};
    var buttons = LANGS.filter(function (l) { return files[l[0]]; }).map(function (l) {
      var f = files[l[0]];
      var size = fmtSize(f.size);
      var primary = (l[0] === cur || Object.keys(files).length === 1) ? " rep-btn-primary" : "";
      var label = tr("ui.reports.open_aria", "Open the {lang} PDF")
        .replace("{lang}", l[1]) + (size ? " (" + size + ")" : "");
      return '<a class="rep-btn' + primary + '" href="' + esc(f.url) + '" target="_blank" rel="noopener"' +
        ' hreflang="' + l[0] + '" aria-label="' + esc(label) + '">' +
        '<span class="rep-btn-lang">' + esc(l[1]) + '</span>' +
        (size ? '<span class="rep-btn-size">PDF · ' + esc(size) + '</span>' : '') + '</a>';
    }).join("");
    return '<article class="rep-card">' +
      '<div class="rep-card-top"><span class="rep-date">' + esc(fmtDate(report.date)) + '</span>' +
      (isLatest ? '<span class="rep-badge">' + esc(tr("ui.reports.latest", "Latest")) + '</span>' : '') + '</div>' +
      '<h4 class="rep-title">' + esc(main.title || "") + '</h4>' +
      '<div class="rep-actions">' + buttons + '</div></article>';
  }

  function render() {
    var host = document.getElementById("rep-list");
    if (!host) return;
    var d = data(), folders = (d && d.folders) || [];
    if (!folders.length) {
      host.innerHTML = '<p class="rep-empty">' +
        esc(tr("ui.reports.empty", "No reports are available yet.")) + '</p>';
      return;
    }
    host.innerHTML = folders.map(function (f) {
      var n = f.reports.length;
      return '<section class="rep-section" id="rep-' + esc(f.id) + '">' +
        '<h3 class="surv-section">' + esc(folderLabel(f.id)) +
        ' <span class="rep-count">' + n + '</span></h3>' +
        '<div class="rep-grid">' +
        f.reports.map(function (r, i) { return card(r, i === 0); }).join("") +
        '</div></section>';
    }).join("");
  }

  global.ReportsTab = { render: render, refreshI18n: render, _data: data };
  render();
})(window);
