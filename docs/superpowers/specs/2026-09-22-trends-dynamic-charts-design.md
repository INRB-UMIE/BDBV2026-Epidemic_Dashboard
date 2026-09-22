# Epidemiological Trends: replace pre-rendered SVGs with dynamic charts

**Date:** 2026-09-22
**Status:** Design — approved; open decisions resolved (D6, D7)
**Scope:** `trends.html` (the "Epidemiological Trends" tab) only

---

## 1. Context

The Trends tab renders four families of charts. Every one of them is today a
**pre-rendered ggplot2/svglite SVG image**:

| Card | Plot family | Source |
|---|---|---|
| `#trends` | `confirmed_cases_and_positivity/` | `status_aggregated.csv` |
| `#trends-deaths` | `cumulative_deaths/` | `cumulative_positive_deaths.csv` |
| `#trends-positivity` | `rolling_positivity/` | `rolling_positivity.csv` |
| `#trends-labs` | `lab_plots/` | `lab_positivity_aggregated.csv` |

The SVGs are produced by `BDBV2026-Processing_Code`'s
`pipelines/epi_linelist_pipeline/4-make-dashboard-plots.R`, committed into the
private `BDBV2026-Processed_Sensitive_Data` repo under
`outputs/<date>/dashboard_plots/`, checked out in CI by `build-dashboard.yml`
(using `EXTERNAL_REPO_TOKEN`), read by `load_dashboard_plots()` in
`Scripts/common/data_sources.py`, and inlined as SVG strings into
`PAYLOAD.onset_trends`. `engine.js` simply assigns `plot.svg` into a div.

Charts were baked as images because the upstream repo is private. That
constraint no longer applies to the **aggregated** tables: they are daily
counts per location, not line-list rows, and the dashboard already publishes a
slice of one of them (`load_onset_imputed_series()` reads
`status_aggregated.csv` for the genomic tab's "Confirmed positive cases"
panel).

### Cost of the status quo

Measured on the shipped `trends.html` (production data, 2026-09-20):

| Slice | Entries | Size |
|---|---:|---:|
| `onset_trends.health_zones` | 59 | 2.15 MB |
| `onset_trends.rolling_positivity` | 3 scales | 1.03 MB |
| `onset_trends.labs` | 20 | 0.57 MB |
| `onset_trends.cumulative_deaths` | 3 scales | 0.45 MB |
| `onset_trends.provinces` | 6 | 0.25 MB |
| `onset_trends.national` | 6 | 0.06 MB |
| **`onset_trends` total** | | **5.35 MB — 28% of the payload** |

`onset_trends` is **not** in `_PAGE_SCOPED_PAYLOAD_KEYS`, so all seven pages
carry all 5.35 MB, including pages that never read it.

Secondary costs: R bakes an English title into every image, so the card titles
cannot follow the EN/FR toggle (`renderPlotCard()` works around this by
composing its own title and using `cropPlotSvgTop()` to shift the viewBox and
crop R's title off); images do not reflow with the resizable rail; and there
are no tooltips.

## 2. Goal

Render the same four chart families from the same numbers, client-side, in the
idiom already used by the Genomic Epidemiology tab (`genomic.js` builds SVG at
runtime via `document.createElementNS`; there is no charting library anywhere
in this project).

## 3. Non-goals

- No change to what data is collected, aggregated, or published upstream.
- No new user controls (no toggles, zoom, brush, or CSV download).
- No change to the CI trust model — same repo, same token, same directory.
- No migration of `genomic.js` onto the shared module in this change.
- No change to the R pipeline. It keeps emitting SVGs; we stop consuming them.

## 4. Decisions taken

| # | Decision | Rationale |
|---|---|---|
| D1 | Keep reading `BDBV2026-Processed_Sensitive_Data` in CI; read the CSVs in `outputs/<date>/` rather than the SVG folders | This is a rendering change, not a data-governance change. Publishing an allowlisted public aggregate feed (the `publish-public-outputs.yml` → `BDBV2026-Spatial_Invasion_Risk` pattern) remains a worthwhile but separable follow-up. |
| D2 | Hand-rolled SVG via a shared `assets/charts.js`, no charting library | Matches `genomic.js`; no new dependency; ~70% of the primitives already exist there. |
| D3 | Visual parity + hover tooltips only | The brief is to present the same data the same way, dynamically. |
| D4 | Extract `charts.js` now; migrate `genomic.js` onto it in a follow-up | Zero regression risk to the recently-finished genomic tab; accepts temporary duplication. |
| D6 | Lab secondary axis renders **0–100**, correcting the source's 0–1 under a `(%)` label | Resolves O1. Geometry is unchanged — only tick labels differ (see §6.5). |
| D7 | Incomplete-reporting cutoff = **`snapshot_date - incomplete_days`**, read from the manifest once the pipeline records it | Resolves O2. Closest faithful reproduction available to the dashboard; never computed in the browser. |
| D5 | Carry **full float precision** for all positivity values — no rounding anywhere | Costs +115 KB on the positivity slice alone (124 KB at 3dp → 238 KB); total slice 363 KB vs 5.35 MB today, still ~15× smaller. Removes an entire class of "did a number change?" question. Fidelity is worth more than the bytes. |

## 5. Provenance of the fidelity contract — IMPORTANT

Section 6 was transcribed from
`INRB-UMIE/BDBV2026-Processing_Code` at **`origin/main` (tip `f232fa4`)**,
file `pipelines/epi_linelist_pipeline/4-make-dashboard-plots.R`, **1175 lines**.

The pipeline is run by `BDBV2026-Processed_Sensitive_Data`'s
`run-processing-code-pipeline.yml`, which checks out `BDBV2026-Processing_Code`
with **no `ref:`**, i.e. the repository default branch, which is `main`.

A local checkout of that repo was 8 commits stale (on branch
`parallel-delay-fitting`, a 755-line version of the script) and described a
**materially different** output layout — flat `national/`/`healthzone/`/`lab/`
rather than the four plot-type families actually in production, and a
now-removed positivity overlay on the cases chart. Conclusions drawn from the
stale file were wrong and were discarded.

**Anyone revisiting this spec must re-read the generator at the default branch
of `BDBV2026-Processing_Code`, not a local checkout.**

**This warning was earned twice.** The colour constants above were first
transcribed from the stale checkout and were WRONG (`#b23b2e`/`#f1ccc6`, the
old brick-red palette). The error survived the discovery that the file was
stale, because only the chart *builders* were re-read from the live generator
while the Aesthetics block was carried forward unchecked. It was caught later
by diffing a production SVG's actual fills against the spec. **Verify constants
against a real output artefact, not only against source.** If that script changes,
this spec's Section 6 is stale and the charts will drift from the data.

## 6. Fidelity contract

Exact behaviour to reproduce. Constants are from the generator's Aesthetics
block.

```
COLOR_INK              #2a2a27      COLOR_POSITIVITY       #5b86b3
COLOR_MUTED            #9c968b      COLOR_DEATHS           #7c1d1d
COLOR_INCOMPLETE       #9c968b      COLOR_SAMPLES_ANALYSED #9c968b
observed onset         #9B7D4E      imputed onset          #C9A266
POSITIVITY_POINT_R     1.8          line linewidth         0.9
bar width              0.9          incomplete band alpha  0.25
ribbon alpha           0.35         DEFAULT_INCOMPLETE_DAYS 7
```

### 6.1 Which locations get a chart

- Entities come from `status_aggregated.csv`, one per distinct
  `(spatial_scale, location)`; `national` has a single location.
- Locations whose name is empty or `NA` are dropped.
- **A location is skipped entirely when its total confirmed count
  (observed + imputed) across all dates is 0.** This is why 59 of the 123
  health zones present in the CSV have charts.
- The entity list drives the scope dropdown, so this rule must be reproduced
  exactly or the dropdown contents change.

**The three families do not cover the same locations, and the cases family is
authoritative for the dropdown.** Measured at the 2026-09-20 snapshot:

| Family | Health zones |
|---|---:|
| cases (`status_aggregated.csv`, non-zero confirmed) | 59 |
| positivity (`rolling_positivity.csv`) | 55 |
| deaths (`cumulative_positive_deaths.csv`) | 45 |

Deaths zones are a strict subset of cases zones. Positivity is **not**: five
zones — Adi, Biringi, Katana, Nyarambe, Rethy — have positivity rows but no
confirmed cases, so they get no cases chart, never appear in the dropdown, and
their positivity data is unreachable in the UI today.

That is existing behaviour and **must be preserved**. Building the dropdown
from the union of the three families would surface five zones the current
dashboard does not show. Build it from the cases family alone.

### 6.2 Confirmed cases (`#trends`)

- Counts: `confirmed_case` **only**. Not `suspected_case`, `probable_case`,
  `not_a_case` or `blank`.
- Split into `observed` / `imputed` on `onset_date_was_imputed == TRUE`.
- Stacked bars, **observed at the bottom**, imputed on top
  (`position_stack(reverse = TRUE)`).
- Series trimmed to the first date with a positive total, restricted to dates
  ≥ 2026-01-01 where any such date exists, then **every missing day filled
  with 0** so bars are contiguous (`complete_date_series()` /
  `earliest_positive_date()`).
- y-axis name `Cases`.
- **No positivity overlay.** The live generator has no `has_positivity`
  branch and no secondary axis on this chart; positivity is its own family.
  Confirmed against production SVGs (`daily_onset_national.svg`,
  `daily_onset_ituri.svg` @ 2026-09-20): neither contains a
  "Sample Positivity" axis or legend entry.
- Caption: `Confirmed cases by date of symptom onset` — with
  `. Shaded region: dates within the last week (reporting likely incomplete).`
  appended **only when an incomplete band is drawn**.

### 6.3 Cumulative deaths (`#trends-deaths`)

- From `cumulative_positive_deaths.csv`.
- Series spans first → last **reporting date present for that location**
  (NOT trimmed to first positive, unlike cases).
- Gaps filled by `complete_cumulative_series()`: `daily_deaths` → 0,
  `cumulative_deaths` → **carried forward from the last observed value**
  (a step, not an interpolation).
- Line in `COLOR_DEATHS`, linewidth 0.9.
- Points drawn **only on days where `daily_deaths > 0`**, size 1.8.
- y-axis name `Cumulative Deaths`.
- Caption: `Cumulative confirmed deaths by reporting date (death alerts with
  confirmed MVE classification)` (+ incomplete note when banded).
  `MVE` is the French acronym (*maladie à virus Ebola*) and is retained
  verbatim; see §10-O3.

### 6.4 Rolling positivity (`#trends-positivity`)

- From `rolling_positivity.csv`, keyed on `date_of_symptom_onset_imputed`.
- **Sparse** — only dates present in the CSV. Not zero-filled. `geom_line`
  connects straight across gaps; the JS line must do the same, **not** insert
  zeros or break the path.
- Values clamped to `[0, 1]` then **multiplied by 100** (percent).
- Ribbon `lower_pct`→`upper_pct` in `COLOR_POSITIVITY` at alpha 0.35;
  line linewidth 0.9; points size 1.8; same colour.
- y-axis name `Sample Positivity (%)`, **lower limit pinned to 0**, upper free.
- Caption: `5-day rolling test positivity by date of symptom onset`
  (+ incomplete note when banded).

### 6.5 Laboratory testing (`#trends-labs`)

- From `lab_positivity_aggregated.csv`, one chart per `lab_name`, labs in
  sorted order; title from `lab_name_long`, falling back to `lab_name`.
- **All lab charts share one x range:** `[min(earliest_analysed_sample) across
  ALL labs, max(lab_analysis_date) across ALL labs]`, so labs stay visually
  comparable. Not per-lab.
- Bars: `total_samples_analysed_daily`, fill `COLOR_SAMPLES_ANALYSED`, width 0.9.
- `max_total = max(1, max(total_samples_analysed_daily))` **for that lab**.
- Positivity clamped to `[0, 1]` then scaled by `* max_total`; ribbon/line/points
  as in §6.4.
- Secondary axis, name `Sample Positivity (%)`, rendering **0–100**
  (**decided — D6**, correcting the source; see §10-O1).

  The source computes `sec_axis(~ . / max_total)`, which yields a 0–1
  proportion under a `(%)` label. We label the same axis 0–100 instead.

  **This changes tick labels only.** The ribbon, line and points are positioned
  on the *primary* axis as `clamp(value) * max_total`; the secondary axis is a
  pure relabelling of that same pixel range. Plotted geometry is identical
  either way, so there is no risk of moving a mark. Concretely, the right-hand
  axis of `lab_inrbk.svg` reads `0.00 / 0.25 / 0.50 / 0.75 / 1.00` today and
  will read `0 / 25 / 50 / 75 / 100`.

  This is the one intentional departure from current appearance in this change,
  and it exists to stop a positivity of 0.67 being readable as "0.67%".
- Dashed vertical line at that lab's `earliest_analysed_sample`, `COLOR_INK`.
- Text annotation `Earliest Sample: YYYY-MM-DD` at `y = max_total * 1.02`,
  `hjust = -0.05`, size 3.2, `COLOR_INK`.
- Caption: `Samples analysed and test positivity by analysis date` (constant —
  no incomplete-note variant).
- Lab→location association: prefer the CSV's own `health_zone`/`province`
  columns, falling back to the manifest index. This matches what `engine.js`
  already does and must be preserved so lab subsetting by selection is unchanged.

### 6.6 Shared x-axis per location

`shared_date_limits()` computes, per location, the min and max date across
**that location's cases rows, deaths rows, and positivity rows combined**, and
applies it to all three charts via `coord_cartesian(xlim = …)`.

Consequence: the three cards for one selection are **date-aligned with each
other**, and a chart may show empty space where its own series does not extend
to the shared range. This must be reproduced, or the cards will silently
disagree about time.

Lab charts use the global lab range from §6.5 instead.

### 6.7 Incomplete-reporting band

- Window: `incomplete_reporting_days`, from
  `pipeline_configs$epi_linelist$nowcasting$test_days`, default 7. The value is
  mirrored into `manifest.json` at `incomplete_styling.days` — **read it from
  the manifest**, do not hardcode 7.
- Dates in the band: `date >= cutoff`.
- Band rectangle spans `min(incomplete_dates) - 0.5` → `x_max + 0.5`, full
  plot height, fill `COLOR_INCOMPLETE` at alpha 0.25, **drawn beneath the data**.
- When no date falls in the window, **no band is drawn and the caption loses
  its incomplete-note sentence** (§6.2–6.4). The two vary together.
- **Cutoff basis (decided — D7):** `snapshot_date - incomplete_days`, where
  `snapshot_date` is the `outputs/<date>` folder name, resolved **at build
  time** and shipped as `trends.incomplete_from`. If the pipeline later records
  the exact cutoff in `manifest.json` (§11.4), read that instead and this
  approximation retires.
- **Never compute the cutoff in the browser.** `new Date()` would let the band
  drift as a page ages between builds. See §10-O2.

## 7. Implementation

### 7.1 Ingestion (Python)

`load_dashboard_plots()` → **`load_trends_series()`** in
`Scripts/common/data_sources.py`.

- Same `DASHBOARD_PLOTS_DIR`; same snapshot resolution from `manifest.json`'s
  `date`, reusing `_onset_manifest_dated_dir()` (already shared with the
  genomic loader) so Trends and the genomic panel stay on one snapshot.
- Reads `status_aggregated.csv`, `cumulative_positive_deaths.csv`,
  `rolling_positivity.csv`, `lab_positivity_aggregated.csv`.
- Health-zone names join to canonical `nom` via the existing `_norm` /
  `nom_by_norm` approach used by `load_onset_imputed_series()` — **not** the
  filename slugs (`_slugify_plot_key`) the SVG path used.
- Missing files tolerated exactly as today: the affected card hides with a
  warning, the build stays green.

### 7.2 Payload

`payload["trends"]` (replacing `onset_trends`):

```jsonc
{
  "asof": "2026-09-20",
  "incomplete_from": "2026-09-13",   // resolved at build time, never in the browser
  "incomplete_days": 7,              // from manifest incomplete_styling.days
  "cases":      { "national": …, "provinces": {…}, "health_zones": {…} },
  "deaths":     { "national": …, "provinces": {…}, "health_zones": {…} },
  "positivity": { "national": …, "provinces": {…}, "health_zones": {…} },
  "labs":       [ … ],
  "lab_x":      { "start": "2026-05-01", "end": "2026-09-20" },
  "x_limits":   { "national": {…}, "provinces": {…}, "health_zones": {…} }
}
```

Per-entity encoding:

| Family | Shape | Notes |
|---|---|---|
| cases | `{start, obs[], imp[]}` | contiguous daily, zero-filled |
| deaths | `{start, cum[], daily[]}` | contiguous daily, `cum` forward-filled; `daily` needed for point placement (§6.3) |
| positivity | `{dates[], mean[], lo[], hi[]}` | sparse, full precision, stored as proportions; ×100 at render |
| labs | `{id, code, label, health_zone, province, earliest, dates[], n[], mean[], lo[], hi[]}` | sparse |

`x_limits` is precomputed server-side from §6.6 so the three cards cannot
disagree, and so the rule lives in one place with a test.

Projected size, measured against the 2026-09-20 production CSVs at full
precision:

| Family | Size |
|---|---:|
| cases | 25 KB |
| deaths (incl. `daily[]`) | 18 KB |
| positivity | 238 KB |
| labs | 83 KB |
| **total** | **363 KB** |

Against 5.35 MB today: **~15×** smaller, before page scoping (§7.3) removes it
from the other six pages entirely.

### 7.3 Page scoping

Add `"trends": {"trends"}` to `_PAGE_SCOPED_PAYLOAD_KEYS` in `chrome.py`.
Verified safe: every reader (`trendsPlotData`, `resolve*Plot`,
`renderTrends*`) is inside the trends view, and the renderers already handle a
null slice. The other six pages drop the slice entirely.

### 7.4 `Scripts/assets/charts.js` (new)

Primitives lifted from `genomic.js`; `genomic.js` keeps its own copy this round (D4).

| Primitive | Lifted from | Consumers |
|---|---|---|
| `svgEl(name, attrs)` | `genomic.js:265` | all |
| time/linear scales, `niceTicks`, `axisX`, `axisY` | Ne + dist panels | all |
| `stackedBars()` | dist panel (obs/imp) | cases |
| `bars()` | dist panel | labs |
| `ciBand()`, `line()`, `points()` | Ne panel | positivity, labs |
| `shadeRegion()` | dist panel ("beyond tree") | incomplete band |
| `markerLine()` + label | Ne panel (dashed tip dates) | lab earliest sample |
| `tooltip(host, svg, resolve)` | `.ne-tip` mousemove/mouseleave | all four |
| `dualAxis()` | **new** | labs |

`dualAxis()` is the only genuinely new primitive.

### 7.5 `Scripts/assets/trends.js` (new)

Four renderers on the existing card contract. `engine.js` keeps ownership of
scope/selection state and the map; `renderTrendsPlots()` becomes a delegation
to `window.TrendsCharts.render({scope, key})`. Loaded page-scoped from
`Scripts/pages/trends.py` via `render_page(..., extra_scripts=…)`, exactly as
`genomic.py` loads `genomic.js`.

Empty-state copy (`ui.trends_no_plot`, `ui.trends_select_province`,
`ui.trends_select_health_zone`, `ui.trends_no_labs`) is reused unchanged.

### 7.6 Removals

Python: `load_dashboard_plots()`, `_load_plot_type_family()`,
`_read_plot_svg()`, `_svg_plot_title()`, `_load_lab_name_map()`, and
`_slugify_plot_key()` if no other caller remains.

JS: `cropPlotSvgTop()`, `PLOT_SVG_TITLE_CROP`, the SVG branch of
`renderPlotCard()`, `asCodeArray()`/`trendsLabCodesForSelection()` if the
manifest-index fallback is no longer needed.

Fixtures: the 182 SVGs under `Data/dashboard_plots/` are replaced by four
small CSV fixtures. **Keep at least two production SVGs checked in under
`tests/fixtures/` as parity references** for §8.

### 7.7 i18n

Titles are composed client-side, so FR works end to end for the first time.
New strings, EN + FR, in `locales/`:

- Axis names: `Cases`, `Cumulative Deaths`, `Sample Positivity (%)`,
  `Samples Analysed`
- Legend: `Confirmed (Observed Onset)`, `Confirmed (Imputed Onset)`,
  `5-day Rolling Test Positivity`, `Reporting likely incomplete`
- Captions: the four caption strings and their incomplete-note variants (§6)
- `Earliest Sample: {date}`
- Tooltip field labels

Place names (provinces, health zones, lab long names) are proper nouns and are
**not** translated, consistent with current behaviour.

### 7.8 CI

No workflow change. `build-dashboard.yml` keeps the same checkout, the same
`EXTERNAL_REPO_TOKEN`, and the same `DASHBOARD_PLOTS_DIR`. Only which files
inside that directory are read changes.

## 8. Verification

Fidelity is the acceptance criterion, so verification is part of the
deliverable, not an afterthought.

1. **Cross-check against an independent existing path.** Assert the new
   national cases series equals `genomic.onset_distribution`'s national series.
   Both derive from `status_aggregated.csv`'s `confirmed_case` via independent
   code. Any divergence is a real bug in one of them. Free, and it runs in CI.
2. **Numeric parity harness.** A test that, for every location and every
   family, recomputes the series directly from the CSVs with a naive
   implementation and asserts equality with `load_trends_series()`'s output —
   including the zero-fill, the forward-fill, the skip rule (§6.1) and the
   shared x-limits (§6.6).
3. **Dropdown entity set is unchanged.** Assert the province and health-zone
   lists exactly equal those in the current `onset_trends` payload for the
   same snapshot — 6 provinces and 59 health zones at 2026-09-20 — and
   specifically that the five positivity-only zones (§6.1) are absent.
4. **Totals reconciliation.** Assert the national series equals the sum of the
   province series, and that both are consistent with the health-zone series,
   for cases and deaths.
5. **Visual A/B.** Build the page, screenshot each card at a fixed rail width,
   and compare side by side against the retained production SVG for the same
   location and snapshot. Manual gate, on: national, one province (Ituri), one
   health zone, and two labs (one dense, one sparse). Reviewed before merge.

   **One expected difference:** the lab charts' right-hand axis labels change
   from `0.00–1.00` to `0–100` (D6/§6.5). Every mark must sit in the same
   place; only those labels may differ. Any other difference is a bug.
6. **Empty/edge states.** A location with a single data point; a location whose
   positivity series is empty while cases exist; a snapshot whose latest date
   is older than the incomplete window (band absent → caption must lose its
   note); a missing CSV.
7. **Payload scoping test.** Mirror `tests/test_genomic_payload_scoping.py`.
8. **Serve a local build and hand over the URL for review before any PR**, per
   established practice for UI work on this repo.

No card ships until its numbers match under (1)–(4) and its appearance is
signed off under (5).

## 9. Risks

| Risk | Mitigation |
|---|---|
| The R generator changes and the charts silently drift | §5 records provenance; the parity harness (§8.2) pins behaviour; note the coupling in the README |
| Lab dual-axis is the fiddliest to match | Verified spec in §6.5; two labs in the visual gate (§8.4) |
| Sparse positivity mis-rendered as zero-filled | Called out in §6.4; covered by §8.2 and an explicit edge case in §8.5 |
| Shared x-limits missed, cards disagree about time | Precomputed server-side (§7.2) with its own test |
| Dropdown silently widens to positivity-only zones | §6.1 makes the cases family authoritative; asserted by §8.3 |
| Stale-source error recurs | §5 is explicit that a local checkout is not authoritative |

## 10. Resolved decisions

Both items below were open at review and have been decided. Rationale is kept
because each one changes something user-visible.

**O1 — Lab secondary axis mislabelled in the source. RESOLVED: fix it (b).**
`sec_axis(~ . / max_total)` with `mean_scaled = clamp(mean) * max_total` yields
a secondary axis reading **0–1**, while its name is `Sample Positivity (%)`.
Confirmed in the production SVG `lab_inrbk.svg`, whose secondary ticks are
`0.00 / 0.25 / 0.50 / 0.75 / 1.00`. The standalone positivity chart (§6.4)
multiplies by 100 and correctly reads 0–100. So the two charts label the same
quantity identically but on different scales.

- **(a) Replicate as-is** — pixel-faithful; perpetuates a mislabel that can be
  misread as "positivity ≈ 1%".
- **(b) Render 0–100 to match §6.4** — internally consistent and correct, but
  the lab card changes appearance versus today.

**Decided: (b).** Render 0–100, and report the mislabel upstream so the SVGs and
the dashboard converge. A number presented under the wrong unit is the one kind
of "different from today" worth accepting, and it is the mislabel — not the fix
— that misrepresents the data. Implementation detail in §6.5: tick labels only,
geometry untouched.

**O2 — Basis for the incomplete-reporting cutoff. RESOLVED: (a) + upstream ask.**
`incomplete_reporting_dates()` uses `Sys.Date() - n_days`, i.e. the wall-clock
date **when the R pipeline ran**. That date is not recorded in any output.

- **(a) `snapshot_date - n_days`** — the `outputs/<date>` folder name. Exact
  whenever the pipeline runs on the snapshot date; off by the sync lag when not.
- **(b) `max(data_date) - n_days`** — data-driven and fully reproducible, but
  can differ from today's band when reporting has a tail.
- **(c) Browser `new Date() - n_days`** — **rejected.** The band would drift as
  the page ages between builds; a page built Monday and viewed Friday would
  shade a window its own data does not support. This is the one option that
  actively misrepresents.

**Decided: (a)** now — `snapshot_date - n_days`, resolved at build time — plus an
upstream ask that the pipeline write the exact cutoff into `manifest.json`
(e.g. `incomplete_styling.cutoff`), after which we read it and the question
closes permanently. Until then the two can differ by the sync lag between the
pipeline run and the snapshot folder date; §8.6 covers the band-absent case.

**O3 — `MVE` in the deaths caption. Open, non-blocking.** French acronym (*maladie à virus Ebola*)
appearing in the English caption. Retained verbatim by default. Rendering it as
`EVD` in EN and `MVE` in FR is a one-line i18n change if wanted — flagging
rather than deciding, since it is user-visible wording.

## 11. Follow-ups (explicitly out of scope)

1. Migrate `genomic.js` onto `charts.js` and delete its duplicated primitives (D4).
2. Publish an allowlisted public aggregate feed and read that instead (D1).
3. Ask the R pipeline to stop emitting the now-unused SVG families.
4. Ask the R pipeline to record the incomplete-reporting cutoff in `manifest.json` (**confirmed follow-up**, D7/O2).
5. Report the lab secondary-axis mislabel upstream so the SVGs match the dashboard (**confirmed follow-up**, D6/O1).
