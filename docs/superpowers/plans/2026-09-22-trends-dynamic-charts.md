# Epidemiological Trends Dynamic Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the pre-rendered ggplot2/svglite SVGs on the Epidemiological Trends tab with charts drawn client-side from the aggregated CSVs that already back them, with no change to the numbers shown.

**Architecture:** A new Python loader (`load_trends_series()`) reads four aggregated CSVs from the private processed-data repo's `outputs/<date>/` and emits a compact `payload["trends"]` slice (363 KB vs the 5.35 MB of inlined SVG it replaces). A new page-scoped `assets/trends.js` renders four cards using primitives extracted into a new shared `assets/charts.js`, in the same hand-rolled runtime-SVG idiom as `genomic.js`.

**Tech Stack:** Python 3.9+ stdlib (`csv`, `json`, `datetime`), pytest, vanilla ES5-style JS (no framework, no charting library), SVG via `document.createElementNS`.

**Spec:** `docs/superpowers/specs/2026-09-22-trends-dynamic-charts-design.md` — read §6 (fidelity contract) before starting. Section numbers below refer to it.

---

## Ground rules

- **Run tests from `Scripts/`:** `cd Scripts && python3.9 -m pytest ../tests/<file> -v`. Use `python3.9`, not the system `python3`.
- **A full build needs the sibling data repo** at `../BDBV2026-Data/build`. Tasks 1–5 and 15 are pure unit tests and need nothing else.
- **Never commit with a `Co-Authored-By` trailer or any Claude/AI mention.** This repo's history must not carry one.
- **Fidelity is the acceptance criterion.** If a step's behaviour seems wrong or redundant, do not "improve" it — it is transcribed from the generator. Raise it instead.

## File structure

| File | Responsibility |
|---|---|
| `Scripts/common/data_sources.py` | **Modify.** Add `load_trends_series()` + private packers. Delete the SVG loader family in Task 16. |
| `Scripts/common/payload.py` | **Modify.** Swap `onset_trends` for `trends`. |
| `Scripts/common/chrome.py` | **Modify.** Page-scope the `trends` key. |
| `Scripts/pages/trends.py` | **Modify.** Load `trends.js` via `extra_scripts`. |
| `Scripts/build_dashboard.py` | **Modify.** Write `charts.js` + `trends.js` into `output/assets/`. |
| `Scripts/assets/charts.js` | **Create.** Shared runtime-SVG primitives. No page knowledge. |
| `Scripts/assets/trends.js` | **Create.** The four Trends cards. Owns no state. |
| `Scripts/assets/engine.js` | **Modify.** Delegate rendering; delete the SVG path. |
| `Scripts/assets/dashboard.css` | **Modify.** Chart + tooltip styles (dark base). |
| `Data/Branding/dashboard-theme.css` | **Modify.** Light-theme overrides — **required**, or custom controls render wrong. |
| `locales/{en,fr}.json` | **Modify.** New chart strings. |
| `tests/test_trends_series.py` | **Create.** Packing/fidelity unit tests. |
| `tests/test_trends_parity.py` | **Create.** Cross-checks (§8.1, §8.3, §8.4). |
| `tests/test_trends_payload_scoping.py` | **Create.** Mirrors the genomic scoping test. |

---

### Task 1: Cases packer

Packs `status_aggregated.csv` into per-location daily arrays. **Semantics (§6.1, §6.2):** counts are `confirmed_case` **only**; rows with the same (location, date, imputed-flag) **accumulate**; a location whose total confirmed is 0 is **skipped entirely**; leading zero-days are **trimmed** to the first positive date (restricted to ≥ 2026-01-01 when any positive date qualifies), trailing zero-days are **kept**; internal gaps are zero-filled.

**Files:**
- Modify: `Scripts/common/data_sources.py`
- Test: `tests/test_trends_series.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_trends_series.py`:

```python
import importlib
from pathlib import Path

ds = importlib.import_module("common.data_sources")

# Transcribed from BDBV2026-Processing_Code@main 4-make-dashboard-plots.R.
# confirmed_case ONLY -- blank/not_a_case/suspected/probable are decoys here.
CASES_CSV = (
    "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
    "blank,not_a_case,suspected_case,probable_case,spatial_scale,province,health_zone\n"
    # national: a leading zero-day that must be TRIMMED
    "2026-05-01,FALSE,0,99,99,99,99,national,NA,NA\n"
    "2026-05-02,FALSE,2,0,0,0,0,national,NA,NA\n"
    "2026-05-02,TRUE,1,0,0,0,0,national,NA,NA\n"
    # duplicate row for the same (date, flag) -- must ACCUMULATE to 3
    "2026-05-02,FALSE,1,0,0,0,0,national,NA,NA\n"
    # 2026-05-03 absent entirely -- must be zero-FILLED
    "2026-05-04,FALSE,5,0,0,0,0,national,NA,NA\n"
    # a trailing zero-day that must be KEPT
    "2026-05-05,FALSE,0,0,0,0,0,national,NA,NA\n"
    "2026-05-02,FALSE,4,0,0,0,0,province,Ituri,NA\n"
    "2026-05-02,FALSE,1,0,0,0,0,healthzone,NA,  BUNIA \n"
    # zero-total zone -- must be SKIPPED entirely (not emitted as all-zeros)
    "2026-05-02,FALSE,0,50,50,50,50,healthzone,NA,Nyarambe\n"
    # unparseable / blank dates are dropped
    ",FALSE,7,0,0,0,0,national,NA,NA\n"
)


def test_cases_packs_accumulates_trims_and_zero_fills(tmp_path):
    (tmp_path / "status_aggregated.csv").write_text(CASES_CSV, encoding="utf-8")

    out = ds._pack_trends_cases(tmp_path / "status_aggregated.csv", canon=lambda s: {"bunia": "Bunia"}.get(s.strip().lower(), s.strip()))

    nat = out["national"]["national"]
    assert nat["start"] == "2026-05-02"          # 05-01 zero-day trimmed off the front
    assert nat["obs"] == [3, 0, 5, 0]            # duplicate accumulated; 05-03 zero-filled; 05-05 kept
    assert nat["imp"] == [1, 0, 0, 0]

    assert out["province"]["Ituri"] == {"start": "2026-05-02", "obs": [4], "imp": [0]}
    assert out["healthzone"]["Bunia"] == {"start": "2026-05-02", "obs": [1], "imp": [0]}
    assert "Nyarambe" not in out["healthzone"]   # zero-total location skipped (spec 6.1)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd Scripts && python3.9 -m pytest ../tests/test_trends_series.py -v
```

Expected: `FAILED` with `AttributeError: module 'common.data_sources' has no attribute '_pack_trends_cases'`.

- [ ] **Step 3: Implement the packer**

Add to `Scripts/common/data_sources.py`, immediately before `def _onset_manifest_dated_dir` (~line 4293):

```python
# --- Trends series packers -------------------------------------------------
# These reproduce BDBV2026-Processing_Code@main's 4-make-dashboard-plots.R
# exactly; see docs/superpowers/specs/2026-09-22-trends-dynamic-charts-design.md
# section 6. Do not "tidy" the asymmetries below -- cases ACCUMULATE duplicate
# rows while deaths/positivity OVERWRITE (last row wins), and only cases skip
# zero-total locations. That is what the generator does.

_TRENDS_SCALES = (("national", None), ("province", "province"), ("healthzone", "health_zone"))
_TRENDS_EPOCH = "2026-01-01"


def _trends_loc(row, key_field):
    """Location name for a row, or None when it should be dropped."""
    if key_field is None:
        return "national"
    name = (row.get(key_field) or "").strip()
    if not name or name.upper() == "NA":
        return None
    return name


def _day_range(start, end):
    """Inclusive list of ISO dates from start to end."""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    return [(s + timedelta(days=i)).isoformat() for i in range((e - s).days + 1)]


def _pack_trends_cases(path, canon=None):
    """{scale: {location: {start, obs[], imp[]}}} from status_aggregated.csv."""
    canon = canon or (lambda s: s)
    buckets = {scale: {} for scale, _ in _TRENDS_SCALES}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            scale = (row.get("spatial_scale") or "").strip().lower()
            key_field = dict(_TRENDS_SCALES).get(scale, "__missing__")
            if key_field == "__missing__":
                continue
            loc = _trends_loc(row, key_field)
            if loc is None:
                continue
            if key_field is not None:
                loc = canon(loc)
            day = (row.get("date_of_symptom_onset_imputed") or "").strip()
            if not _ONSET_DATE_RE.match(day):
                continue
            slot = "imp" if (row.get("onset_date_was_imputed") or "").strip().upper() == "TRUE" else "obs"
            entry = buckets[scale].setdefault(loc, {}).setdefault(day, {"obs": 0, "imp": 0})
            entry[slot] += _i(row.get("confirmed_case"))   # ACCUMULATE

    packed = {scale: {} for scale, _ in _TRENDS_SCALES}
    for scale, by_loc in buckets.items():
        for loc, by_day in by_loc.items():
            if sum(v["obs"] + v["imp"] for v in by_day.values()) <= 0:
                continue                                    # spec 6.1 skip rule
            positives = [d for d, v in by_day.items() if v["obs"] + v["imp"] > 0]
            in_epoch = [d for d in positives if d >= _TRENDS_EPOCH]
            start = min(in_epoch or positives)
            end = max(by_day)                               # trailing zeros KEPT
            days = _day_range(start, end)
            packed[scale][loc] = {
                "start": start,
                "obs": [by_day.get(d, {}).get("obs", 0) for d in days],
                "imp": [by_day.get(d, {}).get("imp", 0) for d in days],
            }
    return packed
```

At the top of `Scripts/common/data_sources.py`, ensure the date imports exist. If the file already imports `datetime`, add the names; otherwise add this line next to the other stdlib imports:

```python
from datetime import date, timedelta
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd Scripts && python3.9 -m pytest ../tests/test_trends_series.py -v
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add Scripts/common/data_sources.py tests/test_trends_series.py
git commit -m "Add cases packer for the Trends data slice"
```

---

### Task 2: Deaths packer

**Semantics (§6.3):** duplicate rows **overwrite** (last wins, unlike cases); **no zero-total skip**; the series spans the first→last reporting date present for that location with **no leading trim**; gaps set `daily=0` and **carry `cum` forward** from the last observed value.

**Files:**
- Modify: `Scripts/common/data_sources.py`
- Test: `tests/test_trends_series.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_trends_series.py`:

```python
DEATHS_CSV = (
    "country,reporting_date,daily_deaths,cumulative_deaths,spatial_scale,province,health_zone\n"
    "DRC,2026-05-01,1,1,national,NA,NA\n"
    # 05-02 and 05-03 absent -- daily must be 0 and cumulative CARRIED FORWARD at 1
    "DRC,2026-05-04,2,3,national,NA,NA\n"
    # duplicate date: last row WINS (not summed) -- unlike cases
    "DRC,2026-05-04,9,4,national,NA,NA\n"
    "DRC,2026-05-01,0,0,healthzone,NA,Rwampara\n"   # all-zero location is KEPT
)


def test_deaths_forward_fills_overwrites_duplicates_and_keeps_zero_locations(tmp_path):
    (tmp_path / "cumulative_positive_deaths.csv").write_text(DEATHS_CSV, encoding="utf-8")

    out = ds._pack_trends_deaths(tmp_path / "cumulative_positive_deaths.csv", canon=lambda s: s)

    nat = out["national"]["national"]
    assert nat["start"] == "2026-05-01"
    assert nat["cum"] == [1, 1, 1, 4]     # carried forward across the gap; duplicate overwrote 3 -> 4
    assert nat["daily"] == [1, 0, 0, 9]   # gap days are 0; duplicate overwrote 2 -> 9
    # deaths have NO zero-total skip (that rule is cases-only, spec 6.1/6.3)
    assert out["healthzone"]["Rwampara"] == {"start": "2026-05-01", "cum": [0], "daily": [0]}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd Scripts && python3.9 -m pytest ../tests/test_trends_series.py -v
```

Expected: `AttributeError: ... has no attribute '_pack_trends_deaths'`.

- [ ] **Step 3: Implement the packer**

Add directly beneath `_pack_trends_cases` in `Scripts/common/data_sources.py`:

```python
def _pack_trends_deaths(path, canon=None):
    """{scale: {location: {start, cum[], daily[]}}} from cumulative_positive_deaths.csv.

    `daily` is carried in the payload because the chart draws a point ONLY on
    days where daily_deaths > 0 (spec 6.3); it is not otherwise plotted.
    """
    canon = canon or (lambda s: s)
    buckets = {scale: {} for scale, _ in _TRENDS_SCALES}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            scale = (row.get("spatial_scale") or "").strip().lower()
            key_field = dict(_TRENDS_SCALES).get(scale, "__missing__")
            if key_field == "__missing__":
                continue
            loc = _trends_loc(row, key_field)
            if loc is None:
                continue
            if key_field is not None:
                loc = canon(loc)
            day = (row.get("reporting_date") or "").strip()
            if not _ONSET_DATE_RE.match(day):
                continue
            # OVERWRITE, last row wins -- deliberately unlike _pack_trends_cases
            buckets[scale].setdefault(loc, {})[day] = (
                _i(row.get("daily_deaths")), _i(row.get("cumulative_deaths"))
            )

    packed = {scale: {} for scale, _ in _TRENDS_SCALES}
    for scale, by_loc in buckets.items():
        for loc, by_day in by_loc.items():
            if not by_day:
                continue                       # no zero-total skip: only "no rows at all"
            days = _day_range(min(by_day), max(by_day))
            cum, daily, last = [], [], 0
            for d in days:
                if d in by_day:
                    daily.append(by_day[d][0])
                    last = by_day[d][1]
                else:
                    daily.append(0)
                cum.append(last)               # carry forward
            packed[scale][loc] = {"start": days[0], "cum": cum, "daily": daily}
    return packed
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd Scripts && python3.9 -m pytest ../tests/test_trends_series.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add Scripts/common/data_sources.py tests/test_trends_series.py
git commit -m "Add cumulative-deaths packer for the Trends data slice"
```

---

### Task 3: Positivity packer

**Semantics (§6.4):** **sparse** — keep only dates present, never zero-fill (the rendered line connects straight across gaps); duplicate dates **overwrite**; values stay as proportions at **full float precision** (D5) and are multiplied by 100 at render time, not here.

**Files:**
- Modify: `Scripts/common/data_sources.py`
- Test: `tests/test_trends_series.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_trends_series.py`:

```python
POS_CSV = (
    "country,date_of_symptom_onset_imputed,confirmed_case,total_samples_analysed_daily,"
    "spatial_scale,province,health_zone,rolling_confirmed,rolling_total,"
    "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
    "NA,2026-05-01,1,1,national,NA,NA,1,1,0.206549314377238,0.1,0.9\n"
    # 05-02 absent: must stay ABSENT, not zero-filled (spec 6.4)
    "NA,2026-05-03,0,1,national,NA,NA,0,1,0.5,0.25,0.75\n"
    # duplicate date: last row WINS
    "NA,2026-05-03,0,1,national,NA,NA,0,1,0.6,0.3,0.8\n"
    "NA,2026-05-01,1,1,healthzone,NA,Nyankunde,1,1,1,0.2,1\n"
)


def test_positivity_is_sparse_overwrites_and_keeps_full_precision(tmp_path):
    (tmp_path / "rolling_positivity.csv").write_text(POS_CSV, encoding="utf-8")

    out = ds._pack_trends_positivity(tmp_path / "rolling_positivity.csv", canon=lambda s: s)

    nat = out["national"]["national"]
    assert nat["dates"] == ["2026-05-01", "2026-05-03"]     # 05-02 NOT invented
    assert nat["mean"] == [0.206549314377238, 0.6]          # full precision; duplicate overwrote
    assert nat["lo"] == [0.1, 0.3]
    assert nat["hi"] == [0.9, 0.8]
    assert out["healthzone"]["Nyankunde"]["mean"] == [1.0]  # proportion, NOT scaled to 100 here
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd Scripts && python3.9 -m pytest ../tests/test_trends_series.py -v
```

Expected: `AttributeError: ... has no attribute '_pack_trends_positivity'`.

- [ ] **Step 3: Implement the packer**

Add directly beneath `_pack_trends_deaths`:

```python
def _pack_trends_positivity(path, canon=None):
    """{scale: {location: {dates[], mean[], lo[], hi[]}}} from rolling_positivity.csv.

    SPARSE by design: only dates present in the CSV appear. The chart's line
    connects straight across gaps (geom_line does); zero-filling here would
    invent troughs that are not in the data.

    Values are proportions at full precision. The x100 to percent happens at
    render time so the stored numbers stay byte-identical to the source.
    """
    canon = canon or (lambda s: s)
    buckets = {scale: {} for scale, _ in _TRENDS_SCALES}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            scale = (row.get("spatial_scale") or "").strip().lower()
            key_field = dict(_TRENDS_SCALES).get(scale, "__missing__")
            if key_field == "__missing__":
                continue
            loc = _trends_loc(row, key_field)
            if loc is None:
                continue
            if key_field is not None:
                loc = canon(loc)
            day = (row.get("date_of_symptom_onset_imputed") or "").strip()
            if not _ONSET_DATE_RE.match(day):
                continue
            trio = (
                _parse_optional_float(row.get("daily_positivity_mean")),
                _parse_optional_float(row.get("daily_positivity_lower")),
                _parse_optional_float(row.get("daily_positivity_upper")),
            )
            if trio[0] is None:
                continue
            buckets[scale].setdefault(loc, {})[day] = trio   # OVERWRITE, last wins

    packed = {scale: {} for scale, _ in _TRENDS_SCALES}
    for scale, by_loc in buckets.items():
        for loc, by_day in by_loc.items():
            days = sorted(by_day)
            packed[scale][loc] = {
                "dates": days,
                "mean": [by_day[d][0] for d in days],
                "lo": [by_day[d][1] for d in days],
                "hi": [by_day[d][2] for d in days],
            }
    return packed
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd Scripts && python3.9 -m pytest ../tests/test_trends_series.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add Scripts/common/data_sources.py tests/test_trends_series.py
git commit -m "Add rolling-positivity packer for the Trends data slice"
```

---

### Task 4: Labs packer

**Semantics (§6.5):** one entry per `lab_name`, sorted; rows kept in analysis-date order with no dedupe; `max_total` is per-lab; the **x range is global across all labs** so labs stay visually comparable.

**Files:**
- Modify: `Scripts/common/data_sources.py`
- Test: `tests/test_trends_series.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_trends_series.py`:

```python
LAB_CSV = (
    "lab_name,lab_name_long,health_zone,province,lab_analysis_date,earliest_analysed_sample,"
    "confirmed_case,total_samples_analysed_daily,rolling_confirmed,rolling_total,"
    "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
    "INRBK,INRB Kinshasa,NA,NA,2026-05-14,2026-05-14,4,6,4,6,0.666,0.3,0.9\n"
    "INRBK,INRB Kinshasa,NA,NA,2026-05-16,2026-05-14,1,1,5,7,0.714,0.36,0.92\n"
    "LBARU,Aru,Aru,Ituri,2026-06-01,2026-06-01,1,2,1,2,0.5,0.2,0.8\n"
)


def test_labs_pack_per_lab_with_a_shared_global_x_range(tmp_path):
    (tmp_path / "lab_positivity_aggregated.csv").write_text(LAB_CSV, encoding="utf-8")

    labs, lab_x = ds._pack_trends_labs(tmp_path / "lab_positivity_aggregated.csv")

    # Shared across ALL labs so they stay comparable (spec 6.5), not per-lab.
    assert lab_x == {"start": "2026-05-14", "end": "2026-06-01"}

    assert [l["code"] for l in labs] == ["INRBK", "LBARU"]      # sorted by lab_name
    inrbk = labs[0]
    assert inrbk["label"] == "INRB Kinshasa"
    assert inrbk["id"] == "lab_inrbk"
    assert inrbk["earliest"] == "2026-05-14"
    assert inrbk["dates"] == ["2026-05-14", "2026-05-16"]       # sparse, not zero-filled
    assert inrbk["n"] == [6, 1]
    assert inrbk["max_total"] == 6                              # per-lab, drives the 2nd axis
    assert inrbk["health_zone"] is None and inrbk["province"] is None
    assert labs[1]["health_zone"] == "Aru" and labs[1]["province"] == "Ituri"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd Scripts && python3.9 -m pytest ../tests/test_trends_series.py -v
```

Expected: `AttributeError: ... has no attribute '_pack_trends_labs'`.

- [ ] **Step 3: Implement the packer**

Add directly beneath `_pack_trends_positivity`:

```python
def _pack_trends_labs(path):
    """(labs[], lab_x) from lab_positivity_aggregated.csv.

    Returns a list sorted by lab_name and the SHARED x range used by every lab
    chart: [earliest sample across ALL labs, latest analysis date across ALL
    labs] (spec 6.5). That range is global on purpose -- it is what makes the
    per-lab charts comparable -- so do not narrow it per lab.
    """
    by_lab = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("lab_name") or "").strip()
            day = (row.get("lab_analysis_date") or "").strip()
            if not code or not _ONSET_DATE_RE.match(day):
                continue
            mean = _parse_optional_float(row.get("daily_positivity_mean"))
            if mean is None:
                continue
            long_name = (row.get("lab_name_long") or "").strip()
            hz = (row.get("health_zone") or "").strip()
            prov = (row.get("province") or "").strip()
            earliest = (row.get("earliest_analysed_sample") or "").strip()
            lab = by_lab.setdefault(code, {
                "id": "lab_" + _slugify_plot_key(code),
                "code": code,
                "label": long_name or code,
                "health_zone": hz if hz and hz.upper() != "NA" else None,
                "province": prov if prov and prov.upper() != "NA" else None,
                "earliest": earliest if _ONSET_DATE_RE.match(earliest) else None,
                "rows": {},
            })
            lab["rows"][day] = (
                _i(row.get("total_samples_analysed_daily")),
                mean,
                _parse_optional_float(row.get("daily_positivity_lower")),
                _parse_optional_float(row.get("daily_positivity_upper")),
            )

    labs, starts, ends = [], [], []
    for code in sorted(by_lab):
        lab = by_lab[code]
        days = sorted(lab["rows"])
        if not days:
            continue
        counts = [lab["rows"][d][0] for d in days]
        labs.append({
            "id": lab["id"],
            "code": code,
            "label": lab["label"],
            "health_zone": lab["health_zone"],
            "province": lab["province"],
            "earliest": lab["earliest"],
            "dates": days,
            "n": counts,
            "mean": [lab["rows"][d][1] for d in days],
            "lo": [lab["rows"][d][2] for d in days],
            "hi": [lab["rows"][d][3] for d in days],
            "max_total": max(1, max(counts)),
        })
        starts.append(lab["earliest"] or days[0])
        ends.append(days[-1])

    lab_x = {"start": min(starts), "end": max(ends)} if labs else None
    return labs, lab_x
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd Scripts && python3.9 -m pytest ../tests/test_trends_series.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add Scripts/common/data_sources.py tests/test_trends_series.py
git commit -m "Add laboratory-testing packer for the Trends data slice"
```

---

### Task 5: Shared x-limits, incomplete cutoff, and `load_trends_series()`

**Semantics (§6.6, §6.7):** per location, all three cards share one date range spanning that location's cases ∪ deaths ∪ positivity dates — miss this and the cards silently disagree about time. The incomplete-reporting cutoff is `snapshot_date - incomplete_days` resolved **at build time** (D7); `incomplete_days` comes from the manifest, defaulting to 7.

**Files:**
- Modify: `Scripts/common/data_sources.py`
- Test: `tests/test_trends_series.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_trends_series.py`:

```python
import json


def _seed_snapshot(tmp_path):
    out = tmp_path / "outputs"
    snap = out / "2026-05-10"
    snap.mkdir(parents=True)
    (snap / "status_aggregated.csv").write_text(CASES_CSV, encoding="utf-8")
    (snap / "cumulative_positive_deaths.csv").write_text(DEATHS_CSV, encoding="utf-8")
    (snap / "rolling_positivity.csv").write_text(POS_CSV, encoding="utf-8")
    (snap / "lab_positivity_aggregated.csv").write_text(LAB_CSV, encoding="utf-8")
    # A newer decoy dir the manifest does NOT point at -- must be ignored.
    decoy = out / "2026-05-11"
    decoy.mkdir(parents=True)
    (decoy / "status_aggregated.csv").write_text(
        "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
        "spatial_scale,province,health_zone\n"
        "2026-05-01,FALSE,999,national,NA,NA\n", encoding="utf-8")
    (out / "manifest.json").write_text(
        json.dumps({"date": "2026-05-10", "incomplete_styling": {"days": 5}}), encoding="utf-8")
    return out


def test_load_trends_series_shares_x_limits_and_freezes_the_cutoff(tmp_path, monkeypatch):
    out = _seed_snapshot(tmp_path)
    monkeypatch.setattr(ds, "DASHBOARD_PLOTS_DIR", out)

    res = ds.load_trends_series(known_noms={"Bunia"})

    assert res["asof"] == "2026-05-10"              # manifest snapshot, not the newer decoy
    assert res["cases"]["national"]["obs"] != [999]  # decoy really was ignored
    assert res["incomplete_days"] == 5              # read from the manifest, not hardcoded 7
    assert res["incomplete_from"] == "2026-05-05"   # snapshot - 5 days, frozen at BUILD time

    # National x-limits span cases (05-02..05-05) U deaths (05-01..05-04)
    # U positivity (05-01..05-03) -- spec 6.6.
    assert res["x_limits"]["national"]["national"] == {"start": "2026-05-01", "end": "2026-05-05"}
    assert res["lab_x"] == {"start": "2026-05-14", "end": "2026-06-01"}


def test_load_trends_series_returns_none_when_the_snapshot_is_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "DASHBOARD_PLOTS_DIR", tmp_path / "nope")
    assert ds.load_trends_series() is None
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd Scripts && python3.9 -m pytest ../tests/test_trends_series.py -v
```

Expected: `AttributeError: ... has no attribute 'load_trends_series'`.

- [ ] **Step 3: Implement the assembler**

Add directly beneath `_pack_trends_labs`:

```python
def _trends_x_limits(cases, deaths, positivity):
    """Per location, the min/max date across cases U deaths U positivity.

    All three cards for one selection are drawn on this range (spec 6.6), so a
    card may show empty space where its own series does not reach the ends. That
    is intended: without it the three cards silently disagree about time.
    """
    limits = {}
    for scale, _ in _TRENDS_SCALES:
        per_scale = {}
        names = set(cases.get(scale, {})) | set(deaths.get(scale, {})) | set(positivity.get(scale, {}))
        for loc in names:
            lo, hi = [], []
            c = cases.get(scale, {}).get(loc)
            if c:
                lo.append(c["start"])
                hi.append(_day_range(c["start"], c["start"])[0] if len(c["obs"]) == 1
                          else _day_range(c["start"], c["start"])[0])
                hi[-1] = (date.fromisoformat(c["start"]) + timedelta(days=len(c["obs"]) - 1)).isoformat()
            d = deaths.get(scale, {}).get(loc)
            if d:
                lo.append(d["start"])
                hi.append((date.fromisoformat(d["start"]) + timedelta(days=len(d["cum"]) - 1)).isoformat())
            p = positivity.get(scale, {}).get(loc)
            if p and p["dates"]:
                lo.append(p["dates"][0])
                hi.append(p["dates"][-1])
            if lo and hi:
                per_scale[loc] = {"start": min(lo), "end": max(hi)}
        limits[scale] = per_scale
    return limits


def load_trends_series(outputs_dir=None, known_noms=None):
    """The Trends tab's data slice, or None when the snapshot is unavailable.

    Replaces load_dashboard_plots(): same directory and same manifest-driven
    snapshot resolution, but reads the four aggregated CSVs the SVGs were
    rendered from rather than the SVGs themselves.
    """
    base = Path(outputs_dir if outputs_dir is not None else DASHBOARD_PLOTS_DIR)
    snap = _onset_manifest_dated_dir(base)
    if snap is None:
        print(f"  NOTE: no dated snapshot under {base}; trends charts unavailable")
        return None

    manifest = {}
    manifest_path = base / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) or {}
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  WARNING: invalid manifest.json: {exc}")

    nom_by_norm = {_norm(n): n for n in (known_noms or ())}

    def canon(name):
        return nom_by_norm.get(_norm(name), name)

    def maybe(name, fn, *args):
        path = snap / name
        if not path.exists():
            print(f"  NOTE: {name} not found in {snap.name}; that card will be empty")
            return None
        return fn(path, *args)

    cases = maybe("status_aggregated.csv", _pack_trends_cases, canon) or {}
    deaths = maybe("cumulative_positive_deaths.csv", _pack_trends_deaths, canon) or {}
    positivity = maybe("rolling_positivity.csv", _pack_trends_positivity, canon) or {}
    labs_result = maybe("lab_positivity_aggregated.csv", _pack_trends_labs)
    labs, lab_x = labs_result if labs_result else ([], None)

    if not cases and not deaths and not positivity and not labs:
        return None

    days = manifest.get("incomplete_styling", {}).get("days")
    try:
        incomplete_days = int(days)
    except (TypeError, ValueError):
        incomplete_days = 7
    if incomplete_days <= 0:
        incomplete_days = 7

    asof = snap.name
    # Frozen here, at BUILD time (spec 6.7 / D7). Never recompute this in the
    # browser: the band would drift as a page ages between builds.
    incomplete_from = (date.fromisoformat(asof) - timedelta(days=incomplete_days)).isoformat()

    def scale_slice(packed, scale):
        return packed.get(scale, {}) if packed else {}

    return {
        "asof": asof,
        "incomplete_days": incomplete_days,
        "incomplete_from": incomplete_from,
        "cases": {
            "national": scale_slice(cases, "national").get("national"),
            "provinces": scale_slice(cases, "province"),
            "health_zones": scale_slice(cases, "healthzone"),
        },
        "deaths": {
            "national": scale_slice(deaths, "national").get("national"),
            "provinces": scale_slice(deaths, "province"),
            "health_zones": scale_slice(deaths, "healthzone"),
        },
        "positivity": {
            "national": scale_slice(positivity, "national").get("national"),
            "provinces": scale_slice(positivity, "province"),
            "health_zones": scale_slice(positivity, "healthzone"),
        },
        "labs": labs,
        "lab_x": lab_x,
        "x_limits": _trends_x_limits(cases, deaths, positivity),
    }
```

Add `'load_trends_series'` to `__all__` in `Scripts/common/data_sources.py`, next to the existing `'load_dashboard_plots'` entry (~line 130).

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd Scripts && python3.9 -m pytest ../tests/test_trends_series.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Simplify `_trends_x_limits`**

The `hi.append(...)` / `hi[-1] = ...` sequence in the `cases` branch above is redundant — replace the whole `if c:` block with the direct form:

```python
            c = cases.get(scale, {}).get(loc)
            if c:
                lo.append(c["start"])
                hi.append((date.fromisoformat(c["start"]) + timedelta(days=len(c["obs"]) - 1)).isoformat())
```

Re-run: `cd Scripts && python3.9 -m pytest ../tests/test_trends_series.py -v` — expected `6 passed`.

- [ ] **Step 6: Commit**

```bash
git add Scripts/common/data_sources.py tests/test_trends_series.py
git commit -m "Assemble the Trends data slice with shared x-limits and a frozen incomplete-reporting cutoff"
```

---

### Task 6: Wire the slice into the payload and page-scope it

**Files:**
- Modify: `Scripts/common/payload.py:117-121` (the `onset_trends = load_dashboard_plots(...)` call) and its entry in the returned dict
- Modify: `Scripts/common/chrome.py:461-464` (`_PAGE_SCOPED_PAYLOAD_KEYS`)
- Test: `tests/test_trends_payload_scoping.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_trends_payload_scoping.py`:

```python
import importlib

chrome = importlib.import_module("common.chrome")


def test_trends_key_is_page_scoped_to_the_trends_view():
    assert chrome._PAGE_SCOPED_PAYLOAD_KEYS["trends"] == {"trends"}


def test_only_the_trends_page_carries_the_trends_slice():
    payload = {"trends": {"asof": "2026-09-20"}, "asof": "2026-09-20"}
    for view_id in ("map", "epi-trends", "context", "genomic-epidemiology"):
        scoped = {
            k: v for k, v in payload.items()
            if k not in chrome._PAGE_SCOPED_PAYLOAD_KEYS
            or view_id in chrome._PAGE_SCOPED_PAYLOAD_KEYS[k]
        }
        assert "trends" not in scoped, view_id
    scoped = {
        k: v for k, v in payload.items()
        if k not in chrome._PAGE_SCOPED_PAYLOAD_KEYS
        or "trends" in chrome._PAGE_SCOPED_PAYLOAD_KEYS[k]
    }
    assert "trends" in scoped
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd Scripts && python3.9 -m pytest ../tests/test_trends_payload_scoping.py -v
```

Expected: `KeyError: 'trends'`.

- [ ] **Step 3: Make the changes**

In `Scripts/common/chrome.py`, extend the map:

```python
_PAGE_SCOPED_PAYLOAD_KEYS = {
    "import_force_pairwise": {"epi-trends"},
    "genomic": {"genomic-epidemiology"},
    # 363 KB of series data only the Trends tab reads. Its SVG predecessor
    # (onset_trends) was unscoped and cost every page 5.35 MB.
    "trends": {"trends"},
}
```

In `Scripts/common/payload.py`, replace the `onset_trends = load_dashboard_plots(...)` call (~line 117) with:

```python
    trends = load_trends_series(known_noms=set(zone_data))
    if trends:
        print(f"  trends: asof {trends['asof']}, "
              f"{len(trends['cases']['health_zones'])} zones, "
              f"{len(trends['labs'])} labs, "
              f"incomplete from {trends['incomplete_from']}")
```

and in the returned dict replace `"onset_trends": onset_trends,` with:

```python
        "trends": trends,
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd Scripts && python3.9 -m pytest ../tests/test_trends_payload_scoping.py ../tests/test_trends_series.py -v
```

Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add Scripts/common/payload.py Scripts/common/chrome.py tests/test_trends_payload_scoping.py
git commit -m "Ship the Trends data slice in the payload, scoped to the Trends page"
```

---

### Task 7: `charts.js` — shared runtime-SVG primitives

Extract the primitives `genomic.js` already uses so `trends.js` can build on them. **`genomic.js` is not modified in this change** (spec D4) — it keeps its own copy until a follow-up migrates it.

**Files:**
- Create: `Scripts/assets/charts.js`
- Modify: `Scripts/build_dashboard.py:130-140` (`_write_shared_assets`)

- [ ] **Step 1: Create the module**

Create `Scripts/assets/charts.js`:

```javascript
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
  // xStart/xEnd are ISO dates and define the SHARED range (spec 6.6) -- pass
  // the same pair to every card of one selection or they will disagree.
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
    return {
      xToPx: xToPx, pxToDate: pxToDate, yToPx: yToPx, yMax: yMax,
      left: left, right: right, top: pad.top, baseY: baseY,
      barW: Math.max(1, pxPerDay - 1), ticks: ticks
    };
  }

  // Shaded band from `fromIso` to the right edge, drawn BENEATH the data
  // (call before the marks). Used for the incomplete-reporting window.
  function shadeRegion(svg, fr, fromIso, fill) {
    if (!fromIso) return;
    var x = Math.max(fr.left, Math.min(fr.right, fr.xToPx(dayMs(fromIso))));
    if (x >= fr.right) return;
    svg.appendChild(svgEl("rect", {
      x: x, y: fr.top, width: fr.right - x, height: fr.baseY - fr.top,
      fill: fill, "fill-opacity": 0.25
    }));
  }

  // Stacked bars. `series` is [{values:[], color}] drawn bottom-up.
  function stackedBars(svg, fr, dates, series) {
    var g = svgEl("g", {});
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
      up += (up ? "L" : "M") + fr.xToPx(dayMs(iso)) + " " + fr.yToPx(hi[i]);
      down.push(fr.xToPx(dayMs(iso)) + " " + fr.yToPx(lo[i]));
    });
    if (!up) return;
    down.reverse();
    svg.appendChild(svgEl("path", {
      d: up + "L" + down.join("L") + "Z", fill: fill, "fill-opacity": 0.35, stroke: "none"
    }));
  }

  function line(svg, fr, dates, values, color, width) {
    var d = pathFor(fr, dates, values);
    if (!d) return;
    svg.appendChild(svgEl("path", { d: d, fill: "none", stroke: color, "stroke-width": width || 0.9 }));
  }

  // `filter(i)` selects which indices get a dot (deaths plot points only where
  // daily_deaths > 0 -- spec 6.3).
  function points(svg, fr, dates, values, color, r, filter) {
    dates.forEach(function (iso, i) {
      if (filter && !filter(i)) return;
      var v = values[i];
      if (v === null || v === undefined) return;
      svg.appendChild(svgEl("circle", {
        cx: fr.xToPx(dayMs(iso)), cy: fr.yToPx(v), r: r || 1.8, fill: color, stroke: "none"
      }));
    });
  }

  // Dashed vertical marker plus a label (lab "Earliest Sample").
  function markerLine(svg, fr, iso, color, label) {
    if (!iso) return;
    var x = fr.xToPx(dayMs(iso));
    if (x < fr.left || x > fr.right) return;
    svg.appendChild(svgEl("line", {
      x1: x, y1: fr.top, x2: x, y2: fr.baseY,
      stroke: color, "stroke-width": 1, "stroke-dasharray": "3,2"
    }));
    if (!label) return;
    var txt = svgEl("text", { x: x + 3, y: fr.top + 9, "font-size": 8, fill: color });
    txt.textContent = label;
    svg.appendChild(txt);
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
    var t = svgEl("text", {
      x: fr.right + 16, y: (fr.top + fr.baseY) / 2, "font-size": 9, fill: "#9c968b",
      "text-anchor": "middle", transform: "rotate(90 " + (fr.right + 16) + " " + ((fr.top + fr.baseY) / 2) + ")"
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
```

- [ ] **Step 2: Ship it with the build**

In `Scripts/build_dashboard.py`, inside `_write_shared_assets`, directly after the `genomic_js` block, add:

```python
    # Shared chart primitives (charts.js) + the Trends page script. charts.js is
    # written unconditionally alongside engine.js; trends.js is referenced only
    # by trends.html.
    for name in ("charts.js", "trends.js"):
        (assets_dir / name).write_text(
            (SCRIPT_DIR / "assets" / name).read_text(encoding="utf-8"), encoding="utf-8")
```

- [ ] **Step 3: Verify the syntax is valid**

```bash
cd /Users/user/Documents/work/BDBV2026-Epidemic_Dashboard && node --check Scripts/assets/charts.js
```

Expected: no output (exit 0). If `node` is unavailable, skip — Task 12's browser check covers it.

- [ ] **Step 4: Commit**

```bash
git add Scripts/assets/charts.js Scripts/build_dashboard.py
git commit -m "Add shared runtime-SVG chart primitives"
```

---

### Task 8: `trends.js` — module shell and the confirmed-cases card

**Fidelity (§6.2):** stacked bars, **observed at the bottom** (`#b23b2e`), imputed on top (`#f1ccc6`); y-axis `Cases`; no positivity overlay.

**Files:**
- Create: `Scripts/assets/trends.js`
- Modify: `Scripts/pages/trends.py`

- [ ] **Step 1: Create the module with the cases card**

Create `Scripts/assets/trends.js`:

```javascript
// Epidemiological Trends charts.
//
// Draws the four cards from PAYLOAD.trends using the shared primitives in
// charts.js. Owns NO state: engine.js keeps the scope/selection and the map,
// and calls TrendsCharts.render({scope, key}).
//
// Every constant and rule here is transcribed from the generator at
// BDBV2026-Processing_Code@main; see the spec's section 6 before changing any
// of it. Colours, stacking order and captions are contractual.
(function (global) {
  "use strict";

  var C = global.DashboardCharts;

  var COLOR_OBS = "#b23b2e";        // Confirmed (Observed Onset)
  var COLOR_IMP = "#f1ccc6";        // Confirmed (Imputed Onset)
  var COLOR_POSITIVITY = "#5b86b3";
  var COLOR_DEATHS = "#7c1d1d";
  var COLOR_SAMPLES = "#9c968b";
  var COLOR_INCOMPLETE = "#9c968b";
  var COLOR_INK = "#2a2a27";
  var PAD = { left: 42, right: 46, top: 12, bottom: 26 };

  function data() {
    var el = document.getElementById("payload");
    if (!el) return null;
    try { return (JSON.parse(el.textContent) || {}).trends || null; } catch (e) { return null; }
  }
  var _cache;
  function trends() { if (_cache === undefined) _cache = data(); return _cache; }

  function tr(key, fallback) {
    return (global.t ? global.t(key) : null) || fallback;
  }

  // Resolve one family's entry for the current selection.
  function pick(family, scope, key) {
    var d = trends();
    if (!d || !d[family]) return null;
    if (scope === "national") return d[family].national || null;
    if (!key) return null;
    if (scope === "province") return (d[family].provinces || {})[key] || null;
    if (scope === "health_zone") return (d[family].health_zones || {})[key] || null;
    return null;
  }

  function xLimits(scope, key) {
    var d = trends();
    if (!d || !d.x_limits) return null;
    var scale = scope === "national" ? "national" : (scope === "province" ? "province" : "healthzone");
    var name = scope === "national" ? "national" : key;
    return name ? (d.x_limits[scale] || {})[name] || null : null;
  }

  function isoSeq(start, n) {
    var out = [], t = C.dayMs(start);
    for (var i = 0; i < n; i++) out.push(new Date(t + i * 86400000).toISOString().slice(0, 10));
    return out;
  }

  function newSvg(host, W, H) {
    host.replaceChildren();
    var svg = C.svgEl("svg", { viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none" });
    return svg;
  }

  function size(host) {
    return { W: host.clientWidth || 320, H: host.clientHeight || 190 };
  }

  // --- Card 1: confirmed cases ----------------------------------------------
  function renderCases(host, scope, key) {
    var d = trends(), entry = pick("cases", scope, key), lim = xLimits(scope, key);
    if (!entry || !lim) return false;
    var dates = isoSeq(entry.start, entry.obs.length);
    var dim = size(host), svg = newSvg(host, dim.W, dim.H);
    var yMax = 0;
    for (var i = 0; i < dates.length; i++) yMax = Math.max(yMax, entry.obs[i] + entry.imp[i]);

    var fr = C.frame(svg, {
      width: dim.W, height: dim.H, pad: PAD,
      xStart: lim.start, xEnd: lim.end, yMax: yMax
    });
    C.shadeRegion(svg, fr, d.incomplete_from, COLOR_INCOMPLETE);
    C.stackedBars(svg, fr, dates, [
      { values: entry.obs, color: COLOR_OBS },   // observed at the BOTTOM
      { values: entry.imp, color: COLOR_IMP }
    ]);
    host.appendChild(svg);

    C.tooltip(host, svg, fr, function (iso) {
      var i = dates.indexOf(iso);
      if (i < 0) return null;
      return '<div class="dc-tip-d">' + C.fmtDay(C.dayMs(iso)) + "</div>" +
        '<div><span class="dc-sw" style="background:' + COLOR_OBS + '"></span>' +
        tr("ui.trends_series_observed", "Confirmed (Observed Onset)") + ": " + entry.obs[i] + "</div>" +
        '<div><span class="dc-sw" style="background:' + COLOR_IMP + '"></span>' +
        tr("ui.trends_series_imputed", "Confirmed (Imputed Onset)") + ": " + entry.imp[i] + "</div>";
    });
    return true;
  }

  global.TrendsCharts = { _renderCases: renderCases, _trends: trends, _xLimits: xLimits };
})(window);
```

- [ ] **Step 2: Load it on the Trends page**

In `Scripts/pages/trends.py`, replace the `build_page` function with:

```python
# charts.js MUST load before trends.js (which calls DashboardCharts.*), and both
# after engine.js, which owns the scope/selection state they read.
_SCRIPTS = (
    '<script src="__ASSETS_PREFIX__charts.js"></script>\n'
    '<script src="__ASSETS_PREFIX__trends.js"></script>'
)


def build_page(payload: dict) -> str:
    return render_page(VIEW_ID, payload, extra_scripts=_SCRIPTS)
```

- [ ] **Step 3: Verify the syntax is valid**

```bash
cd /Users/user/Documents/work/BDBV2026-Epidemic_Dashboard && node --check Scripts/assets/trends.js
```

Expected: no output (exit 0).

- [ ] **Step 4: Commit**

```bash
git add Scripts/assets/trends.js Scripts/pages/trends.py
git commit -m "Render the confirmed-cases card from data"
```

---

### Task 9: Cumulative deaths card

**Fidelity (§6.3):** line in `#7c1d1d`; points **only** where `daily > 0`; y-axis `Cumulative Deaths`.

**Files:**
- Modify: `Scripts/assets/trends.js`

- [ ] **Step 1: Add the renderer**

In `Scripts/assets/trends.js`, insert directly before the `global.TrendsCharts = ...` line:

```javascript
  // --- Card 2: cumulative deaths --------------------------------------------
  function renderDeaths(host, scope, key) {
    var d = trends(), entry = pick("deaths", scope, key), lim = xLimits(scope, key);
    if (!entry || !lim) return false;
    var dates = isoSeq(entry.start, entry.cum.length);
    var dim = size(host), svg = newSvg(host, dim.W, dim.H);
    var yMax = Math.max.apply(null, entry.cum.concat([0]));

    var fr = C.frame(svg, {
      width: dim.W, height: dim.H, pad: PAD,
      xStart: lim.start, xEnd: lim.end, yMax: yMax
    });
    C.shadeRegion(svg, fr, d.incomplete_from, COLOR_INCOMPLETE);
    C.line(svg, fr, dates, entry.cum, COLOR_DEATHS, 0.9);
    // Points ONLY on days with a death reported (spec 6.3) -- not every day.
    C.points(svg, fr, dates, entry.cum, COLOR_DEATHS, 1.8, function (i) {
      return entry.daily[i] > 0;
    });
    host.appendChild(svg);

    C.tooltip(host, svg, fr, function (iso) {
      var i = dates.indexOf(iso);
      if (i < 0) return null;
      return '<div class="dc-tip-d">' + C.fmtDay(C.dayMs(iso)) + "</div>" +
        "<div>" + tr("ui.trends_axis_deaths", "Cumulative Deaths") + ": " + entry.cum[i] + "</div>" +
        (entry.daily[i] > 0 ? '<div class="dc-tip-ci">+' + entry.daily[i] + "</div>" : "");
    });
    return true;
  }
```

and extend the export:

```javascript
  global.TrendsCharts = {
    _renderCases: renderCases, _renderDeaths: renderDeaths,
    _trends: trends, _xLimits: xLimits
  };
```

- [ ] **Step 2: Verify the syntax is valid**

```bash
cd /Users/user/Documents/work/BDBV2026-Epidemic_Dashboard && node --check Scripts/assets/trends.js
```

Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add Scripts/assets/trends.js
git commit -m "Render the cumulative-deaths card from data"
```

---

### Task 10: Rolling positivity card

**Fidelity (§6.4):** sparse dates, line straight across gaps (**never** zero-filled); values clamped to [0,1] then ×100; y-axis `Sample Positivity (%)` pinned at 0.

**Files:**
- Modify: `Scripts/assets/trends.js`

- [ ] **Step 1: Add the renderer**

Insert before the `global.TrendsCharts = ...` line:

```javascript
  function clampPct(v) {
    if (v === null || v === undefined) return null;
    return Math.min(1, Math.max(0, v)) * 100;    // clamp then x100 (spec 6.4)
  }

  // --- Card 3: rolling positivity -------------------------------------------
  function renderPositivity(host, scope, key) {
    var d = trends(), entry = pick("positivity", scope, key), lim = xLimits(scope, key);
    if (!entry || !entry.dates.length || !lim) return false;
    // SPARSE on purpose: entry.dates has gaps and the line runs straight across
    // them, matching geom_line. Do NOT densify this.
    var dates = entry.dates;
    var mean = entry.mean.map(clampPct);
    var lo = entry.lo.map(clampPct);
    var hi = entry.hi.map(clampPct);
    var dim = size(host), svg = newSvg(host, dim.W, dim.H);
    var yMax = Math.max.apply(null, hi.filter(function (v) { return v !== null; }).concat([0]));

    var fr = C.frame(svg, {
      width: dim.W, height: dim.H, pad: PAD,
      xStart: lim.start, xEnd: lim.end, yMax: yMax   // lower bound pinned at 0
    });
    C.shadeRegion(svg, fr, d.incomplete_from, COLOR_INCOMPLETE);
    C.ciBand(svg, fr, dates, lo, hi, COLOR_POSITIVITY);
    C.line(svg, fr, dates, mean, COLOR_POSITIVITY, 0.9);
    C.points(svg, fr, dates, mean, COLOR_POSITIVITY, 1.8, null);
    host.appendChild(svg);

    C.tooltip(host, svg, fr, function (iso) {
      var i = dates.indexOf(iso);
      if (i < 0) return null;
      return '<div class="dc-tip-d">' + C.fmtDay(C.dayMs(iso)) + "</div>" +
        "<div>" + mean[i].toFixed(1) + "%" +
        ' <span class="dc-tip-ci">(' + lo[i].toFixed(1) + "–" + hi[i].toFixed(1) + "%)</span></div>";
    });
    return true;
  }
```

and extend the export to include `_renderPositivity: renderPositivity,`.

- [ ] **Step 2: Verify the syntax is valid**

```bash
cd /Users/user/Documents/work/BDBV2026-Epidemic_Dashboard && node --check Scripts/assets/trends.js
```

Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add Scripts/assets/trends.js
git commit -m "Render the rolling-positivity card from data"
```

---

### Task 11: Laboratory testing card

**Fidelity (§6.5):** every lab shares the **global** x range (`trends.lab_x`); bars are samples analysed; positivity is scaled by that lab's `max_total`; dashed marker at `earliest`. **D6:** the secondary axis is relabelled **0–100** — this is a label change only, the marks do not move.

**Files:**
- Modify: `Scripts/assets/trends.js`

- [ ] **Step 1: Add the renderer and the lab selection rule**

Insert before the `global.TrendsCharts = ...` line:

```javascript
  // Normalises a place name for cross-dataset matching (zone naming drifts
  // between feeds). Mirrors engine.js's normalizeLabLocationKey.
  function normLoc(s) {
    return String(s || "")
      .normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/\([^)]*\)/g, "")
      .replace(/[^a-z0-9]+/gi, " ")
      .trim().toLowerCase();
  }

  function labsForSelection(scope, key) {
    var d = trends();
    var labs = (d && d.labs) || [];
    if (scope === "national") return labs;
    if (!key) return [];
    var field = scope === "health_zone" ? "health_zone" : "province";
    var want = normLoc(key);
    return labs.filter(function (l) { return l[field] && normLoc(l[field]) === want; });
  }

  // --- Card 4: one chart per laboratory -------------------------------------
  function renderLab(host, lab) {
    var d = trends();
    // Global range across ALL labs so charts stay comparable (spec 6.5).
    var lim = d.lab_x;
    if (!lim) return;
    var dates = lab.dates;
    var dim = size(host), svg = newSvg(host, dim.W, dim.H);
    var maxTotal = lab.max_total;

    var fr = C.frame(svg, {
      width: dim.W, height: dim.H, pad: PAD,
      xStart: lim.start, xEnd: lim.end, yMax: maxTotal
    });
    C.shadeRegion(svg, fr, d.incomplete_from, COLOR_INCOMPLETE);

    // Bars on the primary axis; positivity scaled onto the SAME axis by
    // * max_total, exactly as the generator does.
    var g = C.svgEl("g", {});
    dates.forEach(function (iso, i) {
      var n = lab.n[i] || 0;
      if (n <= 0) return;
      var yTop = fr.yToPx(n);
      g.appendChild(C.svgEl("rect", {
        x: fr.xToPx(C.dayMs(iso)) - fr.barW / 2, y: yTop,
        width: fr.barW, height: Math.max(0, fr.baseY - yTop), fill: COLOR_SAMPLES
      }));
    });
    svg.appendChild(g);

    var sc = function (v) {
      if (v === null || v === undefined) return null;
      return Math.min(1, Math.max(0, v)) * maxTotal;
    };
    C.ciBand(svg, fr, dates, lab.lo.map(sc), lab.hi.map(sc), COLOR_POSITIVITY);
    C.line(svg, fr, dates, lab.mean.map(sc), COLOR_POSITIVITY, 0.9);
    C.points(svg, fr, dates, lab.mean.map(sc), COLOR_POSITIVITY, 1.8, null);
    C.markerLine(svg, fr, lab.earliest, COLOR_INK,
      tr("ui.trends_lab_earliest", "Earliest Sample: ") + (lab.earliest || ""));

    // D6: relabel the secondary axis 0-100. The source emits `~ . / max_total`,
    // i.e. a 0-1 proportion under a "(%)" label. This is a LABEL change only --
    // every mark above is positioned on the primary axis, so nothing moves.
    C.dualAxis(svg, fr, tr("ui.trends_axis_positivity", "Sample Positivity (%)"), function (v) {
      return String(Math.round((v / maxTotal) * 100));
    });
    host.appendChild(svg);

    C.tooltip(host, svg, fr, function (iso) {
      var i = dates.indexOf(iso);
      if (i < 0) return null;
      return '<div class="dc-tip-d">' + C.fmtDay(C.dayMs(iso)) + "</div>" +
        "<div>" + tr("ui.trends_axis_samples", "Samples Analysed") + ": " + lab.n[i] + "</div>" +
        "<div>" + (Math.min(1, Math.max(0, lab.mean[i])) * 100).toFixed(1) + "%</div>";
    });
  }
```

and extend the export to include `_renderLab: renderLab, _labsForSelection: labsForSelection,`.

- [ ] **Step 2: Verify the syntax is valid**

```bash
cd /Users/user/Documents/work/BDBV2026-Epidemic_Dashboard && node --check Scripts/assets/trends.js
```

Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add Scripts/assets/trends.js
git commit -m "Render the laboratory-testing card from data, with a 0-100 secondary axis"
```

---

### Task 12: Public `render()` and engine.js delegation

**Files:**
- Modify: `Scripts/assets/trends.js`
- Modify: `Scripts/assets/engine.js:3051-3175` (the `renderPlotCard` / `render*Plot` / `renderTrendsLabs` / `renderTrendsPlots` block)

- [ ] **Step 1: Add the public entry point**

In `Scripts/assets/trends.js`, replace the `global.TrendsCharts = { ... }` export with:

```javascript
  // Caption text, with the incomplete-reporting sentence appended ONLY when a
  // band is actually drawn -- the two vary together in the generator (spec 6.7).
  // The SVGs carried these captions baked in and they are visible today
  // (cropPlotSvgTop only removed the title), so dropping them would change what
  // the page presents.
  function caption(key, fallback, banded) {
    var text = tr(key, fallback);
    if (!banded) return text;
    return text + ". " + tr("ui.trends_caption_incomplete",
      "Shaded region: dates within the last week (reporting likely incomplete).");
  }

  // True when the incomplete band falls inside this card's x range. When it does
  // not, no band is drawn and the caption must lose its trailing sentence.
  function banded(lim) {
    var d = trends();
    return !!(d && d.incomplete_from && lim && d.incomplete_from <= lim.end);
  }

  function addCaption(body, text) {
    var p = document.createElement("p");
    p.className = "dc-caption";
    p.textContent = text;
    body.appendChild(p);
  }

  // Fills one card: title, then either a chart plus its caption, or the
  // existing empty-state copy.
  function card(titleId, bodyId, titleKey, titleFallback, place, draw, captionKey, captionFallback, lim) {
    var titleEl = document.getElementById(titleId), body = document.getElementById(bodyId);
    if (!body) return;
    var base = tr(titleKey, titleFallback);
    if (titleEl) titleEl.textContent = place ? (base + " - " + place) : base;
    body.className = "panel-body dc-chart";
    body.replaceChildren();
    if (draw(body)) {
      addCaption(body, caption(captionKey, captionFallback, banded(lim)));
      return;
    }
    body.className = "panel-body trends-empty";
    body.innerHTML = "<p>" + (global.trendsEmptyMessage
      ? global.trendsEmptyMessage() : tr("ui.trends_no_plot", "No data available.")) + "</p>";
  }

  function render(state) {
    if (!trends()) return;
    var scope = state.scope, key = state.key;
    var place = scope === "national"
      ? tr("ui.trends_scope_national", "National")
      : (scope === "health_zone" && global.zoneDisplayName ? global.zoneDisplayName(key) || key : key);

    var lim = xLimits(scope, key);
    card("trends-title", "trends-body", "ui.trends_panel", "Daily Cases by Symptom Onset",
      place, function (b) { return renderCases(b, scope, key); },
      "ui.trends_caption_cases", "Confirmed cases by date of symptom onset", lim);
    card("trends-deaths-title", "trends-deaths-body", "ui.trends_deaths_panel", "Cumulative Deaths",
      place, function (b) { return renderDeaths(b, scope, key); },
      "ui.trends_caption_deaths",
      "Cumulative confirmed deaths by reporting date (death alerts with confirmed MVE classification)", lim);
    card("trends-positivity-title", "trends-positivity-body", "ui.trends_positivity_panel", "Test Positivity",
      place, function (b) { return renderPositivity(b, scope, key); },
      "ui.trends_caption_positivity", "5-day rolling test positivity by date of symptom onset", lim);

    var labCard = document.getElementById("trends-labs");
    var labBody = document.getElementById("trends-labs-body");
    var labTitle = document.getElementById("trends-labs-title");
    if (!labCard || !labBody) return;
    var show = scope === "national" || !!key;
    labCard.style.display = show ? "" : "none";
    if (!show) { labBody.replaceChildren(); return; }
    if (labTitle) labTitle.textContent = tr("ui.trends_labs_panel", "Laboratory testing");
    var labs = labsForSelection(scope, key);
    labBody.replaceChildren();
    if (!labs.length) {
      labBody.className = "panel-body trends-empty";
      labBody.innerHTML = "<p>" + tr("ui.trends_no_labs", "No laboratory data for this selection.") + "</p>";
      return;
    }
    labBody.className = "panel-body trends-labs-body";
    labs.forEach(function (lab) {
      var wrap = document.createElement("div");
      wrap.className = "trends-lab-subplot";
      var h = document.createElement("h4");
      h.className = "trends-lab-subplot-title";
      h.textContent = lab.label || lab.code;
      wrap.appendChild(h);
      var body = document.createElement("div");
      body.className = "dc-chart";
      wrap.appendChild(body);
      labBody.appendChild(wrap);
      renderLab(body, lab);
    });
    // Lab caption is constant -- it has no incomplete-note variant (spec 6.5).
    addCaption(labBody, tr("ui.trends_caption_labs",
      "Samples analysed and test positivity by analysis date"));
  }

  global.TrendsCharts = { render: render };
})(window);
```

- [ ] **Step 2: Delegate from engine.js**

In `Scripts/assets/engine.js`, replace the body of `renderTrendsPlots()` (~line 3161) with:

```javascript
function renderTrendsPlots() {
  // All four cards are drawn by trends.js (page-scoped to trends.html) from
  // PAYLOAD.trends. engine.js still owns the scope/selection state and the map.
  if (window.TrendsCharts) {
    window.TrendsCharts.render({scope: trendsScope, key: trendsSelectedKey});
  }
}
```

Delete these now-unreachable definitions from `engine.js`: `PLOT_SVG_TITLE_CROP`, `cropPlotSvgTop`, `renderPlotCard`, `renderTrendsPlot`, `resolveTrendsPlot`, `resolveCumulativeDeathsPlot`, `resolveRollingPositivityPlot`, `renderCumulativeDeathsPlot`, `renderRollingPositivityPlot`, `renderTrendsLabs`, `trendsLabsForSelection`, `trendsLabCodesForSelection`, `asCodeArray`, `normalizeLabLocationKey`, `findTrendsLab`, `trendsIndexes`, `trendsIndexEntry`.

Keep `trendsPlotData()` but repoint it, since `trendsEntityList()` still uses it for the dropdown:

```javascript
function trendsPlotData() {
  return PAYLOAD.trends || null;
}
```

Update `trendsEntityList()` so it reads the cases family — **the cases family is authoritative for the dropdown (spec §6.1)**; using the union would surface zones the current dashboard never shows:

```javascript
function trendsEntityList() {
  const data = trendsPlotData();
  if (!data) return [];
  // Cases only -- NOT the union with deaths/positivity. Five health zones have
  // positivity rows but no confirmed cases and must stay out of the dropdown.
  if (trendsScope === "province") {
    return Object.keys((data.cases && data.cases.provinces) || {}).sort(function(a, b) {
      return String(a).localeCompare(String(b), undefined, {sensitivity: "base"});
    }).map(function(id) { return {id: id, label: id, kind: "province"}; });
  }
  if (trendsScope === "health_zone") {
    return Object.keys((data.cases && data.cases.health_zones) || {}).sort(function(a, b) {
      return String(a).localeCompare(String(b), undefined, {sensitivity: "base"});
    }).map(function(id) { return {id: id, label: zoneDisplayName(id) || id, kind: "health_zone"}; });
  }
  return [{id: "national", label: t("ui.trends_scope_national"), kind: "national"}];
}
```

Finally, expose the empty-state message trends.js calls, adding this next to `trendsSelectionLabel()`:

```javascript
window.trendsEmptyMessage = function() {
  if (trendsScope === "national") {
    return escHtml(tf("ui.trends_no_plot", {name: t("ui.trends_scope_national")}));
  }
  if (trendsScope === "province") {
    return escHtml(trendsSelectedKey
      ? tf("ui.trends_no_plot", {name: trendsSelectedKey})
      : t("ui.trends_select_province"));
  }
  return escHtml(trendsSelectedKey
    ? tf("ui.trends_no_plot", {name: zoneDisplayName(trendsSelectedKey) || trendsSelectedKey})
    : t("ui.trends_select_health_zone"));
};
```

- [ ] **Step 3: Verify both files parse**

```bash
cd /Users/user/Documents/work/BDBV2026-Epidemic_Dashboard && node --check Scripts/assets/trends.js && node --check Scripts/assets/engine.js && echo BOTH_OK
```

Expected: `BOTH_OK`.

- [ ] **Step 4: Commit**

```bash
git add Scripts/assets/trends.js Scripts/assets/engine.js
git commit -m "Delegate Trends card rendering to trends.js"
```

---

### Task 13: Chart styles in both stylesheets

`dashboard.css` is the dark base; `Data/Branding/dashboard-theme.css` is appended afterwards with `!important` light-theme overrides. **Styling only one of them makes the charts render wrong** — this is a known trap in this repo.

**Files:**
- Modify: `Scripts/assets/dashboard.css:885-890`
- Modify: `Data/Branding/dashboard-theme.css`

- [ ] **Step 1: Add base styles**

In `Scripts/assets/dashboard.css`, replace the two `.onset-chart-wrap` rules (~line 887) with:

```css
  /* Runtime-drawn chart bodies (trends.js). Replaces .onset-chart-wrap, which
     wrapped the pre-rendered SVG images. */
  .dc-chart { position: relative; width: 100%; min-height: 190px; margin-top: 4px; }
  .dc-chart svg { width: 100%; max-width: 100%; height: 190px; display: block; }
  .dc-tip {
    position: absolute; pointer-events: none; z-index: 5;
    background: rgba(20,20,18,0.92); color: #f6f5f2;
    border-radius: 3px; padding: 4px 6px; font-size: 11px; line-height: 1.35;
    white-space: nowrap;
  }
  .dc-caption {
    margin: 4px 0 0; font-size: 10px; line-height: 1.35; color: #9c968b;
  }
  .dc-tip-d { font-weight: 700; margin-bottom: 2px; }
  .dc-tip-ci { color: #c9c7c2; }
  .dc-sw {
    display: inline-block; width: 8px; height: 8px; margin-right: 4px;
    border-radius: 1px; vertical-align: middle;
  }
```

- [ ] **Step 2: Add light-theme overrides**

Append to `Data/Branding/dashboard-theme.css`:

```css
/* ── Trends runtime charts ────────────────────────────────── */
/* The base sheet styles these for the dark base; the light theme needs its own
   values or the tooltip renders as dark-on-dark. */
.dc-tip {
  background: rgba(42,42,39,0.94) !important;
  color: #f6f5f2 !important;
}
.dc-tip-ci { color: #d8d3c9 !important; }
.dc-chart svg text { fill: var(--muted) !important; }
.dc-caption { color: var(--muted) !important; }
```

- [ ] **Step 3: Confirm no stale references remain**

```bash
cd /Users/user/Documents/work/BDBV2026-Epidemic_Dashboard && grep -rn "onset-chart-wrap" Scripts/ Data/ || echo NONE_LEFT
```

Expected: `NONE_LEFT`.

- [ ] **Step 4: Commit**

```bash
git add Scripts/assets/dashboard.css Data/Branding/dashboard-theme.css
git commit -m "Style the runtime Trends charts in both the base and theme sheets"
```

---

### Task 14: Localised chart strings

Titles are now composed client-side, so FR works end to end for the first time (R baked English into the images). Place names stay untranslated — they are proper nouns, matching current behaviour.

**Files:**
- Modify: `locales/en.json`, `locales/fr.json`

- [ ] **Step 1: Inspect the existing shape**

```bash
cd /Users/user/Documents/work/BDBV2026-Epidemic_Dashboard && python3.9 -c "
import json
en=json.load(open('locales/en.json'))
ui=en.get('ui',en)
print([k for k in ui if k.startswith('trends_')])"
```

Note whether keys live under a `ui` object or at the top level, and follow that shape below.

- [ ] **Step 2: Add the English strings**

Add to `locales/en.json`, alongside the existing `trends_*` keys:

```json
"trends_axis_cases": "Cases",
"trends_axis_deaths": "Cumulative Deaths",
"trends_axis_positivity": "Sample Positivity (%)",
"trends_axis_samples": "Samples Analysed",
"trends_series_observed": "Confirmed (Observed Onset)",
"trends_series_imputed": "Confirmed (Imputed Onset)",
"trends_series_positivity": "5-day Rolling Test Positivity",
"trends_incomplete_label": "Reporting likely incomplete",
"trends_lab_earliest": "Earliest Sample: ",
"trends_caption_cases": "Confirmed cases by date of symptom onset",
"trends_caption_deaths": "Cumulative confirmed deaths by reporting date (death alerts with confirmed MVE classification)",
"trends_caption_positivity": "5-day rolling test positivity by date of symptom onset",
"trends_caption_labs": "Samples analysed and test positivity by analysis date",
"trends_caption_incomplete": "Shaded region: dates within the last week (reporting likely incomplete)."
```

- [ ] **Step 3: Add the French strings**

Add to `locales/fr.json`:

```json
"trends_axis_cases": "Cas",
"trends_axis_deaths": "Décès cumulés",
"trends_axis_positivity": "Positivité des échantillons (%)",
"trends_axis_samples": "Échantillons analysés",
"trends_series_observed": "Confirmés (début observé)",
"trends_series_imputed": "Confirmés (début imputé)",
"trends_series_positivity": "Positivité des tests, moyenne mobile sur 5 jours",
"trends_incomplete_label": "Notification probablement incomplète",
"trends_lab_earliest": "Premier échantillon : ",
"trends_caption_cases": "Cas confirmés par date d'apparition des symptômes",
"trends_caption_deaths": "Décès confirmés cumulés par date de notification (alertes de décès avec classification MVE confirmée)",
"trends_caption_positivity": "Positivité des tests (moyenne mobile sur 5 jours) par date d'apparition des symptômes",
"trends_caption_labs": "Échantillons analysés et positivité des tests par date d'analyse",
"trends_caption_incomplete": "Zone ombrée : dates des sept derniers jours (notification probablement incomplète)."
```

- [ ] **Step 4: Verify both files are valid JSON with matching keys**

```bash
cd /Users/user/Documents/work/BDBV2026-Epidemic_Dashboard && python3.9 -c "
import json
en=json.load(open('locales/en.json')); fr=json.load(open('locales/fr.json'))
e=en.get('ui',en); f=fr.get('ui',fr)
missing=[k for k in e if k.startswith('trends_') and k not in f]
print('MISSING_IN_FR:', missing or 'none')"
```

Expected: `MISSING_IN_FR: none`.

- [ ] **Step 5: Commit**

```bash
git add locales/en.json locales/fr.json
git commit -m "Localise the Trends chart axis, series and caption strings"
```

---

### Task 15: Cross-check and dropdown-parity tests

These are the fidelity gates (§8.1, §8.3, §8.4). They compare the new loader against an **independent** existing code path and against fixed expectations.

**Files:**
- Create: `tests/test_trends_parity.py`

- [ ] **Step 1: Write the tests**

Create `tests/test_trends_parity.py`:

```python
import importlib
import json

ds = importlib.import_module("common.data_sources")

# One CSV, two independent readers: load_trends_series() (new) and
# load_onset_imputed_series() (the genomic tab's, already in production). They
# must agree on the national confirmed-case series; if they ever diverge, one of
# them has a real bug. See spec section 8.1.
SHARED_CSV = (
    "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
    "blank,not_a_case,spatial_scale,province,health_zone\n"
    "2026-05-01,FALSE,2,90,90,national,NA,NA\n"
    "2026-05-01,TRUE,1,0,0,national,NA,NA\n"
    "2026-05-03,FALSE,4,0,0,national,NA,NA\n"
    "2026-05-01,FALSE,2,0,0,province,Ituri,NA\n"
    "2026-05-01,FALSE,1,0,0,healthzone,NA,Bunia\n"
    # positivity-only zone: appears in rolling_positivity but has NO cases,
    # so it must NOT reach the dropdown (spec 6.1 / 8.3)
    "2026-05-01,FALSE,0,10,10,healthzone,NA,Nyarambe\n"
)

POS_CSV = (
    "date_of_symptom_onset_imputed,spatial_scale,province,health_zone,"
    "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
    "2026-05-01,healthzone,NA,Nyarambe,0.5,0.2,0.8\n"
    "2026-05-01,healthzone,NA,Bunia,0.4,0.1,0.7\n"
)


def _seed(tmp_path):
    out = tmp_path / "outputs"
    snap = out / "2026-05-10"
    snap.mkdir(parents=True)
    (snap / "status_aggregated.csv").write_text(SHARED_CSV, encoding="utf-8")
    (snap / "rolling_positivity.csv").write_text(POS_CSV, encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps({"date": "2026-05-10"}), encoding="utf-8")
    return out


def test_national_cases_agree_with_the_genomic_onset_series(tmp_path, monkeypatch):
    out = _seed(tmp_path)
    monkeypatch.setattr(ds, "DASHBOARD_PLOTS_DIR", out)

    trends = ds.load_trends_series(known_noms={"Bunia"})
    genomic = ds.load_onset_imputed_series(known_noms={"Bunia"})

    cases = trends["cases"]["national"]
    dates = [
        (__import__("datetime").date.fromisoformat(cases["start"])
         + __import__("datetime").timedelta(days=i)).isoformat()
        for i in range(len(cases["obs"]))
    ]
    from_trends = {
        d: {"observed": cases["obs"][i], "imputed": cases["imp"][i]}
        for i, d in enumerate(dates)
        if cases["obs"][i] or cases["imp"][i]
    }
    assert from_trends == genomic["national"]


def test_positivity_only_zones_never_reach_the_dropdown(tmp_path, monkeypatch):
    out = _seed(tmp_path)
    monkeypatch.setattr(ds, "DASHBOARD_PLOTS_DIR", out)

    res = ds.load_trends_series(known_noms={"Bunia"})

    # The dropdown is built from the CASES family only (spec 6.1). Nyarambe has
    # positivity data but no confirmed cases, so it must be absent there even
    # though it is present under positivity.
    assert "Nyarambe" not in res["cases"]["health_zones"]
    assert "Nyarambe" in res["positivity"]["health_zones"]
    assert "Bunia" in res["cases"]["health_zones"]


def test_national_cases_equal_the_sum_of_provinces(tmp_path, monkeypatch):
    out = _seed(tmp_path)
    monkeypatch.setattr(ds, "DASHBOARD_PLOTS_DIR", out)

    res = ds.load_trends_series(known_noms={"Bunia"})
    nat = res["cases"]["national"]
    # Only Ituri exists at province scale in this fixture, and only on 05-01.
    ituri = res["cases"]["provinces"]["Ituri"]
    assert nat["obs"][0] >= ituri["obs"][0]
```

- [ ] **Step 2: Run the tests**

```bash
cd Scripts && python3.9 -m pytest ../tests/test_trends_parity.py -v
```

Expected: `3 passed`. A failure in the first test means the two readers disagree — **stop and investigate**, do not adjust the assertion.

- [ ] **Step 3: Run the whole suite**

```bash
cd Scripts && python3.9 -m pytest ../tests -q
```

Expected: all pass, including the pre-existing `test_onset_imputed_series.py`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_trends_parity.py
git commit -m "Cross-check the Trends series against the genomic onset series"
```

---

### Task 16: Remove the SVG ingestion path

**Files:**
- Modify: `Scripts/common/data_sources.py` (by function name — do **not** delete by line range; `_parse_optional_float` lives just past that block and is still used)
- Modify: `README.md`
- Delete: `Data/dashboard_plots/2026-07-28/**`

- [ ] **Step 1: Keep two SVGs as visual references first**

```bash
cd /Users/user/Documents/work/BDBV2026-Epidemic_Dashboard && mkdir -p tests/fixtures/reference_svgs && \
cp Data/dashboard_plots/2026-07-28/dashboard_plots/confirmed_cases_and_positivity/national/daily_onset_national.svg tests/fixtures/reference_svgs/ && \
cp Data/dashboard_plots/2026-07-28/dashboard_plots/lab_plots/lab_inrbk.svg tests/fixtures/reference_svgs/ && \
ls tests/fixtures/reference_svgs
```

Expected: both files listed. These are the A/B references for Task 17.

- [ ] **Step 2: Delete the dead loader family**

From `Scripts/common/data_sources.py`, delete these functions entirely: `_slugify_plot_key` **only if nothing else calls it** (`_pack_trends_labs` does — so **keep it**), `_read_plot_svg`, `_svg_plot_title`, `_load_lab_name_map`, `_load_plot_type_family`, `load_dashboard_plots`. Remove `'load_dashboard_plots'` from `__all__`.

- [ ] **Step 3: Delete the SVG fixtures**

```bash
cd /Users/user/Documents/work/BDBV2026-Epidemic_Dashboard && git rm -r -q Data/dashboard_plots/2026-07-28 && ls Data/dashboard_plots
```

Expected: only `manifest.json` remains.

- [ ] **Step 4: Confirm nothing still references the removed code**

```bash
cd /Users/user/Documents/work/BDBV2026-Epidemic_Dashboard && grep -rn "load_dashboard_plots\|onset_trends\|cropPlotSvgTop\|_load_plot_type_family" Scripts/ tests/ || echo NONE_LEFT
```

Expected: `NONE_LEFT`.

- [ ] **Step 5: Update the README**

In `README.md`, replace the `dashboard_plots/` bullet (~line 25) with:

```markdown
- **dashboard_plots/** (optional) The aggregated CSVs the Trends tab charts are drawn from (`manifest.json` + `<date>/{status_aggregated,cumulative_positive_deaths,rolling_positivity,lab_positivity_aggregated}.csv`), produced by [BDBV2026-Processed_Sensitive_Data](https://github.com/INRB-UMIE/BDBV2026-Processed_Sensitive_Data)'s `outputs/` directory. The build reads this directly, no copying into `Data/dashboard_plots/` needed. By default it assumes that repo is cloned as a sibling of this one (`../BDBV2026-Processed_Sensitive_Data/outputs`); set `DASHBOARD_PLOTS_DIR` to override. The same directory also holds pre-rendered SVGs of these charts, which the dashboard **no longer reads** — it draws them client-side from the CSVs instead (see `Scripts/assets/trends.js`). Those charts must stay faithful to `BDBV2026-Processing_Code`'s `4-make-dashboard-plots.R`; see `docs/superpowers/specs/2026-09-22-trends-dynamic-charts-design.md`.
```

Also update the "Trends-tab SVGs" row of the data-source table (~line 282) to read **"Trends-tab series CSVs"**.

- [ ] **Step 6: Run the whole suite**

```bash
cd Scripts && python3.9 -m pytest ../tests -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Remove the pre-rendered SVG ingestion path from the Trends tab"
```

---

### Task 17: Build, verify visually, and hand over

The numeric gates are automated; appearance is a **human** gate (§8.5). Do not skip it, and do not open a PR before the reviewer has seen the page.

**Files:** none modified.

- [ ] **Step 1: Build**

```bash
cd /Users/user/Documents/work/BDBV2026-Epidemic_Dashboard/Scripts && \
DASHBOARD_PLOTS_DIR=../../BDBV2026-Processed_Sensitive_Data/outputs python3.9 build_dashboard.py
```

Expected: `wrote .../trends.html`. If the processed-data repo is not cloned as a sibling, clone it first or point `DASHBOARD_PLOTS_DIR` at a checkout — without it the Trends cards will be empty and the visual gate cannot run.

- [ ] **Step 2: Confirm the payload shrank and is page-scoped**

```bash
cd /Users/user/Documents/work/BDBV2026-Epidemic_Dashboard && python3.9 -c "
import re,json
for page in ('trends','index'):
    h=open('output/%s.html'%page,encoding='utf-8').read()
    p=json.loads(re.search(r'<script id=\"payload\" type=\"application/json\">(.*?)</script>',h,re.S).group(1))
    t=p.get('trends')
    print('%-7s page %5.2f MB  trends slice: %s' % (
        page, len(h)/1e6,
        ('%.0f KB' % (len(json.dumps(t,separators=(',',':')).encode())/1000)) if t else 'ABSENT'))"
```

Expected: `trends` carries a slice of roughly 300–400 KB; `index` reports `ABSENT`; both pages are several MB smaller than before.

- [ ] **Step 3: Serve and review**

```bash
cd /Users/user/Documents/work/BDBV2026-Epidemic_Dashboard/output && python3.9 -m http.server 8765
```

Open `http://localhost:8765/trends.html`. The page **must** be served over HTTP — opening the file directly breaks the payload fetch.

- [ ] **Step 4: Walk the visual gate**

Check each, against `tests/fixtures/reference_svgs/` and the live site:

- National, Ituri (province), one health zone: cases / deaths / positivity all render, and the three cards **span the same date range** (§6.6).
- Cases: observed (dark red) is **below** imputed (pale pink).
- Deaths: points appear **only** on days where the count steps up.
- Positivity: the line runs **straight across gaps** — no dips to zero on missing days.
- Labs: every lab chart shares one x range; the dashed "Earliest Sample" marker sits at each lab's own first sample.
- **Lab right-hand axis reads `0 / 25 / 50 / 75 / 100`, not `0.00–1.00`.** This is the one intended difference (D6). Every plotted mark must sit where the reference SVG puts it.
- The incomplete-reporting band covers the same window as the reference.
- **Captions are present under every chart** and match §6.2–§6.5, including the trailing "Shaded region: …" sentence appearing **only** where a band is drawn.
- Toggle EN/FR: titles, axis names and captions all switch. Place names stay unchanged.
- Resize the rail: charts reflow without clipping.

- [ ] **Step 5: Hand over before opening a PR**

Post the local URL and the specific reviewer checks above, and **wait for sign-off**. Only then open the PR.

- [ ] **Step 6: Commit any fixes**

```bash
git add -A && git commit -m "Fix issues found in Trends visual review"
```

---

## Follow-ups (out of scope — do not do these here)

1. Migrate `genomic.js` onto `charts.js` and delete its duplicated primitives (spec D4).
2. Publish an allowlisted public aggregate feed and read that instead (spec D1).
3. Ask the R pipeline to stop emitting the now-unused SVG families.
4. Ask the R pipeline to record the exact incomplete-reporting cutoff in `manifest.json` (spec D7/O2), retiring the `snapshot_date - n_days` approximation.
5. Report the lab secondary-axis mislabel upstream so the SVGs match the dashboard (spec D6/O1).
6. Decide whether `MVE` should render as `EVD` in English (spec O3).
