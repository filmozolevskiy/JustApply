"""Tracer tests: Role Relevance parse/pass helper."""

import pytest


@pytest.mark.parametrize(
    ("payload", "expected_value", "expected_note"),
    [
        ({"roleRelevant": True}, True, "ok"),
        ({"roleRelevant": False}, False, "ok"),
        ({"roleRelevant": None}, None, "ok"),
        ({}, None, "omitted"),
        ({"roleRelevant": "yes"}, None, "unexpected 'yes' (treated as unsure)"),
        ({"roleRelevant": 0}, None, "unexpected 0 (treated as unsure)"),
        ("not-an-object", None, "not an object"),
        (None, None, "not an object"),
    ],
)
def test_parse_role_relevant_table(payload, expected_value, expected_note):
    from src.core.role_relevance import parse_role_relevant

    value, note = parse_role_relevant(payload)
    assert value is expected_value
    assert note == expected_note


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        (None, True),
    ],
)
def test_passes_role_relevance_only_false_rejects(value, expected):
    from src.core.role_relevance import passes_role_relevance

    assert passes_role_relevance(value) is expected
