"""Convert BEAST Ne trajectory exports into dashboard SkyGrid / exponential JSON.

Source layout (BDBV2026-Phylogenetic_Analyses)::

    outputs/beast/<YYYY-MM-DD>/*.ne.txt   # Tracer-style Ne tables (preferred)
    outputs/beast/<YYYY-MM-DD>/*skygrid*.tsv  # legacy SkyGrid summary tables

The latest dated folder that contains at least one convertible file is used.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

_DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def resolve_latest_beast_ne_dir(beast_dir: Path) -> Path | None:
    """Newest ``YYYY-MM-DD`` folder under ``outputs/beast`` with convertible Ne files."""
    base = Path(beast_dir)
    if not base.is_dir():
        return None
    dated = sorted(
        p for p in base.iterdir()
        if p.is_dir() and _DATE_DIR_RE.match(p.name) and _folder_has_ne(p)
    )
    return dated[-1] if dated else None


def _folder_has_ne(folder: Path) -> bool:
    return bool(list(folder.glob("*.ne.txt")) or list(folder.glob("*skygrid*.tsv")))


def _classify_ne_file(path: Path, header_line: str = "") -> str | None:
    """Return ``skygrid`` / ``exponential`` / None from filename + optional title row."""
    name = path.name.lower()
    title = (header_line or "").lower()
    if "skygrid" in title or "skygrid" in name or re.search(r"(^|[._-])sg([._-]|$)", name):
        if "growthrate" in name and "ne_trajectory" not in name and path.suffix == ".tsv":
            return None  # growth-rate summary, not an Ne curve
        return "skygrid"
    if (
        "exponential" in title
        or "egc" in name
        or "growthrate_ne_trajectory" in name
        or re.search(r"(^|[._-])exp([._-]|$)", name)
    ):
        return "exponential"
    return None


def _parse_ne_txt(path: Path) -> dict | None:
    """Parse Tracer-style ``*.ne.txt`` into a dashboard Ne product."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) < 2:
        return None
    title = lines[0].strip()
    # Find the header row (time/date/median/…)
    header_idx = None
    for i, line in enumerate(lines[:5]):
        cols = [c.strip().lower() for c in line.split("\t")]
        if "date" in cols and ("median" in cols or "mean" in cols):
            header_idx = i
            break
    if header_idx is None:
        return None
    reader = csv.DictReader(io.StringIO("\n".join(lines[header_idx:])), delimiter="\t")
    points = []
    for row in reader:
        date = (row.get("date") or "").strip()
        if not _ISO_DATE_RE.match(date):
            continue
        try:
            med = float(row.get("median") or row.get("mean") or "")
            lo = float(row.get("lower") or "")
            hi = float(row.get("upper") or "")
        except (TypeError, ValueError):
            continue
        points.append({
            "date": date,
            "neMedian": med,
            "neLower": lo,
            "neUpper": hi,
            "tBP": None,
        })
    if not points:
        return None
    # Newest first in BEAST exports; sort ascending for plotting.
    points.sort(key=lambda p: p["date"])
    most_recent = points[-1]["date"]
    root = points[0]["date"]
    # tBP = years before most-recent tip (matches Genomic_Epi convention).
    from datetime import datetime
    mr = datetime.strptime(most_recent, "%Y-%m-%d")
    for p in points:
        d = datetime.strptime(p["date"], "%Y-%m-%d")
        p["tBP"] = round((mr - d).days / 365.25, 6)
    kind = _classify_ne_file(path, title)
    return {
        "model": "skygrid" if kind == "skygrid" else "exponential",
        "mostRecentDate": most_recent,
        "rootDate": root,
        "gridPoints": len(points),
        "sourceFile": path.name,
        "points": points,
    }


def _parse_skygrid_tsv(path: Path) -> dict | None:
    """Parse legacy ``*skygrid*.tsv`` summary tables into a SkyGrid product."""
    text = path.read_text(encoding="utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    points = []
    for row in reader:
        date = (row.get("date") or "").strip()
        if not _ISO_DATE_RE.match(date):
            continue
        try:
            med = float(row.get("median") or "")
            lo = float(row.get("lower_95_hpd") or row.get("lower_95_qi") or "")
            hi = float(row.get("upper_95_hpd") or row.get("upper_95_qi") or "")
        except (TypeError, ValueError):
            continue
        tbp_raw = row.get("time_into_past")
        try:
            tbp = float(tbp_raw) if tbp_raw not in (None, "") else None
        except ValueError:
            tbp = None
        points.append({
            "date": date,
            "neMedian": med,
            "neLower": lo,
            "neUpper": hi,
            "tBP": tbp,
        })
    if not points:
        return None
    points.sort(key=lambda p: p["date"])
    return {
        "model": "skygrid",
        "mostRecentDate": points[-1]["date"],
        "rootDate": points[0]["date"],
        "gridPoints": len(points),
        "sourceFile": path.name,
        "points": points,
    }


def load_beast_ne_products(beast_dir: Path | None = None) -> dict:
    """Load SkyGrid + exponential Ne products from the latest beast output folder.

    Returns ``{}`` when absent. On success includes ``skygrid`` and/or
    ``exponential`` plus ``ne_folder_date`` / ``ne_source_dir``.
    """
    base = Path(beast_dir) if beast_dir is not None else None
    if base is None:
        return {}
    folder = resolve_latest_beast_ne_dir(base)
    if folder is None:
        return {}

    products: dict = {
        "ne_folder_date": folder.name,
        "ne_source_dir": str(folder),
    }
    # Prefer *.ne.txt; fall back to legacy skygrid TSV only if SG missing.
    for path in sorted(folder.glob("*.ne.txt")):
        title = path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
        kind = _classify_ne_file(path, title[0] if title else "")
        if kind is None or kind in products:
            continue
        parsed = _parse_ne_txt(path)
        if parsed:
            products[kind] = parsed

    if "skygrid" not in products:
        for path in sorted(folder.glob("*skygrid*.tsv")):
            if "growthrate" in path.name.lower() and "ne_trajectory" not in path.name.lower():
                continue
            if _classify_ne_file(path) != "skygrid":
                continue
            parsed = _parse_skygrid_tsv(path)
            if parsed:
                products["skygrid"] = parsed
                break

    if "skygrid" not in products and "exponential" not in products:
        return {}
    return products


def ne_stale_relative_to_tree(ne_folder_date: str | None, tree_folder_date: str | None) -> bool:
    """True when the phylogeny folder date is newer than the Ne drop."""
    if not ne_folder_date or not tree_folder_date:
        return False
    if not (_DATE_DIR_RE.match(ne_folder_date) and _DATE_DIR_RE.match(tree_folder_date)):
        return False
    return tree_folder_date > ne_folder_date
