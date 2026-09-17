"""Load and normalise HIPSTR/BEAST trees from BDBV2026-Phylogenetic_Analyses.

Raw trees use pipe-delimited FASTA-style tip names (see the phylo repo's
``docs/sequence-naming-convention.md``). The dashboard's PearTree embed expects
NEXUS with ``accession``, ``health_zone``, and ``date`` annotations on each tip,
plus companion ``tips`` / ``meta`` JSON-like structures in the payload.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

_DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIP_NAME_RE = re.compile(
    r"([\w-]+\|PP_[\w.]+(?:\|[^,\):&\[]+)*)"
    r"(\[(?:[^\]]|\[[^\]]*\])*\])?"
)
_HEIGHT_MEDIAN_RE = re.compile(r"height_median=([0-9.eE+-]+)")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YM_DATE_RE = re.compile(r"^\d{4}-\d{2}$")

# Prefer the EGC tree in each dated drop (matches the dashboard's historical default).
_TREE_GLOBS = (
    "*GTR_EGC*.hipstr.tree",
    "*EGC*.hipstr.tree",
    "*GTR_EGC*.HIPSTR.tree",
    "*EGC*.HIPSTR.tree",
    "*GTR_EGC*.tree",
    "*EGC*.tree",
    "*.tree",
)


def resolve_latest_phylogeny_tree(phylogenies_dir: Path) -> Path | None:
    """Return the preferred ``.tree`` file from the newest ``YYYY-MM-DD`` folder."""
    base = Path(phylogenies_dir)
    if not base.is_dir():
        return None
    dated = sorted(
        p for p in base.iterdir()
        if p.is_dir() and _DATE_DIR_RE.match(p.name)
    )
    if not dated:
        return None
    latest = dated[-1]
    for pattern in _TREE_GLOBS:
        matches = sorted(latest.glob(pattern))
        if matches:
            return matches[0]
    return None


def _parse_fasta_header(name: str) -> tuple[str, str, str]:
    """Parse a pipe-delimited tip name → (accession, health_zone, date_raw)."""
    parts = name.split("|")
    if len(parts) >= 6:
        return parts[1].strip(), parts[4].strip(), parts[-1].strip()
    if len(parts) >= 5:
        return parts[1].strip(), parts[3].strip(), parts[-1].strip()
    return name.strip(), "", ""


def _normalise_tip_date(raw: str) -> str:
    raw = (raw or "").strip()
    if _ISO_DATE_RE.match(raw):
        return raw
    if _YM_DATE_RE.match(raw):
        return f"{raw}-01"
    return raw


def _infer_meta_dates(raw_nexus: str, tip_dates: list[str]) -> tuple[str, str]:
    """Infer ``(rootDate, mostRecentDate)`` ISO strings for the payload meta."""
    iso_dates = sorted(d for d in tip_dates if _ISO_DATE_RE.match(d))
    if not iso_dates:
        return "", ""
    most_recent = iso_dates[-1]
    heights = [float(x) for x in _HEIGHT_MEDIAN_RE.findall(raw_nexus)]
    if heights:
        present = datetime.strptime(most_recent, "%Y-%m-%d")
        root = present - timedelta(days=max(heights) * 365.25)
        return root.strftime("%Y-%m-%d"), most_recent
    return iso_dates[0], most_recent


def prepare_phylo_tree_products(tree_path: Path) -> dict:
    """Read a raw phylo ``.tree`` and return dashboard-ready tree/tips/meta."""
    raw = tree_path.read_text(encoding="utf-8")
    folder_date = tree_path.parent.name if _DATE_DIR_RE.match(tree_path.parent.name) else ""

    tips: list[dict] = []
    tip_meta_by_name: dict[str, dict] = {}
    for match in _TIP_NAME_RE.finditer(raw):
        full_name = match.group(1)
        if full_name in tip_meta_by_name:
            continue
        accession, health_zone, date_raw = _parse_fasta_header(full_name)
        date = _normalise_tip_date(date_raw)
        tip = {
            "id": accession,
            "date": date,
            "location": health_zone,
            "health_zone": health_zone,
            "health_area": None,
            "exported": False,
        }
        tips.append(tip)
        tip_meta_by_name[full_name] = tip

    if not tips:
        return {}

    root_date, most_recent = _infer_meta_dates(raw, [t["date"] for t in tips])

    def _replace_tip(match: re.Match) -> str:
        full_name = match.group(1)
        tip = tip_meta_by_name.get(full_name)
        if not tip:
            return match.group(0)
        acc = tip["id"]
        zone = tip["health_zone"].replace('"', "")
        date = tip["date"].replace('"', "")
        return (
            f'{acc}[&date="{date}",accession="{acc}",location="{zone}",'
            f'health_zone="{zone}"]'
        )

    tree = _TIP_NAME_RE.sub(_replace_tip, raw)
    # PearTree accepts both casings; normalise to the producer convention.
    if "BEGIN TREES" not in tree and "Begin trees" in tree:
        tree = tree.replace("Begin trees;", "BEGIN TREES;").replace("End;", "END;")

    meta = {
        "mostRecentDate": most_recent,
        "rootDate": root_date,
        "sourceTree": tree_path.name,
        "updated": folder_date or tree_path.stat().st_mtime,
        "tipCount": len(tips),
    }
    if isinstance(meta["updated"], float):
        meta["updated"] = datetime.fromtimestamp(meta["updated"]).strftime("%Y-%m-%d")

    return {
        "tree": tree,
        "tips": tips,
        "meta": meta,
        "data_build_date": meta["updated"],
        "source_phylo_tree": str(tree_path),
    }
