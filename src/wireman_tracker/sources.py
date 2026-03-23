from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from wireman_tracker.browser import dump_dom
from wireman_tracker.config import (
    AREA1_APPLICATIONS_URL,
    BERGELECTRIC_QUERY_TERMS,
    EMCOR_QUERY_TERMS,
    MAX_DESCRIPTION_CHARS,
    MORTENSON_QUERY_TERMS,
    NIETC_CURRENT_OPENINGS_URL,
    OEG_BOARD_URL,
    OREGON_APPRENTICESHIP_OPENINGS_URL,
    OREGON_INSIDE_ELECTRICIAN_DETAILS_URL,
    SOURCE_URLS,
    TURNER_QUERY_TERMS,
    WASHINGTON_ARTS_PROXY_URL,
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


def _committee_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _format_area_label(areas: Iterable[int]) -> str:
    unique = sorted({int(area) for area in areas if str(area).strip().isdigit()})
    if not unique:
        return ""
    if len(unique) == 1:
        return f"Area {unique[0]}"
    if len(unique) == 2:
        return f"Areas {unique[0]} & {unique[1]}"
    head = ", ".join(str(area) for area in unique[:-1])
    return f"Areas {head}, & {unique[-1]}"


def _summarize_counties(county_names: list[str], limit: int = 6) -> str:
    cleaned = [clean_text(name) for name in county_names if clean_text(name)]
    if not cleaned:
        return ""

    unique = list(dict.fromkeys(cleaned))
    if len(unique) <= limit:
        return ", ".join(unique)
    return ", ".join(unique[:limit]) + f", +{len(unique) - limit} more"


OREGON_COUNTY_LABELS = {
    "all counties in oregon": "Oregon statewide coverage",
    "clackamas": "Portland metro",
    "multnomah": "Portland metro",
    "washington": "Portland metro",
    "yamhill": "Willamette Valley",
    "marion": "Willamette Valley",
    "polk": "Willamette Valley",
    "linn": "Willamette Valley",
    "lane": "Eugene corridor",
    "clatsop": "North Coast, OR",
    "tillamook": "North Coast, OR",
    "deschutes": "Central Oregon",
    "crook": "Central Oregon",
    "jackson": "Southern Oregon",
    "josephine": "Southern Oregon",
    "klamath": "Southern Oregon",
    "lake": "Southern Oregon",
    "morrow": "Eastern Oregon",
    "umatilla": "Eastern Oregon",
    "union": "Eastern Oregon",
    "wallowa": "Eastern Oregon",
    "baker": "Eastern Oregon",
    "gilliam": "Eastern Oregon",
    "wheeler": "Eastern Oregon",
}


def _dedupe_labels(values: Iterable[str]) -> list[str]:
    ordered: list[str] = []
    for value in values:
        cleaned = clean_text(value)
        if cleaned and cleaned not in ordered:
            ordered.append(cleaned)
    return ordered


def _canonicalize_washington_occupation(value: str) -> str:
    cleaned = clean_text(re.sub(r"\s*\(.*?\)\s*", "", value))
    if cleaned.lower() == "inside electrician":
        return "Inside Electrician"
    if cleaned.lower() == "inside wireman":
        return "Inside Wireman"
    return cleaned


def _summarize_oregon_county_coverage(county_names: list[str]) -> list[str]:
    labels: list[str] = []
    for county in county_names:
        normalized = clean_text(county).lower()
        label = OREGON_COUNTY_LABELS.get(normalized)
        if label and label not in labels:
            labels.append(label)
    return labels


def _load_oregon_openings_payload(session: requests.Session) -> dict:
    html = fetch_text(session, OREGON_APPRENTICESHIP_OPENINGS_URL)
    match = re.search(r"var\s+heccData\s*=\s*(\{.*?\});", html, re.S)
    if not match:
        raise RuntimeError("Could not locate Oregon Apprenticeship heccData payload.")
    return json.loads(match.group(1))


def _load_inside_electrician_detail_map(session: requests.Session) -> dict[str, dict[str, str]]:
    html = fetch_text(session, OREGON_INSIDE_ELECTRICIAN_DETAILS_URL)
    soup = BeautifulSoup(html, "html.parser")
    details: dict[str, dict[str, str]] = {}

    for row in soup.select("table tr"):
        cells = row.select("td")
        link = row.select_one('a[href*="apprenticeship-details.aspx?appid="]')
        if len(cells) < 3 or not link:
            continue

        committee = clean_text(cells[0].get_text(" ", strip=True))
        if not committee:
            continue

        details[_committee_key(committee)] = {
            "detail_url": absolute_url("https://www.oregon.gov", link["href"]),
            "average_wage": clean_text(cells[2].get_text(" ", strip=True)),
        }

    return details


def _fetch_area1_committee_status(session: requests.Session) -> dict:
    text = clean_text(BeautifulSoup(fetch_text(session, AREA1_APPLICATIONS_URL), "html.parser").get_text(" ", strip=True))
    match = re.search(
        r"Applications\s+for\s+(\d{4})\s+will\s+be\s+open\s+from:\s+([A-Za-z]+\s+\d{1,2}\w*)\s+to\s+([A-Za-z]+\s+\d{1,2}\w*)",
        text,
        re.I,
    )
    note = "Area I applications page did not expose a clear application window."
    window = ""
    posted_date = ""
    is_open = False

    if match:
        year, start_label, end_label = match.groups()
        window = f"{start_label}, {year} to {end_label}, {year}"
        note = f"Area I applications for {year} are open from {start_label} to {end_label}."
        normalized_start = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", start_label, flags=re.I)
        posted_date = f"{year}-{datetime.strptime(normalized_start, '%B %d').strftime('%m-%d')}"
        is_open = True

    return {
        "committee": "AREA I INSIDE ELECTRICAL JATC",
        "is_open": is_open,
        "detail_url": AREA1_APPLICATIONS_URL,
        "status_note": note,
        "application_window": window,
        "posted_date": posted_date,
        "status_source": "committee site",
    }


def _fetch_nietc_inside_status(session: requests.Session) -> dict:
    text = clean_text(
        BeautifulSoup(fetch_text(session, NIETC_CURRENT_OPENINGS_URL), "html.parser").get_text(" ", strip=True)
    )
    status_line = ""
    if "Inside Program – Closed" in text or "Inside Program - Closed" in text:
        status_line = "Inside Program - Closed"

    updated_match = re.search(r"updated\s+(\d{1,2}/\d{1,2}/\d{2,4})", text, re.I)
    slowdown_note = ""
    if "work slowdown" in text.lower():
        slowdown_note = " due to the current work slowdown and pause on new apprentice classes"

    note = "NIETC current application page did not expose a clear inside-electrician status."
    if status_line:
        note = f"NIETC lists the Inside Program as closed{slowdown_note}."
        if updated_match:
            note += f" Updated {updated_match.group(1)}."

    return {
        "committee": "NECA-IBEW ELECTRICAL JATC",
        "is_open": False,
        "detail_url": NIETC_CURRENT_OPENINGS_URL,
        "status_note": note,
        "posted_date": updated_match.group(1) if updated_match else "",
        "status_source": "committee site",
    }


def _direct_committee_overrides(session: requests.Session) -> dict[str, dict]:
    overrides = {}
    for payload in (_fetch_area1_committee_status(session), _fetch_nietc_inside_status(session)):
        overrides[_committee_key(payload["committee"])] = payload
    return overrides


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


def scrape_oregon_apprenticeship(session: requests.Session) -> tuple[list[JobLead], SourceReport]:
    report = SourceReport(
        source_key="oregonapprenticeship",
        source_name="Oregon Apprenticeship",
        source_url=SOURCE_URLS["oregonapprenticeship"],
    )
    payload = _load_oregon_openings_payload(session)
    detail_map = _load_inside_electrician_detail_map(session)
    overrides = _direct_committee_overrides(session)
    jobs: list[JobLead] = []
    skipped_due_to_direct_status = 0
    statewide_open_count = 0

    for standard in payload.get("standards", []):
        state_title = clean_text(standard.get("state_title"))
        trade_name = clean_text(standard.get("trade_name"))
        combined_title = f"{state_title} {trade_name}".lower()
        if "inside electrician" not in combined_title:
            continue

        is_open = bool(standard.get("is_open"))
        committee = clean_text(standard.get("committee"))
        committee_lookup = _committee_key(committee)
        override = overrides.get(committee_lookup)
        if override is not None:
            is_open = bool(override.get("is_open"))

        if standard.get("state") == "OR" and bool(standard.get("is_open")):
            statewide_open_count += 1

        if not is_open or clean_text(standard.get("state")) != "OR":
            if override and not override.get("is_open"):
                skipped_due_to_direct_status += 1
            continue

        county_entries = standard.get("counties") or {}
        county_names = [
            clean_text(item.get("county_text"))
            for item in county_entries.values()
            if isinstance(item, dict)
        ]
        area_numbers = [
            int(item.get("area"))
            for item in county_entries.values()
            if isinstance(item, dict) and str(item.get("area", "")).isdigit()
        ]
        area_label = _format_area_label(area_numbers)
        counties_summary = _summarize_counties(county_names)
        detail_info = detail_map.get(committee_lookup, {})
        detail_url = clean_text(override.get("detail_url") if override else "") or clean_text(detail_info.get("detail_url")) or SOURCE_URLS["oregonapprenticeship"]
        average_wage = clean_text(detail_info.get("average_wage"))
        location = clean_text(
            "; ".join(
                value
                for value in (
                    clean_text(f"{standard.get('city')}, {standard.get('state')}"),
                    area_label,
                )
                if value
            )
        )
        status_note = clean_text(override.get("status_note") if override else "")
        website = clean_text(standard.get("website"))
        contact = clean_text(standard.get("contact"))
        phone = clean_text(standard.get("phone"))
        email = clean_text(standard.get("email"))
        description_parts = [
            "Official Oregon Apprenticeship openings board currently lists this committee as open for Inside Electrician.",
            status_note,
            area_label,
            f"Counties: {counties_summary}" if counties_summary else "",
            f"Contact: {contact}" if contact else "",
            f"Phone: {phone}" if phone else "",
            f"Email: {email}" if email else "",
            f"Website: {website}" if website else "",
            f"Avg journey wage: {average_wage}" if average_wage else "",
        ]

        jobs.append(
            JobLead(
                job_key=stable_job_key("oregonapprenticeship", standard.get("identifier") or detail_url),
                source_key="oregonapprenticeship",
                source_name="Oregon Apprenticeship",
                company=committee,
                title=f"{state_title} Apprenticeship Intake Open",
                detail_url=detail_url,
                source_url=SOURCE_URLS["oregonapprenticeship"],
                location=location,
                posted_date=clean_text(override.get("posted_date") if override else ""),
                description=truncate_text(" | ".join(part for part in description_parts if part), MAX_DESCRIPTION_CHARS),
                source_context="Official Oregon Apprenticeship openings board",
                discovered_via=clean_text(override.get("status_source") if override else "state openings board"),
                metadata={
                    key: value
                    for key, value in {
                        "lead_type": "program",
                        "program_status": "open",
                        "program_status_source": clean_text(override.get("status_source") if override else "state openings board"),
                        "program_status_note": status_note,
                        "committee": committee,
                        "state_title": state_title,
                        "trade_name": trade_name,
                        "areas": area_label,
                        "counties": county_names,
                        "contact": contact,
                        "phone": phone,
                        "email": email,
                        "website": website,
                        "average_wage": average_wage,
                        "application_window": clean_text(override.get("application_window") if override else ""),
                    }.items()
                    if value
                },
            )
        )

    report.total_fetched = len(jobs)
    report.notes.append(
        f"Oregon Apprenticeship currently marks {statewide_open_count} Inside Electrician program entries as open statewide."
    )
    if skipped_due_to_direct_status:
        report.notes.append(
            f"Skipped {skipped_due_to_direct_status} committee entry where a direct committee page currently says applications are closed or paused."
        )
    nietc_override = overrides.get(_committee_key("NECA-IBEW ELECTRICAL JATC"))
    if nietc_override and nietc_override.get("status_note"):
        report.notes.append(clean_text(str(nietc_override["status_note"])))
    return dedupe_by_job_key(jobs), report


def _washington_arts_request(
    session: requests.Session,
    *,
    service_name: str,
    url_data: str,
    method: str,
    request_content: dict | None = None,
) -> requests.Response:
    payload: dict[str, str] = {
        "ServiceName": service_name,
        "UrlData": url_data,
        "RestHttpMethod": method,
    }
    if request_content is not None:
        payload["RequestContent"] = json.dumps(request_content)
    response = session.post(WASHINGTON_ARTS_PROXY_URL, json=payload, timeout=30)
    response.raise_for_status()
    return response


def _lookup_washington_programs(session: requests.Session, keyword: str) -> list[dict]:
    response = _washington_arts_request(
        session,
        service_name="ArtsPublic",
        url_data="api/ARTS/ExternalProgramOccupationLookup",
        method="POST",
        request_content={
            "Counties": [str(index) for index in range(1, 78, 2)],
            "KeywordSearch": keyword,
            "SOCCode": "",
            "SortByColumnName": "programName",
            "SortDirection": "asc",
            "StartRow": 0,
            "NumberOfRows": 25,
        },
    )
    payload = response.json()
    return payload if isinstance(payload, list) else []


def _fetch_washington_program_detail(session: requests.Session, program_id: int) -> dict:
    response = _washington_arts_request(
        session,
        service_name="ARTSPublic",
        url_data=f"api/ARTS/ExternalGetProgramDetail?programOccupationId=0&programId={program_id}",
        method="GET",
    )
    payload = response.json()
    return payload.get("returnValue", {}) if isinstance(payload, dict) else {}


def scrape_washington_apprenticeship(session: requests.Session) -> tuple[list[JobLead], SourceReport]:
    report = SourceReport(
        source_key="washingtonapprenticeship",
        source_name="Washington L&I Apprenticeship",
        source_url=SOURCE_URLS["washingtonapprenticeship"],
    )
    keywords = ("inside electrician", "inside wireman")
    grouped: dict[int, dict[str, object]] = {}

    for keyword in keywords:
        for item in _lookup_washington_programs(session, keyword):
            try:
                program_id = int(item.get("programId"))
            except (TypeError, ValueError):
                continue

            entry = grouped.setdefault(
                program_id,
                {
                    "program_id": program_id,
                    "program_name": clean_text(item.get("programName")),
                    "occupation_names": [],
                    "county_names": [],
                },
            )
            occupations = entry["occupation_names"]
            counties = entry["county_names"]
            if not isinstance(occupations, list) or not isinstance(counties, list):
                continue

            occupations.append(clean_text(item.get("occupationName")))
            counties.extend(
                clean_text(part)
                for part in clean_text(item.get("countyName")).split(",")
                if clean_text(part)
            )

    jobs: list[JobLead] = []
    oregon_serving_count = 0

    for program_id, entry in grouped.items():
        detail = _fetch_washington_program_detail(session, program_id)
        occupation_names = _dedupe_labels(
            _canonicalize_washington_occupation(value)
            for value in entry.get("occupation_names", [])
            if isinstance(value, str)
        )
        county_names = _dedupe_labels(entry.get("county_names", []))
        regional_matches = _summarize_oregon_county_coverage(county_names)
        if regional_matches:
            oregon_serving_count += 1

        title = " / ".join(occupation_names) if occupation_names else "Inside Electrician / Inside Wireman"
        title = f"{title} Apprenticeship Pathway"
        city_name = clean_text(detail.get("cityName")).strip(" ,")
        state_code = clean_text(detail.get("stateCode")).strip(" ,")
        location = clean_text(
            "; ".join(
                value
                for value in (
                    clean_text(f"{city_name}, {state_code}") if city_name and state_code else "",
                    f"Serves {truncate_text(', '.join(county_names), 120)}" if county_names else "",
                )
                if value
            )
        )
        detail_url = (
            f"{SOURCE_URLS['washingtonapprenticeship']}#/program-details"
            f"?programId={program_id}&from=%2Fprogram-search"
        )
        term_hours = clean_text(str(detail.get("termHours") or ""))
        journey_rate = clean_text(str(detail.get("journeyLevelRate") or ""))
        website = clean_text(detail.get("webSiteAddress"))
        standard_url = clean_text(detail.get("standardUrl"))
        contact = clean_text(detail.get("contactName"))
        phone = clean_text(detail.get("phoneNumber"))
        email = clean_text(detail.get("email"))
        description_parts = [
            "Official Washington L&I apprenticeship directory entry for this inside electrician / inside wireman pathway.",
            "Current public program details do not confirm whether applications are open, so treat this as a nearby pathway to check directly.",
            f"Coverage: {_summarize_counties(county_names, limit=8)}" if county_names else "",
            f"Oregon-facing coverage: {', '.join(regional_matches)}" if regional_matches else "",
            f"Contact: {contact}" if contact else "",
            f"Phone: {phone}" if phone else "",
            f"Email: {email}" if email else "",
            f"Website: {website}" if website else "",
            f"Standards PDF: {standard_url}" if standard_url else "",
            f"Term hours: {term_hours}" if term_hours else "",
            f"Journey wage: ${journey_rate}" if journey_rate else "",
        ]

        jobs.append(
            JobLead(
                job_key=stable_job_key("washingtonapprenticeship", str(program_id)),
                source_key="washingtonapprenticeship",
                source_name="Washington L&I Apprenticeship",
                company=clean_text(detail.get("programName")) or clean_text(str(entry.get("program_name", ""))),
                title=title,
                detail_url=detail_url,
                source_url=SOURCE_URLS["washingtonapprenticeship"],
                location=location,
                description=truncate_text(" | ".join(part for part in description_parts if part), MAX_DESCRIPTION_CHARS),
                source_context="Official Washington L&I apprenticeship directory",
                discovered_via="state apprenticeship directory",
                metadata={
                    key: value
                    for key, value in {
                        "lead_type": "pathway",
                        "program_status": "directory",
                        "program_status_source": "state apprenticeship directory",
                        "occupation_names": occupation_names,
                        "county_names": county_names,
                        "contact": contact,
                        "phone": phone,
                        "email": email,
                        "website": website,
                        "standard_url": standard_url,
                        "term_hours": term_hours,
                        "journey_wage": f"${journey_rate}" if journey_rate else "",
                        "regional_matches": regional_matches,
                        "program_id": program_id,
                    }.items()
                    if value
                },
            )
        )

    report.total_fetched = len(jobs)
    report.notes.append(
        f"Washington L&I currently lists {len(jobs)} inside wireman / inside electrician pathways from the public directory."
    )
    if oregon_serving_count:
        report.notes.append(
            f"{oregon_serving_count} Washington pathways explicitly cover Oregon counties or Oregon-wide service areas."
        )
    report.notes.append(
        "Washington directory entries are shown as pathways to check directly, not guaranteed-open application windows."
    )
    return dedupe_by_job_key(jobs), report


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
        ("oregonapprenticeship", lambda: scrape_oregon_apprenticeship(session)),
        ("washingtonapprenticeship", lambda: scrape_washington_apprenticeship(session)),
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
