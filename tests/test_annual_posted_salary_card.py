"""Matched Kanban card Annual Posted Salary display (PRD #171 / issue #178)."""

import os
import subprocess

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BOARD_RENDERER_PATH = os.path.join(REPO_ROOT, "src", "web", "static", "js", "boardRenderer.js")


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

        const fallbackRaw = cardSalaryDisplay({ salary: '$70/hr' });
        if (fallbackRaw !== '$70/hr') process.exit(5);

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
