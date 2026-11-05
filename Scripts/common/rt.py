"""
Time-varying reproduction number (Rt) estimates.

Input: the newest ``Data/inrb_dashboard_Rt_data_<YYYYMMDD>.csv`` (the date in
the file name is the estimation run date). Columns:

    area, area_type (national | province), date, rt_mean, rt_lower_95, rt_upper_95

Output (``PAYLOAD.rt``, read by the Epidemiological Trends Rt card and the
Current Snapshot Rt card)::

    {
      "run_date": "2026-11-02", "source_file": "...csv",
      "national": {"dates": [...], "mean": [...], "lo": [...], "hi": [...]},
      "provinces": {"Ituri": {...same...}, ...},
    }

Returns ``{}`` when no file is present, so the build stays green and both
cards show their empty state.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from common.paths import DATA_ROOT

RT_GLOB = "inrb_dashboard_Rt_data_*.csv"
_RUN_DATE_RE = re.compile(r"_(\d{8})\.csv$")
_REQUIRED = ("area", "area_type", "date", "rt_mean", "rt_lower_95", "rt_upper_95")


def latest_rt_file(data_root: Path = DATA_ROOT) -> Path | None:
    """Newest file by the YYYYMMDD in its name (not by mtime, which a git
    checkout resets)."""
    dated = []
    for p in Path(data_root).glob(RT_GLOB):
        m = _RUN_DATE_RE.search(p.name)
        if m:
            dated.append((m.group(1), p))
    return max(dated)[1] if dated else None


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 4) if f == f else None  # NaN -> None


def load_rt_estimates(data_root: Path = DATA_ROOT) -> dict:
    path = latest_rt_file(data_root)
    if path is None:
        print(f"  NOTE: no {RT_GLOB} under {data_root}; Rt cards will show no data")
        return {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in _REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path.name}: missing column(s) {missing}")
        rows = list(reader)

    series: dict[tuple[str, str], dict[str, tuple]] = {}
    for r in rows:
        kind = (r["area_type"] or "").strip().lower()
        area = (r["area"] or "").strip()
        date = (r["date"] or "").strip()[:10]
        if kind not in ("national", "province") or not area or not date:
            continue
        key = ("national", "National") if kind == "national" else ("province", area)
        # Last row wins on a duplicated (area, date).
        series.setdefault(key, {})[date] = (_num(r["rt_mean"]), _num(r["rt_lower_95"]), _num(r["rt_upper_95"]))

    def pack(by_date):
        dates = sorted(by_date)
        return {
            "dates": dates,
            "mean": [by_date[d][0] for d in dates],
            "lo": [by_date[d][1] for d in dates],
            "hi": [by_date[d][2] for d in dates],
        }

    m = _RUN_DATE_RE.search(path.name)
    run = m.group(1)
    out = {
        "source_file": path.name,
        "run_date": f"{run[:4]}-{run[4:6]}-{run[6:]}",
        "national": pack(series[("national", "National")]) if ("national", "National") in series else None,
        "provinces": {a: pack(v) for (k, a), v in sorted(series.items()) if k == "province"},
    }
    nat = out["national"]
    print(f"  Rt: {path.name} (run {out['run_date']}), national "
          f"{nat['dates'][0] + '..' + nat['dates'][-1] if nat else 'missing'}, "
          f"{len(out['provinces'])} provinces")
    return out
