"""Replay every eval fixture. This is the acceptance suite for governance."""

import pytest

from agentic_os.evals import fixture_paths, load_fixture, run_fixture

PATHS = fixture_paths()


def test_there_are_at_least_ten_fixtures():
    assert len(PATHS) >= 10


@pytest.mark.parametrize("path", PATHS, ids=[p.stem for p in PATHS])
def test_fixture(path, tmp_path):
    fixture = load_fixture(path)
    outcome = run_fixture(fixture, work_dir=tmp_path)
    assert outcome.passed, "; ".join(outcome.failures)


def test_fixtures_cover_denial_reasons():
    """The suite must exercise every class of governance denial."""
    reasons = set()
    for path in PATHS:
        fixture = load_fixture(path)
        for run in fixture.runs:
            for denial in run.expect.denied:
                reasons.add(denial.reason_contains)
    for expected in ("scopes", "purpose", "budget", "policy", "approval", "rate limit"):
        assert any(expected in reason for reason in reasons), f"no fixture covers {expected!r}"
