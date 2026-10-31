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
_FU_ADD = ('<label class="surv-select-label"><span class="sr-only" data-i18n="ui.surv.add_zone">Add a health zone</span>'
           '<select id="surv-fu21-add" class="surv-select"></select></label>')

_BODY = f"""<div id="surv-page">
  <div id="surv-inner">
    <div class="surv-intro">
      <p data-i18n-html="ui.surv.intro">Contact tracing indicators are taken from the contact tracing analytics report (aggregate tables only). Testing indicators use the same line-list snapshot as the Epidemiological Trends tab.</p>
      <p class="surv-asof" id="surv-asof"></p>
    </div>
    <div class="surv-headline" id="surv-headline"></div>

    <h2 class="surv-section" data-i18n="ui.surv.section_ct">Contact tracing</h2>
    <div class="surv-grid">
      {_card("surv-ct-known", "ui.surv.known_title", "New cases and share already known as contacts",
             "ui.surv.known_tip", "Bars: new confirmed cases per week of notification. Line (right axis): % of those cases who were already registered as a contact on or before the day they were notified. Percentages are shown only for weeks with at least 20 cases. Shaded weeks are incomplete.",
             controls=_CT_SCOPE, wide=True)}
      {_card("surv-ct-source", "ui.surv.source_title", "New cases that became source cases",
             "ui.surv.source_tip", "% of new cases each week who appear as the source case of at least one listed contact. Weeks with at least 20 cases. The shaded period is incomplete: contacts are often listed days after notification.")}
      {_card("surv-fu-visits", "ui.surv.visits_title", "Follow-up visits with a recorded result",
             "ui.surv.visits_tip", "Bars: contact follow-up visits recorded per week. Line (right axis): % of those visits with a result (e.g. seen, symptomatic) recorded.")}
    </div>

    <h2 class="surv-section" data-i18n="ui.surv.section_fu">Contact follow-up</h2>
    <div class="surv-grid">
      {_card("surv-fu21", "ui.surv.fu21_title", "Contacts fully followed up, by month of first follow-up",
             "ui.surv.fu21_tip", "% of contacts with a result recorded up to day 21 of follow-up (first follow-up = day 1); contacts who became cases count as complete if followed up until detection. Only contacts whose day 21 had passed by the data cut are included. Dotted line: all zones. Click a zone below the chart to hide it, or add another from the list. Zone-months with fewer than 10 contacts are not shown.",
             controls=_FU_ADD, wide=True)}
    </div>

    <h2 class="surv-section" data-i18n="ui.surv.section_delays">Delays</h2>
    <div class="surv-grid">
      {_card("surv-journey", "ui.surv.journey_title", "Patient journey: days since symptom onset",
             "ui.surv.journey_tip", "Confirmed cases. Dot: median; diamond: mean; bar: interquartile range (IQR). The last three steps concern source cases only. Only cases with onset at least 26 days before the data cut are included, so that later steps have had time to happen.",
             chart_class="surv-chart surv-chart-journey")}
      {_card("surv-delays", "ui.surv.delays_title", "Median delay by week of onset",
             "ui.surv.delays_tip", "Median (line) and IQR (band) of days from symptom onset to each step, by week of onset. Weeks with at least 5 cases. Click a series in the legend to hide or show it.")}
    </div>

    <h2 class="surv-section" data-i18n="ui.surv.section_testing">Testing</h2>
    <div class="surv-grid">
      {_card("surv-tests", "ui.surv.tests_title", "Samples tested and test positivity",
             "ui.surv.tests_tip", "Bars: samples with a lab result, by date of symptom onset (dark: positive). Line (right axis): 5-day rolling test positivity with 95% Wilson interval. Shaded: last 7 days, reporting likely incomplete.",
             controls=_TEST_SCOPE, wide=True)}
      {_card("surv-labs", "ui.surv.labs_title", "Laboratory throughput",
             "ui.surv.labs_tip", "Samples analysed per week by laboratory, by date of analysis. Click a laboratory in the legend to hide or show it. The table lists every laboratory's totals.",
             wide=True)}
    </div>
    <div class="surv-table-wrap" id="surv-labs-table"></div>

    <h2 class="surv-section" data-i18n="ui.surv.section_provinces">Contact tracing indicators by province</h2>
    <div class="surv-table-wrap" id="surv-province-table"></div>
    <p class="surv-caption" id="surv-province-caption"></p>
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
