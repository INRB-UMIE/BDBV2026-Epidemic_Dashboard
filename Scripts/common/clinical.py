"""
Clinical Symptoms tab data: PAYLOAD.clinical.

Reads the summary tables BDBV2026-Processing_Code step 9
(9-clinical-aggregates.R) writes to outputs/<DATE>/clinical/, for the same
manifest-resolved snapshot date as the Trends tab. Those tables are already
aggregated and small counts are already suppressed there (counts 1 to
min_cell_count - 1 written as NA with suppressed = TRUE); nothing here
recomputes from individual records.

Shape (one entry per location: "national", "province:<name>"):

    {"asof", "meta": {...clinical_meta.json},
     "labels": {code: {"en", "fr", "confirmed"}},
     "order": [codes, most frequent nationally first],
     "locations": {key: {
        "label", "summary": {...},
        "symptoms": {breakdown: {group: {"den", "den_s", "n": [..], "pct": [..], "s": [..]}}},
        "los": {status: {"bins": [..], "lo": [..], "hi": [..], "n": [..], "s": [..]}},
        "pyramid": {"bands": [..], "female": [..], "male": [..],
                    "female_dead": [..], "male_dead": [..], "s_female": [..], "s_male": [..]},
        "hcw": {"months": [..], "n": [..], "s": [..], "roles": {role: n}, "roles_s": {role: bool}}}}}

Suppressed values are null with a matching s/..._s flag of 1, so the page
can show "<N" rather than treating them as zero.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from common.data_sources import _fix_mojibake, _onset_manifest_dated_dir
from common.paths import DASHBOARD_PLOTS_DIR

CLINICAL_DIRNAME = "clinical"
_FILES = ("clinical_summary.csv", "clinical_symptoms.csv", "clinical_length_of_stay.csv",
          "clinical_age_sex.csv", "clinical_health_workers.csv")


def _read(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _na(v) -> bool:
    return v is None or str(v).strip() in ("", "NA", "NaN")


def _int(v):
    if _na(v):
        return None
    try:
        return int(round(float(v)))
    except ValueError:
        return None


def _float(v):
    if _na(v):
        return None
    try:
        return round(float(v), 1)
    except ValueError:
        return None


def _true(v) -> bool:
    return str(v).strip().upper() in ("TRUE", "T", "1")


def _key(r: dict) -> str | None:
    scale = (r.get("spatial_scale") or "").strip()
    if scale == "national":
        return "national"
    if scale == "province":
        loc = _fix_mojibake((r.get("location") or "").strip())
        return "province:" + loc if loc else None
    return None


def load_clinical(outputs_dir: Path | None = None):
    base = Path(outputs_dir if outputs_dir is not None else DASHBOARD_PLOTS_DIR)
    snap = _onset_manifest_dated_dir(base)
    if snap is None:
        print(f"  NOTE: no dated snapshot under {base}; clinical tab will be empty")
        return None
    cdir = snap / CLINICAL_DIRNAME
    if not (cdir / "clinical_summary.csv").exists():
        print(f"  NOTE: {CLINICAL_DIRNAME}/ not found in {snap.name} (run Processing_Code step 9); "
              "clinical tab will be empty")
        return None

    meta = {}
    try:
        meta = json.loads((cdir / "clinical_meta.json").read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        pass

    locs: dict[str, dict] = {}

    def loc(r):
        k = _key(r)
        if k is None:
            return None
        if k not in locs:
            locs[k] = {"label": None if k == "national" else k.split(":", 1)[1],
                       "summary": {}, "symptoms": {}, "los": {}, "pyramid": None, "hcw": None}
        return locs[k]

    # --- summary ---
    for r in _read(cdir / "clinical_summary.csv"):
        L = loc(r)
        if L is None:
            continue
        L["summary"] = {
            k: (_float(v) if k.endswith(("_median", "_q25", "_q75")) else _int(v))
            for k, v in r.items() if k not in ("spatial_scale", "location")
        }

    # --- symptoms ---
    labels: dict[str, dict] = {}
    raw_sym: dict[str, dict] = {}
    p = cdir / "clinical_symptoms.csv"
    if p.exists():
        for r in _read(p):
            L = loc(r)
            if L is None:
                continue
            code = (r.get("symptom_code") or "").strip().upper()
            if not code:
                continue
            labels.setdefault(code, {
                "en": (r.get("symptom_label_en") or code).strip(),
                "fr": (r.get("symptom_label_fr") or code).strip(),
                "confirmed": _true(r.get("label_confirmed")),
            })
            g = raw_sym.setdefault(_key(r), {}).setdefault(r["breakdown"], {}).setdefault(r["group"], {})
            g[code] = (_int(r.get("n_with_symptom")), _float(r.get("pct")), _true(r.get("suppressed")),
                       _int(r.get("n_symptoms_recorded")))
    # Order: most frequent nationally (overall) first; unknown last.
    nat_all = (raw_sym.get("national") or {}).get("all", {}).get("all", {})
    order = sorted(labels, key=lambda c: (-(nat_all.get(c, (0, None))[1] or -1), c))
    for k, by_bd in raw_sym.items():
        out = {}
        for bd, groups in by_bd.items():
            out[bd] = {}
            for grp, codes in groups.items():
                den = next((v[3] for v in codes.values()), None)
                out[bd][grp] = {
                    "den": den,
                    "n": [codes.get(c, (None,))[0] for c in order],
                    "pct": [codes.get(c, (None, None))[1] for c in order],
                    "s": [1 if codes.get(c, (None, None, False))[2] else 0 for c in order],
                }
        locs[k]["symptoms"] = out

    # --- length of stay ---
    p = cdir / "clinical_length_of_stay.csv"
    if p.exists():
        for r in _read(p):
            L = loc(r)
            if L is None:
                continue
            h = L["los"].setdefault(r["status_at_sampling"], {"bins": [], "lo": [], "hi": [], "n": [], "s": []})
            h["bins"].append(r["stay_bin"])
            h["lo"].append(_int(r["bin_lo"]))
            h["hi"].append(_int(r["bin_hi"]))
            h["n"].append(_int(r["n"]))
            h["s"].append(1 if _true(r["suppressed"]) else 0)

    # --- age pyramid ---
    p = cdir / "clinical_age_sex.csv"
    if p.exists():
        for r in _read(p):
            L = loc(r)
            if L is None:
                continue
            if L["pyramid"] is None:
                L["pyramid"] = {"bands": [], "female": [], "male": [], "female_dead": [], "male_dead": [],
                                "s_female": [], "s_male": []}
            py = L["pyramid"]
            band, sx = r["age_band"], r["sex"]
            if band not in py["bands"]:
                py["bands"].append(band)
                for f in ("female", "male", "female_dead", "male_dead", "s_female", "s_male"):
                    py[f].append(None if not f.startswith("s_") else 0)
            i = py["bands"].index(band)
            if sx in ("female", "male"):
                py[sx][i] = _int(r["n"])
                py[sx + "_dead"][i] = _int(r["n_dead_at_sampling"])
                py["s_" + sx][i] = 1 if _true(r["suppressed"]) else 0

    # --- health workers ---
    p = cdir / "clinical_health_workers.csv"
    if p.exists():
        for r in _read(p):
            L = loc(r)
            if L is None:
                continue
            if L["hcw"] is None:
                L["hcw"] = {"months": [], "n": [], "s": [], "roles": {}, "roles_s": {}}
            h = L["hcw"]
            if r["breakdown"] == "onset_month":
                h["months"].append(r["group"])
                h["n"].append(_int(r["n"]))
                h["s"].append(1 if _true(r["suppressed"]) else 0)
            elif r["breakdown"] == "role":
                h["roles"][r["group"]] = _int(r["n"])
                h["roles_s"][r["group"]] = _true(r["suppressed"])

    if not locs:
        return None
    return {
        "asof": snap.name,
        "meta": {
            "min_cell_count": meta.get("min_cell_count", 10),
            "max_delay_days": meta.get("max_delay_days"),
            "symptom_age_groups": meta.get("symptom_age_groups") or [],
            "unconfirmed_symptom_codes": meta.get("unconfirmed_symptom_codes") or [],
        },
        "labels": labels,
        "order": order,
        "locations": locs,
    }
