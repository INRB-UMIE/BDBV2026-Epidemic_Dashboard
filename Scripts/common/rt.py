"""
Time-varying reproduction number (Rt) estimates.

Input: the newest ``inrb_dashboard_Rt_data_<YYYYMMDD>.csv`` (the date in the
file name is the estimation run date), from ``Data/`` and, when a token is set,
from a GitHub repo too; whichever has the later run date wins (a tie uses the
local file). See "Remote source" below. Columns:

    area, area_type, date, rt_mean, rt_lower_95, rt_upper_95

``area_type`` is one of national, province, health_zone, health_area. A
health_area row's ``area`` must be "<zone>|<area>", the key the Trends tab
uses for health areas. Today's files carry national + province only.

Output (``PAYLOAD.rt``, read by the Epidemiological Trends Rt card and the
Current Snapshot Rt card)::

    {
      "run_date": "2026-11-02", "source_file": "...csv",
      "national": {"dates": [...], "mean": [...], "lo": [...], "hi": [...]},
      "provinces": {"Ituri": {...same...}, ...},
      "health_zones": {...}, "health_areas": {...},   # {} when not estimated
    }

The Trends Rt card is shown only at scopes whose level is non-empty, so adding
zone or area rows switches it on there with no front-end change.

Remote source: set ``RT_GITHUB_TOKEN`` (a fine-grained PAT with Contents: Read
on the repo) to also look in ``RT_REMOTE_REPO`` (default
mrc-ide/ebola-bvd-2026-outputs), branch ``RT_REMOTE_REF`` (default
inrb-dashboard-data), folder ``RT_REMOTE_PATH`` (default inrb_dashboard).
Without a token, or if GitHub can't be reached, the build uses ``Data/`` alone.
The token is only ever sent to api.github.com and is never printed.

Returns ``{}`` when no file is found anywhere, so the build stays green and
both cards show their empty state.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import ssl
import urllib.error
import urllib.request
from pathlib import Path

from common.paths import DATA_ROOT

RT_GLOB = "inrb_dashboard_Rt_data_*.csv"
RT_REMOTE_REPO = os.environ.get("RT_REMOTE_REPO", "").strip() or "mrc-ide/ebola-bvd-2026-outputs"
RT_REMOTE_REF = os.environ.get("RT_REMOTE_REF", "").strip() or "inrb-dashboard-data"
RT_REMOTE_PATH = os.environ.get("RT_REMOTE_PATH", "").strip().strip("/") or "inrb_dashboard"
_FETCH_TIMEOUT_S = 25
_RUN_DATE_RE = re.compile(r"_(\d{8})\.csv$")
# area_type -> payload key for the per-location levels.
_LEVELS = {"national": None, "province": "provinces",
           "health_zone": "health_zones", "health_area": "health_areas"}
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


def _github_get(url: str, token: str, raw: bool = False):
    headers = {
        "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "BDBV2026-Dashboard-Build/1.0",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_S,
                                context=ssl.create_default_context()) as resp:
        body = resp.read().decode("utf-8")
    return body if raw else json.loads(body)


def latest_remote_rt() -> tuple[str, str] | None:
    """``(filename, csv_text)`` of the newest Rt file in the GitHub repo, or
    None when no token is set or GitHub can't be reached (never raises)."""
    token = os.environ.get("RT_GITHUB_TOKEN", "").strip()
    if not token:
        print("  NOTE: RT_GITHUB_TOKEN not set; Rt read from Data/ only")
        return None
    listing_url = (f"https://api.github.com/repos/{RT_REMOTE_REPO}/contents/"
                   f"{RT_REMOTE_PATH}?ref={RT_REMOTE_REF}")
    try:
        items = _github_get(listing_url, token)
        dated = []
        for it in items if isinstance(items, list) else []:
            m = _RUN_DATE_RE.search(it.get("name", ""))
            if it.get("type") == "file" and m and it["name"].startswith(RT_GLOB.split("*")[0]):
                dated.append((m.group(1), it))
        if not dated:
            print(f"  NOTE: no {RT_GLOB} in {RT_REMOTE_REPO}@{RT_REMOTE_REF}/{RT_REMOTE_PATH}")
            return None
        _, item = max(dated, key=lambda d: d[0])
        return item["name"], _github_get(item["url"], token, raw=True)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
        # HTTPError text carries the status only (401/403/404), never the token.
        print(f"  NOTE: Rt fetch from {RT_REMOTE_REPO} failed ({exc}); using Data/ only")
        return None


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 4) if f == f else None  # NaN -> None


def load_rt_estimates(data_root: Path = DATA_ROOT) -> dict:
    path = latest_rt_file(data_root)
    name, text = (path.name, None) if path else (None, None)
    remote = latest_remote_rt()
    if remote:
        rname, rtext = remote
        if name is None or _RUN_DATE_RE.search(rname).group(1) > _RUN_DATE_RE.search(name).group(1):
            name, text = rname, rtext
            print(f"  Rt: using {rname} from {RT_REMOTE_REPO}")
    if name is None:
        print(f"  NOTE: no {RT_GLOB} under {data_root} or on GitHub; Rt cards will show no data")
        return {}
    if text is None:
        text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff"), newline=""))
    missing = [c for c in _REQUIRED if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"{name}: missing column(s) {missing}")
    rows = list(reader)

    series: dict[tuple[str, str], dict[str, tuple]] = {}
    for r in rows:
        kind = (r["area_type"] or "").strip().lower()
        area = (r["area"] or "").strip()
        date = (r["date"] or "").strip()[:10]
        if kind not in _LEVELS or not area or not date:
            continue
        key = ("national", "National") if kind == "national" else (kind, area)
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

    m = _RUN_DATE_RE.search(name)
    run = m.group(1)
    out = {
        "source_file": name,
        "run_date": f"{run[:4]}-{run[4:6]}-{run[6:]}",
        "national": pack(series[("national", "National")]) if ("national", "National") in series else None,
    }
    for kind, out_key in _LEVELS.items():
        if out_key:
            out[out_key] = {a: pack(v) for (k, a), v in sorted(series.items()) if k == kind}
    nat = out["national"]
    print(f"  Rt: {name} (run {out['run_date']}), national "
          f"{nat['dates'][0] + '..' + nat['dates'][-1] if nat else 'missing'}, "
          f"{len(out['provinces'])} provinces, {len(out['health_zones'])} health zones, "
          f"{len(out['health_areas'])} health areas")
    return out
