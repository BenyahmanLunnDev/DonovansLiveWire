from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from wireman_tracker.config import KEEP_EXPIRED_DAYS, TIMEZONE_NAME
from wireman_tracker.models import JobLead, SourceReport
from wireman_tracker.utils import now_iso, repo_path, today_iso


def load_previous_jobs(root: Path) -> dict[str, JobLead]:
    current_path = repo_path(root, "data", "current", "jobs.json")
    if not current_path.exists():
        return {}

    payload = json.loads(current_path.read_text(encoding="utf-8"))
    jobs = [JobLead.from_dict(item) for item in payload.get("jobs", [])]
    return {job.job_key: job for job in jobs}


def load_previous_reports(root: Path) -> dict[str, SourceReport]:
    reports_path = repo_path(root, "data", "current", "reports.json")
    if not reports_path.exists():
        return {}

    payload = json.loads(reports_path.read_text(encoding="utf-8"))
    reports = [SourceReport.from_dict(item) for item in payload.get("reports", [])]
    return {report.source_key: report for report in reports}


def merge_with_history(
    current_jobs: list[JobLead],
    previous_jobs: dict[str, JobLead],
    reports: list[SourceReport],
) -> list[JobLead]:
    today = date.fromisoformat(today_iso())
    merged: dict[str, JobLead] = {}
    stale_sources = {report.source_key for report in reports if report.status == "error"}

    for job in current_jobs:
        previous = previous_jobs.get(job.job_key)
        if previous:
            job.first_seen = previous.first_seen or today.isoformat()
            job.seen_count = previous.seen_count + 1
        else:
            job.first_seen = today.isoformat()
            job.seen_count = 1

        job.last_seen = today.isoformat()
        job.expired_on = ""
        job.status = "active"
        job.stale_source = False
        job.stale_since = ""
        merged[job.job_key] = job

    keep_until = today - timedelta(days=KEEP_EXPIRED_DAYS)

    for key, previous in previous_jobs.items():
        if key in merged:
            continue

        if previous.status == "expired":
            expired_date = (
                date.fromisoformat(previous.expired_on)
                if previous.expired_on
                else date.fromisoformat(previous.last_seen or today.isoformat())
            )
            if expired_date < keep_until:
                continue
            merged[key] = previous
            continue

        if previous.source_key in stale_sources and previous.bucket in {"priority", "watch"}:
            stale_copy = JobLead.from_dict(previous.to_dict())
            stale_copy.status = "active"
            stale_copy.expired_on = ""
            stale_copy.stale_source = True
            stale_copy.stale_since = previous.stale_since or today.isoformat()
            merged[key] = stale_copy
            continue

        expired_copy = JobLead.from_dict(previous.to_dict())
        expired_copy.status = "expired"
        expired_copy.stale_source = False
        expired_copy.stale_since = ""
        expired_copy.expired_on = today.isoformat()
        merged[key] = expired_copy

    return sorted(
        merged.values(),
        key=lambda job: (
            job.status != "active",
            job.stale_source,
            -job.score,
            job.company.lower(),
            job.title.lower(),
        ),
    )


def save_artifacts(root: Path, jobs: list[JobLead], reports: list[SourceReport]) -> None:
    generated_at = now_iso()
    today = today_iso()

    current_dir = repo_path(root, "data", "current")
    history_dir = repo_path(root, "data", "history")
    docs_dir = repo_path(root, "docs")
    current_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": generated_at,
        "timezone": TIMEZONE_NAME,
        "jobs": [job.to_dict() for job in jobs],
    }
    current_path = current_dir / "jobs.json"
    current_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    history_payload = {
        "generated_at": generated_at,
        "timezone": TIMEZONE_NAME,
        "jobs": [job.to_dict() for job in jobs],
        "reports": [report.to_dict() for report in reports],
    }
    history_path = history_dir / f"{today}.json"
    history_path.write_text(json.dumps(history_payload, indent=2), encoding="utf-8")

    reports_path = current_dir / "reports.json"
    reports_path.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "reports": [report.to_dict() for report in reports],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
