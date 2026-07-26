"""Annual Posted Salary card + drawer display (PRD #171 / issues #178, #182)."""

import os
import subprocess

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BOARD_RENDERER_PATH = os.path.join(REPO_ROOT, "src", "web", "static", "js", "boardRenderer.js")
DRAWER_CONTROLLER_PATH = os.path.join(REPO_ROOT, "src", "web", "static", "js", "drawerController.js")


def _run_node(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_format_annual_posted_salary_for_matched_card():
    """Matched card salary line prefers Annual Posted Salary band with currency."""
    result = _run_node(
        """
        import {
          formatAnnualPostedSalary,
          cardSalaryDisplay,
        } from './src/web/static/js/boardRenderer.js';

        const band = formatAnnualPostedSalary({
          annualMin: 125000,
          annualMax: 145000,
          annualCurrency: 'USD',
          salary: '$125k - $145k',
        });
        if (band !== 'USD 125,000–145,000') process.exit(1);

        const point = formatAnnualPostedSalary({
          annualMin: 130000,
          annualMax: 130000,
          annualCurrency: 'CAD',
          salary: '$130,000',
        });
        if (point !== 'CAD 130,000') process.exit(2);

        const none = formatAnnualPostedSalary({ salary: '$70/hr' });
        if (none !== '') process.exit(3);

        const preferAnnual = cardSalaryDisplay({
          annualMin: 120000,
          annualMax: 140000,
          annualCurrency: 'USD',
          salary: '$120k-$140k raw',
        });
        if (preferAnnual !== 'USD 120,000–140,000') process.exit(4);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_scraped_card_omits_salary_without_annual_band():
    """Scraped / no-band cards omit salary line — raw Posted Salary is never primary UI."""
    result = _run_node(
        """
        import { cardSalaryDisplay } from './src/web/static/js/boardRenderer.js';

        const scrapedWithRaw = cardSalaryDisplay({
          status: 'scraped',
          salary: '$70–80/hr',
        });
        if (scrapedWithRaw !== '') process.exit(1);

        const legacyMatchedNoBand = cardSalaryDisplay({
          status: 'matched',
          salary: '$120,000 - $140,000',
        });
        if (legacyMatchedNoBand !== '') process.exit(2);

        const empty = cardSalaryDisplay({ status: 'scraped' });
        if (empty !== '') process.exit(3);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_board_renderer_card_uses_annual_salary_display():
    """Kanban card salary meta uses cardSalaryDisplay / annual band helper."""
    with open(BOARD_RENDERER_PATH, encoding="utf-8") as f:
        content = f.read()
    assert "cardSalaryDisplay" in content
    assert "formatAnnualPostedSalary" in content
    assert "kanban-card-meta-salary" in content


def test_drawer_salary_display_matches_card_annual_band():
    """Matched+ drawer salary uses Annual Posted Salary band; equal ends collapse."""
    result = _run_node(
        """
        import { drawerSalaryDisplay } from './src/web/static/js/drawerController.js';
        import { formatAnnualPostedSalary } from './src/web/static/js/boardRenderer.js';

        const bandJob = {
          status: 'matched',
          annualMin: 125000,
          annualMax: 145000,
          annualCurrency: 'USD',
          salary: '$125k - $145k raw',
        };
        const band = drawerSalaryDisplay(bandJob);
        if (band !== 'USD 125,000–145,000') process.exit(1);
        if (band !== formatAnnualPostedSalary(bandJob)) process.exit(2);
        if (band.includes('$125k')) process.exit(3);

        const pointJob = {
          status: 'matched',
          annualMin: 130000,
          annualMax: 130000,
          annualCurrency: 'CAD',
          salary: '$130,000',
        };
        if (drawerSalaryDisplay(pointJob) !== 'CAD 130,000') process.exit(4);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_drawer_salary_omits_raw_when_no_annual_band():
    """Without an annual band, drawer shows Not specified — never raw Posted Salary as primary."""
    result = _run_node(
        """
        import { drawerSalaryDisplay } from './src/web/static/js/drawerController.js';

        const scraped = drawerSalaryDisplay({
          status: 'scraped',
          salary: '$70–80/hr',
        });
        if (scraped !== 'Not specified') process.exit(1);

        const legacy = drawerSalaryDisplay({
          status: 'matched',
          salary: '$120,000 - $140,000',
        });
        if (legacy !== 'Not specified') process.exit(2);

        const empty = drawerSalaryDisplay({ status: 'matched' });
        if (empty !== 'Not specified') process.exit(3);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_drawer_uses_drawer_salary_display_helper():
    """Drawer Job Info salary row uses drawerSalaryDisplay, not raw job.salary."""
    with open(DRAWER_CONTROLLER_PATH, encoding="utf-8") as f:
        content = f.read()
    assert "drawerSalaryDisplay(job)" in content
    assert "drawer-salary" in content
    assert "job.salary || 'Not specified'" not in content
    assert "buildCompanyResearchSectionHtml" in content
