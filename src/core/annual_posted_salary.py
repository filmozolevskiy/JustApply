"""Normalize structured Posted Salary facts into an Annual Posted Salary band.

Yearly path for issue #178. Hourly/monthly/daily and multi-location resolution
are extended in later slices (#179).
"""

from __future__ import annotations

from typing import Any


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


def annualize_posted_salary(facts: dict | None) -> dict[str, int | str] | None:
    """Return ``{annualMin, annualMax, annualCurrency}`` for yearly facts, else None."""
    if not isinstance(facts, dict):
        return None

    period = str(facts.get("period") or "").strip().lower()
    if period not in {"yearly", "year", "annual", "annually"}:
        return None

    amount_min = _as_int_amount(facts.get("amountMin"))
    if amount_min is None:
        amount_min = _as_int_amount(facts.get("amount"))
    if amount_min is None:
        return None

    amount_max = _as_int_amount(facts.get("amountMax"))
    if amount_max is None:
        amount_max = amount_min
    if amount_max < amount_min:
        amount_min, amount_max = amount_max, amount_min

    currency = str(facts.get("currency") or "").strip().upper()
    if not currency:
        return None

    return {
        "annualMin": amount_min,
        "annualMax": amount_max,
        "annualCurrency": currency,
    }
