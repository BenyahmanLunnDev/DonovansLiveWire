from wireman_tracker.models import JobLead
from wireman_tracker.persistence import merge_with_history


def build_job(job_key: str, title: str) -> JobLead:
    return JobLead(
        job_key=job_key,
        source_key="test",
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
    merged = merge_with_history(current, {"job-1": previous})

    statuses = {job.job_key: job.status for job in merged}
    assert statuses["job-1"] == "expired"
    assert statuses["job-2"] == "active"


def test_merge_preserves_first_seen_for_existing_jobs() -> None:
    previous = build_job("job-1", "Electrical Apprentice")
    previous.first_seen = "2026-03-10"
    previous.last_seen = "2026-03-19"
    previous.seen_count = 4

    current = [build_job("job-1", "Electrical Apprentice")]
    merged = merge_with_history(current, {"job-1": previous})
    merged_job = next(job for job in merged if job.job_key == "job-1")

    assert merged_job.first_seen == "2026-03-10"
    assert merged_job.seen_count == 5
