"""Tests for Job Search Settings region pickers — Issue #103.

Client (static): country-scoped Search Regions, Per-Region Limit stepper,
run-control gating, and structured POST /api/search payload.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kanban_js import read_dashboard_html, get_script_section


def _dashboard_script() -> str:
    return get_script_section(read_dashboard_html())


def _get_function_body(content: str, func_name: str, window: int = 8000) -> str:
    for prefix in (f"async function {func_name}(", f"function {func_name}("):
        idx = content.find(prefix)
        if idx != -1:
            return content[idx : idx + window]
    raise AssertionError(f"{func_name} not found in content")


def test_location_field_removed():
    html = read_dashboard_html()
    assert 'id="kb-filter-location"' not in html, "Free-text Location field must be removed"
    assert ">Location</label>" not in html or "kb-filter-location" not in html


def test_per_region_limit_stepper_present():
    html = read_dashboard_html()
    assert 'id="kb-per-region-limit"' in html, "Per-Region Limit input must exist"
    assert 'min="25"' in html and 'max="1000"' in html and 'step="25"' in html
    assert 'value="200"' in html, "Default Per-Region Limit must be 200"


def test_region_pickers_load_from_api():
    script = _dashboard_script()
    assert "/api/regions" in script, "Dashboard must fetch regions from GET /api/regions"
    assert "initSearchRegionPickers" in script or "loadRegionsMap" in script


def test_country_scoped_region_pickers():
    script = _dashboard_script()
    html = read_dashboard_html()
    assert "region-country-tabs" in html or "region-country-tab" in script
    assert "region-chip" in script or "region-chip-grid" in html
    body = _get_function_body(script, "renderRegionPickers", window=4000)
    assert "regionsMap" in body or "activeRegionTab" in body
    assert "activeRegionTab" in script, "Region pickers must use country tabs"


def test_run_button_gating_function():
    script = _dashboard_script()
    assert "updateScrapeRunButtonState" in script, "Must gate run button on region selection"


def test_run_button_disabled_until_regions_valid():
    script = _dashboard_script()
    body = _get_function_body(script, "updateScrapeRunButtonState", window=3000)
    assert "kb-scrape-btn-panel" in body, "Must target the scrape run button"
    assert "disabled" in body, "Must disable run button when regions incomplete"


def test_run_button_hint_when_incomplete():
    html = read_dashboard_html()
    assert "kb-region-hint" in html, "Hint element must explain why run is disabled"
    script = _dashboard_script()
    body = _get_function_body(script, "updateScrapeRunButtonState", window=3000)
    assert "kb-region-hint" in body, "Gating logic must show/hide the hint"


def test_trigger_scrape_sends_search_regions():
    script = _dashboard_script()
    body = _get_function_body(script, "triggerScrapeRun", window=6000)
    assert "search_regions" in body, "triggerScrapeRun must send search_regions"
    assert "per_region_limit" in body, "triggerScrapeRun must send per_region_limit"
    assert "location:" not in body or "location" not in re.findall(
        r"location\s*:", body.split("JSON.stringify")[1] if "JSON.stringify" in body else body
    ), "triggerScrapeRun must not send free-text location in POST body"


def test_trigger_scrape_collects_selected_regions():
    script = _dashboard_script()
    assert "getSelectedSearchRegions" in script, "Must collect structured region pairs"


def test_clamp_per_region_limit_client():
    script = _dashboard_script()
    assert "clampPerRegionLimit" in script, "Client must clamp Per-Region Limit to 25–1000"


def test_job_search_settings_two_column_layout():
    html = read_dashboard_html()
    assert "job-search-settings-split" in html
    assert "job-search-scope-col" in html
    assert "job-search-refine-col" in html
    assert "job-search-actions" in html
    assert "Refine results (optional)" in html


def test_reset_filters_clears_regions_and_limit():
    script = _dashboard_script()
    body = _get_function_body(script, "resetKbFilters", window=4000)
    assert "kb-per-region-limit" in body, "Reset must restore Per-Region Limit default"
    assert "selectedSearchRegions" in body, "Reset must clear selected Search Regions"
    assert "kb-filter-location" not in body, "Reset must not reference removed location field"
