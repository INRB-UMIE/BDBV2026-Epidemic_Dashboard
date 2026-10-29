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
# Pipe-delimited FASTA tip label. Quotes are excluded so a closing ' cannot be
# absorbed into the collection date (that is what collapsed quoted trees to a
# handful of PearTree leaves).
_PIPE_TIP_BODY = r"[\w-]+\|PP_[\w.]+(?:\|[^,\):&\[\]'\"]+)*"
# BEAST drops disagree on quoting. Older files leave the label bare and put the
# annotation immediately after it:
#   id|PP_acc|DRC|province|zone|date[&rate=...]
# full.n982 (2026-10-19) quotes the label and leaves the annotation outside:
#   'id|PP_acc|DRC|province|zone|date'[&rate=...]
_QUOTED_TIP_RE = re.compile(rf"'({_PIPE_TIP_BODY})'")
_TIP_NAME_RE = re.compile(
    rf"({_PIPE_TIP_BODY})"
    r"(\[(?:[^\]]|\[[^\]]*\])*\])?"
)
# ``full.n982.GTR_SG.hipstr.tree`` / ``..._n778.GTR...`` — the n-count is how
# many tips the file claims to contain. ``hipstr_0062`` is not an n-count.
_FILENAME_TIP_COUNT_RE = re.compile(r"(?:^|[._])n(\d+)(?=[._]|$)")
# PearTree's Newick tokenizer (bundle function Gl). Leaf count with this split
# is the number of tips the genomic tab actually draws.
_PEARTREE_TOKEN_RE = re.compile(
    r"""\s*('[^']*'|"[^"]*"|;|\(|\)|,|:|=|\[&|\]|\{|\})\s*"""
)
# A closing label-quote left inside the date, or a date annotation still
# wrapped in the label quotes. Either one makes PearTree end the taxon name
# before the health-zone annotation.
_BROKEN_DATE_QUOTE_RE = re.compile(r'\[&date="[^"]*\'')
_DATE_INSIDE_QUOTE_RE = re.compile(r"'[^'\r\n]*\[&date=")
_HEIGHT_MEDIAN_RE = re.compile(r"height_median=([0-9.eE+-]+)")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YM_DATE_RE = re.compile(r"^\d{4}-\d{2}$")
# TreeAnnotator emits ``height_95.0%_HPD``; PearTree's node-bar schema only
# groups suffixes matching ``_95%_HPD`` (no decimal). Rewrite so bars bind to
# the 95% height HPD interval from the input tree.
_HPD_PCT_DOT_ZERO_RE = re.compile(r"_(\d+)\.0%_HPD\b")

# Prefer EGC trees when present; otherwise SG / hipstrCA / any .tree.
# Dated BEAST drops (outputs/beast/<date>/) increasingly ship the display tree
# alongside Ne curves, so callers may pass both PHYLOGENIES_DIR and BEAST_NE_DIR.
_TREE_GLOBS = (
    "*GTR_EGC*.hipstr.tree",
    "*EGC*.hipstr.tree",
    "*GTR_EGC*.HIPSTR.tree",
    "*EGC*.HIPSTR.tree",
    "*GTR_EGC*.tree",
    "*EGC*.tree",
    "*SG*.hipstrCA.tree",
    "*SG*.hipstr.tree",
    "*hipstrCA.tree",
    "*.hipstr.tree",
    "*.HIPSTR.tree",
    "*.tree",
)


def _preferred_tree_in(folder: Path) -> Path | None:
    for pattern in _TREE_GLOBS:
        matches = sorted(folder.glob(pattern))
        if matches:
            return matches[0]
    return None


def resolve_latest_phylogeny_tree(*dirs: Path) -> Path | None:
    """Return the preferred ``.tree`` from the newest ``YYYY-MM-DD`` folder.

    Searches each directory root independently (typically ``data/phylogenies``
    and ``outputs/beast``). Folder *names* decide recency — the newest date
    that contains a usable tree wins, regardless of which root it lives under.
    """
    candidates: list[tuple[str, Path]] = []
    for raw in dirs:
        if raw is None:
            continue
        base = Path(raw)
        if not base.is_dir():
            continue
        for folder in base.iterdir():
            if not (folder.is_dir() and _DATE_DIR_RE.match(folder.name)):
                continue
            tree = _preferred_tree_in(folder)
            if tree is not None:
                candidates.append((folder.name, tree))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def _classify_tip_names(raw: str) -> str:
    """Return ``quoted``, ``bare``, ``mixed``, or ``none`` for pipe-delimited tips.

    A label is quoted only when single quotes wrap the whole pipe-delimited
    name. Shorter matches inside that name are not a second, bare label.
    """
    quoted = 0
    quoted_name_at: set[int] = set()
    for match in _QUOTED_TIP_RE.finditer(raw):
        quoted += 1
        quoted_name_at.add(match.start(1))
    bare = 0
    for match in _TIP_NAME_RE.finditer(raw):
        if match.start(1) in quoted_name_at:
            continue
        if match.start() > 0 and raw[match.start() - 1] == "'":
            continue
        bare += 1
    if quoted and bare:
        return "mixed"
    if quoted:
        return "quoted"
    if bare:
        return "bare"
    return "none"


def _unwrap_quoted_tips(raw: str) -> str:
    """Drop the single quotes around pipe-delimited tip labels.

    The BEAST annotation that follows the closing quote (``'name'[&rate=...]``)
    is left in place so the existing rewrite can consume it.
    """
    return _QUOTED_TIP_RE.sub(r"\1", raw)


def tip_count_from_filename(filename: str) -> int | None:
    """Return the ``n<tips>`` count declared in a tree filename, if present."""
    matches = _FILENAME_TIP_COUNT_RE.findall(Path(filename).name)
    if not matches:
        return None
    return int(matches[-1])


def count_displayed_tips(nexus: str) -> int:
    """Count leaves PearTree's Newick tokenizer would draw from ``nexus``.

    Mirrors the bundle's ``Gl`` splitter: single- and double-quoted runs are
    atomic tokens, and ``[&...]`` comments (including ``{...}`` sets) are not
    tree structure. A rewritten tree that still has a stray quote inside a
    date annotation collapses here, which is the failure this count is for.
    """
    newick = ""
    for line in nexus.splitlines():
        start = line.find("(")
        if start != -1:
            newick = line[start:]
            break
    if not newick:
        raise ValueError("no Newick tree found")

    tokens = [tok for tok in _PEARTREE_TOKEN_RE.split(newick) if tok]
    level = 0
    node: dict | None = None
    stack: list[dict] = []
    after_close = False
    expect_length = False
    in_annotation = False
    expect_key = True
    ann_key: str | None = None
    in_set = False

    for tok in tokens:
        if in_annotation:
            if tok == "=":
                expect_key = False
            elif tok == ",":
                if not in_set:
                    expect_key = True
            elif tok == "{":
                in_set = True
                if node is not None and ann_key is not None:
                    node.setdefault("annotations", {})[ann_key] = []
            elif tok == "}":
                in_set = False
            elif tok == "]":
                in_annotation = False
                expect_key = True
            else:
                value = tok
                if value[:1] in "\"'":
                    value = value[1:]
                if value[-1:] in "\"'":
                    value = value[:-1]
                if node is None:
                    continue
                annotations = node.setdefault("annotations", {})
                if expect_key:
                    ann_key = value.replace(".", "_", 1)
                elif in_set and ann_key is not None:
                    bucket = annotations.setdefault(ann_key, [])
                    if isinstance(bucket, list):
                        bucket.append(value)
                elif ann_key is not None:
                    annotations[ann_key] = value
            continue
        if tok == "(":
            child: dict = {"children": [], "annotations": {}}
            level += 1
            if node is not None:
                stack.append(node)
            node = child
            after_close = False
        elif tok == ",":
            after_close = False
            parent = stack.pop()
            parent["children"].append(node)
            node = parent
        elif tok == ")":
            after_close = False
            parent = stack.pop()
            parent["children"].append(node)
            level -= 1
            node = parent
            after_close = True
        elif tok == ":":
            after_close = False
            expect_length = True
        elif tok == ";":
            if level > 0:
                raise ValueError(f"unbalanced brackets (depth {level})")
            break
        elif tok == "[&":
            in_annotation = True
            expect_key = True
            in_set = False
        elif expect_length:
            expect_length = False
        elif after_close:
            after_close = False
        else:
            if node is not None:
                node.setdefault("children", [])
                stack.append(node)
            node = {"name": tok, "children": [], "annotations": {}}
    if level > 0:
        raise ValueError(f"unbalanced brackets at end of tree (depth {level})")
    if node is None:
        return 0

    leaves = 0
    pending = [node]
    while pending:
        current = pending.pop()
        kids = current.get("children") or []
        if kids:
            pending.extend(kids)
        else:
            leaves += 1
    return leaves


def _parse_fasta_header(name: str) -> tuple[str, str, str]:
    """Parse a pipe-delimited tip name → (accession, health_zone, date_raw)."""
    name = name.strip().strip("'\"").strip()
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


def _assert_tip_quotes_readable(tree_path: Path, nexus: str, quoting: str) -> None:
    """Reject a rewritten tree whose quotes PearTree cannot read as labels.

    This does not depend on an ``n<count>`` token in the filename. A tree with
    no tip count in its name is still imported only when its quotation marks
    leave each date annotation outside the taxon name.
    """
    if _BROKEN_DATE_QUOTE_RE.search(nexus) or _DATE_INSIDE_QUOTE_RE.search(nexus):
        raise ValueError(
            f"{tree_path.name}: tip quotation marks cannot be read "
            f"(tip names were {quoting})"
        )


def _require_displayed_tip_count(tree_path: Path, nexus: str, extracted: int, quoting: str) -> int:
    """Fail the build if quotes are unreadable or the rewrite drops tips.

    A filename ``n<count>`` token is checked against the drawn tip count only
    when that token is present. Trees whose names do not declare a tip count
    are still imported, after the quotation-mark check.
    """
    _assert_tip_quotes_readable(tree_path, nexus, quoting)
    try:
        displayed = count_displayed_tips(nexus)
    except ValueError as exc:
        raise ValueError(
            f"{tree_path.name}: rewritten tree is not readable "
            f"(tip names were {quoting}): {exc}"
        ) from exc
    # Fewer leaves than labels means the rewrite broke Newick (the quoted-date
    # failure mode). That check does not depend on the filename.
    if displayed < extracted:
        raise ValueError(
            f"{tree_path.name}: PearTree would display {displayed} tips "
            f"but {extracted} tip labels were read (tip names were {quoting})"
        )
    declared = tip_count_from_filename(tree_path.name)
    if declared is not None and displayed != declared:
        raise ValueError(
            f"{tree_path.name}: filename declares n{declared} tips "
            f"but {displayed} tips would be displayed (tip names were {quoting})"
        )
    return displayed


def prepare_phylo_tree_products(tree_path: Path) -> dict:
    """Read a raw phylo ``.tree`` and return dashboard-ready tree/tips/meta.

    Quoted and bare pipe-delimited tip labels are both accepted. Quoted labels
    are unwrapped before annotation rewrite so PearTree does not treat the
    closing quote as the end of the taxon name. The rewritten tree is always
    checked for readable quotation marks. When the filename says ``n<N>``, the
    drawn tip count is checked against that number as well.
    """
    raw = tree_path.read_text(encoding="utf-8")
    quoting = _classify_tip_names(raw)
    if quoting in ("quoted", "mixed"):
        raw = _unwrap_quoted_tips(raw)
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
    # Map BEAST ``height_95.0%_HPD`` (and siblings like ``height_50.0%_HPD``)
    # onto PearTree's expected ``_95%_HPD`` / ``_50%_HPD`` suffix form. Node
    # bars read ``annotationSchema.get("height").group.hpd``, which only
    # resolves when the key ends with ``_95%_HPD``.
    tree = _HPD_PCT_DOT_ZERO_RE.sub(r"_\1%_HPD", tree)
    # PearTree accepts both casings; normalise to the producer convention.
    if "BEGIN TREES" not in tree and "Begin trees" in tree:
        tree = tree.replace("Begin trees;", "BEGIN TREES;").replace("End;", "END;")

    displayed = _require_displayed_tip_count(tree_path, tree, len(tips), quoting)
    declared = tip_count_from_filename(tree_path.name)
    declared_note = f", filename n{declared}" if declared is not None else ""
    print(f"  genomic tip names ({quoting}): {displayed} displayed{declared_note}")
    meta = {
        "mostRecentDate": most_recent,
        "rootDate": root_date,
        "sourceTree": tree_path.name,
        "updated": folder_date or tree_path.stat().st_mtime,
        "tipCount": displayed,
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
