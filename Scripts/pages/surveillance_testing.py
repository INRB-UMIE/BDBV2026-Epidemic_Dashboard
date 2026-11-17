"""
"Surveillance and Testing" page -> output/surveillance-testing.html.

A map-free page (body class "mapless-view", see common/chrome.py): a scrolling
grid of cards drawn at runtime by surveillance.js from PAYLOAD.surveillance
(common/surveillance.py). Panels mirror the contact tracing report
(BDBV2026-Contact_Tracing_Analytics) -- Fig 3A-D and Fig 2A-B -- plus testing
volume/positivity and laboratory throughput from the Trends tab's sources.

Every card body starts empty; surveillance.js fills it or shows the card's
empty state, so a build without one of the two sources still renders.
"""

from __future__ import annotations

from common.chrome import render_page

VIEW_ID = "surveillance-testing"


def _card(card_id: str, title_key: str, title: str, tip_key: str, tip: str,
          controls: str = "", wide: bool = False, chart_class: str = "surv-chart") -> str:
    return f"""
    <section class="surv-card{' surv-wide' if wide else ''}" id="{card_id}">
      <div class="surv-card-head">
        <span class="surv-title" tabindex="0">
          <h3 data-i18n="{title_key}">{title}</h3>
          <span class="surv-info" aria-hidden="true">i</span>
          <span class="surv-tip" role="tooltip" data-i18n="{tip_key}">{tip}</span>
        </span>
        <span class="surv-controls">{controls}</span>
      </div>
      <div class="surv-legend" id="{card_id}-legend"></div>
      <div class="{chart_class}" id="{card_id}-chart"></div>
      <p class="surv-caption" id="{card_id}-caption"></p>
    </section>"""


_CT_SCOPE = ('<label class="surv-select-label"><span class="sr-only" data-i18n="ui.surv.scope">Area</span>'
             '<select id="surv-ct-scope" class="surv-select"></select></label>')
_TEST_SCOPE = ('<label class="surv-select-label"><span class="sr-only" data-i18n="ui.surv.scope">Area</span>'
               '<select id="surv-test-scope" class="surv-select"></select></label>')
_BACKFILL_SCOPE = ('<label class="surv-select-label"><span class="sr-only" data-i18n="ui.surv.scope">Area</span>'
                   '<select id="surv-backfill-scope" class="surv-select"></select></label>')
_FU_ADD = ('<label class="surv-select-label"><span class="sr-only" data-i18n="ui.surv.add_zone">Add a health zone</span>'
           '<select id="surv-fu21-add" class="surv-select"></select></label>')

_BODY = f"""<div id="surv-page">
<div id="surv-layout">
  <nav id="surv-nav" aria-label="Sections">
    <ul>
      <li><button type="button" class="surv-nav-link" data-target="surv-sec-ct" data-i18n="ui.surv.section_ct">Contact tracing</button></li>
      <li><button type="button" class="surv-nav-link" data-target="surv-sec-testing" data-i18n="ui.surv.section_testing">Testing</button></li>
      <li><button type="button" class="surv-nav-link" data-target="surv-sec-delays" data-i18n="ui.surv.section_delays">Delays</button></li>
      <li><button type="button" class="surv-nav-link" data-target="surv-sec-backfill" data-i18n="ui.surv.section_backfill">Reporting completeness</button></li>
    </ul>
  </nav>
  <div id="surv-inner">
    <div class="surv-intro">
      <p data-i18n-html="ui.surv.intro">Contact tracing indicators use the same aggregate tables and definitions as the contact tracing analytics report. Testing indicators use the same line-list snapshot as the Epidemiological Trends tab.</p>
      <p class="surv-asof" id="surv-asof"></p>
    </div>
    <div class="surv-headline" id="surv-headline"></div>

    <section class="surv-sec" id="surv-sec-ct">
      <h2 class="surv-section" data-i18n="ui.surv.section_ct">Contact tracing</h2>
      <div class="surv-grid">
        {_card("surv-ct-source", "ui.surv.source_title", "New cases that became source cases",
               "ui.surv.source_tip", "% of new cases each week who appear as the source case of at least one listed contact. Weeks with at least 20 cases. The shaded period is incomplete: contacts are often listed days after notification.",
               controls=_CT_SCOPE)}
        {_card("surv-fu-visits", "ui.surv.visits_title", "Follow-up visits with a recorded result",
               "ui.surv.visits_tip", "Bars: contact follow-up visits recorded per week. Line (right axis): % of those visits with a result (e.g. seen, symptomatic) recorded.")}
        {_card("surv-fu21", "ui.surv.fu21_title", "Contacts fully followed up, by month of first follow-up",
               "ui.surv.fu21_tip", "% of contacts with a result recorded up to day 21 of follow-up (first follow-up = day 1); contacts who became cases count as complete if followed up until detection. Only contacts whose day 21 had passed by the data cut are included. Dotted line: all zones. Click a zone below the chart to hide it, or add another from the list. Zone-months with fewer than 10 contacts are not shown.",
               controls=_FU_ADD, wide=True)}
      </div>

      <h3 class="surv-subsection" data-i18n="ui.surv.section_provinces">Contact tracing indicators by province</h3>
      <div class="surv-table-wrap" id="surv-province-table"></div>
      <p class="surv-caption" id="surv-province-caption"></p>
    </section>

    <section class="surv-sec" id="surv-sec-testing">
      <h2 class="surv-section" data-i18n="ui.surv.section_testing">Testing</h2>
      <div class="surv-grid">
        {_card("surv-tests", "ui.surv.tests_title", "Samples tested and test positivity",
               "ui.surv.tests_tip", "Bars: samples with a lab result, by date of symptom onset (dark: positive). Line (right axis): 5-day rolling test positivity with 95% Wilson interval. Shaded: recent days where reporting is likely incomplete (window estimated from how earlier data exports filled in).",
               controls=_TEST_SCOPE, wide=True)}
        {_card("surv-labs", "ui.surv.labs_title", "Laboratory throughput",
               "ui.surv.labs_tip", "Samples analysed per week by laboratory, by date of analysis. Click a laboratory in the legend to hide or show it. The table lists every laboratory's totals.",
               wide=True)}
        {_card("surv-tat", "ui.surv.tat_title", "Laboratory turnaround time",
               "ui.surv.tat_tip", "Days from sample collection to laboratory analysis: median over each laboratory's samples analysed in the previous 5 days, by date of analysis. Hover for the interquartile range and number of samples. Click a laboratory in the legend to hide or show it.",
               wide=True)}
      </div>
      <div class="surv-table-wrap" id="surv-labs-table"></div>
    </section>

    <section class="surv-sec" id="surv-sec-delays">
      <h2 class="surv-section" data-i18n="ui.surv.section_delays">Delays</h2>
      <div class="surv-grid">
        {_card("surv-journey", "ui.surv.journey_title", "Patient journey: days since symptom onset",
               "ui.surv.journey_tip", "Confirmed cases. Dot: median; diamond: mean; bar: interquartile range (IQR). The last three steps concern source cases only. Only cases with onset at least 26 days before the data cut are included, so that later steps have had time to happen.",
               chart_class="surv-chart surv-chart-journey")}
        {_card("surv-delays", "ui.surv.delays_title", "Median delay by week of onset",
               "ui.surv.delays_tip", "Median (line) and IQR (band) of days from symptom onset to each step, by week of onset. Weeks with at least 5 cases. Click a series in the legend to hide or show it.")}
      </div>
    </section>

    <section class="surv-sec" id="surv-sec-backfill">
      <h2 class="surv-section" data-i18n="ui.surv.section_backfill">Reporting completeness</h2>
      <div class="surv-grid">
        {_card("surv-backfill", "ui.surv.backfill_title", "How quickly confirmed cases are reported",
               "ui.surv.backfill_tip", "Line: share of the eventual number of confirmed cases already in the line list, by days since symptom onset, estimated by comparing earlier data exports with the latest one. Band: 10th to 90th percentile across onset dates. Dotted line: 90% complete. Shaded: the days since onset still below 90%, which is the grey window shown on the onset-date charts for this area. Only areas with enough cases for their own estimate are listed.",
               controls=_BACKFILL_SCOPE)}
        {_card("surv-backfill-curve", "ui.surv.epicurve_title", "The same epidemic curve in successive data exports",
               "ui.surv.epicurve_tip", "Confirmed cases per day by date of symptom onset (7-day average), as each of several earlier data exports showed them, for the area chosen on the left. Each curve falls away just before its export date (dotted line) and fills in later: that drop is late reporting, not a real decline.")}
      </div>
    </section>
  </div>
</div>
</div>"""

# charts.js before surveillance.js (which calls DashboardCharts.*), both after
# engine.js (i18n helpers t/tf).
_SCRIPTS = (
    '<script src="__ASSETS_PREFIX__charts.js"></script>\n'
    '<script src="__ASSETS_PREFIX__surveillance.js"></script>'
)


def build_page(payload: dict) -> str:
    return render_page(VIEW_ID, payload, page_body=_BODY, extra_scripts=_SCRIPTS)
