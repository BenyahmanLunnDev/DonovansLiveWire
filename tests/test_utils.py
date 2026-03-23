from wireman_tracker.utils import extract_date


def test_extract_date_supports_numeric_dates() -> None:
    assert extract_date("Posted 3/11/2026 for this role.") == "3/11/2026"


def test_extract_date_supports_month_name_dates() -> None:
    assert extract_date("Posted Mar 13, 2026 for this role.") == "Mar 13, 2026"
