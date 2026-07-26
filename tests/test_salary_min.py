"""Salary Min free-text parser (PRD #171 / issue #181)."""

from src.core.annual_posted_salary import parse_salary_min


def test_parse_salary_min_dollar_k_suffix():
    assert parse_salary_min("$120k") == 120000
    assert parse_salary_min("$120K") == 120000


def test_parse_salary_min_plain_integer_and_commas():
    assert parse_salary_min("120000") == 120000
    assert parse_salary_min("120,000") == 120000
    assert parse_salary_min("$120,000") == 120000


def test_parse_salary_min_empty_or_invalid_disables_gate():
    assert parse_salary_min("") is None
    assert parse_salary_min(None) is None
    assert parse_salary_min("   ") is None
    assert parse_salary_min("abc") is None
    assert parse_salary_min("$") is None
    assert parse_salary_min("k") is None
