from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from wireman_tracker.browser import dump_dom
from wireman_tracker.config import (
    BERGELECTRIC_QUERY_TERMS,
    EMCOR_QUERY_TERMS,
    MAX_DESCRIPTION_CHARS,
    MORTENSON_QUERY_TERMS,
    OEG_BOARD_URL,
    SOURCE_URLS,
    TURNER_QUERY_TERMS,
)
from wireman_tracker.models import JobLead, SourceReport
from wireman_tracker.utils import (
    absolute_url,
    clean_text,
    dedupe_by_job_key,
    ensure_query_parameter,
    extract_date,
    fetch_json,
    fetch_text,
    stable_job_key,
    truncate_text,
)


def _extract_pipe_field(text: str, label: str, stop_labels: Iterable[str]) -> str:
    tokens = [clean_text(token) for token in text.split("|") if clean_text(token)]
    stop_lookup = {value.lower() for value in stop_labels}
    label_lookup = label.lower()
    for index, token in enumerate(tokens):
        if token.lower() != label_lookup:
            continue
        values: list[str] = []
        for next_token in tokens[index + 1 :]:
            if next_token.lower() in stop_lookup:
                break
            values.append(next_token)
        return clean_text(", ".join(values))
    return ""


def _safe_fetch_text(session: requests.Session, url: str) -> str:
    try:
        return fetch_text(session, url)
    except Exception:
        return ""


def _build_icims_search_url(base_url: str, term: str) -> str:
    return (
        f"{base_url}/jobs/search?"
        f"ss=1&searchKeyword={quote_plus(term)}&searchRelation=keyword_all"
        "&mobile=false&width=1366&height=500&bga=true&needsRedirect=false"
        "&jan1offset=-480&jun1offset=-420&in_iframe=1"
    )


def _scrape_icims_source(
    session: requests.Session,
    *,
    source_key: str,
    source_name: str,
    source_url: str,
    search_base_url: str,
    query_terms: list[str],
    default_company: str,
) -> tuple[list[JobLead], SourceReport]:
    report = SourceReport(
        source_key=source_key,
        source_name=source_name,
        source_url=source_url,
    )
    jobs: list[JobLead] = []
    seen_urls: set[str] = set()

    for term in query_terms:
        search_url = _build_icims_search_url(search_base_url, term)
        html = fetch_text(session, search_url)
        soup = BeautifulSoup(html, "html.parser")

        for row in soup.select(".iCIMS_JobsTable .row"):
            link = row.select_one('a[href*="/jobs/"]')
            if not link:
                continue

            detail_url = absolute_url(search_base_url, link["href"])
            if "/jobs/login" in detail_url or detail_url in seen_urls:
                continue

            seen_urls.add(detail_url)
            title = clean_text(link.get_text(" ", strip=True)).replace("Title ", "").strip()
            row_text = clean_text(row.get_text(" | ", strip=True))

            detail_html = _safe_fetch_text(session, detail_url)
            detail_soup = BeautifulSoup(detail_html, "html.parser")
            content = detail_soup.select_one(".iCIMS_JobContent")
            description = (
                truncate_text(content.get_text(" | ", strip=True), MAX_DESCRIPTION_CHARS)
                if content
                else row_text
            )
            company = _extract_pipe_field(
                description,
                "Company",
                {"Category", "Position Type", "Location Type", "Posted Date", "Travel", "Remote"},
            ) or default_company
            location = (
                _extract_pipe_field(
                    description,
                    "Job Locations",
                    {"ID", "Company", "Category", "Position Type", "Location Type", "Travel", "Remote"},
                )
                or _extract_pipe_field(
                    row_text,
                    "Location",
                    {"ID", "Title", "Category", "Position Type", "Remote"},
                )
                or row_text
            )
            posted_date = extract_date(description) or extract_date(row_text)
            metadata = {
                "category": _extract_pipe_field(
                    description,
                    "Category",
                    {"Position Type", "Location Type", "Travel", "Remote", "Posted Date"},
                ),
                "position_type": _extract_pipe_field(
                    description,
                    "Position Type",
                    {"Location Type", "Travel", "Remote", "Posted Date"},
                ),
            }

            jobs.append(
                JobLead(
                    job_key=stable_job_key(source_key, detail_url),
                    source_key=source_key,
                    source_name=source_name,
                    company=company,
                    title=title,
                    detail_url=detail_url,
                    source_url=source_url,
                    location=location,
                    posted_date=posted_date,
                    description=description,
                    source_context=f"{source_name} iCIMS search query '{term}'",
                    discovered_via="iCIMS iframe search",
                    metadata={key: value for key, value in metadata.items() if value},
                )
            )

    report.total_fetched = len(jobs)
    return dedupe_by_job_key(jobs), report


def _parse_turner_cards(html: str, query_term: str) -> list[JobLead]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobLead] = []
    for anchor in soup.select('a[data-tag="displayJobTitle"][href]'):
        title = clean_text(anchor.get_text(" ", strip=True))
        detail_url = absolute_url("https://turnerconstruction.csod.com", anchor["href"])

        card = anchor
        while card and not (
            getattr(card, "select_one", None)
            and card.select_one('[data-tag="displayJobLocation"]')
        ):
            card = card.parent

        location = ""
        posted_date = ""
        if card:
            location_node = card.select_one('[data-tag="displayJobLocation"]')
            posted_node = card.select_one('[data-tag="displayJobPostingDate"]')
            location = clean_text(location_node.get_text(" ", strip=True)) if location_node else ""
            posted_date = clean_text(posted_node.get_text(" ", strip=True)) if posted_node else ""

        jobs.append(
            JobLead(
                job_key=stable_job_key("turner", detail_url),
                source_key="turner",
                source_name="Turner Construction",
                company="Turner Construction",
                title=title,
                detail_url=detail_url,
                source_url=SOURCE_URLS["turner"],
                location=location,
                posted_date=posted_date,
                source_context=f"Turner labor and skilled trade search query '{query_term}'",
                discovered_via="hydrated Chromium DOM",
            )
        )
    return jobs


def _parse_oeg_cards(html: str) -> list[JobLead]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobLead] = []

    for card in soup.select('div.opportunity[data-automation="opportunity"]'):
        link = card.select_one('a[data-automation="job-title"][href]')
        if not link:
            continue

        title = clean_text(link.get_text(" ", strip=True))
        detail_url = absolute_url(OEG_BOARD_URL, link["href"])
        posted_date = clean_text(
            (card.select_one('small[data-automation="opportunity-posted-date"]') or card).get_text(
                " ",
                strip=True,
            )
        )
        locations = [
            clean_text(node.get_text(" ", strip=True))
            for node in card.select('span[data-automation="city-state-zip-country-label"]')
        ]
        location = clean_text("; ".join(dict.fromkeys(value for value in locations if value)))
        description = truncate_text(card.get_text(" | ", strip=True), MAX_DESCRIPTION_CHARS)
        metadata = {
            "category": clean_text(
                (card.select_one('span[data-automation="job-category"]') or card).get_text(" ", strip=True)
            ),
            "schedule": clean_text(
                (card.select_one('span[data-automation="job-hours"]') or card).get_text(" ", strip=True)
            ),
            "job_location_type": clean_text(
                (card.select_one('span[data-automation="job-location-type"]') or card).get_text(" ", strip=True)
            ),
        }

        jobs.append(
            JobLead(
                job_key=stable_job_key("oeg", detail_url),
                source_key="oeg",
                source_name="OEG",
                company="OEG",
                title=title,
                detail_url=detail_url,
                source_url=SOURCE_URLS["oeg"],
                location=location,
                posted_date=posted_date,
                description=description,
                source_context="OEG UKG careers board",
                discovered_via="hydrated Chromium DOM",
                metadata={key: value for key, value in metadata.items() if value},
            )
        )

    return dedupe_by_job_key(jobs)


def _turner_detail_needed(title: str) -> bool:
    title_lower = title.lower()
    return any(
        phrase in title_lower
        for phrase in ("apprentice", "electrician", "electrical apprentice", "wireman")
    )


def scrape_cei(session: requests.Session) -> tuple[list[JobLead], SourceReport]:
    report = SourceReport(
        source_key="cei",
        source_name="Cupertino Electric",
        source_url=SOURCE_URLS["cei"],
    )
    jobs: list[JobLead] = []

    list_url = ensure_query_parameter("https://jobs.jobvite.com/cei", "nl", "1")
    html = fetch_text(session, list_url)
    soup = BeautifulSoup(html, "html.parser")

    for row in soup.select(".jv-job-list tbody tr"):
        link = row.select_one(".jv-job-list-name a[href]")
        if not link:
            continue

        title = clean_text(link.get_text(" ", strip=True))
        detail_url = ensure_query_parameter(
            absolute_url("https://jobs.jobvite.com/cei", link["href"]),
            "nl",
            "1",
        )
        location = clean_text(
            (row.select_one(".jv-job-list-location") or row).get_text(" ", strip=True)
        )

        detail_html = _safe_fetch_text(session, detail_url)
        detail_soup = BeautifulSoup(detail_html, "html.parser")
        detail_page = detail_soup.select_one(".jv-page")
        description = (
            truncate_text(detail_page.get_text(" | ", strip=True), MAX_DESCRIPTION_CHARS)
            if detail_page
            else ""
        )
        title_node = detail_soup.select_one(".jv-page h2")
        if title_node:
            title = clean_text(title_node.get_text(" ", strip=True))

        jobs.append(
            JobLead(
                job_key=stable_job_key("cei", detail_url),
                source_key="cei",
                source_name="Cupertino Electric",
                company="Cupertino Electric",
                title=title,
                detail_url=detail_url,
                source_url=SOURCE_URLS["cei"],
                location=location,
                posted_date=extract_date(description),
                description=description,
                source_context="CEI Jobvite careers feed",
                discovered_via="Jobvite no-layout listing",
            )
        )

    report.total_fetched = len(jobs)
    return dedupe_by_job_key(jobs), report


def scrape_emcor(session: requests.Session) -> tuple[list[JobLead], SourceReport]:
    return _scrape_icims_source(
        session,
        source_key="emcor",
        source_name="EMCOR Group",
        source_url=SOURCE_URLS["emcor"],
        search_base_url="https://careers-emcorgroup.icims.com",
        query_terms=EMCOR_QUERY_TERMS,
        default_company="EMCOR Group",
    )


def scrape_bergelectric(session: requests.Session) -> tuple[list[JobLead], SourceReport]:
    return _scrape_icims_source(
        session,
        source_key="bergelectric",
        source_name="Bergelectric",
        source_url=SOURCE_URLS["bergelectric"],
        search_base_url="https://careers-bergelectric.icims.com",
        query_terms=BERGELECTRIC_QUERY_TERMS,
        default_company="Bergelectric Corp.",
    )


def scrape_primeelectric(session: requests.Session) -> tuple[list[JobLead], SourceReport]:
    report = SourceReport(
        source_key="primeelectric",
        source_name="PRIME Electric",
        source_url=SOURCE_URLS["primeelectric"],
    )
    jobs: list[JobLead] = []

    payload = fetch_json(
        session,
        "https://api.lever.co/v0/postings/primee",
        params={"mode": "json"},
    )

    for item in payload:
        detail_url = clean_text(item.get("hostedUrl") or item.get("applyUrl"))
        if not detail_url:
            continue

        categories = item.get("categories") or {}
        location = clean_text(
            categories.get("location") or ", ".join(categories.get("allLocations") or [])
        )
        description = truncate_text(
            " | ".join(
                part
                for part in (
                    clean_text(item.get("openingPlain")),
                    clean_text(item.get("descriptionPlain")),
                    clean_text(item.get("additionalPlain")),
                )
                if part
            ),
            MAX_DESCRIPTION_CHARS,
        )
        created_at = item.get("createdAt")
        posted_date = ""
        if isinstance(created_at, (int, float)):
            posted_date = datetime.fromtimestamp(created_at / 1000, tz=timezone.utc).date().isoformat()

        context_parts = [
            "PRIME Electric Lever careers feed",
            clean_text(categories.get("department")),
            clean_text(categories.get("team")),
            clean_text(categories.get("commitment")),
        ]

        jobs.append(
            JobLead(
                job_key=stable_job_key("primeelectric", detail_url),
                source_key="primeelectric",
                source_name="PRIME Electric",
                company="PRIME Electric",
                title=clean_text(item.get("text")),
                detail_url=detail_url,
                source_url=SOURCE_URLS["primeelectric"],
                location=location,
                posted_date=posted_date,
                description=description,
                source_context=" | ".join(part for part in context_parts if part),
                discovered_via="Lever JSON API",
                metadata={
                    key: value
                    for key, value in {
                        "department": clean_text(categories.get("department")),
                        "team": clean_text(categories.get("team")),
                        "commitment": clean_text(categories.get("commitment")),
                        "workplace_type": clean_text(item.get("workplaceType")),
                    }.items()
                    if value
                },
            )
        )

    report.total_fetched = len(jobs)
    return dedupe_by_job_key(jobs), report


def scrape_oeg(
    session: requests.Session,
    browser_path: str | None = None,
) -> tuple[list[JobLead], SourceReport]:
    report = SourceReport(
        source_key="oeg",
        source_name="OEG",
        source_url=SOURCE_URLS["oeg"],
        used_browser=True,
    )

    html = dump_dom(OEG_BOARD_URL, browser_path=browser_path)
    jobs = _parse_oeg_cards(html)

    for job in jobs:
        if not _turner_detail_needed(job.title):
            continue
        detail_html = dump_dom(job.detail_url, browser_path=browser_path)
        detail_soup = BeautifulSoup(detail_html, "html.parser")
        detail_text = clean_text(detail_soup.get_text(" | ", strip=True))
        if detail_text:
            job.description = truncate_text(detail_text, MAX_DESCRIPTION_CHARS)
            job.posted_date = extract_date(detail_text) or job.posted_date

    report.total_fetched = len(jobs)
    return jobs, report


def scrape_mortenson(session: requests.Session) -> tuple[list[JobLead], SourceReport]:
    report = SourceReport(
        source_key="mortenson",
        source_name="Mortenson",
        source_url=SOURCE_URLS["mortenson"],
    )
    jobs: list[JobLead] = []
    search_page_url = "https://www.mortenson.com/careers/search"
    landing_html = fetch_text(session, search_page_url)
    landing_soup = BeautifulSoup(landing_html, "html.parser")

    api_token = landing_soup.select_one('meta[name="coveo_api_token"]')
    org_id = landing_soup.select_one('meta[name="coveo_org_id"]')
    if not api_token or not org_id:
        report.status = "error"
        report.errors.append("Could not locate Mortenson Coveo credentials on the careers search page.")
        return jobs, report

    api_url = f"https://platform.cloud.coveo.com/rest/search/v2?organizationId={org_id['content']}"
    headers = {"Authorization": f"Bearer {api_token['content']}", "Content-Type": "application/json"}
    seen_urls: set[str] = set()

    for term in MORTENSON_QUERY_TERMS:
        response = session.post(
            api_url,
            headers=headers,
            json={
                "q": term,
                "searchHub": "mortenson_careers_search",
                "pipeline": "Mortenson Careers Search Pipeline",
                "numberOfResults": 50,
                "fieldsToInclude": [
                    "category",
                    "team",
                    "country",
                    "state",
                    "city",
                    "clickableuri",
                    "source",
                    "title",
                    "date",
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        for result in payload.get("results", []):
            raw = result.get("raw", {})
            detail_url = result.get("clickUri") or raw.get("clickableuri")
            if not detail_url or detail_url in seen_urls:
                continue

            seen_urls.add(detail_url)
            detail_html = _safe_fetch_text(session, detail_url)
            detail_soup = BeautifulSoup(detail_html, "html.parser")
            title_node = detail_soup.select_one(".cmp-title")
            title = clean_text(title_node.get_text(" ", strip=True)) if title_node else clean_text(result.get("title"))
            text_blocks = [
                clean_text(node.get_text(" ", strip=True))
                for node in detail_soup.select(".cmp-text")
                if clean_text(node.get_text(" ", strip=True))
            ]
            description = truncate_text(" | ".join(text_blocks[:8]), MAX_DESCRIPTION_CHARS)
            date_value = raw.get("date")
            posted_date = ""
            if isinstance(date_value, (float, int)):
                posted_date = datetime.fromtimestamp(date_value / 1000, tz=timezone.utc).date().isoformat()

            location_parts = [raw.get("city"), raw.get("state"), raw.get("country")]
            location = clean_text(", ".join(str(part) for part in location_parts if part))
            context_parts = [str(raw.get("team") or ""), str(raw.get("category") or ""), f"query {term}"]

            jobs.append(
                JobLead(
                    job_key=stable_job_key("mortenson", detail_url),
                    source_key="mortenson",
                    source_name="Mortenson",
                    company="Mortenson",
                    title=title,
                    detail_url=detail_url,
                    source_url=SOURCE_URLS["mortenson"],
                    location=location,
                    posted_date=posted_date,
                    description=description,
                    source_context=" | ".join(part for part in context_parts if part),
                    discovered_via="Mortenson Coveo search",
                    metadata={
                        "team": raw.get("team"),
                        "category": raw.get("category"),
                    },
                )
            )

    report.total_fetched = len(jobs)
    return dedupe_by_job_key(jobs), report


def scrape_turner(
    session: requests.Session,
    browser_path: str | None = None,
) -> tuple[list[JobLead], SourceReport]:
    report = SourceReport(
        source_key="turner",
        source_name="Turner Construction",
        source_url=SOURCE_URLS["turner"],
        used_browser=True,
    )
    jobs: list[JobLead] = []

    for term in TURNER_QUERY_TERMS:
        search_url = f"https://turnerconstruction.csod.com/ux/ats/careersite/4/home?c=turnerconstruction&sq={quote_plus(term)}"
        html = dump_dom(search_url, browser_path=browser_path)
        jobs.extend(_parse_turner_cards(html, term))

    deduped = dedupe_by_job_key(jobs)
    for job in deduped:
        if not _turner_detail_needed(job.title):
            continue
        detail_html = dump_dom(job.detail_url, browser_path=browser_path)
        detail_soup = BeautifulSoup(detail_html, "html.parser")
        detail_block = detail_soup.select_one(".p-view-jobdetails")
        if detail_block:
            job.description = truncate_text(
                detail_block.get_text(" | ", strip=True),
                MAX_DESCRIPTION_CHARS,
            )
            job.posted_date = extract_date(job.description) or job.posted_date

    report.total_fetched = len(deduped)
    return deduped, report


def scrape_kiewit(session: requests.Session) -> tuple[list[JobLead], SourceReport]:
    report = SourceReport(
        source_key="kiewit",
        source_name="Kiewit",
        source_url=SOURCE_URLS["kiewit"],
        status="warning",
    )

    html = fetch_text(session, SOURCE_URLS["kiewit"])
    if "formstack.com/forms/kiewit_union_interest_form" in html:
        report.notes.append(
            "The Kiewit union craft page currently behaves like an interest form rather than an openings feed."
        )
    else:
        report.notes.append("Kiewit did not expose structured listings from the supplied landing page.")

    report.total_fetched = 0
    return [], report


def scrape_all_sources(
    session: requests.Session,
    browser_path: str | None = None,
) -> tuple[list[JobLead], list[SourceReport]]:
    jobs: list[JobLead] = []
    reports: list[SourceReport] = []
    source_calls = [
        ("cei", lambda: scrape_cei(session)),
        ("emcor", lambda: scrape_emcor(session)),
        ("bergelectric", lambda: scrape_bergelectric(session)),
        ("primeelectric", lambda: scrape_primeelectric(session)),
        ("oeg", lambda: scrape_oeg(session, browser_path=browser_path)),
        ("mortenson", lambda: scrape_mortenson(session)),
        ("turner", lambda: scrape_turner(session, browser_path=browser_path)),
        ("kiewit", lambda: scrape_kiewit(session)),
    ]

    for source_key, fetcher in source_calls:
        try:
            source_jobs, report = fetcher()
        except Exception as exc:
            fallback_report = SourceReport(
                source_key=source_key,
                source_name=source_key.title(),
                source_url=SOURCE_URLS.get(source_key, ""),
                status="error",
                errors=[str(exc)],
            )
            reports.append(fallback_report)
            continue

        jobs.extend(source_jobs)
        reports.append(report)

    return dedupe_by_job_key(jobs), reports
