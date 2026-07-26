"""Normalize structured Posted Salary facts into an Annual Posted Salary band.

Supports yearly, hourly, monthly, and daily periods, plus multi-location band
resolution (job listing location match, else first band).
"""

from __future__ import annotations

from typing import Any

_YEARLY_PERIODS = frozenset({"yearly", "year", "annual", "annually"})
_HOURLY_PERIODS = frozenset({"hourly", "hour", "hr", "per_hour", "per-hour"})
_MONTHLY_PERIODS = frozenset({"monthly", "month", "per_month", "per-month"})
_DAILY_PERIODS = frozenset({"daily", "day", "per_day", "per-day"})

DEFAULT_HOURS_PER_YEAR = 2080
DEFAULT_DAYS_PER_YEAR = 260


def _as_int_amount(value: Any) -> int | None:
    if value is None or value is False:
        return None
    if isinstance(value, bool):
        return None
    try:
        amount = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    if amount < 0:
        return None
    return amount


def _normalize_period(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _hours_per_year(facts: dict) -> int:
    hours_per_week = _as_int_amount(facts.get("hoursPerWeek"))
    if hours_per_week is None or hours_per_week <= 0:
        return DEFAULT_HOURS_PER_YEAR
    return hours_per_week * 52


def _days_per_year(facts: dict) -> int:
    days_per_year = _as_int_amount(facts.get("daysPerYear"))
    if days_per_year is None or days_per_year <= 0:
        return DEFAULT_DAYS_PER_YEAR
    return days_per_year


def _annualize_amounts(amount_min: int, amount_max: int, period: str, facts: dict) -> tuple[int, int] | None:
    if period in _YEARLY_PERIODS:
        return amount_min, amount_max
    if period in _HOURLY_PERIODS:
        hours = _hours_per_year(facts)
        return amount_min * hours, amount_max * hours
    if period in _MONTHLY_PERIODS:
        return amount_min * 12, amount_max * 12
    if period in _DAILY_PERIODS:
        days = _days_per_year(facts)
        return amount_min * days, amount_max * days
    return None


def _locations_match(band_location: str, job_location: str) -> bool:
    """True when band and job listing locations refer to the same place."""
    band = band_location.strip().lower()
    job = job_location.strip().lower()
    if not band or not job:
        return False
    if band in job or job in band:
        return True
    band_city = band.split(",", 1)[0].strip()
    job_city = job.split(",", 1)[0].strip()
    if band_city and band_city in job:
        return True
    if job_city and job_city in band:
        return True
    return False


def _pick_band(facts: dict, job_location: str | None) -> dict | None:
    bands = facts.get("bands")
    if isinstance(bands, list) and bands:
        location = str(job_location or "").strip()
        if location:
            for band in bands:
                if not isinstance(band, dict):
                    continue
                band_location = str(band.get("location") or "")
                if _locations_match(band_location, location):
                    return band
        first = bands[0]
        return first if isinstance(first, dict) else None
    return facts


def _band_to_annual(band: dict) -> dict[str, int | str] | None:
    period = _normalize_period(band.get("period"))
    amount_min = _as_int_amount(band.get("amountMin"))
    if amount_min is None:
        amount_min = _as_int_amount(band.get("amount"))
    if amount_min is None:
        return None

    amount_max = _as_int_amount(band.get("amountMax"))
    if amount_max is None:
        amount_max = amount_min
    if amount_max < amount_min:
        amount_min, amount_max = amount_max, amount_min

    currency = str(band.get("currency") or "").strip().upper()
    if not currency:
        return None

    annualized = _annualize_amounts(amount_min, amount_max, period, band)
    if annualized is None:
        return None
    annual_min, annual_max = annualized
    return {
        "annualMin": annual_min,
        "annualMax": annual_max,
        "annualCurrency": currency,
    }


def annualize_posted_salary(
    facts: dict | None,
    job_location: str | None = None,
) -> dict[str, int | str] | None:
    """Return ``{annualMin, annualMax, annualCurrency}`` from Posted Salary facts.

    Multi-location ``bands`` pick the entry matching ``job_location`` (substring,
    case-insensitive), else the first band. Flat facts (no ``bands``) annualize
    as a single band.
    """
    if not isinstance(facts, dict):
        return None

    band = _pick_band(facts, job_location)
    if not isinstance(band, dict):
        return None
    return _band_to_annual(band)
