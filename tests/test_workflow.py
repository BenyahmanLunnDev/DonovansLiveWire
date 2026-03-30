from datetime import datetime
from zoneinfo import ZoneInfo

from wireman_tracker.workflow import should_run_schedule


def test_should_run_schedule_for_pacific_daylight_time() -> None:
    current = datetime(2026, 7, 1, 6, 7, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert should_run_schedule("7 13 * * *", at=current) is True
    assert should_run_schedule("7 14 * * *", at=current) is False


def test_should_run_schedule_for_pacific_standard_time() -> None:
    current = datetime(2026, 12, 1, 6, 7, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert should_run_schedule("7 14 * * *", at=current) is True
    assert should_run_schedule("7 13 * * *", at=current) is False
