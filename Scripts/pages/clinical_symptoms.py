"""
"Clinical Symptoms" page -> output/clinical-symptoms.html.

A map-free page (body class "mapless-view", see common/chrome.py) laid out
like Surveillance and Testing: cards drawn at runtime by clinical.js from
PAYLOAD.clinical (common/clinical.py), which holds the summary tables from
BDBV2026-Processing_Code step 9 (9-clinical-aggregates.R). Small counts are
suppressed in that step, before anything reaches this page.

Every card body starts empty; clinical.js fills it or shows the card's empty
state, so a build without step 9's tables still renders.
"""

from __future__ import annotations

from common.chrome import render_page

VIEW_ID = "clinical-symptoms"


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


def _toggle(group_id: str) -> str:
    # Filled by clinical.js (labels are translated there).
    return f'<span class="clin-toggle" id="{group_id}" role="group"></span>'


_SCOPE = ('<label class="surv-select-label"><span data-i18n="ui.clin.area">Area</span> '
          '<select id="clin-scope" class="surv-select"></select></label>')

_BODY = f"""<div id="clin-page">
  <div id="clin-inner">
    <div class="surv-intro">
      <p data-i18n-html="ui.clin.intro">Confirmed cases in the line list. Small counts (under 10) are hidden to protect privacy. The line list does not record whether each case survived, so "dead at sampling" counts only people who had already died when their sample was taken: it is not a case fatality rate.</p>
      <p class="surv-asof" id="clin-asof"></p>
      <p class="clin-scope-row">{_SCOPE}</p>
    </div>
    <div class="surv-headline" id="clin-headline"></div>

    <div class="surv-grid">
{_card("clin-symptoms", "ui.clin.symptoms_title", "Reported symptoms",
       "ui.clin.symptoms_tip", "Share of confirmed cases reporting each symptom, among cases with at least one symptom recorded. Compare groups with the buttons. Symptoms are recorded less often for people who were dead at sampling.",
       controls=_toggle("clin-sym-by"), wide=True, chart_class="surv-chart clin-chart-symptoms")}
{_card("clin-los", "ui.clin.los_title", "Length of hospital stay",
       "ui.clin.los_tip", "Days from hospital admission to discharge date, for confirmed cases with both dates recorded. Stays outside 0 to 60 days are left out. The discharge date does not say whether the patient recovered or died.",
       controls=_toggle("clin-los-by"))}
{_card("clin-pyramid", "ui.clin.pyramid_title", "Age and sex",
       "ui.clin.pyramid_tip", "Confirmed cases by age group and sex. The darker part of each bar is people who were already dead when sampled.")}
{_card("clin-hcw", "ui.clin.hcw_title", "Health workers infected",
       "ui.clin.hcw_tip", "Confirmed cases recorded as health workers, by month of symptom onset. Roles are grouped from free-text entries.",
       wide=True)}
    </div>
  </div>
</div>"""

_SCRIPTS = (
    '<script src="__ASSETS_PREFIX__charts.js"></script>\n'
    '<script src="__ASSETS_PREFIX__clinical.js"></script>'
)


def build_page(payload: dict) -> str:
    return render_page(VIEW_ID, payload, page_body=_BODY, extra_scripts=_SCRIPTS)
