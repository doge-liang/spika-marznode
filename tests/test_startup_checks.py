"""node refuses to start when AUTH_GENERATION_ALGORITHM is unset (its
decouple default is xxh128, which silently mismatches a `plain` panel and
rejects every client)."""
import pytest

from marznode.startup_checks import require_auth_algorithm_set, MissingAuthAlgorithm


def test_present_returns_value():
    assert require_auth_algorithm_set({"AUTH_GENERATION_ALGORITHM": "plain"}) == "plain"


def test_strips_whitespace():
    assert require_auth_algorithm_set({"AUTH_GENERATION_ALGORITHM": " plain "}) == "plain"


def test_absent_raises():
    with pytest.raises(MissingAuthAlgorithm):
        require_auth_algorithm_set({})


def test_blank_raises():
    with pytest.raises(MissingAuthAlgorithm):
        require_auth_algorithm_set({"AUTH_GENERATION_ALGORITHM": "   "})
