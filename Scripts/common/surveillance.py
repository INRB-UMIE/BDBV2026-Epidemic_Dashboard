"""
Data slice for the "Surveillance and Testing" tab (PAYLOAD.surveillance).

Two independent sources, either of which may be missing (the tab then shows
an empty state for those cards rather than failing the build):

1. Contact tracing -- AGGREGATE tables written by
   BDBV2026-Contact_Tracing_Analytics (outputs/<DATE>/tables/), the same
   numbers as the contact tracing report. Only tables/ is ever read: derived/
   in that repo holds person-level data and must never reach this public
   dashboard. Panels that the report draws from person-level data come from
   the tables/dashboard_* files its step 13 writes.

2. Testing -- rolling_positivity.csv and lab_positivity_aggregated.csv from the
   same BDBV2026-Processed_Sensitive_Data snapshot the Trends tab uses.

Small cells: health-zone x month follow-up cells with fewer than
FU21_MIN_CONTACTS contacts are dropped here, before they reach the payload,
matching the report's Fig 3D ("months with <10 contacts omitted").
"""

from __future__ import annotations

import csv
import json
import re
from datetime import date, timedelta
from pathlib import Path

from common.paths import CT_ANALYTICS_OUTPUTS, DASHBOARD_PLOTS_DIR
from common.data_sources import (
    _fix_mojibake, _i0, _onset_manifest_dated_dir, _or_none, _parse_optional_float,
    _round_prop,
)

_DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

# Report Fig 3D rules.
FU21_MIN_CONTACTS = 10          # cells with fewer contacts are omitted
FU21_ZONE_MIN_TOTAL = 150       # a zone needs this many contacts in total ...
FU21_DEFAULT_ZONES = 9          # ... and the top 9 by contacts are shown by default
# Report Fig 3A/3B: percentage lines only for weeks with at least this many cases.
MIN_WEEK_CASES_FOR_PCT = 20
# Report Fig 3 starts its x axis here (earlier weeks have a handful of cases).
CT_WEEKS_FROM = "2026-05-11"


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _f(v):
    return _parse_optional_float(v)


def _r1(v):
    return None if v is None else round(v, 1)


def latest_ct_tables_dir(base: Path | None = None) -> Path | None:
    """outputs/<latest DATE>/tables that contains weekly_national.csv."""
    base = Path(base) if base is not None else CT_ANALYTICS_OUTPUTS
    if not base.is_dir():
        return None
    dated = sorted((p for p in base.iterdir() if p.is_dir() and _DATE_DIR_RE.match(p.name)),
                   key=lambda p: p.name, reverse=True)
    for d in dated:
        t = d / "tables"
        if (t / "weekly_national.csv").exists():
            return t
    return None


# --- contact tracing ---------------------------------------------------------------

def _weekly(rows, week_key):
    """Weekly CT series from weekly_national.csv / weekly_top_hz.csv rows."""
    rows = sorted((r for r in rows if _ISO_RE.match(r.get(week_key) or "")),
                  key=lambda r: r[week_key])
    rows = [r for r in rows if r[week_key][:10] >= CT_WEEKS_FROM]
    out = {"weeks": [], "new_cases": [], "prev_contact": [], "became_source": [],
           "pct_prev_contact": [], "pct_became_source": []}
    for r in rows:
        n = _i0(_f(r.get("new_cases")))
        prev = _i0(_f(r.get("new_cases_prev_contact")))
        src = _i0(_f(r.get("new_cases_became_source")))
        out["weeks"].append(r[week_key][:10])
        out["new_cases"].append(n)
        out["prev_contact"].append(prev)
        out["became_source"].append(src)
        ok = n >= MIN_WEEK_CASES_FOR_PCT
        out["pct_prev_contact"].append(_r1(100 * prev / n) if ok else None)
        out["pct_became_source"].append(_r1(100 * src / n) if ok else None)
    return out


def _fu21(tdir: Path):
    path = tdir / "fu21_complete_hz_month.csv"
    if not path.exists():
        return None
    rows = _read_csv(path)
    months = sorted({r["lc_month"] for r in rows if r.get("lc_month")})
    totals: dict[str, int] = {}
    cells: dict[str, dict[str, list]] = {}
    for r in rows:
        z = (r.get("src_health_zone") or "").strip()
        m = r.get("lc_month")
        if not z or z.upper() == "NA" or not m:
            continue
        n, k = _i0(_f(r.get("n"))), _i0(_f(r.get("k")))
        totals[z] = totals.get(z, 0) + n
        c = cells.setdefault(z, {}).setdefault(m, [0, 0])
        c[0] += k
        c[1] += n

    nat_path = tdir / "dashboard_fu21_by_month.csv"
    national = None
    if nat_path.exists():
        nat = {r["month"]: (_i0(_f(r["k"])), _i0(_f(r["n"]))) for r in _read_csv(nat_path)}
        # Months whose national total is below the small-cell threshold (the
        # first weeks of the outbreak) are dropped, as in the report.
        months = sorted(m for m in set(months) | set(nat)
                        if nat.get(m, (0, 0))[1] >= FU21_MIN_CONTACTS)
        national = {"k": [nat.get(m, (None, None))[0] for m in months],
                    "n": [nat.get(m, (None, None))[1] for m in months]}

    zones = {}
    for z, by_m in cells.items():
        k_list, n_list = [], []
        for m in months:
            k, n = by_m.get(m, (0, 0))
            keep = n >= FU21_MIN_CONTACTS
            k_list.append(k if keep else None)
            n_list.append(n if keep else None)
        if any(n is not None for n in n_list):
            # Total of the SHOWN cells only: including suppressed ones would let
            # anyone recover a hidden cell by subtraction.
            zones[z] = {"k": k_list, "n": n_list, "total": sum(n for n in n_list if n is not None)}
    # Zone selection follows the report (all of a zone's contacts, 03_figures.py);
    # only the ranking uses that, never the payload.
    eligible = sorted((z for z in zones if totals.get(z, 0) >= FU21_ZONE_MIN_TOTAL),
                      key=lambda z: -totals[z])
    return {
        "months": months,
        "national": national,
        "zones": zones,
        "default_zones": eligible[:FU21_DEFAULT_ZONES],
        "min_contacts": FU21_MIN_CONTACTS,
    }


def _journey(tdir: Path):
    path = tdir / "dashboard_patient_journey.csv"
    if not path.exists():
        return None
    out = []
    for r in _read_csv(path):
        out.append({
            "step": r["step"], "label": r["label"], "n": _i0(_f(r["n"])),
            "mean": _f(r["mean"]), "median": _f(r["median"]),
            "q1": _f(r["q1"]), "q3": _f(r["q3"]),
            "source_only": (r.get("source_cases_only") or "").strip().lower() == "true",
        })
    return out


def _delays_weekly(tdir: Path):
    path = tdir / "dashboard_delays_weekly.csv"
    if not path.exists():
        return None
    out: dict[str, dict] = {}
    for r in sorted(_read_csv(path), key=lambda r: (r["step"], r["wk"])):
        s = out.setdefault(r["step"], {"weeks": [], "n": [], "median": [], "q1": [], "q3": []})
        s["weeks"].append(r["wk"][:10])
        s["n"].append(_i0(_f(r["n"])))
        for k in ("median", "q1", "q3"):
            s[k].append(_f(r[k]))
    return out


def _area_table(tdir: Path, name: str):
    path = tdir / name
    if not path.exists():
        return None
    out = []
    for r in _read_csv(path):
        out.append({
            "area": r.get("area"),
            "cases": _i0(_f(r.get("cases"))),
            "deaths": _i0(_f(r.get("deaths"))),
            "pct_cases_source": _r1(_f(r.get("pct_cases_source"))),
            "pct_cases_prev_contact": _r1(_f(r.get("pct_cases_prev_contact"))),
            "_pct_prev_raw": _f(r.get("pct_cases_prev_contact")),
            "source_cases": _i0(_f(r.get("source_cases"))),
            "contacts": _i0(_f(r.get("contacts"))),
            "med_contacts": _f(r.get("med_contacts")),
            "pct_fu_complete": _r1(_f(r.get("pct_fu_complete"))),
            "fu_lo": _r1(_f(r.get("fu_wilson_lo"))),
            "fu_hi": _r1(_f(r.get("fu_wilson_hi"))),
        })
    return out


def load_contact_tracing(tables_dir: Path | None = None):
    tdir = Path(tables_dir) if tables_dir is not None else latest_ct_tables_dir()
    if tdir is None:
        print(f"  NOTE: no contact tracing tables under {CT_ANALYTICS_OUTPUTS}; "
              "Surveillance and Testing CT cards will be empty")
        return None
    meta = {}
    meta_path = tdir / "dashboard_meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  WARNING: unreadable {meta_path}: {exc}")
    data_cut = meta.get("data_cut") or tdir.parent.name
    if not meta.get("last_full_week"):
        cut = date.fromisoformat(data_cut)
        meta["last_full_week"] = (cut - timedelta(days=cut.weekday() + 7)).isoformat()

    weekly = None
    wpath = tdir / "weekly_national.csv"
    rows = _read_csv(wpath)
    if rows:
        key = next(iter(rows[0]))          # the unnamed index column holds the week
        weekly = _weekly(rows, key)
    by_zone = {}
    zpath = tdir / "weekly_top_hz.csv"
    if zpath.exists():
        zrows: dict[str, list] = {}
        for r in _read_csv(zpath):
            z = (r.get("health_zone") or "").strip()
            if z:
                zrows.setdefault(z, []).append(r)
        by_zone = {z: _weekly(rs, "week") for z, rs in sorted(zrows.items())}

    followup = None
    fpath = tdir / "followup_visits_weekly.csv"
    if fpath.exists():
        frows = sorted((r for r in _read_csv(fpath) if _ISO_RE.match(r.get("wk") or "")),
                       key=lambda r: r["wk"])
        frows = [r for r in frows if r["wk"][:10] >= CT_WEEKS_FROM]
        followup = {"weeks": [r["wk"][:10] for r in frows],
                    "visits": [_i0(_f(r["visits"])) for r in frows],
                    "pct_result": [_r1(_f(r["pct_result"])) for r in frows]}

    provinces = _area_table(tdir, "province_table.csv")
    national_row = next((r for r in (provinces or []) if (r["area"] or "").lower() == "national"), None)
    headline = None
    if national_row:
        headline = {
            "cases": national_row["cases"],
            "prev_contact_pct": national_row["pct_cases_prev_contact"],
            # From the UNROUNDED percentage: 0.536% of 8,953 is 48, 0.5% is 45.
            "prev_contact_n": round(national_row["cases"] * (national_row["_pct_prev_raw"] or 0) / 100),
            "any_time_n": meta.get("n_cases_contact_any_time"),
            "contacts": national_row["contacts"],
            "fu_contacts": meta.get("fu21_contacts"),
            "fu_complete": meta.get("fu21_complete"),
            "fu_pct": national_row["pct_fu_complete"],
            "source_cases": national_row["source_cases"],
        }

    for r in (provinces or []):
        r.pop("_pct_prev_raw", None)

    return {
        "data_cut": data_cut,
        "meta": meta,
        "headline": headline,
        "weekly": weekly,
        "weekly_by_zone": by_zone,
        "followup": followup,
        "fu21": _fu21(tdir),
        "journey": _journey(tdir),
        "delays_weekly": _delays_weekly(tdir),
        "provinces": [r for r in (provinces or []) if r is not national_row],
        "national": national_row,
    }


# --- testing --------------------------------------------------------------------------

_TEST_SCALES = {"national": None, "province": "province", "healthzone": "health_zone"}


def _pack_testing(path: Path):
    by: dict[str, dict[str, dict]] = {s: {} for s in _TEST_SCALES}
    for r in _read_csv(path):
        scale = (r.get("spatial_scale") or "").strip().lower()
        if scale not in _TEST_SCALES:
            continue
        field = _TEST_SCALES[scale]
        loc = "national" if field is None else _or_none(r.get(field))
        if not loc:
            continue
        loc = _fix_mojibake(loc)
        day = (r.get("date_of_symptom_onset_imputed") or "").strip()
        if not _ISO_RE.match(day):
            continue
        by[scale].setdefault(loc, {})[day[:10]] = (
            _i0(_f(r.get("total_samples_analysed_daily"))),
            _i0(_f(r.get("confirmed_case"))),
            _round_prop(_f(r.get("daily_positivity_mean"))),
            _round_prop(_f(r.get("daily_positivity_lower"))),
            _round_prop(_f(r.get("daily_positivity_upper"))),
        )
    packed = {}
    for scale, locs in by.items():
        packed[scale] = {}
        for loc, days in locs.items():
            ds = sorted(days)
            packed[scale][loc] = {
                "dates": ds,
                "n": [days[d][0] for d in ds],
                "pos": [days[d][1] for d in ds],
                "mean": [days[d][2] for d in ds],
                "lo": [days[d][3] for d in ds],
                "hi": [days[d][4] for d in ds],
                "total_n": sum(days[d][0] for d in ds),
                "total_pos": sum(days[d][1] for d in ds),
            }
    return packed


def _pack_labs(path: Path):
    labs: dict[str, dict] = {}
    for r in _read_csv(path):
        code = (r.get("lab_name") or "").strip()
        day = (r.get("lab_analysis_date") or "").strip()
        if not code or not _ISO_RE.match(day):
            continue
        long_name = _or_none(r.get("lab_name_long"))
        lab = labs.setdefault(code, {
            "code": code,
            "label": _fix_mojibake(long_name) if long_name else code,
            "health_zone": _fix_mojibake(_or_none(r.get("health_zone")) or "") or None,
            "province": _fix_mojibake(_or_none(r.get("province")) or "") or None,
            "days": {},
        })
        n = _i0(_f(r.get("total_samples_analysed_daily")))
        pos = _i0(_f(r.get("confirmed_case")))
        prev = lab["days"].get(day[:10], (0, 0))
        lab["days"][day[:10]] = (prev[0] + n, prev[1] + pos)
    out = []
    for code in sorted(labs, key=lambda c: -sum(v[0] for v in labs[c]["days"].values())):
        lab = labs[code]
        ds = sorted(lab["days"])
        n = [lab["days"][d][0] for d in ds]
        pos = [lab["days"][d][1] for d in ds]
        out.append({
            "code": code, "label": lab["label"], "health_zone": lab["health_zone"],
            "province": lab["province"], "dates": ds, "n": n, "pos": pos,
            "total_n": sum(n), "total_pos": sum(pos),
            "first": ds[0] if ds else None, "last": ds[-1] if ds else None,
        })
    return out


def load_testing(outputs_dir: Path | None = None):
    base = Path(outputs_dir if outputs_dir is not None else DASHBOARD_PLOTS_DIR)
    snap = _onset_manifest_dated_dir(base)
    if snap is None:
        print(f"  NOTE: no dated snapshot under {base}; testing cards will be empty")
        return None
    pos_path, lab_path = snap / "rolling_positivity.csv", snap / "lab_positivity_aggregated.csv"
    series = _pack_testing(pos_path) if pos_path.exists() else None
    labs = _pack_labs(lab_path) if lab_path.exists() else []
    if not series and not labs:
        return None
    asof = snap.name
    return {
        "asof": asof,
        # Same 7-day incomplete-reporting window the Trends tab shades.
        "incomplete_from": (date.fromisoformat(asof) - timedelta(days=7)).isoformat(),
        "national": (series or {}).get("national", {}).get("national"),
        "provinces": (series or {}).get("province", {}),
        "health_zones": (series or {}).get("healthzone", {}),
        "labs": labs,
    }


def load_surveillance(ct_tables_dir=None, outputs_dir=None):
    ct = load_contact_tracing(ct_tables_dir)
    testing = load_testing(outputs_dir)
    if ct is None and testing is None:
        return None
    return {"contact_tracing": ct, "testing": testing}
