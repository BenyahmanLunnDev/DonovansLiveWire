from __future__ import annotations

import argparse
import json
from pathlib import Path

from wireman_tracker.persistence import (
    load_previous_jobs,
    load_previous_reports,
    merge_with_history,
    save_artifacts,
)
from wireman_tracker.render import render_index, render_latest_json
from wireman_tracker.scoring import evaluate_job
from wireman_tracker.sources import scrape_all_sources
from wireman_tracker.utils import make_session, now_iso, repo_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Wireman Tracker pipeline.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to write generated files into.",
    )
    parser.add_argument(
        "--browser-path",
        default=None,
        help="Optional explicit browser binary for hydrated DOM fallback.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    session = make_session()
    generated_at = now_iso()

    scraped_jobs, reports = scrape_all_sources(session, browser_path=args.browser_path)
    scored_jobs = [evaluate_job(job) for job in scraped_jobs]
    previous_jobs = load_previous_jobs(root)
    previous_reports = load_previous_reports(root)

    for report in reports:
        previous = previous_reports.get(report.source_key)
        report.last_attempt_at = generated_at
        report.last_success_at = (
            generated_at if report.status != "error" else (previous.last_success_at if previous else "")
        )

    merged_jobs = merge_with_history(scored_jobs, previous_jobs, reports)

    for report in reports:
        active_relevant = [
            job
            for job in merged_jobs
            if job.source_key == report.source_key and job.status == "active" and job.bucket in {"priority", "watch"}
        ]
        report.total_relevant = len(active_relevant)
        report.stale_relevant_count = sum(1 for job in active_relevant if job.stale_source)
        report.serving_stale = report.status == "error" and report.stale_relevant_count > 0
        if report.serving_stale:
            report.notes.append(
                f"Serving {report.stale_relevant_count} last-known-good lead(s) until this source recovers."
            )
        elif report.status == "error" and not report.last_success_at and report.total_relevant == 0:
            report.notes.append("No last-known-good leads are available for this source yet.")
        elif report.status != "error" and previous_reports.get(report.source_key, None):
            previous = previous_reports.get(report.source_key)
            if previous and previous.status == "error":
                report.notes.append("Source recovered in this run after a previous outage.")

    save_artifacts(root, merged_jobs, reports)

    docs_dir = repo_path(root, "docs")
    docs_dir.mkdir(parents=True, exist_ok=True)
    repo_path(root, "docs", "index.html").write_text(
        render_index(generated_at, merged_jobs, reports),
        encoding="utf-8",
    )
    repo_path(root, "docs", "latest.json").write_text(
        render_latest_json(generated_at, merged_jobs, reports),
        encoding="utf-8",
    )
    repo_path(root, "data", "current", "summary.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "active_relevant": sum(
                    1
                    for job in merged_jobs
                    if job.status == "active" and job.bucket in {"priority", "watch"}
                ),
                "fresh_active_relevant": sum(
                    1
                    for job in merged_jobs
                    if job.status == "active" and job.bucket in {"priority", "watch"} and not job.stale_source
                ),
                "stale_active_relevant": sum(
                    1
                    for job in merged_jobs
                    if job.status == "active" and job.bucket in {"priority", "watch"} and job.stale_source
                ),
                "expired_relevant": sum(
                    1
                    for job in merged_jobs
                    if job.status == "expired" and job.bucket in {"priority", "watch"}
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return 0
