import importlib
from pathlib import Path

beast = importlib.import_module("common.beast_ne")
ds = importlib.import_module("common.data_sources")


def _write_ne_txt(folder: Path, name: str, title: str, rows: list[tuple]):
    folder.mkdir(parents=True, exist_ok=True)
    lines = [
        f"\t{title}\t\t\t",
        "time\tdate\tdatetime\tmilliseconds\tmean\tmedian\tupper\tlower",
    ]
    for time, date, mean, median, upper, lower in rows:
        lines.append(
            f"{time}\t{date}\t{date}T00:00:00\t0\t{mean}\t{median}\t{upper}\t{lower}"
        )
    (folder / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_resolve_latest_beast_ne_dir(tmp_path):
    old = tmp_path / "2026-07-10"
    new = tmp_path / "2026-08-17"
    _write_ne_txt(
        old, "old.SG.ne.txt", "Bayesian SkyGrid: old.log",
        [(2026.1, "2026-06-01", 1, 1, 2, 0.5)],
    )
    _write_ne_txt(
        new, "new.SG.ne.txt", "Bayesian SkyGrid: new.log",
        [(2026.2, "2026-08-01", 2, 2, 3, 1)],
    )
    assert beast.resolve_latest_beast_ne_dir(tmp_path).name == "2026-08-17"


def test_load_beast_ne_products_sg_and_egc(tmp_path):
    folder = tmp_path / "2026-08-17"
    _write_ne_txt(
        folder, "Ituri.GTRI_SG.ne.txt", "Bayesian SkyGrid: Ituri.SG.log",
        [
            (2026.1, "2026-01-01", 0.1, 0.1, 1.0, 0.01),
            (2026.5, "2026-08-01", 8.0, 7.0, 20.0, 1.0),
        ],
    )
    _write_ne_txt(
        folder, "Ituri.GTRI_EGC.ne.txt", "Exponential Growth: Ituri.EGC.log",
        [
            (2026.1, "2026-01-01", 0.2, 0.2, 0.5, 0.05),
            (2026.5, "2026-08-01", 30.0, 28.0, 50.0, 15.0),
        ],
    )
    out = beast.load_beast_ne_products(tmp_path)
    assert out["ne_folder_date"] == "2026-08-17"
    assert out["skygrid"]["points"][0]["date"] == "2026-01-01"
    assert out["skygrid"]["points"][-1]["neMedian"] == 7.0
    assert out["exponential"]["points"][-1]["neUpper"] == 50.0


def test_ne_stale_note_when_tree_newer():
    note = beast.ne_stale_relative_to_tree("2026-08-01", "2026-08-13")
    assert note and "do not correspond" in note
    assert beast.ne_stale_relative_to_tree("2026-08-17", "2026-08-13") is None


def test_load_genomic_products_uses_beast_ne(tmp_path, monkeypatch):
    phylo_dir = tmp_path / "phy"
    beast_dir = tmp_path / "beast"
    drop = phylo_dir / "2026-08-20"
    drop.mkdir(parents=True)
    (drop / "Ituri.GTR_EGC.hipstr.tree").write_text(
        "#NEXUS\nBegin trees;\n"
        "tree TREE1 = [&R] ('26FHV045|PP_006XHKB.2|DRC|Ituri|Bunia|2026-05-03':0.1);\n"
        "End;\n",
        encoding="utf-8",
    )
    _write_ne_txt(
        beast_dir / "2026-08-10",
        "Ituri.GTRI_SG.ne.txt",
        "Bayesian SkyGrid: Ituri.SG.log",
        [(2026.4, "2026-06-01", 2, 2, 4, 1)],
    )
    monkeypatch.setattr(ds, "PHYLOGENIES_DIR", phylo_dir)
    monkeypatch.setattr(ds, "BEAST_NE_DIR", beast_dir)
    monkeypatch.setattr(ds, "GENOMIC_DIR", tmp_path / "missing-gen")
    out = ds.load_genomic_products()
    assert out["skygrid"]["points"][0]["neMedian"] == 2
    assert out.get("ne_stale_note")  # tree folder 2026-08-20 > Ne 2026-08-10
