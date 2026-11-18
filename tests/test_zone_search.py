"""Static guards for the unified health-zone search component.

The search is one DOM node (common/chrome.py) shared by every view, positioned
by dashboard.css per body.view-* and driven by ZONE_SEARCH_VIEWS in engine.js.
Nothing at runtime checks that those three stay in agreement, so these tests do.

See docs/superpowers/specs/2026-08-14-unified-zone-search-design.md.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHROME = REPO / "Scripts" / "common" / "chrome.py"
ENGINE = REPO / "Scripts" / "assets" / "engine.js"
CSS = REPO / "Scripts" / "assets" / "dashboard.css"

# Views that render a real map + search. Kept as a literal rather than imported
# so a mistake in chrome.NAV_ITEMS cannot make this test agree with itself.
NON_STUB_VIEWS = ["map", "trends", "epi-trends", "context", "genomic-epidemiology"]

# Search boxes replaced by the single component. None may come back.
RETIRED_IDS = [
    "zone-search-wrap",
    "trends-search-input",
    "trends-search-results",
    "trends-search-wrap",
    "trends-search-slot",
    "epi-search-input",
    "epi-search-results",
    "epi-search-wrap",
]


def _chrome():
    return CHROME.read_text(encoding="utf-8")


def _engine():
    return ENGINE.read_text(encoding="utf-8")


def _css():
    """dashboard.css with comments stripped.

    A commented-out rule must not satisfy (or trip) any of these guards --
    that is a silent false pass in exactly the drift they exist to catch.
    """
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.DOTALL)


def test_exactly_one_search_input():
    assert _chrome().count('id="zone-search-input"') == 1


def test_no_retired_search_markup():
    text = _chrome()
    present = [i for i in RETIRED_IDS if i in text]
    assert not present, f"retired search markup still in chrome.py: {present}"


def test_controls_panel_holds_no_search_input():
    """#zone-search must not have been left inside the LAYER panel."""
    text = _chrome()
    start = text.index('<div id="controls"')
    end = text.index('<div id="legend"', start)
    assert 'type="search"' not in text[start:end]


def test_zone_search_is_a_sibling_of_map():
    """Not nested in #controls or any rail -- one node, positioned by CSS."""
    text = _chrome()
    map_at = text.index('<div id="map"></div>')
    search_at = text.index('<div id="zone-search">')
    controls_at = text.index('<div id="controls"')
    assert map_at < search_at < controls_at


def test_retired_css_vocabulary_is_gone():
    """.location-search-* was the light rail vocabulary; it is now the
    component's own styling and the class names go away. .zone-search-option
    is NOT in this list -- it is retained as the new option class."""
    css, engine = _css(), _engine()
    for selector in (".location-search-wrap", ".location-search-results"):
        assert selector not in css, f"{selector} still styled in dashboard.css"
        assert selector not in engine, f"{selector} still referenced in engine.js"


def test_component_has_a_visually_hidden_utility():
    """The live region is announcement-only: it must be in the a11y tree but
    off-screen. A bare substring check would pass on an empty rule."""
    rules = _rules_for(_css(), ".visually-hidden")
    assert rules, ".visually-hidden is not defined in dashboard.css"
    body = rules[0][1].replace(" ", "")
    for decl in ("position:absolute", "width:1px", "height:1px", "overflow:hidden"):
        assert decl in body, f".visually-hidden is missing {decl}"
    assert 'class="visually-hidden"' in _chrome(), "nothing applies .visually-hidden"


# --- CSS structure helpers -------------------------------------------------
# The repo has no CSS parser dependency and this stylesheet nests at most one
# level (@media > rule), so brace-balance walks are enough.

def _media_blocks(css):
    """[(query, body)] for every @media block."""
    blocks = []
    for m in re.finditer(r"(@media[^{]*)\{", css):
        depth, i = 1, m.end()
        while depth and i < len(css):
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
            i += 1
        blocks.append((m.group(1).strip(), css[m.end():i - 1]))
    return blocks


def _band_c(css):
    """The narrow branch. There is more than one max-width:700px block in the
    file, so concatenate them all."""
    return "\n".join(
        body for query, body in _media_blocks(css)
        if query == "@media (max-width: 700px)"
    )


def _band_b(css):
    """The mid branch. Unlike band C there is exactly one such block."""
    return "\n".join(
        body for query, body in _media_blocks(css)
        if query == "@media (max-width: 999.98px)"
    )


def _rules(text):
    """[(selector, body)] for every flat rule. @media headers do not match --
    their bodies contain braces, which the body pattern forbids."""
    return [(m.group(1).strip(), m.group(2)) for m in re.finditer(r"([^{}]*)\{([^{}]*)\}", text)]


def _rules_for(text, target):
    """Rules whose selector list contains exactly `target` as a whole selector
    (so #info matches "#info" and "body.view-x #info", not "#info-body")."""
    out = []
    for selector, body in _rules(text):
        if re.search(rf"(^|[\s,]){re.escape(target)}\s*(,|$)", selector):
            out.append((selector, body))
    return out


def test_stylesheet_nesting_stays_within_helper_assumptions():
    """_rules()/_media_blocks() assume at most one level of nesting
    (@media > rule). Violate that and _rules() silently drops the enclosing
    rule and fabricates a selector from the leftovers -- no error, just wrong
    data, which would make the band assertions below pass vacuously. Fail
    loudly here instead."""
    css = _css()
    assert css.count("{") == css.count("}"), "unbalanced braces in dashboard.css"
    for at_rule in ("@supports", "@keyframes", "@font-face", "@container", "@layer"):
        assert at_rule not in css, (
            f"{at_rule} introduces nesting the CSS test helpers cannot parse; "
            "extend _rules()/_media_blocks() before using it"
        )
    # Native CSS nesting needs no preprocessor and still balances braces, so
    # neither check above sees it. Given `#zone-search { &:hover { ... } }`,
    # _rules() skips the outer rule and matches the INNER block as a flat rule
    # with selector "&:hover" -- dropping #zone-search from the parsed set.
    assert "&" not in css, (
        "native CSS nesting (or a stray &) breaks the flat-rule parser in "
        "_rules(); extend the helpers before using it"
    )


# --token: value;  (comments already stripped by _css())
CSS_DECL = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")

OWNED_TOKENS = ["--layer-panel-width", "--context-panel-width", "--zone-search-height"]


def _root_block():
    """The single :root { ... } declaration block."""
    css = _css()
    start = css.index(":root {")
    return css[start:css.index("}", start)]


def test_tokens_declared_exactly_once_in_root():
    css = _css()
    root = _root_block()
    for token in OWNED_TOKENS:
        declared = [m.group(1) for m in CSS_DECL.finditer(css) if m.group(1) == token]
        assert len(declared) == 1, f"{token} declared {len(declared)} times, expected 1"
        assert token in root, f"{token} is not declared in :root"


def test_search_offset_reads_panel_tokens_only_in_band_a():
    """Band A is the unqualified default; bands B and C are max-width blocks.

    #controls / #context-national read these tokens for their own width in ALL
    bands -- that is correct and unconstrained. The constraint is on the
    CONSUMER: only the band-A search offset may read them.
    """
    for query, body in _media_blocks(_css()):
        for selector, decls in _rules(body):
            if "#zone-search" not in selector:
                continue
            for token in ("--layer-panel-width", "--context-panel-width"):
                assert token not in decls, (
                    f"search offset reads {token} inside {query}: {selector}"
                )


def test_band_a_offsets_sit_beside_the_two_corner_panels():
    """The first #zone-search rule for each of these views is the band-A one
    (bands B and C come later in the file and are grouped selectors). If Task 4
    ever adds a standalone per-view rule in a band-B/C block ABOVE this point,
    this regex matches that instead -- it fails loudly rather than silently,
    since band B/C rules must not contain these tokens, but the fix is to
    anchor the search rather than to relax the assertion."""
    css = _css()
    # Snapshot (view-map) now has a summary rail, so its search takes the map
    # corner and clamps to the visible map like Trends -- it reads the rail
    # width, not the LAYER panel's.
    for view, token in (("map", "--snapshot-panel-width"), ("context", "--context-panel-width")):
        m = re.search(rf"body\.view-{view} #zone-search \{{([^}}]*)\}}", css)
        assert m, f"no band-A #zone-search rule for view-{view}"
        assert token in m.group(1), f"band-A view-{view} offset does not read {token}"


def test_zone_search_positioned_for_every_non_stub_view():
    css = _css()
    for view in NON_STUB_VIEWS:
        assert f"body.view-{view} #zone-search" in css, f"no #zone-search rule for view-{view}"
    assert "body.stub-view #zone-search" in css


# Which panels each band pushes below the search. Band A displaces nothing --
# there the search sits BESIDE the corner panel, not above it. #context-national
# appears only in band B: at <=700px a pre-existing rule already drops it to
# top:clamp(128px, 24vh, 200px), well clear of the search.
DISPLACED_BY_BAND = {
    "band B": ["#controls", "#context-national"],
    "band C": ["#controls", "#info", "#trends-legend", "#epi-trends-legend"],
}

DROP_OFFSET = "calc(12px + var(--zone-search-drop))"


def test_displaced_panels_offset_by_the_drop_token_in_the_right_band():
    """Asserting the offset exists SOMEWHERE would pass for a panel displaced
    in the wrong band -- which is exactly how a band-B max-height leaked into
    band C once already. Anchor each panel to the band that must move it."""
    css = _css()
    bands = {"band B": _band_b(css), "band C": _band_c(css)}
    for band, panels in DISPLACED_BY_BAND.items():
        assert bands[band], f"{band} block not found in dashboard.css"
        for panel in panels:
            rules = _rules_for(bands[band], panel)
            assert rules, f"{panel} has no rule in {band}"
            assert any(DROP_OFFSET in body for _sel, body in rules), (
                f"{panel} must be displaced in {band} but no rule there "
                f"offsets by {DROP_OFFSET}"
            )


def test_nothing_is_displaced_in_band_a():
    """Band A is the unqualified default. An offset leaking into it would push
    the corner panels down on wide screens, where the search sits beside them
    and there is nothing to make room for."""
    css = _css()
    outside = css
    for _query, body in _media_blocks(css):
        outside = outside.replace(body, "")
    # The one deliberate exception: on Snapshot the map shares its width with
    # the summary rail, so the search takes the corner at every width and the
    # LAYER panel drops below it (body.view-map #controls).
    outside = "".join(
        f"{sel}{{{body}}}" for sel, body in _rules(outside)
        if sel.strip() != "body.view-map #controls"
    )
    assert DROP_OFFSET not in outside, (
        "a displacement offset leaked into band A (the unqualified default)"
    )


def test_zone_search_input_reads_the_height_token():
    assert "min-height:var(--zone-search-height)" in _css().replace(" ", "")


def test_zone_search_repositioned_in_band_c():
    """Test 5's per-BAND half: a view positioned only in band A must fail."""
    band_c = _band_c(_css())
    for view in ["map", "context", "trends", "epi-trends"]:
        assert f"body.view-{view} #zone-search" in band_c, (
            f"view-{view} has no band-C #zone-search rule"
        )


def test_genomic_search_hidden_in_band_c():
    band_c = _band_c(_css())
    rules = _rules_for(band_c, "#zone-search")
    genomic = [b for s, b in rules if "genomic-epidemiology" in s]
    assert genomic, "no band-C #zone-search rule for the genomic view"
    assert any("display:none" in b.replace(" ", "") for b in genomic)


def test_zone_search_views_covers_exactly_the_non_stub_views():
    """A tab added later must not silently ship without a search, and a
    removed tab must not leave a dangling entry."""
    engine = _engine()
    start = engine.index("const ZONE_SEARCH_VIEWS = {")
    block = engine[start:engine.index("\n};", start)]
    keys = set(re.findall(r'^\s*"([a-z-]+)":\s*\{', block, flags=re.MULTILINE))
    assert keys == set(NON_STUB_VIEWS), f"ZONE_SEARCH_VIEWS keys {sorted(keys)}"


def test_view_is_read_from_the_body_dataset_not_active_view():
    """bootstrapInitialView() runs at the bottom of engine.js, long after the
    search block, so activeView is still its "map" default there."""
    engine = _engine()
    assert "document.body.dataset.initialView" in engine
    start = engine.index("const ZONE_SEARCH_VIEW_ID =")
    assert "dataset.initialView" in engine[start:start + 200]


def test_no_fitbounds_mixes_padding_with_a_directional_key():
    """Leaflet resolves `paddingBottomRight || padding || [0,0]`, so a
    directional key REPLACES padding on that side instead of adding to it --
    and [0,0] is an array, hence truthy. Mixing them silently drops padding on
    one side, which is invisible in a screenshot unless the fitted geometry
    happens to sit near an edge.
    """
    engine = _engine()
    for call in re.findall(r"fitBounds\((.*?)\n?\s*\}\);", engine, flags=re.DOTALL):
        has_plain = re.search(r"\bpadding\s*:", call)
        has_directional = re.search(r"\bpadding(TopLeft|BottomRight)\s*:", call)
        assert not (has_plain and has_directional), (
            f"fitBounds mixes padding with a directional key:\n{call}"
        )


def test_applystatici18n_dependencies_are_declared_before_the_controller_calls_it():
    """wireZoneSearch() calls applyStaticI18n() during module init. Any
    module-level `let`/`const` that applyStaticI18n() reads must therefore be
    declared ABOVE that call, or it is in its temporal dead zone and throws a
    ReferenceError at page load -- killing the rest of engine.js. The other
    guards here read the file as text and cannot see this; node --check only
    validates syntax. This one pins the ordering."""
    engine = _engine()
    start = engine.index("function applyStaticI18n() {")
    body = engine[start:engine.index("\n}", start)]
    call_at = engine.index("applyStaticI18n();", engine.index("(function wireZoneSearch()"))
    late = []
    for m in re.finditer(r"^(?:let|const)\s+([A-Za-z_$][\w$]*)", engine, flags=re.MULTILINE):
        name = m.group(1)
        if m.start() > call_at and re.search(rf"\b{re.escape(name)}\b", body):
            late.append((name, engine[:m.start()].count("\n") + 1))
    assert not late, (
        "applyStaticI18n() reads module-level bindings declared after the "
        f"zone-search controller calls it (temporal dead zone): {late}"
    )


GENOMIC = REPO / "Scripts" / "assets" / "genomic.js"


def test_zone_click_emitter_threads_options():
    """The search needs a non-toggling select; map clicks keep toggling."""
    engine = ENGINE.read_text(encoding="utf-8")
    assert "_emitZoneClick: function (nom, opts)" in engine
    assert "onZoneClickCb(nom, opts)" in engine


def test_genomic_select_zone_honours_the_toggle_option():
    genomic = GENOMIC.read_text(encoding="utf-8")
    assert "function selectZone(nom, opts)" in genomic
    assert "opts.toggle === false" in genomic


def test_genomic_publishes_its_panel_width():
    """The CSS rail clamp reads --genomic-panel-width; applyWidth() is the
    single writer of the inline px width, so it must publish it too."""
    genomic = GENOMIC.read_text(encoding="utf-8")
    assert "--genomic-panel-width" in genomic


def test_zone_search_view_panels_name_real_elements():
    """ZONE_SEARCH_VIEWS[...].panel is passed straight to getElementById(), and
    expandPanel() then looks up that panel's toggle button. Both halves fail
    silently -- a wrong id finds no panel, a panel with no toggle hits
    expandPanel()'s `if (btn)` guard -- so check the element AND its toggle."""
    engine = _engine()
    start = engine.index("const ZONE_SEARCH_VIEWS = {")
    block = engine[start:engine.index("\n};", start)]
    panels = re.findall(r'panel:\s*"([a-z-]+)"', block)
    assert panels, "no panel fields found -- did the field get renamed?"
    chrome = _chrome()
    for pid in panels:
        assert f'id="{pid}"' in chrome, f'ZONE_SEARCH_VIEWS names panel #{pid}, absent from chrome.py'
        # expandPanel() special-cases #info, whose toggle carries no data-target.
        toggle = f'id="info-toggle"' if pid == "info" else f'data-target="{pid}"'
        assert toggle in chrome, (
            f'panel #{pid} has no toggle button ({toggle}); expandPanel() would '
            "silently no-op on it"
        )


LOCALES = [REPO / "locales" / "en.yaml", REPO / "locales" / "fr.yaml"]

# Keys engine.js names from JS rather than from a data-i18n attribute. Nothing
# else in the repo checks these exist -- a typo would silently render the key
# path as the UI string, in one language only.
JS_NAMED_KEYS = [
    "zone_search",
    "zone_search_placeholder",
    "zone_search_no_matches",
    "zone_search_matches",
    "trends_search",
    "trends_search_placeholder",
]


def test_every_js_named_locale_key_exists_in_both_locales():
    for path in LOCALES:
        text = path.read_text(encoding="utf-8")
        missing = [k for k in JS_NAMED_KEYS if not re.search(rf"^\s*{k}:", text, re.MULTILINE)]
        assert not missing, f"{path.name} is missing {missing}"


def test_zone_search_views_only_names_existing_keys():
    engine = _engine()
    start = engine.index("const ZONE_SEARCH_VIEWS = {")
    block = engine[start:engine.index("\n};", start)]
    referenced = set(re.findall(r'"ui\.([a-z_]+)"', block))
    for path in LOCALES:
        text = path.read_text(encoding="utf-8")
        missing = [k for k in sorted(referenced) if not re.search(rf"^\s*{k}:", text, re.MULTILINE)]
        assert not missing, f"{path.name} is missing {missing}"
