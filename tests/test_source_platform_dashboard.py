"""Dashboard Source Platform options + Apify Spend Confirmation (#202).

Approved seams:
- Dashboard Source Platform options (Bright Data + Apify LinkedIn only)
- Spend Confirmation Apify PPE estimate (regions × limit × $0.001)
Static / dashboard tests only — no live Actor.
"""

import re

from kanban_js import load_dashboard_js, read_dashboard_html, read_dashboard_module


def _get_function_body(content: str, func_name: str, window: int = 12000) -> str:
    for prefix in (f"async function {func_name}(", f"function {func_name}("):
        idx = content.find(prefix)
        if idx != -1:
            return content[idx : idx + window]
    raise AssertionError(f"{func_name} not found in content")


def test_source_platform_options_are_brightdata_and_apify_linkedin_only():
    html = read_dashboard_html()
    select_match = re.search(
        r'<select[^>]*id="kb-filter-platform"[^>]*>(.*?)</select>',
        html,
        re.DOTALL,
    )
    assert select_match, "Source Platform select #kb-filter-platform must exist"
    select_html = select_match.group(1)

    assert 'value="brightdata_linkedin"' in select_html
    assert "LinkedIn (Bright Data)" in select_html
    assert 'value="apify_linkedin"' in select_html
    assert "LinkedIn (Apify)" in select_html

    assert 'value="apify_indeed"' not in select_html
    assert 'value="apify_glassdoor"' not in select_html
    assert "Indeed (Apify)" not in select_html
    assert "Glassdoor (Apify)" not in select_html

    option_values = re.findall(r'value="([^"]+)"', select_html)
    assert option_values == ["brightdata_linkedin", "apify_linkedin"]


def test_brightdata_remains_default_source_platform():
    html = read_dashboard_html()
    select_match = re.search(
        r'<select[^>]*id="kb-filter-platform"[^>]*>(.*?)</select>',
        html,
        re.DOTALL,
    )
    assert select_match
    select_html = select_match.group(1)
    assert re.search(
        r'<option[^>]*value="brightdata_linkedin"[^>]*selected',
        select_html,
    ), "LinkedIn (Bright Data) must remain the default selected option"


def test_apify_linkedin_scrape_ppe_constant_is_named():
    script = read_dashboard_module("spendConfirmation.js")
    assert "APIFY_LINKEDIN_SCRAPE_COST_PER_RESULT" in script
    assert re.search(
        r"APIFY_LINKEDIN_SCRAPE_COST_PER_RESULT\s*=\s*0\.001\b",
        script,
    ), "Apify LinkedIn PPE must be the named constant 0.001"


def test_brightdata_scrape_cost_constant_unchanged():
    script = read_dashboard_module("spendConfirmation.js")
    assert re.search(r"SCRAPE_COST_PER_RECORD\s*=\s*0\.0015\b", script)


def test_recompute_scrape_spend_uses_platform_rate():
    script = read_dashboard_module("spendConfirmation.js")
    body = _get_function_body(script, "recomputeScrapeSpendEstimate", window=2500)
    assert "platform" in body
    assert "APIFY_LINKEDIN_SCRAPE_COST_PER_RESULT" in body
    assert "SCRAPE_COST_PER_RECORD" in body
    assert "apify_linkedin" in body


def test_scrape_spend_modal_accepts_platform():
    script = read_dashboard_module("spendConfirmation.js")
    body = _get_function_body(script, "showScrapeSpendConfirmModal", window=9000)
    assert "platform" in body


def test_apify_spend_receipt_names_apify_linkedin_not_brightdata():
    script = read_dashboard_module("spendConfirmation.js")
    body = _get_function_body(script, "buildScrapeSpendReceiptBodyHtml", window=8000)
    assert "Apify LinkedIn scrape" in body
    assert "apify_linkedin" in body
    assert "Bright Data" in body
    assert "Apify LinkedIn PPE" in body
    # Display rate comes from the named PPE constant via `rate`, not a second literal.
    assert "costPerRecordLabel" in body
    assert "${rate}" in body or "${costPerRecordLabel}" in body


def test_recompute_apify_spend_math_is_regions_times_limit_times_ppe():
    """External behavior: Apify ceiling is regionCount × limit × $0.001."""
    script = read_dashboard_module("spendConfirmation.js")
    body = _get_function_body(script, "recomputeScrapeSpendEstimate", window=2500)
    assert "regionCount * limit" in body or "regionCount*limit" in body
    assert "maxPostings * rate" in body or "maxPostings*rate" in body
    assert "APIFY_LINKEDIN_SCRAPE_COST_PER_RESULT" in body
    assert re.search(r"APIFY_LINKEDIN_SCRAPE_COST_PER_RESULT\s*=\s*0\.001\b", script)


def test_trigger_scrape_passes_platform_into_spend_modal():
    script = load_dashboard_js()
    body = _get_function_body(script, "triggerScrapeRun", window=10000)
    modal_call_idx = body.find("showScrapeSpendConfirmModal")
    assert modal_call_idx != -1
    modal_slice = body[modal_call_idx : modal_call_idx + 500]
    assert "platform" in modal_slice
