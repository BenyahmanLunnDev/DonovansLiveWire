from wireman_tracker.models import JobLead, SourceReport
from wireman_tracker.persistence import merge_with_history
from wireman_tracker.utils import today_iso


def build_job(job_key: str, title: str, *, source_key: str = "test") -> JobLead:
    return JobLead(
        job_key=job_key,
        source_key=source_key,
        source_name="Test",
        company="Test",
        title=title,
        detail_url=f"https://example.com/{job_key}",
        source_url="https://example.com",
        bucket="watch",
        score=60,
    )


def test_merge_marks_missing_jobs_as_expired() -> None:
    previous = build_job("job-1", "Electrical Apprentice")
    previous.first_seen = "2026-03-18"
    previous.last_seen = "2026-03-19"
    previous.status = "active"

    current = [build_job("job-2", "Inside Wireman Apprentice")]
    merged = merge_with_history(current, {"job-1": previous}, [])

    statuses = {job.job_key: job.status for job in merged}
    assert statuses["job-1"] == "expired"
    assert statuses["job-2"] == "active"


def test_merge_preserves_first_seen_for_existing_jobs() -> None:
    previous = build_job("job-1", "Electrical Apprentice")
    previous.first_seen = "2026-03-10"
    previous.last_seen = "2026-03-19"
    previous.seen_count = 4

    current = [build_job("job-1", "Electrical Apprentice")]
    merged = merge_with_history(current, {"job-1": previous}, [])
    merged_job = next(job for job in merged if job.job_key == "job-1")

    assert merged_job.first_seen == "2026-03-10"
    assert merged_job.seen_count == 5


def test_merge_keeps_last_good_job_when_source_errors() -> None:
    previous = build_job(
        "job-1",
        "Inside Wireman Apprenticeship Pathway",
        source_key="washingtonapprenticeship",
    )
    previous.first_seen = "2026-03-20"
    previous.last_seen = "2026-03-28"
    previous.status = "active"

    reports = [
        SourceReport(
            source_key="washingtonapprenticeship",
            source_name="Washington L&I Apprenticeship",
            source_url="https://secure.lni.wa.gov/arts-public/",
            status="error",
        )
    ]

    merged = merge_with_history([], {"job-1": previous}, reports)
    merged_job = next(job for job in merged if job.job_key == "job-1")

    assert merged_job.status == "active"
    assert merged_job.stale_source is True
    assert merged_job.stale_since == today_iso()
    assert merged_job.last_seen == "2026-03-28"


def test_merge_expires_stale_job_after_source_recovers_without_it() -> None:
    previous = build_job(
        "job-1",
        "Inside Wireman Apprenticeship Pathway",
        source_key="washingtonapprenticeship",
    )
    previous.first_seen = "2026-03-20"
    previous.last_seen = "2026-03-28"
    previous.status = "active"
    previous.stale_source = True
    previous.stale_since = "2026-03-29"

    reports = [
        SourceReport(
            source_key="washingtonapprenticeship",
            source_name="Washington L&I Apprenticeship",
            source_url="https://secure.lni.wa.gov/arts-public/",
            status="ok",
        )
    ]

    merged = merge_with_history([], {"job-1": previous}, reports)
    merged_job = next(job for job in merged if job.job_key == "job-1")

    assert merged_job.status == "expired"
    assert merged_job.stale_source is False
