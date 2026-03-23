from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests

from wireman_tracker.config import DEFAULT_HEADERS, REQUEST_TIMEOUT_SECONDS, TIMEZONE


WHITESPACE_RE = re.compile(r"\s+")
DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
MONTH_DATE_RE = re.compile(
    r"\b("
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"[a-z]*\s+\d{1,2},\s+\d{4}"
    r")\b",
    re.IGNORECASE,
)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.replace("\xa0", " ").replace("\u202f", " ")
    cleaned = cleaned.replace("\r", " ").replace("\n", " ")
    cleaned = WHITESPACE_RE.sub(" ", cleaned)
    return cleaned.strip(" |")


def truncate_text(value: str, limit: int) -> str:
    value = clean_text(value)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def fetch_text(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text


def fetch_json(session: requests.Session, url: str, **kwargs) -> dict:
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS, **kwargs)
    response.raise_for_status()
    return response.json()


def absolute_url(base_url: str, maybe_relative: str) -> str:
    return urljoin(base_url, maybe_relative)


def ensure_query_parameter(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params[key] = value
    return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))


def stable_job_key(source_key: str, identifier: str) -> str:
    digest = hashlib.sha1(identifier.encode("utf-8")).hexdigest()
    return f"{source_key}:{digest}"


def today_local() -> datetime:
    return datetime.now(TIMEZONE)


def today_iso() -> str:
    return today_local().date().isoformat()


def now_iso() -> str:
    return today_local().isoformat()


def extract_date(value: str) -> str:
    match = DATE_RE.search(value)
    if match:
        return match.group(1)
    month_match = MONTH_DATE_RE.search(value)
    return month_match.group(1) if month_match else ""


def keep_best_text(*values: str) -> str:
    cleaned = [clean_text(value) for value in values if clean_text(value)]
    if not cleaned:
        return ""
    return max(cleaned, key=len)


def dedupe_by_job_key(jobs: Iterable) -> list:
    best: dict[str, object] = {}
    for job in jobs:
        current = best.get(job.job_key)
        if current is None:
            best[job.job_key] = job
            continue
        current_desc = getattr(current, "description", "")
        job_desc = getattr(job, "description", "")
        if len(job_desc) > len(current_desc):
            best[job.job_key] = job
    return list(best.values())


def repo_path(root: Path, *parts: str) -> Path:
    return root.joinpath(*parts)
