"""Static assertions for Company Research drawer and spend modal wiring."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_drawer_includes_glassdoor_section():
    ui_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "web", "static", "js", "companyResearchUi.js"
    )
    drawer_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "web", "static", "js", "drawerController.js"
    )
    with open(ui_path, encoding="utf-8") as f:
        ui_content = f.read()
    with open(drawer_path, encoding="utf-8") as f:
        drawer_content = f.read()
    assert "Glassdoor Company Research" in ui_content
    assert "buildCompanyResearchSectionHtml" in drawer_content


def test_drawer_hides_research_on_scraped_lane():
    path = os.path.join(
        os.path.dirname(__file__), "..", "src", "web", "static", "js", "companyResearchUi.js"
    )
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "companyResearchAllowed" in content
    assert "scraped" not in content.split("companyResearchAllowed")[1][:200]


def test_board_orchestration_research_company_action():
    path = os.path.join(
        os.path.dirname(__file__), "..", "src", "web", "static", "js", "boardOrchestration.js"
    )
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "researchCompany" in content
    assert "company-research-preflight" in content


def test_spend_modal_glassdoor_job_title_field():
    path = os.path.join(
        os.path.dirname(__file__), "..", "src", "web", "static", "js", "spendConfirmation.js"
    )
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "buildGlassdoorSpendBodyHtml" in content
    assert "spend-glassdoor-job-title" in content


def test_drawer_refresh_button_in_researched_section():
    path = os.path.join(
        os.path.dirname(__file__), "..", "src", "web", "static", "js", "companyResearchUi.js"
    )
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "Refresh" in content
    assert "showActions: true" in content


def test_research_company_skips_spend_when_fully_cached():
    path = os.path.join(
        os.path.dirname(__file__), "..", "src", "web", "static", "js", "boardOrchestration.js"
    )
    with open(path, encoding="utf-8") as f:
        content = f.read()
    research_fn = content.split("async function researchCompany")[1].split("function reclassifyJob")[0]
    assert "will_call_apify" in research_fn
    assert "showSpendConfirmModal" in research_fn
    assert research_fn.index("will_call_apify") < research_fn.index("showSpendConfirmModal")


def test_research_company_passes_existing_glassdoor_title_to_preflight():
    path = os.path.join(
        os.path.dirname(__file__), "..", "src", "web", "static", "js", "boardOrchestration.js"
    )
    with open(path, encoding="utf-8") as f:
        content = f.read()
    research_fn = content.split("async function researchCompany")[1].split("function reclassifyJob")[0]
    assert "companyResearch" in research_fn
    assert "glassdoorJobTitle" in research_fn
