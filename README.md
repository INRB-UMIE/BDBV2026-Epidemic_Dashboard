# Bundibugyo Ebola virus outbreak 2026 — Dashboard

![Logos for Project Lead Organizations: Institute National de Recherche Biomedicale (INRB), One Health Institute for Africa (INOHA), Institut National de Santé Publique (INSP), Unité de Modélisation et Intelligence Epidémique (UMIE), and AfricaCDC](https://github.com/INRB-UMIE/BDBV2026-Epidemic_Dashboard/blob/main/Data/Branding/all_logos.png)

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
- **dashboard_plots/** (optional) Pre-built province SVG charts for the Trends tab (`manifest.json` + `daily_onset_*.svg`). CI copies the latest plots from [BDBV2026-Linelist_Processing](https://github.com/INRB-UMIE/BDBV2026-Linelist_Processing) before each build; locally, run `src/3-dashboard_plots/build_onset_plots.py` there and copy into `Data/dashboard_plots/`.
- **Methods** Methods for dashboard, see below.
- **ToS** ToS for dashboard, see below. 

## Repository layout
```
BDBV-Epidemic_Dashboard/
├── Scripts/
│   └── build_dashboard_public.py   # builds output/dashboard.html
├── layer_config.yaml               # map layer exclusions, labels, palettes (requires PyYAML)
├── requirements.txt                # Python dependencies for the build script
├── Data/
│   ├── health_zone_metadata.csv    # fallback fields (relative risk, population bounds, etc.)
│   ├── ic_model_estimates.csv      # optional Imperial College bounds for tracker tooltip
│   ├── caveats.csv                 # optional tracker footnotes (metric + warning)
│   ├── dashboard_plots/            # optional Trends-tab SVGs (manifest.json + *.svg)
│   ├── Methods/Contributors_Methods_Data_website.docx
│   ├── ToS/Terms of Use.txt
│   └── Branding/                   # partner logos + urls.txt
├── output/
│   └── dashboard.html              # build artefact (self-contained, ~4 MB)
└── index.html                      # publicly served copy
```

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
python Scripts/build_dashboard_public.py
```

This produces a single self-contained `output/dashboard.html` that embeds
all geometry, per-zone aggregates, Methods text, Terms of Use, and partner
logos.

Override default paths with environment variables if the repos are not
sibling directories:

```bash
BUILD_DIR=/path/to/BDBV-Data/build \
DATA_ROOT=/path/to/Data \
python Scripts/build_dashboard_public.py
```

Copy the build to the site entry point before deploying to GitHub Pages:

```bash
cp output/dashboard.html index.html
```

## Automated rebuild (GitHub Actions)

Workflow [`.github/workflows/build-dashboard.yml`](.github/workflows/build-dashboard.yml) builds the dashboard from three sources:

| Source | Repo | Ref used |
|---|---|---|
| Geometry & datasets | [`BDBV2026-Data`](https://github.com/INRB-UMIE/BDBV2026-Data) | Latest GitHub **release** (or the exact commit dispatched after a data release) |
| Trends-tab SVGs | [`BDBV2026-Linelist_Processing`](https://github.com/INRB-UMIE/BDBV2026-Linelist_Processing) | `main` |
| Dashboard config & copy | this repo | triggering commit on `main` |

**Triggers:**

- **Push to `main`** (any file except `index.html` / `output/**`) — rebuild with latest data release + latest linelist plots.
- **Data release** — `release.yml` on the data repo dispatches after a successful release; uses that release commit.
- **Linelist plot update** — pushing `dashboard_plots/*.svg` or `manifest.json` to linelist `main` dispatches a rebuild (latest data release + that linelist commit).
- **Manual** — Actions → *Build dashboard* → optional `data_repo_ref` (empty = latest release) and `linelist_repo_ref` (default `main`).

Commits `output/dashboard.html` and `index.html` back to **`main`**.

**Secrets (this repo):**

| Secret | Purpose |
|---|---|
| `EXTERNAL_REPO_TOKEN` | Fine-grained PAT with **Contents: Read** on `BDBV2026-Linelist_Processing` only (private repo checkout) |

**Secret (data repo only):** `DASHBOARD_DISPATCH_TOKEN` — fine-grained PAT with **Contents: Write** on `BDBV2026-Epidemic_Dashboard`. Without it, release dispatch steps warn and skip (local/manual builds still work).

## Citation
Please cite the original data providers (links above) and this repository if any code or derived data is reused.

INRB/INOHA/INSP DRC Data Dashboard DOI: 10.5281/zenodo.20347624

## Additional license, warranty, and copyright information
We provide a license for our code (see LICENSE) and do not claim ownership, nor the right to license, the data we have obtained nor any third-party software tools/code used in our analyses.  Please cite the appropriate agency, paper, and/or individual in publications and/or derivatives using these data, contact them regarding the legal use of these data, and remember to pass-forward any existing license/warranty/copyright information.  As a reminder (even though you are not supposed to copy/use anything in this repository), should you violate our license, THE DATA AND SOFTWARE ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE DATA AND/OR SOFTWARE OR THE USE OR OTHER DEALINGS IN THE DATA AND/OR SOFTWARE.
