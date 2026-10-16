#!/usr/bin/env python3
"""
Simplify the DRC health-area (aire de sante) shapefile into a small GeoJSON for
the Trends tab's "Health Area" scope.

Input  (default): ../BDBV2026-Processed_Sensitive_Data/assets/geo/rdc_aires-de-sante/RDC_Aires de santÇ.shp
Output (default): health_areas_simplified.geojson next to that shapefile.

Run it again only when the source shapefile changes; the dashboard build reads
the output (see HEALTH_AREA_GEOJSON in common/paths.py) and keeps just the
health areas that have Trends data.

Why hand-rolled: the build environment has numpy but no GIS stack (no
shapely/pyshp/geopandas/mapshaper), and adding one for a one-off conversion
is not worth it. Shapefile polygons (type 5) and dBASE tables are simple
binary formats, read directly below.

Simplification is TOPOLOGY-AWARE: each ring is cut into arcs at the vertices
where the set of neighbouring polygons changes, every shared arc is simplified
exactly once, and both neighbours reuse that one result. Simplifying each
polygon on its own would let neighbours drift apart along a shared border and
open slivers/overlaps between them on the map.

Usage:
    python Scripts/simplify_health_areas.py [--tolerance 0.0008] [--shp PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DIR = (SCRIPT_DIR.parent.parent / "BDBV2026-Processed_Sensitive_Data"
               / "assets" / "geo" / "rdc_aires-de-sante")
DEFAULT_SHP = DEFAULT_DIR / "RDC_Aires de santÇ.shp"
DEFAULT_OUT = DEFAULT_DIR / "health_areas_simplified.geojson"

# Snap grid (degrees) used to recognise a vertex shared by two polygons. The
# source digitises shared borders with identical vertices, so this only has
# to absorb float noise (1e-7 deg is ~1 cm).
SNAP = 1e-7
# Output coordinate precision: 4 decimals is ~11 m, well below what the
# simplification tolerance keeps anyway.
OUT_DECIMALS = 4


# --- readers -----------------------------------------------------------------

def read_dbf(path: Path, encoding: str = "utf-8") -> list[dict]:
    b = path.read_bytes()
    n = struct.unpack("<I", b[4:8])[0]
    header_len, record_len = struct.unpack("<HH", b[8:12])
    fields, o = [], 32
    while b[o] != 0x0D:
        name = b[o:o + 11].split(b"\0")[0].decode("ascii")
        fields.append((name, b[o + 16]))
        o += 32
    out = []
    for i in range(n):
        rec = b[header_len + i * record_len: header_len + (i + 1) * record_len]
        if rec[:1] == b"*":          # deleted record
            out.append(None)
            continue
        pos, row = 1, {}
        for name, length in fields:
            row[name] = rec[pos:pos + length].decode(encoding, "replace").strip()
            pos += length
        out.append(row)
    return out


def read_shp_polygons(path: Path) -> list[list[np.ndarray]]:
    """One entry per record: a list of rings, each an (n, 2) float array."""
    b = path.read_bytes()
    shape_type = struct.unpack("<i", b[32:36])[0]
    if shape_type not in (5, 15, 25):
        raise SystemExit(f"expected a polygon shapefile, got shape type {shape_type}")
    o, shapes = 100, []
    while o < len(b):
        _num, clen = struct.unpack(">ii", b[o:o + 8])
        o += 8
        c = b[o:o + clen * 2]
        o += clen * 2
        st = struct.unpack("<i", c[:4])[0]
        if st == 0:
            shapes.append([])
            continue
        nparts, npts = struct.unpack("<ii", c[36:44])
        parts = list(struct.unpack(f"<{nparts}i", c[44:44 + 4 * nparts])) + [npts]
        start = 44 + 4 * nparts
        pts = np.frombuffer(c, dtype="<f8", count=2 * npts, offset=start).reshape(-1, 2)
        shapes.append([pts[parts[k]:parts[k + 1]].copy() for k in range(nparts)])
    return shapes


# --- geometry helpers ----------------------------------------------------------

def signed_area(ring: np.ndarray) -> float:
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def point_in_ring(pt, ring: np.ndarray) -> bool:
    x, y = pt
    xs, ys = ring[:, 0], ring[:, 1]
    xj, yj = np.roll(xs, 1), np.roll(ys, 1)
    cross = (ys > y) != (yj > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xint = (xj - xs) * (y - ys) / (yj - ys) + xs
    return bool(np.count_nonzero(cross & (x < xint)) % 2)


def douglas_peucker(pts: np.ndarray, tol: float) -> np.ndarray:
    """Iterative Douglas-Peucker on an open polyline; endpoints always kept."""
    n = len(pts)
    if n <= 2:
        return pts
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]
        seg = pts[i + 1:j]
        d = b - a
        norm = np.hypot(d[0], d[1])
        if norm == 0:
            dist = np.hypot(seg[:, 0] - a[0], seg[:, 1] - a[1])
        else:
            dist = np.abs(d[0] * (seg[:, 1] - a[1]) - d[1] * (seg[:, 0] - a[0])) / norm
        k = int(np.argmax(dist))
        if dist[k] > tol:
            m = i + 1 + k
            keep[m] = True
            stack.append((i, m))
            stack.append((m, j))
    return pts[keep]


# --- topology-aware simplification -----------------------------------------------

def simplify_rings(all_rings: list[np.ndarray], tol: float) -> list[np.ndarray | None]:
    """Simplify every ring, sharing the result for arcs two rings have in common."""
    # Drop the closing duplicate; work on open vertex lists.
    opened = []
    for r in all_rings:
        if len(r) > 1 and np.array_equal(r[0], r[-1]):
            r = r[:-1]
        opened.append(r)

    keys = [[(int(round(x / SNAP)), int(round(y / SNAP))) for x, y in r] for r in opened]

    # Which rings touch each vertex.
    owners: dict[tuple, set] = {}
    for ri, ks in enumerate(keys):
        for k in ks:
            owners.setdefault(k, set()).add(ri)

    arc_cache: dict[tuple, list] = {}
    out: list[np.ndarray | None] = []
    for ri, (ring, ks) in enumerate(zip(opened, keys)):
        n = len(ks)
        if n < 3:
            out.append(None)
            continue
        sets = [frozenset(owners[k]) for k in ks]
        nodes = [i for i in range(n)
                 if sets[i] != sets[i - 1] or sets[i] != sets[(i + 1) % n] or len(sets[i]) > 2]
        if not nodes:
            # Island ring (no neighbours): anchor on vertex 0 and the vertex
            # farthest from it so DP has two fixed ends to work between.
            far = int(np.argmax(np.hypot(*(ring - ring[0]).T)))
            nodes = sorted({0, far})
            if len(nodes) == 1:
                out.append(None)
                continue
        kept: list[int] = []
        for a_idx, start in enumerate(nodes):
            end = nodes[(a_idx + 1) % len(nodes)]
            idx = list(range(start, end + 1)) if end > start else list(range(start, n)) + list(range(0, end + 1))
            arc_keys = tuple(ks[i] for i in idx)
            rev = arc_keys[::-1]
            canonical, flipped = (arc_keys, False) if arc_keys <= rev else (rev, True)
            if canonical not in arc_cache:
                c_idx = idx[::-1] if flipped else idx
                pts = ring[c_idx]
                simp = douglas_peucker(pts, tol)
                arc_cache[canonical] = [tuple(p) for p in simp]
            simp_pts = arc_cache[canonical]
            if flipped:
                simp_pts = simp_pts[::-1]
            kept.extend(simp_pts[:-1])          # drop end; it starts the next arc
        if len(kept) < 3:
            out.append(None)
            continue
        arr = np.asarray(kept)
        out.append(np.vstack([arr, arr[:1]]))   # re-close
    return out


def assemble(rings: list[np.ndarray]) -> list[list[np.ndarray]]:
    """Group shapefile rings into polygons: outer rings (clockwise in the
    shapefile spec) each with the holes that fall inside them."""
    outers, holes = [], []
    for r in rings:
        (outers if signed_area(r) < 0 else holes).append(r)
    if not outers:                     # some writers ignore the winding rule
        outers, holes = holes, []
    polys = [[o] for o in outers]
    for h in holes:
        for p in polys:
            if point_in_ring(h[0], p[0]):
                p.append(h)
                break
    return polys


def to_geojson_ring(ring: np.ndarray, outer: bool) -> list:
    # RFC 7946: exterior counter-clockwise, holes clockwise.
    ccw = signed_area(ring) > 0
    if ccw != outer:
        ring = ring[::-1]
    return [[round(float(x), OUT_DECIMALS), round(float(y), OUT_DECIMALS)] for x, y in ring]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shp", type=Path, default=DEFAULT_SHP)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--tolerance", type=float, default=0.0008,
                    help="Douglas-Peucker tolerance in degrees (default 0.0008, ~90 m)")
    args = ap.parse_args(argv)

    shp = args.shp
    if not shp.exists():
        print(f"shapefile not found: {shp}", file=sys.stderr)
        return 1
    cpg = shp.with_suffix(".cpg")
    encoding = cpg.read_text().strip() if cpg.exists() else "utf-8"
    records = read_dbf(shp.with_suffix(".dbf"), encoding=encoding)
    shapes = read_shp_polygons(shp)
    if len(records) != len(shapes):
        print(f"record count mismatch: {len(records)} dbf vs {len(shapes)} shp", file=sys.stderr)
        return 1

    flat, owner = [], []
    for si, rings in enumerate(shapes):
        for r in rings:
            flat.append(r)
            owner.append(si)
    n_in = sum(len(r) for r in flat)
    simplified = simplify_rings(flat, args.tolerance)

    per_shape: dict[int, list[np.ndarray]] = {}
    for si, r in zip(owner, simplified):
        if r is not None and abs(signed_area(r)) > 0:
            per_shape.setdefault(si, []).append(r)

    features, n_out, dropped = [], 0, 0
    for si, rec in enumerate(records):
        rings = per_shape.get(si)
        if rec is None or not rings:
            dropped += 1
            continue
        polys = assemble(rings)
        coords = [[to_geojson_ring(p[0], True)] + [to_geojson_ring(h, False) for h in p[1:]]
                  for p in polys]
        n_out += sum(len(r) for p in coords for r in p)
        geom = ({"type": "Polygon", "coordinates": coords[0]} if len(coords) == 1
                else {"type": "MultiPolygon", "coordinates": coords})
        features.append({
            "type": "Feature",
            "properties": {
                "province": rec.get("Province", ""),
                "zone": rec.get("ZS", ""),
                "area": rec.get("AS_", ""),
                "pcode": rec.get("PCODE", ""),
            },
            "geometry": geom,
        })

    fc = {
        "type": "FeatureCollection",
        "_source": shp.name,
        "_tolerance_deg": args.tolerance,
        "features": features,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size_mb = args.out.stat().st_size / 1e6
    print(f"{len(features)} health areas written to {args.out} ({size_mb:.1f} MB); "
          f"vertices {n_in:,} -> {n_out:,}; {dropped} records without usable geometry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
