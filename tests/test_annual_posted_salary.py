"""Annual Posted Salary annualizer (PRD #171 / issue #179)."""

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


def test_missing_or_incomplete_facts_return_none():
    assert annualize_posted_salary(None) is None
    assert annualize_posted_salary({}) is None
    assert annualize_posted_salary({"period": "yearly", "currency": "USD"}) is None
    assert annualize_posted_salary({"period": "hourly", "currency": "USD"}) is None


def test_hourly_band_uses_2080_hours_default():
    band = annualize_posted_salary(
        {
            "period": "hourly",
            "amountMin": 70,
            "amountMax": 80,
            "currency": "USD",
        }
    )
    assert band == {
        "annualMin": 70 * 2080,
        "annualMax": 80 * 2080,
        "annualCurrency": "USD",
    }


def test_hourly_uses_stated_hours_per_week():
    band = annualize_posted_salary(
        {
            "period": "hourly",
            "amountMin": 50,
            "amountMax": 50,
            "currency": "CAD",
            "hoursPerWeek": 30,
        }
    )
    assert band == {
        "annualMin": 50 * 30 * 52,
        "annualMax": 50 * 30 * 52,
        "annualCurrency": "CAD",
    }


def test_monthly_amounts_times_twelve():
    band = annualize_posted_salary(
        {
            "period": "monthly",
            "amountMin": 10000,
            "amountMax": 12000,
            "currency": "USD",
        }
    )
    assert band == {
        "annualMin": 120000,
        "annualMax": 144000,
        "annualCurrency": "USD",
    }


def test_daily_amounts_use_260_default():
    band = annualize_posted_salary(
        {
            "period": "daily",
            "amountMin": 400,
            "amountMax": 500,
            "currency": "USD",
        }
    )
    assert band == {
        "annualMin": 400 * 260,
        "annualMax": 500 * 260,
        "annualCurrency": "USD",
    }


def test_multi_location_picks_matching_job_location():
    facts = {
        "bands": [
            {
                "location": "Toronto, ON",
                "period": "yearly",
                "amountMin": 100000,
                "amountMax": 120000,
                "currency": "CAD",
            },
            {
                "location": "New York, NY",
                "period": "yearly",
                "amountMin": 130000,
                "amountMax": 150000,
                "currency": "USD",
            },
        ]
    }
    band = annualize_posted_salary(facts, job_location="New York, United States")
    assert band == {
        "annualMin": 130000,
        "annualMax": 150000,
        "annualCurrency": "USD",
    }


def test_multi_location_falls_back_to_first_band():
    facts = {
        "bands": [
            {
                "location": "Toronto, ON",
                "period": "yearly",
                "amountMin": 100000,
                "amountMax": 120000,
                "currency": "CAD",
            },
            {
                "location": "New York, NY",
                "period": "yearly",
                "amountMin": 130000,
                "amountMax": 150000,
                "currency": "USD",
            },
        ]
    }
    band = annualize_posted_salary(facts, job_location="Austin, TX")
    assert band == {
        "annualMin": 100000,
        "annualMax": 120000,
        "annualCurrency": "CAD",
    }


def test_multi_location_hourly_band_annualizes_for_matched_location():
    facts = {
        "bands": [
            {
                "location": "Remote Canada",
                "period": "hourly",
                "amountMin": 60,
                "amountMax": 70,
                "currency": "CAD",
            },
            {
                "location": "San Francisco, CA",
                "period": "hourly",
                "amountMin": 80,
                "amountMax": 90,
                "currency": "USD",
                "hoursPerWeek": 40,
            },
        ]
    }
    band = annualize_posted_salary(facts, job_location="San Francisco Bay Area")
    assert band == {
        "annualMin": 80 * 40 * 52,
        "annualMax": 90 * 40 * 52,
        "annualCurrency": "USD",
    }
