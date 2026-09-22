[![DOI](https://zenodo.org/badge/1245855497.svg)](https://doi.org/10.5281/zenodo.20347623)

# Bundibugyo Ebola virus outbreak 2026 — Dashboard

![Logos for Project Lead Organizations: Institute National de Recherche Biomedicale (INRB), Institut National de Santé Publique (INSP), Unité de Modélisation et Intelligence Epidémique (UMIE), and AfricaCDC](https://github.com/INRB-UMIE/BDBV2026-Epidemic_Dashboard/blob/main/Data/Branding/all_logos.png)

This work is led by the Institut National de Recherche Biomédicale (INRB) Kinshasa/One Health Institute for Africa (INOHA) Kinshasa (Dav Ebengo, Placide Mbala-Kingebeni and Tania Bishola), and the Institut National de Santé Publique (INSP) (Pierre Akilimali, Adelard Lofungola).

**Collaborating institutions and agencies**
- Institut National de Santé Publique (INSP)
- National Institute of Biomedical Research (INRB)
- Africa Centres for Disease Control and Prevention, Addis Ababa, Ethiopia
- World Health Organization, Geneva, Switzerland
- World Health Organization Country Office, Kinshasa, Democratic Republic of the Congo
- Northeastern University, United States
- University of Oxford, United Kingdom

# Statement on continuing work and analyses before publication
Please note that the epidemiological data presented here is based on work in progress and should be considered preliminary. Our analyses are ongoing, and a publication communicating our findings is in preparation. Contextual data are publicly accessible; please refer to the original license when re-using these data. If you intend to use the epidemiological data prior to our publication, or have other enquiries, please contact [Prof. Placide Mbala-Kingebeni](mailto:placide.mbala@inrb.cd) (INRB, DRC), [Prof. Dav Ebengo](mailto:dav.ebengo@umie-inrb.org) (INRB, DRC), and [Pierre Akilimali](mailto:pierre.akilimali@insp.cd) (INSP).

## Data
- **health_zone_metadata.csv** Metadata file for dashboard, see below. 
- **ic_model_estimates.csv** (optional) Imperial College model date and case bounds for the tracker tooltip (`PAYLOAD.ic_model`; independent of INSP sitreps).
- **caveats.csv** (optional) Per-metric warnings in the title-panel tracker: `metric` (`confirmed_cases`, `suspected_cases`, `confirmed_deaths`, `suspected_deaths`) and `warning` text; adds a mark beside the count and a footnote below.
- **dashboard_plots/** (optional) The aggregated CSVs the Trends tab charts are drawn from (`manifest.json` + `<date>/{status_aggregated,cumulative_positive_deaths,rolling_positivity,lab_positivity_aggregated}.csv`), produced by [BDBV2026-Processed_Sensitive_Data](https://github.com/INRB-UMIE/BDBV2026-Processed_Sensitive_Data)'s `outputs/` directory. The build reads this directly, no copying into `Data/dashboard_plots/` needed. By default it assumes that repo is cloned as a sibling of this one (`../BDBV2026-Processed_Sensitive_Data/outputs`); set `DASHBOARD_PLOTS_DIR` to override. The same directory also holds pre-rendered SVGs of these charts, which the dashboard **no longer reads** — it draws them client-side from the CSVs instead (see `Scripts/assets/trends.js` and `Scripts/assets/charts.js`). The charts must stay faithful to the *data* produced by `BDBV2026-Processing_Code`'s `4-make-dashboard-plots.R`; their visual style follows the Genomic Epidemiology tab. See `docs/superpowers/specs/2026-09-22-trends-dynamic-charts-design.md`.
- **Methods** Methods for dashboard, see below.
- **ToS** ToS for dashboard, see below. 

## Dashboard tabs

Beyond the shared map engine and header/footer chrome (see "Multi-page
structure" below), each of the four "real" pages has its own controls and
responsive behaviour worth documenting here, since none of it is obvious
from the code alone.

**Current Snapshot** (`index.html`) — the main map, coloured by whichever
layer is selected (confirmed/suspected cases, deaths, genomic sequencing,
etc.), with a health-zone search, a layer-controls panel (top-left), and a
zone-details panel (top-right). Both side panels are collapsible via the
toggle in their header. On narrow screens (≤700px) the Leaflet zoom control
is hidden (pinch-to-zoom is used instead) and both panels start collapsed to
just their title bar, pinned to the top of the map pane.

**Epidemiological Trends** (`trends.html`) — a right-hand rail with
National / Provincial / Health Zone scope buttons and a location search
(matches every province and health zone, regardless of whether a plot
exists for it) above a scrollable column of plot cards: daily cases by
symptom onset (shown by default), cumulative deaths, test positivity, and
per-lab submission subplots, all filtered to the selected scope. The map
itself animates cumulative confirmed cases over time and autoplays on
entering the tab; the map/plots split (60:40 by default) is user-draggable
and remembered per browser via `localStorage`. The Leaflet zoom control is
hidden on this tab at every screen size. On narrow screens the map and
plots column stack vertically instead of sitting side by side, and the
location search relocates into the map's top-left corner (the zoom
control's old spot).

**Spatial Risk** (`spatial-risk.html`) — National / Provincial scope
buttons and a location search (shares its search index with Trends) above
a health-zone table ranked by invasion risk. Any column header is
clickable/focusable to sort by it (a ▲/▼ arrow marks the active column and
direction), replacing the old fixed "rank by relative risk / rank by
priority" buttons. There's no dedicated Health Zone scope, since ranking a
table of one zone isn't meaningful — picking one from search selects/
highlights its row instead of filtering the list. The map-colouring legend
is collapsible and sits bottom-right of the map pane on wide screens
(top-left on narrow screens). The Leaflet zoom control is hidden on this
tab at every screen size. On narrow screens the map and ranked table stack
vertically instead of sitting side by side.

### Narrow-screen (≤700px) behaviour shared by every page

- The site header collapses to a compact stack; the SitRep/build-info line
  and the Methods/Terms links move into a tap-to-expand info icon instead
  of sitting in the footer.
- The page tabs become a single horizontally-scrollable row instead of
  wrapping onto multiple lines.
- Every collapsible panel (layer controls, legends, plot cards) plus the
  Current Snapshot zone-details panel auto-collapses to just its title bar
  on load.

## Repository layout
```
BDBV-Epidemic_Dashboard/
├── Scripts/
│   ├── build_dashboard.py          # master/orchestrator -- builds all 7 pages
│   ├── common/
│   │   ├── paths.py                 # DATA_ROOT, BUILD_DIR, output filenames, etc.
│   │   ├── data_sources.py          # all data-loading functions (geometry, metadata,
│   │   │                            #   ic model, matrices, plots, phr context, ...)
│   │   ├── payload.py               # build_shared_payload() -- one JSON payload shared
│   │   │                            #   by every page (see "Multi-page structure")
│   │   ├── theme.py                 # theme CSS loader + JSON serialization helper
│   │   └── chrome.py                # shared <head>/CSS wiring + body markup + nav bar +
│   │                                 #   STUB_VIEWS ("coming soon" pages, see below)
│   ├── assets/
│   │   ├── dashboard.css            # extracted base stylesheet (+ theme layer at build time)
│   │   └── engine.js                # shared JS engine (map, panels, i18n, view logic)
│   └── pages/
│       ├── snapshot.py              # "Current Snapshot"          -> output/index.html
│       ├── trends.py                # "Epidemiological Trends"    -> output/trends.html
│       ├── spatial_risk.py          # "Spatial Risk"               -> output/spatial-risk.html
│       ├── context.py               # "Public Health Context"      -> output/context.html
│       ├── clinical_symptoms.py     # "Clinical Symptoms" (stub)   -> output/clinical-symptoms.html
│       ├── surveillance_testing.py  # "Surveillance and Testing" (stub) -> output/surveillance-testing.html
│       └── genomic_epidemiology.py  # "Genomic Epidemiology" (stub) -> output/genomic-epidemiology.html
├── layer_config.yaml               # map layer exclusions, labels, palettes (requires PyYAML)
├── requirements.txt                # Python dependencies for the build script
├── Data/
│   ├── health_zone_metadata.csv    # fallback fields (relative risk, population bounds, etc.)
│   ├── ic_model_estimates.csv      # optional Imperial College bounds for tracker tooltip
│   ├── caveats.csv                 # optional tracker footnotes (metric + warning)
│   ├── dashboard_plots/            # optional Trends-page CSVs (manifest.json + *.csv)
│   ├── Methods/Contributors_Methods_Data_website.docx
│   ├── ToS/Terms of Use.txt
│   └── Branding/                   # partner logos, urls.txt, dashboard-theme.css (cream theme)
├── output/                         # build artefacts (7 pages + shared assets)
│   ├── index.html                  # Current Snapshot
│   ├── trends.html                 # Epidemiological Trends
│   ├── spatial-risk.html           # Spatial Risk
│   ├── context.html                # Public Health Context
│   ├── clinical-symptoms.html      # Clinical Symptoms (coming soon)
│   ├── surveillance-testing.html   # Surveillance and Testing (coming soon)
│   ├── genomic-epidemiology.html   # Genomic Epidemiology (coming soon)
│   └── assets/
│       ├── dashboard.css
│       └── engine.js
├── index.html, trends.html, spatial-risk.html, context.html,
│   clinical-symptoms.html, surveillance-testing.html, genomic-epidemiology.html  # publicly served copies
└── assets/                         # publicly served copy of output/assets/
```

### Multi-page structure

The dashboard used to be one HTML file with tabs sharing a single Leaflet
map instance, JS-toggled between them. It's now separate pages/URLs (real
navigation, not JS tab-switching), each built by its own script in
`Scripts/pages/`, assembled by the master `Scripts/build_dashboard.py`.

**Still shared across every page, for now:** the JSON data payload
(`common/payload.py`) and the JS engine (`assets/engine.js`). This is
deliberate, not an oversight -- Trends and Context both drive their content
by clicking the *same* Leaflet map (province/health-zone selection), so all
four "real" pages currently need the full map + full payload, not just
Snapshot and Spatial risk. Splitting the payload/engine further so each page
only ships what it needs (e.g. Trends wouldn't need `invasion_risk`, Context
wouldn't need `matrices`/`flow_catalogs`) is a natural follow-up once you
decide whether Trends/Context should keep their map-click interaction or
move to a simpler dropdown-based selector.

**"Coming soon" stub pages:** Clinical Symptoms, Surveillance and Testing,
and Genomic Epidemiology are placeholders (`STUB_VIEWS` in
`common/chrome.py`) -- they get the same shared header/tabs/footer chrome
and the same full map engine/payload underneath (currently hidden via a
`stub-view` body class) as the four real pages, just showing a "coming
soon" panel instead of real content. When you're ready to build these out,
each one's `pages/*.py` module is the place to add real payload/markup, and
you may want to drop the "carries the full map payload for no reason" cost
at the same time.

Each page in `Scripts/pages/` is currently a thin wrapper around
`common.chrome.render_page(view_id, payload)` -- that's the seam to hang any
future page-specific logic on (payload trimming, page-specific JS, etc.).

## Prerequisites

**Required companion repo:** The build script reads geometry, epidemiological
data, population, health facility, OSRM travel-time, IDP, and Flowminder
data from the [BDBV2026-Data](https://github.com/INRB-UMIE/BDBV2026-Data)
repository. It must be cloned as a sibling directory:

```
inrb/
├── BDBV-Data/               # companion repo (must be built first)
│   ├── build/
│   │   ├── drc_health_zones.geojson   # zone polygons + embedded properties
│   │   └── long/                      # OSRM matrices, etc.
│   └── data/
│       ├── IDP/processed/             # displacement matrices
│       └── flowminder/processed/      # mobility matrices
└── BDBV-Epidemic_Dashboard/           # this repo
```

Run the BDBV2026-Data build pipeline first so that `build/` is populated.

## Setup

Dependencies: Python 3.10+ with `pandas`, `python-docx`, `shapely`, `numpy`, and
`PyYAML` (reads `layer_config.yaml` for map layer exclusions and styling).

**pip (venv or existing Python):**

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**conda:**

```bash
conda create -n ebov2026 -c conda-forge python=3.12 \
    pandas python-docx shapely numpy pyyaml
conda activate ebov2026
```

## Building the dashboard

```bash
python Scripts/build_dashboard.py
```

This produces four pages in `output/` (`index.html`, `spatial-risk.html`,
`trends.html`, `context.html`) plus `output/assets/` (`dashboard.css`,
`engine.js`), embedding all geometry, per-zone aggregates, Methods text,
Terms of Use, and partner logos into each page's inline JSON payload.

Override default paths with environment variables if the repos are not
sibling directories:

```bash
BUILD_DIR=/path/to/BDBV-Data/build \
DATA_ROOT=/path/to/Data \
DASHBOARD_PLOTS_DIR=/path/to/BDBV2026-Processed_Sensitive_Data/outputs \
python Scripts/build_dashboard.py
```

`DASHBOARD_PLOTS_DIR` is optional and independent of `DATA_ROOT` -- point it
straight at a checked-out/mounted copy of `BDBV2026-Processed_Sensitive_Data`'s
`outputs/` directory to build Trends-tab plots from it directly, with no copy
step. Leave it unset and it defaults to `../BDBV2026-Processed_Sensitive_Data/outputs`
(a sibling of this repo), same convention as `BUILD_DIR` above.

### CARTO basemap key

The map's basemap tiles come from CARTO's raster endpoint
(`basemaps.cartocdn.com/light_all`), which since 2026 requires an API key.
Without one the tiles still render, but under a repeated **"API key required"**
watermark. Keys are free (no CARTO account needed) up to a fair-use limit of 5M
tile requests per calendar month: <https://carto.com/basemaps/apikey>.

`Scripts/assets/engine.js` holds a `{{CARTO_BASEMAP_KEY}}` placeholder;
`Scripts/build_dashboard.py` substitutes the `CARTO_BASEMAP_KEY` environment
variable into it when writing `assets/engine.js`:

```bash
CARTO_BASEMAP_KEY=your_key_here python Scripts/build_dashboard.py
```

Leave it unset and the build still succeeds, printing a warning and producing a
watermarked map -- the intended default for local iteration, so day-to-day work
doesn't spend the shared quota.

**The key is public, and that is expected.** This is a static site: whatever key
the build injects is served in `assets/engine.js` to every visitor. CARTO
basemap keys are designed as client-side credentials (the protection is the
per-key fair-use quota, not secrecy), so this is not a leak — but it does mean
the key must not be treated as one, and CARTO's terms require only that the
OSM/CARTO attribution stays visible on the map. In CI it is held as the
`CARTO_BASEMAP_KEY` repository secret purely so it lives in one rotatable place
instead of in the source; both `build-dashboard.yml` and `pr-preview.yml` pass
it through. Set it under **Settings → Secrets and variables → Actions**.

Note that CARTO is retiring these raster basemaps in favour of vector ones
(`light_all` → `positron-gl-style`). That migration means moving the map from
Leaflet to MapLibre GL JS and is not done here; the key applies to both.

Copy the build to the site entry point before deploying to GitHub Pages:

```bash
cp output/index.html output/spatial-risk.html output/trends.html output/context.html .
rm -rf assets && cp -r output/assets assets
```

## Automated rebuild (GitHub Actions)

Workflow [`.github/workflows/build-dashboard.yml`](.github/workflows/build-dashboard.yml) builds the dashboard from three sources:

| Source | Repo | Ref used |
|---|---|---|
| Geometry & datasets | [`BDBV2026-Data`](https://github.com/INRB-UMIE/BDBV2026-Data) | Latest GitHub **release** (or the exact commit dispatched after a data release) |
| Trends-tab series CSVs | [`BDBV2026-Processed_Sensitive_Data`](https://github.com/INRB-UMIE/BDBV2026-Processed_Sensitive_Data) (`outputs/`) | `main` |
| Dashboard config & copy | this repo | triggering commit on `main` |

The processed-data repo is checked out to `BDBV2026-Processed_Sensitive_Data/`
in the runner's workspace and the build points `DASHBOARD_PLOTS_DIR` straight
at its `outputs/` directory -- there's no separate copy/rsync step, so the
build always reads whatever that checkout has.

**Triggers:**

- **Push to `main`** (any file except `index.html` / `output/**`) — rebuild with latest data release + latest processed-data plots.
- **Data release** — `release.yml` on the data repo dispatches after a successful release; uses that release commit.
- **Processed-data plot update** — pushing `outputs/*/dashboard_plots/` or `outputs/manifest.json` to the processed-data repo's `main` dispatches a rebuild (latest data release + that processed-data commit). Field/event names (`linelist_repo_ref`, `linelist-updated`, etc.) are historical, kept as a contract with that repo's dispatch sender -- see the workflow file's header comment.
- **Manual** — Actions → *Build dashboard* → optional `data_repo_ref` (empty = latest release) and `linelist_repo_ref` (default `main`).

Commits `output/` (all four pages + `assets/`) and the repo-root copies
(`index.html`, `spatial-risk.html`, `trends.html`, `context.html`, `assets/`)
back to **`main`**.

**Secrets (this repo):**

| Secret | Purpose |
|---|---|
| `EXTERNAL_REPO_TOKEN` | Fine-grained PAT with **Contents: Read** on `BDBV2026-Processed_Sensitive_Data` only (private repo checkout) |

**Secret (data repo only):** `DASHBOARD_DISPATCH_TOKEN` — fine-grained PAT with **Contents: Write** on `BDBV2026-Epidemic_Dashboard`. Without it, release dispatch steps warn and skip (local/manual builds still work).

## Citation
You can reference this repository by its [Zenodo DOI](https://doi.org/10.5281/zenodo.20347624) and the accompannying publication on [Lancet Infectious Diseases by Mbulayi et al](https://www.thelancet.com/journals/laninf/article/PIIS1473-3099(26)00330-0/fulltext). Please cite the original data providers (links above) if any code or derived data is reused.

INRB/INOHA/INSP DRC Data Dashboard DOI: 10.5281/zenodo.20347624

## Additional license, warranty, and copyright information
We provide a license for our code (see LICENSE) and do not claim ownership, nor the right to license, the data we have obtained nor any third-party software tools/code used in our analyses.  Please cite the appropriate agency, paper, and/or individual in publications and/or derivatives using these data, contact them regarding the legal use of these data, and remember to pass-forward any existing license/warranty/copyright information.  As a reminder (even though you are not supposed to copy/use anything in this repository), should you violate our license, THE DATA AND SOFTWARE ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE DATA AND/OR SOFTWARE OR THE USE OR OTHER DEALINGS IN THE DATA AND/OR SOFTWARE.
