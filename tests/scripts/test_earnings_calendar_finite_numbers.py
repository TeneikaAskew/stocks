"""Actual producer scalar rules share literal API conformance vectors."""
import pytest

from scripts import fetch_earnings_calendar as calendar
from tests._catalyst_number_cases import CASES, input_value


@pytest.fixture(autouse=True)
def no_external_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Provider/database calls forbidden")

    import requests
    from gcp import database
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(database, "get_engine", forbidden)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case"])
def test_safe_num_finite_nullable_contract(case):
    result = calendar._safe_num(input_value(case))
    if case["expected"] is None:
        assert result is None
    else:
        assert result == case["expected"]
        assert isinstance(result, float)


@pytest.mark.parametrize("value,expected", [
    (0, 0), (-5, -5), ("12", 12), ("3.9", 3),
])
def test_valid_integer_helper_callers_preserve_existing_conversion(value, expected):
    assert calendar._safe_int(value) == expected


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["expected"] is None],
    ids=lambda c: c["case"],
)
def test_integer_helper_does_not_manufacture_unknown_numbers(case):
    assert calendar._safe_int(input_value(case)) is None
