"""Static guards for the header headline-numbers block (#tracker).

The block is assembled by buildTracker() in Scripts/assets/engine.js from i18n
keys in locales/*.yaml, and painted by two stylesheets: Scripts/assets/
dashboard.css plus the optional brand layer Data/Branding/dashboard-theme.css.
Nothing at runtime checks that the four stay in agreement -- a locale key that
survives a rename, or a CSS rule left pointing at a deleted class, fails
silently and only in one of the two themes. These tests make that a build
failure.

See docs/superpowers/specs/2026-08-15-tracker-headline-numbers-design.md.
"""
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]

# ENGINE/CSS/THEME are read by the markup and stylesheet guards below; the
# locale guards above need only LOCALES.
ENGINE = REPO / "Scripts" / "assets" / "engine.js"
CSS = REPO / "Scripts" / "assets" / "dashboard.css"
THEME = REPO / "Data" / "Branding" / "dashboard-theme.css"
LOCALES = REPO / "locales"

LANGS = ("en", "fr")

# The abbreviations and the per-country row's labels. Removing them is the
# whole point of the redesign, so none may come back.
#
# suspected_one/suspected_other joined them in 2026-09: INSP restructured the
# sitrep headline block and stopped publishing the counts, so the header was
# showing values 52 and 76 days stale beside figures refreshed every few days.
# They were also never cumulative -- the tile read "CAS SUSPECTS DU JOUR" --
# yet they rendered directly under a cumulative confirmed total.
RETIRED_KEYS = ("outbreak_size", "conf", "susp", "conf_deaths", "susp_deaths",
                "suspected_one", "suspected_other")

REQUIRED_KEYS = (
    "eyebrow",
    "eyebrow_nodate",
    "cases",
    "deaths",
    "recovered",
)


def _tracker_strings(lang):
    data = yaml.safe_load((LOCALES / f"{lang}.yaml").read_text(encoding="utf-8"))
    return data["ui"]["tracker"]


def test_retired_tracker_keys_are_gone():
    for lang in LANGS:
        present = set(_tracker_strings(lang)) & set(RETIRED_KEYS)
        assert not present, (
            f"{lang}.yaml still defines retired ui.tracker keys: {sorted(present)}"
        )


def test_required_tracker_keys_present():
    for lang in LANGS:
        missing = set(REQUIRED_KEYS) - set(_tracker_strings(lang))
        assert not missing, (
            f"{lang}.yaml is missing ui.tracker keys: {sorted(missing)}"
        )


def test_tracker_keys_match_across_locales():
    en = set(_tracker_strings("en"))
    fr = set(_tracker_strings("fr"))
    assert en == fr, (
        f"ui.tracker keys differ: en-only={sorted(en - fr)}, "
        f"fr-only={sorted(fr - en)}"
    )


def test_eyebrow_placeholders():
    for lang in LANGS:
        tr = _tracker_strings(lang)
        assert "{date}" in tr["eyebrow"], (
            f"{lang} ui.tracker.eyebrow must interpolate {{date}}"
        )
        # eyebrow_nodate is what renders when PAYLOAD.asof is empty --
        # ASOF_FALLBACK is "" (data_sources.py:259) -- so it must not leave a
        # dangling "cumulative to ".
        assert "{date}" not in tr["eyebrow_nodate"], (
            f"{lang} ui.tracker.eyebrow_nodate must not interpolate {{date}}"
        )


def test_tracker_strings_are_lowercase():
    """#tracker .global-title and .global-cell .sub apply text-transform:
    uppercase, so a capitalised value renders doubly shouted -- or worse, looks
    deliberate. Store lowercase and let the CSS decide."""
    for lang in LANGS:
        for key, value in _tracker_strings(lang).items():
            assert value == value.lower(), (
                f"{lang} ui.tracker.{key} is not lowercase: {value!r}"
            )


def _build_tracker_source():
    """The body of buildTracker(), from its declaration to the next top-level
    function. Scoping the assertions this way keeps them from tripping over
    unrelated uses of the same words elsewhere in a 4000-line file."""
    src = ENGINE.read_text(encoding="utf-8")
    start = src.index("function buildTracker()")
    end = src.index("\nfunction ", start + 1)
    body = src[start:end]
    # The slice ends at the first column-0 "function", so a nested helper
    # declared flush-left would cut it short mid-function -- and every guard
    # below would then pass or fail for the wrong reason, silently. These two
    # assertions turn that into a loud failure instead.
    assert "tracker.innerHTML" in body, "buildTracker() source slice is truncated"
    assert body.rstrip().endswith("}"), "buildTracker() source slice is truncated"
    return body


def test_build_tracker_has_no_per_country_branch():
    body = _build_tracker_source()
    for token in ("countries-row", "tracker-countries", "per_country",
                  "conf-d", "susp-d"):
        assert token not in body, (
            f"buildTracker() still references {token!r}; the per-country row "
            f"was removed (totals.per_country stays in the payload, it is "
            f"only no longer rendered)"
        )
    # Word-boundary so a future countryCode/countrySelector is not a false
    # positive -- only the bare identifier the retired row used.
    assert not re.search(r"\bcountry\b", body), (
        "buildTracker() still references a bare `country` identifier; the "
        "per-country row was removed"
    )


def test_build_tracker_renders_no_suspected_qualifier():
    """The "N suspected" line under each confirmed figure was removed in
    2026-09. Nothing may reintroduce it: the source it came from no longer
    publishes the number, and the number it last published was a daily count
    sitting under a cumulative total."""
    body = _build_tracker_source()
    for token in ("class='qual'", "class='qnum'",
                  "ui.tracker.suspected_one", "ui.tracker.suspected_other",
                  "qualifier("):
        assert token not in body, f"buildTracker() must not emit {token!r}"
    for field in ("global_suspected_cases", "global_suspected_deaths"):
        assert field not in body, (
            f"buildTracker() must not read {field} -- it is stale upstream"
        )


def test_build_tracker_reads_confirmed_cases_not_total():
    body = _build_tracker_source()
    assert "global_confirmed_cases" in body
    assert "global_total_cases" not in body, (
        "the headline figure is labelled 'confirmed', so it reads "
        "totals.global_confirmed_cases; global_total_cases is an alias for the "
        "same number whose name no longer matches the label"
    )


def _tracker_lines(path):
    """Every line of the stylesheet that names a selector under #tracker.

    Comments are stripped first so a commented-out rule cannot satisfy or trip
    an assertion. Assumes each rule sits on one line, as dashboard.css does --
    for a stylesheet that splits selectors from declarations, this returns the
    selector lines only and sees no declarations at all.
    """
    text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    return "\n".join(ln for ln in text.splitlines() if "#tracker" in ln)


def _hex_luma(value):
    """Rough perceived brightness of a #rgb or #rrggbb colour, 0-255."""
    h = value.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b


def test_stylesheets_carry_no_qualifier_rules():
    """The .qual/.qnum rules went with the markup; a stray rule would be dead
    weight and would imply the line still exists."""
    for path in (REPO / "Scripts" / "assets" / "dashboard.css",
                 REPO / "Data" / "Branding" / "dashboard-theme.css"):
        css = path.read_text(encoding="utf-8")
        for sel in (".global-cell .qual", ".qual .qnum"):
            assert sel not in css, f"{path.name} still styles {sel}"


def test_global_row_is_top_aligned():
    # Three rules select .global-row (base plus two media queries); only the
    # base one declares alignment, so assert on the declaration rather than on
    # whichever rule happens to come first in the file.
    lines = [ln for ln in _tracker_lines(CSS).splitlines()
             if "#tracker .global-row" in ln]
    assert lines, "no #tracker .global-row rule found"
    assert any("align-items:flex-start" in ln for ln in lines), (
        "the recovered cell carries no .qual line, so aligning bottoms would "
        "drop its big number out of line with the other two"
    )
    assert not any("align-items:flex-end" in ln for ln in lines)


# Selectors the per-country row owned. Matched only against lines that already
# mention #tracker, so an unrelated .name or .dot elsewhere in the file is not
# our business. \.conf\b also matches .conf-d, which is retired too.
RETIRED_SELECTORS = (
    r"\.countries-row\b",
    r"\.country\b",
    r"\.conf\b",
    r"\.susp\b",
    r"\.dot\b",
    r"\.nums\b",
    r"\.name\b",
)

RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def _rule_blocks(path):
    """(selector, declarations) for every brace-delimited rule in the file.
    @media openers do not match, because their bodies contain braces."""
    text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    return [(m.group(1).strip(), m.group(2)) for m in RULE.finditer(text)]


def test_base_stylesheet_has_no_country_row_rules():
    lines = _tracker_lines(CSS)
    for pattern in RETIRED_SELECTORS:
        assert not re.search(pattern, lines), (
            f"dashboard.css still styles {pattern} under #tracker"
        )


def test_no_rule_hides_the_eyebrow():
    # The eyebrow is the only place the block states its as-of date. Hiding it
    # on phones, as the old max-width:700px rule did, leaves three undated
    # numbers -- #header-narrow-row carries only the dashboard build time,
    # which is a different date.
    for selector, body in _rule_blocks(CSS):
        if "#tracker .global-title" in selector:
            assert "display:none" not in body.replace(" ", ""), (
                f"rule {selector!r} hides the eyebrow"
            )


def _tracker_declarations(path):
    """The declaration bodies of every rule selecting under #tracker. The theme
    layer puts selectors and declarations on separate lines, so _tracker_lines()
    sees no colours at all -- this is the one that does."""
    return "\n".join(body for sel, body in _rule_blocks(path) if "#tracker" in sel)


def test_theme_layer_has_no_country_row_rules():
    lines = _tracker_lines(THEME)
    for pattern in RETIRED_SELECTORS:
        assert not re.search(pattern, lines), (
            f"dashboard-theme.css still styles {pattern} under #tracker"
        )


def test_theme_layer_drops_the_hardcoded_rust():
    assert "#a66b55" not in THEME.read_text(encoding="utf-8"), (
        "the suspected-deaths colour was the one hard-coded hex in the tracker "
        "theme rules; it leaves with the row it painted"
    )


def test_tracker_hues_are_one_meaning_each():
    """Each headline hue names exactly one thing. The collision this redesign
    removes was --terracotta painting both confirmed cases and suspected
    cases."""
    decls = _tracker_declarations(THEME)
    for token in ("var(--maroon)", "var(--green)"):
        assert decls.count(token) == 1, (
            f"{token} is used {decls.count(token)} times under #tracker; each "
            f"hue must name exactly one thing"
        )
    # --terracotta is the cases hue and also the caveat mark, which annotates a
    # number rather than being one. Two uses, no more.
    assert decls.count("var(--terracotta)") == 2
    assert "var(--red)" not in decls


def test_tracker_media_rules_come_after_the_base_rules():
    """Media queries add no specificity. An equal-specificity #tracker rule in
    an @media block that sits EARLIER in the file therefore loses the
    source-order tiebreak to the unconditional rule below it, and silently does
    nothing -- no warning, no visible error, it just never applies. Every
    #tracker media override has to sit after the base block."""
    text = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.DOTALL)
    lines = text.splitlines()
    base, nested = [], []
    for i, ln in enumerate(lines):
        m = re.match(r"( *)#tracker\b", ln)
        if not m:
            continue
        # Bucket on the measured indent rather than two fixed widths: an
        # oddly-indented rule then lands in a bucket instead of disappearing
        # from both, which would hide exactly the bug this test exists to catch.
        (base if len(m.group(1)) <= 2 else nested).append(i)
    assert base, "no unconditional #tracker rules found"
    assert nested, "no @media #tracker rules found"
    assert min(nested) > max(base), (
        f"an @media #tracker rule at line {min(nested) + 1} sits before the "
        f"last unconditional rule at line {max(base) + 1}; it loses the "
        f"source-order tiebreak and will silently never apply"
    )

