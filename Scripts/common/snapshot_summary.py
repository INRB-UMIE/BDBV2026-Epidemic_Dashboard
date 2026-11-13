"""
Compact per-zone summary for the Current Snapshot summary rail.

The Snapshot rail summarises the other tabs (Epidemiological Trends,
Surveillance and Testing, Genomic Epidemiology). Their own payload slices are
page-scoped (see _PAGE_SCOPED_PAYLOAD_KEYS in common/chrome.py) because they
are large -- ``trends`` alone is ~1.5 MB with health areas -- so instead of
un-scoping them, this module derives just what the rail draws:

* ``curve``: daily confirmed cases by symptom onset (observed + imputed, the
  Trends tab's cases card) and the 5-day rolling test positivity line (the
  Trends tab's positivity card), national and per health zone.
* ``labs``: per-laboratory totals plus the last 14 days, from the
  Surveillance and Testing tab's testing slice.
* ``testing``: samples tested / positive among residents of each zone.
* ``ct``: contact tracing headline numbers (national, province, zone).
* ``sequences``: genomes in the current phylogeny.

Invasion risk, public-health context, case counts and recency already ship on
every page, so the rail reads those straight from the shared payload.

Everything is read from the already-assembled shared payload, so a build
missing any source simply omits that block and the rail shows "no data".
"""

from __future__ import annotations

from datetime import date, timedelta

RECENT_DAYS = 14


def _r(v, nd=3):
    return None if v is None else round(float(v), nd)


def _curve(cases: dict | None, pos: dict | None) -> dict | None:
    if not cases and not pos:
        return None
    out: dict = {}
    if cases:
        out["start"] = cases.get("start")
        out["obs"] = list(cases.get("obs") or [])
        out["imp"] = list(cases.get("imp") or [])
    if pos and pos.get("dates"):
        out["pos"] = {
            "dates": list(pos["dates"]),
            "mean": [_r(v) for v in pos.get("mean") or []],
            "lo": [_r(v) for v in pos.get("lo") or []],
            "hi": [_r(v) for v in pos.get("hi") or []],
        }
    return out


def _lab_summary(lab: dict, asof: str | None) -> dict:
    dates = lab.get("dates") or []
    n = lab.get("n") or []
    pos = lab.get("pos") or []
    recent_n = recent_pos = 0
    if asof and dates:
        cutoff = (date.fromisoformat(asof) - timedelta(days=RECENT_DAYS)).isoformat()
        for d, nn, pp in zip(dates, n, pos):
            if d > cutoff:
                recent_n += int(nn or 0)
                recent_pos += int(pp or 0)
    return {
        "code": lab.get("code"),
        "label": lab.get("label") or lab.get("code"),
        "health_zone": lab.get("health_zone"),
        "province": lab.get("province"),
        "total_n": int(lab.get("total_n") or 0),
        "total_pos": int(lab.get("total_pos") or 0),
        "recent_n": recent_n,
        "recent_pos": recent_pos,
        "first": lab.get("first"),
        "last": lab.get("last"),
    }


def _testing_totals(entry: dict | None) -> dict | None:
    if not entry:
        return None
    return {"n": int(entry.get("total_n") or 0), "pos": int(entry.get("total_pos") or 0)}


def _sum_present(values):
    vals = [v for v in values if v is not None]
    return sum(vals) if vals else None


def build_snapshot_summary(payload: dict) -> dict:
    trends = payload.get("trends") or {}
    surv = payload.get("surveillance") or {}
    ct = surv.get("contact_tracing") or {}
    testing = surv.get("testing") or {}
    genomic = payload.get("genomic") or {}
    zone_data = payload.get("zone_data") or {}

    t_cases = trends.get("cases") or {}
    t_pos = trends.get("positivity") or {}
    zone_cases = t_cases.get("health_zones") or {}
    zone_pos = t_pos.get("health_zones") or {}

    labs = [_lab_summary(l, testing.get("asof")) for l in testing.get("labs") or []]
    labs.sort(key=lambda l: -l["total_n"])

    fu21 = ct.get("fu21") or {}
    fu_zones = fu21.get("zones") or {}
    weekly_by_zone = ct.get("weekly_by_zone") or {}

    zones: dict = {}
    noms = set(zone_cases) | set(zone_pos) | set(testing.get("health_zones") or {}) \
        | set(fu_zones) | set(weekly_by_zone) \
        | {l["health_zone"] for l in labs if l["health_zone"]}
    for nom in sorted(noms):
        z: dict = {}
        curve = _curve(zone_cases.get(nom), zone_pos.get(nom))
        if curve:
            z["curve"] = curve
        tt = _testing_totals((testing.get("health_zones") or {}).get(nom))
        if tt:
            z["testing"] = tt
        zl = [l["code"] for l in labs if l["health_zone"] == nom]
        if zl:
            z["labs"] = zl
        zct: dict = {}
        fz = fu_zones.get(nom)
        if fz:
            zct["fu_k"] = _sum_present(fz.get("k") or [])
            zct["fu_n"] = _sum_present(fz.get("n") or [])
        wz = weekly_by_zone.get(nom)
        if wz:
            zct["cases"] = sum(wz.get("new_cases") or [])
            zct["prev_contact"] = sum(wz.get("prev_contact") or [])
            zct["became_source"] = sum(wz.get("became_source") or [])
        if zct:
            z["ct"] = zct
        if z:
            zones[nom] = z

    nat_ct = None
    if ct:
        nat_ct = {
            "headline": ct.get("headline"),
            "national": ct.get("national"),
            "provinces": {p["area"]: p for p in ct.get("provinces") or [] if p.get("area")},
        }

    tips = genomic.get("tips") or []
    if tips:
        sequences = len(tips)
    else:
        sequences = _sum_present(
            (z or {}).get("genomic_sequence_count") for z in zone_data.values()
        )
    meta = genomic.get("meta") or {}

    return {
        "asof": {
            "cases": trends.get("asof"),
            "testing": testing.get("asof"),
            "ct": ct.get("data_cut"),
            "sequences": meta.get("updated") or genomic.get("data_build_date"),
        },
        "incomplete_from": trends.get("incomplete_from"),
        "recent_days": RECENT_DAYS,
        "national": {
            "curve": _curve(t_cases.get("national"), t_pos.get("national")),
            "testing": _testing_totals(testing.get("national")),
        },
        "provinces": {
            p: {"testing": _testing_totals(v)} for p, v in (testing.get("provinces") or {}).items()
        },
        "zones": zones,
        "labs": labs,
        "ct": nat_ct,
        "sequences": sequences,
    }
