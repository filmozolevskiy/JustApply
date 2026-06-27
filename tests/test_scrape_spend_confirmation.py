"""Tests for scrape Spend Confirmation (checkout-receipt) — Issue #104.

Client (static): triggerScrapeRun opens spend modal before POST /api/search,
checkout-receipt layout with live cost recompute, limit sync back to settings.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kanban_js import read_dashboard_html, get_script_section


def _dashboard_script() -> str:
    return get_script_section(read_dashboard_html())


def _get_function_body(content: str, func_name: str, window: int = 12000) -> str:
    for prefix in (f"async function {func_name}(", f"function {func_name}("):
        idx = content.find(prefix)
        if idx != -1:
            return content[idx : idx + window]
    raise AssertionError(f"{func_name} not found in content")


def test_scrape_spend_confirm_modal_function_exists():
    script = _dashboard_script()
    assert "showScrapeSpendConfirmModal" in script


def test_trigger_scrape_shows_modal_before_post():
    script = _dashboard_script()
    body = _get_function_body(script, "triggerScrapeRun")
    modal_idx = body.find("showScrapeSpendConfirmModal")
    fetch_idx = body.find("/api/search")
    assert modal_idx != -1, "triggerScrapeRun must open scrape spend confirmation modal"
    assert fetch_idx != -1, "triggerScrapeRun must POST to /api/search"
    assert modal_idx < fetch_idx, "Spend modal must appear before POST /api/search"


def test_trigger_scrape_cancels_without_post():
    script = _dashboard_script()
    body = _get_function_body(script, "triggerScrapeRun")
    assert (
        "if (!ok)" in body
        or "if (!confirmed)" in body
        or "!spendResult.confirmed" in body
    ), "triggerScrapeRun must abort when user cancels the modal"


def test_scrape_spend_receipt_layout_classes():
    html = read_dashboard_html()
    assert "spend-receipt-grid" in html or "spend-receipt-grid" in _dashboard_script()
    script = _dashboard_script()
    assert "spend-receipt-left" in script or "spend-receipt-grid" in script
    assert "spend-receipt-right" in script or "spend-receipt-grid" in script


def test_scrape_spend_shows_scope_keyword_regions_time():
    script = _dashboard_script()
    body = _get_function_body(script, "buildScrapeSpendReceiptBodyHtml", window=6000)
    assert "query" in body or "keyword" in body.lower()
    assert "region" in body.lower()
    assert "time" in body.lower() or "timeRange" in body


def test_scrape_spend_cost_per_record_constant():
    script = _dashboard_script()
    assert "SCRAPE_COST_PER_RECORD" in script or "COST_PER_RECORD" in script
    assert "0.0015" in script


def test_scrape_spend_recompute_max_postings_and_spend():
    script = _dashboard_script()
    assert "recomputeScrapeSpendEstimate" in script or "maxPostings" in script
    body = _get_function_body(
        script,
        "recomputeScrapeSpendEstimate" if "recomputeScrapeSpendEstimate" in script else "buildScrapeSpendReceiptBodyHtml",
        window=4000,
    )
    assert "maxPostings" in body or "max_postings" in body or "Max postings" in body
    assert "maxSpend" in body or "max_spend" in body or "Max spend" in body


def test_scrape_spend_modal_limit_stepper_clamps():
    script = _dashboard_script()
    body = _get_function_body(script, "showScrapeSpendConfirmModal", window=8000)
    assert "PER_REGION_LIMIT" in body or "clampPerRegionLimit" in body
    assert "STEP" in body or "step" in body.lower()


def test_scrape_spend_syncs_limit_to_settings():
    script = _dashboard_script()
    body = _get_function_body(script, "triggerScrapeRun")
    assert "kb-per-region-limit" in body, (
        "Confirmed modal limit must write back to Job Search Settings"
    )


def test_scrape_spend_ceiling_note_not_single_fabricated_figure():
    script = _dashboard_script()
    body = _get_function_body(script, "buildScrapeSpendReceiptBodyHtml", window=6000)
    assert "ceiling" in body.lower() or "depends on" in body.lower() or "actual cost" in body.lower()


def test_spend_confirmation_prototype_removed():
    proto = os.path.join(
        os.path.dirname(__file__), "..", "src", "web", "prototypes", "spend-confirmation.prototype.html"
    )
    assert not os.path.exists(proto), "Prototype must be deleted once folded into dashboard"
