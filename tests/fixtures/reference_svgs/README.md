# Reference SVGs

These two files are retained samples of the pre-rendered charts the
Epidemiological Trends tab used to display, back when it rendered
R/ggplot2 SVG images produced by `4-make-dashboard-plots.R`.

They are kept as **data** references for the visual-comparison gate:
use them to check that the daily onset counts, dates, values, and gaps
in the current client-side charts still match what the R pipeline
produced, not to check appearance. They are **not** style references
— the live charts now follow the Genomic Epidemiology tab's visual
language, so colours, spacing, and fonts deliberately differ from what
these SVGs show.

Both files are from the 2026-07-28 `dashboard_plots` snapshot and use
the since-retired brick-red palette.

- `daily_onset_national.svg` — was
  `confirmed_cases_and_positivity/national/daily_onset_national.svg`
- `lab_inrbk.svg` — was `lab_plots/lab_inrbk.svg`
