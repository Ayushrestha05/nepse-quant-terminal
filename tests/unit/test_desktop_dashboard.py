import pytest

from apps.desktop.dashboard import _number


def test_number_input_accepts_finite_values_and_rejects_invalid_values():
    assert _number("1,234.5") == 1234.5
    assert _number("", fallback=2.0) == 2.0
    for value in ("abc", "nan", "inf"):
        with pytest.raises(ValueError):
            _number(value)
