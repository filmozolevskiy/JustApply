"""Annual Posted Salary annualizer — yearly path (PRD #171 / issue #178)."""

from src.core.annual_posted_salary import annualize_posted_salary


def test_yearly_point_figure_becomes_equal_min_and_max():
    band = annualize_posted_salary(
        {
            "period": "yearly",
            "amountMin": 130000,
            "currency": "USD",
        }
    )
    assert band == {
        "annualMin": 130000,
        "annualMax": 130000,
        "annualCurrency": "USD",
    }


def test_yearly_band_preserves_min_and_max():
    band = annualize_posted_salary(
        {
            "period": "yearly",
            "amountMin": 120000,
            "amountMax": 140000,
            "currency": "CAD",
        }
    )
    assert band == {
        "annualMin": 120000,
        "annualMax": 140000,
        "annualCurrency": "CAD",
    }


def test_missing_or_non_yearly_facts_return_none():
    assert annualize_posted_salary(None) is None
    assert annualize_posted_salary({}) is None
    assert annualize_posted_salary({"period": "hourly", "amountMin": 70, "currency": "USD"}) is None
    assert annualize_posted_salary({"period": "yearly", "currency": "USD"}) is None
