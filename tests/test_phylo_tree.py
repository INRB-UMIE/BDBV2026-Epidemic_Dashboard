import importlib
import json
from pathlib import Path

phylo = importlib.import_module("common.phylo_tree")
ds = importlib.import_module("common.data_sources")


def _write_raw_tree(dirpath: Path, folder: str, name: str, body: str):
    drop = dirpath / folder
    drop.mkdir(parents=True)
    (drop / name).write_text(body, encoding="utf-8")


def test_resolve_latest_phylogeny_tree_prefers_newest_egc(tmp_path):
    older = "2026-06-07"
    newer = "2026-08-13"
    _write_raw_tree(tmp_path, older, "old.HIPSTR.tree", "#NEXUS\n")
    _write_raw_tree(tmp_path, newer, "Ituri2026.DRC_trimmed_n515.GTRI_SG.hipstrCA.tree", "#NEXUS\n")
    _write_raw_tree(tmp_path, newer, "Ituri2026.DRC_trimmed_n515.GTR_EGC.hipstr.tree", "#NEXUS\n")
    path = phylo.resolve_latest_phylogeny_tree(tmp_path)
    assert path.name == "Ituri2026.DRC_trimmed_n515.GTR_EGC.hipstr.tree"


def test_prepare_phylo_tree_products_adds_dashboard_annotations(tmp_path):
    nexus = (
        "#NEXUS\nBegin trees;\n"
        "tree TREE1 = [&R] (('26FHV045|PP_006XHKB.2|DRC|Ituri|Bunia|2026-05-03':0.1,"
        "'26FHV058|PP_006Y8ME.2|DRC|Ituri|Katwa|2026-05-06':0.2):0.3, "
        "'26FHV046|PP_00711R7.2|DRC|Ituri|Rwampara|2026-05-03':0.4);\nEnd;\n"
    )
    tree_path = tmp_path / "2026-08-13" / "demo.tree"
    tree_path.parent.mkdir(parents=True)
    tree_path.write_text(nexus, encoding="utf-8")
    out = phylo.prepare_phylo_tree_products(tree_path)
    assert len(out["tips"]) == 3
    assert out["tips"][0]["id"] == "PP_006XHKB.2"
    assert out["tips"][0]["health_zone"] == "Bunia"
    assert out["meta"]["tipCount"] == 3
    assert 'health_zone="Bunia"' in out["tree"]
    assert 'accession="PP_006XHKB.2"' in out["tree"]


def test_prepare_phylo_tree_products_maps_beast_height_95_hpd_for_peartree(tmp_path):
    """BEAST TreeAnnotator uses height_95.0%_HPD; PearTree node bars need _95%_HPD."""
    nexus = (
        "#NEXUS\nBegin trees;\n"
        "tree TREE1 = [&R] (('26FHV045|PP_006XHKB.2|DRC|Ituri|Bunia|2026-05-03':0.1,"
        "'26FHV058|PP_006Y8ME.2|DRC|Ituri|Katwa|2026-05-06':0.2)"
        "[&height_mean=0.2,height_median=0.19,height_range={0.1,0.3},"
        "height_50.0%_HPD={0.15,0.22},height_95.0%_HPD={0.12,0.28},"
        "rate_95%_HPD={0.05,0.2}]:0.3);\n"
        "End;\n"
    )
    tree_path = tmp_path / "2026-09-01" / "demo.hipstr.tree"
    tree_path.parent.mkdir(parents=True)
    tree_path.write_text(nexus, encoding="utf-8")
    out = phylo.prepare_phylo_tree_products(tree_path)
    tree = out["tree"]
    assert "height_95.0%_HPD" not in tree
    assert "height_50.0%_HPD" not in tree
    assert "height_95%_HPD={0.12,0.28}" in tree
    assert "height_50%_HPD={0.15,0.22}" in tree
    # Non-``.0`` HPD keys (e.g. rate) are already PearTree-shaped — leave alone.
    assert "rate_95%_HPD={0.05,0.2}" in tree


def test_load_genomic_products_uses_phylo_tree(tmp_path, monkeypatch):
    phylo_dir = tmp_path / "phy"
    gen_dir = tmp_path / "gen"
    nexus = (
        "#NEXUS\nBegin trees;\n"
        "tree TREE1 = [&R] ('26FHV045|PP_006XHKB.2|DRC|Ituri|Bunia|2026-05-03':0.1);\nEnd;\n"
    )
    _write_raw_tree(phylo_dir, "2026-08-13", "Ituri2026.DRC_trimmed_n1.GTR_EGC.hipstr.tree", nexus)
    gen_dir.mkdir()
    (gen_dir / "ituri-tree.ptree").write_text("#NEXUS\nBEGIN TREES;\ntree T = ((A,B),C);\nEND;\n")
    (gen_dir / "ituri-tips.json").write_text(json.dumps([{"id": "A", "health_zone": "Bunia", "date": "2026-05-01"}]))
    (gen_dir / "ituri-meta.json").write_text(json.dumps({"mostRecentDate": "2026-06-23", "updated": "2026-08-12", "tipCount": 1}))
    (gen_dir / "skygrid.json").write_text(json.dumps({"points": [{"date": "2026-06-01", "neMedian": 1, "neLower": 0.5, "neUpper": 2}]}))
    (gen_dir / "exponential.json").write_text(json.dumps({"points": []}))
    monkeypatch.setattr(ds, "PHYLOGENIES_DIR", phylo_dir)
    monkeypatch.setattr(ds, "GENOMIC_DIR", gen_dir)
    monkeypatch.setattr(ds, "BEAST_NE_DIR", tmp_path / "no-beast")
    out = ds.load_genomic_products()
    assert out["tips"][0]["id"] == "PP_006XHKB.2"
    # No BEAST Ne; Genomic_Epi tipCount matches → sidecars attached
    assert out["skygrid"]["points"][0]["neMedian"] == 1


def test_resolve_latest_phylogeny_tree_prefers_newer_beast_folder(tmp_path):
    """Newest dated folder wins even when the tree lives under outputs/beast."""
    phy = tmp_path / "phylogenies"
    beast = tmp_path / "beast"
    _write_raw_tree(phy, "2026-08-13", "Ituri2026.GTR_EGC.hipstr.tree", "#NEXUS\n")
    _write_raw_tree(
        beast, "2026-09-01",
        "Ituri2026.DRC_trimmed.ADAR_masked.final.SG.aln.hipstrCA.tree",
        "#NEXUS\n",
    )
    path = phylo.resolve_latest_phylogeny_tree(phy, beast)
    assert path.parent.name == "2026-09-01"
    assert path.name.endswith("hipstrCA.tree")


def test_load_genomic_products_uses_newer_beast_tree_and_ne(tmp_path, monkeypatch):
    phylo_dir = tmp_path / "phy"
    beast_dir = tmp_path / "beast"
    nexus_old = (
        "#NEXUS\nBegin trees;\n"
        "tree TREE1 = [&R] ('26FHV045|PP_006XHKB.2|DRC|Ituri|Bunia|2026-05-03':0.1);\nEnd;\n"
    )
    nexus_new = (
        "#NEXUS\nBegin trees;\n"
        "tree TREE1 = [&R] ('26FHV999|PP_NEWTIP.1|DRC|Ituri|Mongbwalu|2026-08-01':0.1);\nEnd;\n"
    )
    _write_raw_tree(phylo_dir, "2026-08-13", "Ituri.GTR_EGC.hipstr.tree", nexus_old)
    drop = beast_dir / "2026-09-01"
    drop.mkdir(parents=True)
    (drop / "Ituri.final.SG.aln.hipstrCA.tree").write_text(nexus_new, encoding="utf-8")
    # Minimal SkyGrid Ne in the same newest folder
    (drop / "Ituri.final.SG.aln.ne.txt").write_text(
        "\tBayesian SkyGrid: Ituri.SG.log\t\t\t\n"
        "time\tdate\tdatetime\tmilliseconds\tmean\tmedian\tupper\tlower\n"
        "2026.5\t2026-08-01\t2026-08-01T00:00:00\t0\t2\t2\t4\t1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ds, "PHYLOGENIES_DIR", phylo_dir)
    monkeypatch.setattr(ds, "BEAST_NE_DIR", beast_dir)
    monkeypatch.setattr(ds, "GENOMIC_DIR", tmp_path / "missing-gen")
    out = ds.load_genomic_products()
    assert out["tips"][0]["id"] == "PP_NEWTIP.1"
    assert out["meta"]["updated"] == "2026-09-01"
    assert out["skygrid"]["points"][0]["neMedian"] == 2
    assert out.get("ne_stale") is not True
