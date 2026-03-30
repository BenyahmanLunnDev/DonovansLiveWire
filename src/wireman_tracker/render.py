from __future__ import annotations

import json
import re
from datetime import datetime
from html import escape
from urllib.parse import quote

from wireman_tracker.models import JobLead, SourceReport


STATE_NAME_LOOKUP = {
    "AZ": "Arizona",
    "CA": "California",
    "CO": "Colorado",
    "ID": "Idaho",
    "IN": "Indiana",
    "LA": "Louisiana",
    "MT": "Montana",
    "ND": "North Dakota",
    "NM": "New Mexico",
    "OH": "Ohio",
    "OR": "Oregon",
    "SD": "South Dakota",
    "TX": "Texas",
    "WA": "Washington",
    "WY": "Wyoming",
}


def _favicon_data_uri() -> str:
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
        "<rect width='64' height='64' rx='16' fill='#081120'/>"
        "<path d='M35 6L16 36h12l-3 22 23-31H36l-1-21z' fill='#fbbf24'/>"
        "</svg>"
    )
    return f"data:image/svg+xml,{quote(svg)}"


def _badge(label: str, tone: str) -> str:
    tone_map = {
        "priority": "badge-priority",
        "watch": "badge-watch",
        "status": "badge-status",
        "source": "badge-source",
        "hub": "badge-hub",
        "regional": "badge-regional",
        "warn": "badge-warn",
        "relocation": "badge-relocation",
        "expired": "badge-expired",
        "stale": "badge-stale",
    }
    classes = tone_map.get(tone, "badge-source")
    return f'<span class="badge {classes}">{escape(label)}</span>'


def _format_date_label(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return raw
    return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"


def _format_datetime_label(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value

    tz_name = parsed.strftime("%Z") or "local"
    hour = parsed.strftime("%I").lstrip("0") or "12"
    return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year} at {hour}:{parsed.strftime('%M')} {parsed.strftime('%p')} {tz_name}"


def _format_location(value: str) -> str:
    raw = value.strip()
    if not raw:
        return "Location not listed"

    compact = raw.replace(";", ",")
    matches = re.findall(r"\bUS-([A-Z]{2})-([^,;]+)", compact)
    if matches:
        return "; ".join(f"{city.replace('-', ' ').strip()}, {state}" for state, city in matches)

    state_only = re.fullmatch(r"([A-Z]{2}),\s+United States", raw)
    if state_only:
        state = state_only.group(1)
        return STATE_NAME_LOOKUP.get(state, state)

    if raw.endswith(", United States"):
        return raw[: -len(", United States")]

    return raw


def _reason_chips(job: JobLead) -> list[str]:
    labels: list[str] = []
    if job.metadata.get("lead_type") == "program":
        labels.append("Open intake")
        if str(job.metadata.get("program_status_source", "")).lower() == "committee site":
            labels.append("Committee-confirmed")
        else:
            labels.append("Official board")
    elif job.source_key == "californiaapprenticeship":
        labels.append("California sponsor")
        labels.append("Check directly")
    elif job.metadata.get("lead_type") == "pathway":
        labels.append("Official pathway")
        if job.metadata.get("regional_matches"):
            labels.append("Nearby coverage")

    if any("data center" in reason for reason in job.reasons):
        labels.append("Data center")
    if any("mission critical" in reason for reason in job.reasons):
        labels.append("Mission-critical")
    if any("regional apprentice opportunity" in reason for reason in job.reasons):
        labels.append("Regional fit")
    if any("low voltage" in reason for reason in job.reasons):
        labels.append("Low-voltage track")
    if any("trainee" in reason for reason in job.reasons):
        labels.append("Trainee track")
    if any(
        phrase in reason
        for reason in job.reasons
        for phrase in ("title matches 'apprentice electrician'", "title matches 'electrical apprentice'", "title matches 'electrician apprentice'")
    ):
        labels.append("Direct apprentice title")
    if job.metadata.get("relocation_assistance"):
        labels.append("Relocation mentioned")

    if not labels:
        labels.append("Trade-fit match")

    deduped: list[str] = []
    for label in labels:
        if label not in deduped:
            deduped.append(label)
    return deduped[:3]


def _truncate(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _list_preview(values: list[str] | tuple[str, ...], limit: int = 6) -> str:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return ", ".join(cleaned)
    return f"{', '.join(cleaned[:limit])}, +{len(cleaned) - limit} more"


def _lead_label(job: JobLead) -> tuple[str, str]:
    lead_type = str(job.metadata.get("lead_type", "")).lower()
    if lead_type == "program":
        return ("Open Intake", "status")
    if job.source_key == "californiaapprenticeship":
        return ("California Sponsor", "regional")
    if lead_type == "pathway":
        return ("Official Pathway", "watch")
    if job.bucket == "priority":
        return ("Priority Job", "priority")
    if job.metadata.get("regional_matches"):
        return ("Regional Opening", "regional")
    return ("National Opening", "source")


def _lead_action(job: JobLead) -> tuple[str, str]:
    lead_type = str(job.metadata.get("lead_type", "")).lower()
    if lead_type == "program":
        return (job.detail_url, "View intake details")
    if job.source_key == "californiaapprenticeship":
        return (job.detail_url, "Check sponsor entry")
    if lead_type == "pathway":
        return (job.detail_url, "Check official pathway")
    if job.status == "expired":
        return (job.detail_url, "Open old listing")
    return (job.detail_url, "Open listing")


def _primary_place(job: JobLead) -> str:
    place = _format_location(job.location)
    return place.split(";", 1)[0].strip()


def _secondary_place(job: JobLead) -> str:
    place = _format_location(job.location)
    if ";" not in place:
        return ""
    return place.split(";", 1)[1].strip()


def _coverage_line(job: JobLead) -> str:
    lead_type = str(job.metadata.get("lead_type", "")).lower()
    if lead_type == "program":
        areas = str(job.metadata.get("areas", "")).strip()
        counties = _list_preview(job.metadata.get("counties", []), limit=5)
        if areas and counties:
            return f"{areas} · {counties}"
        return areas or counties
    if lead_type == "pathway":
        regional = _list_preview(job.metadata.get("regional_matches", []), limit=2)
        counties = _list_preview(job.metadata.get("county_names", []), limit=5)
        if regional and counties:
            return f"{regional} · {counties}"
        return regional or counties
    secondary_place = _secondary_place(job)
    if secondary_place:
        return secondary_place
    return _list_preview(job.hub_matches, limit=2)


def _contact_line(job: JobLead) -> str:
    contact = str(job.metadata.get("contact", "")).strip()
    phone = str(job.metadata.get("phone", "")).strip()
    website = str(job.metadata.get("website", "")).strip()
    if contact and phone:
        return f"{contact} · {phone}"
    if contact:
        return contact
    if phone:
        return phone
    if website:
        return website
    return ""


def _status_note(job: JobLead) -> str:
    lead_type = str(job.metadata.get("lead_type", "")).lower()
    if job.status == "expired":
        removed = _format_date_label(job.expired_on or job.last_seen)
        return f"Removed {removed}" if removed else "No longer listed on source."
    if job.stale_source and job.last_seen:
        return f"Last verified {_format_date_label(job.last_seen)}"
    if lead_type == "program":
        status_note = str(job.metadata.get("program_status_note", "")).strip()
        if status_note:
            return status_note
        if str(job.metadata.get("program_status_source", "")).lower() == "committee site":
            return "Committee page confirms the window."
        return "Official board currently lists this intake as open."
    if job.source_key == "californiaapprenticeship":
        return "Official sponsor record. Check directly for intake timing."
    if lead_type == "pathway":
        return "Official directory record. Public status is not confirmed open."
    if job.first_seen == job.last_seen:
        return "New in this scrape."
    posted = _format_date_label(job.posted_date)
    if posted:
        return f"Posted {posted}"
    return "Previously seen and still active."


def _job_blurb(job: JobLead) -> str:
    lead_type = str(job.metadata.get("lead_type", "")).lower()
    parts: list[str] = []

    if lead_type == "program":
        parts.append("Official apprenticeship intake for Donovan’s target trade.")
        status_note = str(job.metadata.get("program_status_note", "")).strip()
        if status_note:
            parts.append(status_note)
        coverage = _coverage_line(job)
        if coverage:
            parts.append(f"Coverage: {coverage}")
        contact = _contact_line(job)
        if contact:
            parts.append(f"Contact: {contact}")
        average_wage = str(job.metadata.get("average_wage", "")).strip()
        if average_wage:
            parts.append(f"Avg. journey wage: {average_wage}")
        return _truncate(" | ".join(part for part in parts if part), 240)

    if lead_type == "pathway":
        if job.source_key == "californiaapprenticeship":
            parts.append("Official California apprenticeship sponsor listing.")
        else:
            parts.append("Official nearby apprenticeship pathway listing.")
        parts.append("Use this as a real sponsor or program contact, not a guaranteed-open job posting.")
        coverage = _coverage_line(job)
        if coverage:
            parts.append(f"Coverage: {coverage}")
        contact = _contact_line(job)
        if contact:
            parts.append(f"Contact: {contact}")
        return _truncate(" | ".join(part for part in parts if part), 235)

    description = job.description or "Description not captured for this listing yet."
    return _truncate(description, 220)


def _california_pathway_sort_key(job: JobLead) -> tuple[int, int, str]:
    regional_text = " ".join(str(value).lower() for value in job.metadata.get("regional_matches", []))
    location_text = job.location.lower()

    if any(term in regional_text for term in ("northern california", "sacramento", "bay area")):
        region_rank = 0
    elif ", or" in location_text or ", nv" in location_text:
        region_rank = 0
    elif "central valley" in regional_text:
        region_rank = 1
    elif "southern california" in regional_text:
        region_rank = 2
    else:
        region_rank = 3

    return (region_rank, -job.score, job.company.lower())


def _search_text(job: JobLead) -> str:
    return " ".join(
        part
        for part in (
            job.title,
            job.company,
            job.location,
            job.source_name,
            job.description,
        )
        if part
    ).lower()


def _card_attrs(job: JobLead, lane: str) -> str:
    lead_type = str(job.metadata.get("lead_type", "")).lower()
    return (
        f'data-search="{escape(_search_text(job))}" '
        f'data-lane="{escape(lane)}" '
        f'data-bucket="{escape(job.bucket)}" '
        f'data-kind="{"program" if lead_type == "program" else ("pathway" if lead_type == "pathway" else "job")}" '
        f'data-region="{"1" if job.metadata.get("regional_matches") else "0"}" '
        f'data-relocation="{"1" if job.metadata.get("relocation_assistance") else "0"}" '
        f'data-new="{"1" if job.first_seen == job.last_seen and job.status == "active" else "0"}" '
        f'data-stale="{"1" if job.stale_source else "0"}" '
        f'data-official="{"1" if lead_type in {"program", "pathway"} else "0"}"'
    )


def _directory_card(job: JobLead, lane: str) -> str:
    label_text, label_tone = _lead_label(job)
    action_url, action_label = _lead_action(job)
    verification_badge = (
        _badge("Committee-confirmed", "hub")
        if str(job.metadata.get("program_status_source", "")).lower() == "committee site"
        else (
            _badge("Official board", "watch")
            if job.metadata.get("lead_type") == "program"
            else (
                _badge("Check directly", "watch")
                if job.metadata.get("lead_type") == "pathway"
                else ""
            )
        )
    )
    status_badge = _badge("Stale source", "stale") if job.stale_source else ""
    coverage = _coverage_line(job)
    contact = _contact_line(job)
    reason_chips = "".join(_badge(label, "watch") for label in _reason_chips(job))
    debug_reasons = "".join(f"<li>{escape(reason)}</li>" for reason in job.reasons)

    return f"""
    <article class="job-card job-card--directory" {_card_attrs(job, lane)}>
      <div class="job-card__cluster">
        {_badge(label_text, label_tone)}
        {verification_badge}
        {status_badge}
      </div>
      <p class="job-card__place">{escape(_primary_place(job))}</p>
      <h3 class="job-card__title"><a href="{escape(action_url)}">{escape(job.company)}</a></h3>
      <p class="job-card__subtitle">{escape(job.title)}</p>
      <p class="job-card__description">{escape(_job_blurb(job))}</p>
      <dl class="job-card__facts">
        <div>
          <dt>Status</dt>
          <dd>{escape(_status_note(job))}</dd>
        </div>
        {'<div><dt>Coverage</dt><dd>' + escape(coverage) + '</dd></div>' if coverage else ''}
        {'<div><dt>Contact</dt><dd>' + escape(contact) + '</dd></div>' if contact else ''}
      </dl>
      <div class="job-card__reasons">{reason_chips}</div>
      <div class="job-card__footer">
        <span class="job-card__score">{escape(job.source_name)}</span>
        <a class="job-card__link" href="{escape(action_url)}">{escape(action_label)}</a>
      </div>
      <details class="job-card__details">
        <summary>Why it made the board</summary>
        <ul>{debug_reasons}</ul>
      </details>
    </article>
    """


def _opening_card(job: JobLead, lane: str) -> str:
    label_text, label_tone = _lead_label(job)
    action_url, action_label = _lead_action(job)
    status_badge = (
        _badge("No longer on source", "expired")
        if job.status == "expired"
        else (
            _badge("Stale source", "stale")
            if job.stale_source
            else (
                _badge("New this run", "status")
                if job.first_seen == job.last_seen
                else _badge("Seen before", "source")
            )
        )
    )
    supporting_badges = []
    if job.metadata.get("relocation_assistance"):
        supporting_badges.append(_badge("Relocation listed", "relocation"))
    for hub in job.hub_matches[:1]:
        supporting_badges.append(_badge(hub, "hub"))
    if not supporting_badges and job.metadata.get("regional_matches"):
        supporting_badges.append(_badge(job.metadata["regional_matches"][0], "regional"))
    secondary_place = _secondary_place(job)
    company_line = job.company
    if secondary_place:
        company_line = f"{job.company} · {secondary_place}"
    reason_chips = "".join(_badge(label, "watch") for label in _reason_chips(job))
    debug_reasons = "".join(f"<li>{escape(reason)}</li>" for reason in job.reasons)

    return f"""
    <article class="job-card job-card--opening" {_card_attrs(job, lane)}>
      <div class="job-card__cluster">
        {status_badge}
        {_badge(label_text, label_tone)}
        {''.join(supporting_badges)}
      </div>
      <p class="job-card__place">{escape(_primary_place(job))}</p>
      <h3 class="job-card__title"><a href="{escape(action_url)}">{escape(job.title)}</a></h3>
      <p class="job-card__subtitle">{escape(company_line)}</p>
      <p class="job-card__meta">{escape(_status_note(job))}</p>
      <p class="job-card__description">{escape(_job_blurb(job))}</p>
      <div class="job-card__reasons">{reason_chips}</div>
      <div class="job-card__footer">
        <span class="job-card__score">{escape(f'Score {job.score}')}</span>
        <a class="job-card__link" href="{escape(action_url)}">{escape(action_label)}</a>
      </div>
      <details class="job-card__details">
        <summary>Why it made the board</summary>
        <ul>{debug_reasons}</ul>
      </details>
    </article>
    """


def _job_card(job: JobLead, lane: str) -> str:
    if str(job.metadata.get("lead_type", "")).lower() in {"program", "pathway"}:
        return _directory_card(job, lane)
    return _opening_card(job, lane)


def _feed_row(job: JobLead) -> str:
    action_url, action_label = _lead_action(job)
    label_text, label_tone = _lead_label(job)
    lead_type = str(job.metadata.get("lead_type", "")).lower()
    title = job.company if lead_type in {"program", "pathway"} else job.title
    support = job.title if title == job.company else job.company
    place = _primary_place(job)
    note = _status_note(job)
    return f"""
    <li class="feed-row">
      <div class="feed-row__copy">
        <div class="feed-row__badges">{_badge(label_text, label_tone)}</div>
        <p class="feed-row__title">{escape(title)}</p>
        <p class="feed-row__meta">{escape(place)}{' · ' + escape(support) if support else ''}</p>
        <p class="feed-row__note">{escape(note)}</p>
      </div>
      <a class="feed-row__link" href="{escape(action_url)}">{escape(action_label)}</a>
    </li>
    """


def _feed_module(title: str, eyebrow: str, items_html: str, empty_copy: str) -> str:
    content = items_html or f'<p class="feed-panel__empty">{escape(empty_copy)}</p>'
    return f"""
    <article class="feed-panel">
      <p class="feed-panel__eyebrow">{escape(eyebrow)}</p>
      <h3 class="feed-panel__title">{escape(title)}</h3>
      <div class="feed-panel__body">{content}</div>
    </article>
    """


def _change_line(label: str, title: str, detail: str, href: str = "") -> str:
    link = f'<a class="feed-row__link" href="{escape(href)}">Open</a>' if href else ""
    return f"""
    <li class="feed-row feed-row--compact">
      <div class="feed-row__copy">
        <p class="feed-row__overline">{escape(label)}</p>
        <p class="feed-row__title">{escape(title)}</p>
        <p class="feed-row__note">{escape(detail)}</p>
      </div>
      {link}
    </li>
    """


def _source_card(report: SourceReport) -> str:
    tone = "source"
    if report.status == "warning":
        tone = "warn"
    elif report.status == "error":
        tone = "expired"

    notes = report.notes + report.errors
    notes_html = "".join(f"<li>{escape(note)}</li>" for note in notes) or "<li>No extra notes.</li>"
    browser_note = _badge("Browser fallback", "watch") if report.used_browser else ""
    stale_note = _badge("Serving stale", "stale") if report.serving_stale else ""
    last_success = (
        f"Last good scrape {escape(_format_datetime_label(report.last_success_at))}"
        if report.last_success_at
        else "No successful scrape recorded yet"
    )
    last_attempt = (
        f"Last attempt {escape(_format_datetime_label(report.last_attempt_at))}"
        if report.last_attempt_at
        else ""
    )

    return f"""
    <article class="source-card">
      <div class="source-card__badges">
        {_badge(report.status.title(), tone)}
        {browser_note}
        {stale_note}
      </div>
      <div class="source-card__header">
        <h3>{escape(report.source_name)}</h3>
        <a href="{escape(report.source_url)}">Open source</a>
      </div>
      <p class="source-card__stats">
        Fetched {report.total_fetched} listings · Visible leads {report.total_relevant} · Stale holds {report.stale_relevant_count}
      </p>
      <p class="source-card__stats">{last_success}{' · ' + last_attempt if last_attempt else ''}</p>
      <ul class="source-card__notes">{notes_html}</ul>
    </article>
    """


def _page_styles() -> str:
    return """
      :root {
        color-scheme: dark;
        --bg: #07101d;
        --bg-panel: rgba(13, 24, 43, 0.92);
        --bg-panel-soft: rgba(9, 17, 31, 0.88);
        --stroke: rgba(132, 154, 193, 0.16);
        --text: #edf2ff;
        --text-muted: #9fb0d6;
        --text-soft: #6f84af;
        --gold: #fbbf24;
        --cyan: #7dd3fc;
        --mint: #9ae6b4;
        --red: #fb7185;
        --violet: #a78bfa;
        --shadow: 0 18px 45px rgba(0, 0, 0, 0.28);
        --radius-xl: 30px;
        --radius-lg: 22px;
        --radius-md: 16px;
        --content: 1180px;
        --gutter: clamp(1rem, 3vw, 1.5rem);
        --section-space: clamp(2.2rem, 5vw, 4.4rem);
        font-family: "Space Grotesk", "Segoe UI", sans-serif;
      }
      * { box-sizing: border-box; }
      html { scroll-behavior: smooth; }
      body {
        margin: 0;
        min-height: 100vh;
        background:
          radial-gradient(circle at top left, rgba(59, 130, 246, 0.16), transparent 30%),
          radial-gradient(circle at top right, rgba(251, 191, 36, 0.08), transparent 30%),
          linear-gradient(180deg, #081120 0%, #07101d 60%, #050b15 100%);
        color: var(--text);
      }
      a { color: inherit; }
      button, input { font: inherit; }
      .sr-only {
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border: 0;
      }
      :focus-visible { outline: 2px solid rgba(125, 211, 252, 0.92); outline-offset: 2px; }
      .shell {
        width: min(var(--content), calc(100vw - 2 * var(--gutter)));
        margin: 0 auto;
        padding: clamp(1.2rem, 3vw, 1.8rem) 0 5rem;
      }
      .eyebrow {
        margin: 0 0 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.3em;
        font-size: 0.72rem;
        color: var(--text-soft);
      }
      .masthead, .feed-panel, .lane, .toolbar, .source-card, .job-card {
        border-radius: var(--radius-lg);
        background: linear-gradient(180deg, rgba(15, 27, 49, 0.95), rgba(9, 17, 31, 0.92));
        border: 1px solid var(--stroke);
        box-shadow: var(--shadow);
      }
      .masthead {
        position: relative;
        overflow: hidden;
        padding: clamp(1.6rem, 4vw, 2.5rem);
        border-radius: var(--radius-xl);
      }
      .masthead::after {
        content: "";
        position: absolute;
        right: -5rem;
        bottom: -7rem;
        width: 15rem;
        height: 15rem;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(251, 191, 36, 0.2), transparent 70%);
        pointer-events: none;
      }
      .masthead h1, .section-head h2, .lane-head h3, .feed-panel__title, .source-card__header h3, .job-card__title {
        margin: 0;
        font-weight: 700;
        letter-spacing: -0.03em;
      }
      .masthead h1 {
        max-width: 12ch;
        font-size: clamp(2.4rem, 7vw, 4.5rem);
        line-height: 0.95;
      }
      .masthead__lede {
        max-width: 56rem;
        margin: 1rem 0 0;
        color: var(--text-muted);
        line-height: 1.55;
        font-size: clamp(1rem, 2.3vw, 1.15rem);
      }
      .masthead__meta {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        margin-top: 1.2rem;
        color: var(--text-muted);
        font-size: 0.95rem;
      }
      .masthead__stats, .feed-grid, .lane-grid, .source-grid { display: grid; gap: 1rem; }
      .masthead__stats { grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: 1.5rem; }
      .stat-card {
        padding: 1rem;
        border-radius: var(--radius-md);
        background: rgba(9, 17, 31, 0.64);
        border: 1px solid rgba(132, 154, 193, 0.12);
      }
      .stat-card__value { font-size: clamp(1.4rem, 4vw, 2rem); font-weight: 700; letter-spacing: -0.04em; }
      .stat-card__label { margin-top: 0.35rem; color: var(--text-muted); font-size: 0.86rem; }
      .view-nav, .toolbar__filters {
        display: flex;
        gap: 0.6rem;
        overflow-x: auto;
      }
      .view-nav {
        position: sticky;
        top: 0.65rem;
        z-index: 30;
        padding: 0.8rem;
        margin-top: 1.2rem;
        border-radius: 999px;
        background: rgba(7, 14, 27, 0.82);
        backdrop-filter: blur(16px);
        border: 1px solid rgba(132, 154, 193, 0.14);
      }
      .view-link, .filter-chip {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 2.5rem;
        padding: 0.72rem 1rem;
        border-radius: 999px;
        border: 1px solid rgba(125, 211, 252, 0.2);
        background: rgba(8, 17, 32, 0.72);
        color: var(--text-muted);
        text-decoration: none;
        white-space: nowrap;
        transition: 160ms ease;
      }
      .view-link:hover, .filter-chip:hover, .filter-chip.is-active {
        color: var(--text);
        border-color: rgba(125, 211, 252, 0.42);
        background: rgba(16, 27, 49, 0.98);
      }
      .view-link.is-active {
        color: #07101d;
        border-color: transparent;
        background: linear-gradient(135deg, var(--gold), #fcd34d);
      }
      .section { padding-top: var(--section-space); scroll-margin-top: 5.5rem; }
      .section-head, .lane-head, .source-card__header, .toolbar__top, .job-card__footer {
        display: flex;
        align-items: end;
        justify-content: space-between;
        gap: 1rem;
      }
      .section-head { margin-bottom: 1.2rem; }
      .section-head p, .lane-head p, .job-card__subtitle, .job-card__meta, .job-card__description, .job-card__details, .source-card__stats, .feed-panel__empty, .toolbar__hint {
        color: var(--text-muted);
      }
      .section-head p, .lane-head p { margin: 0.45rem 0 0; max-width: 48rem; line-height: 1.5; }
      .section-link, .feed-row__link, .source-card__header a, .job-card__link { color: var(--cyan); text-decoration: none; font-weight: 600; }
      .feed-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .feed-panel, .lane, .toolbar, .source-card, .job-card { padding: 1rem; }
      .feed-panel__eyebrow, .feed-row__overline {
        margin: 0 0 0.5rem;
        text-transform: uppercase;
        letter-spacing: 0.22em;
        font-size: 0.72rem;
        color: var(--text-soft);
      }
      .feed-list { list-style: none; margin: 1rem 0 0; padding: 0; display: grid; gap: 0.8rem; }
      .feed-row {
        display: flex;
        justify-content: space-between;
        gap: 0.85rem;
        padding-top: 0.85rem;
        border-top: 1px solid rgba(132, 154, 193, 0.1);
      }
      .feed-row:first-child { padding-top: 0; border-top: 0; }
      .feed-row__badges, .job-card__cluster, .job-card__reasons, .source-card__badges { display: flex; flex-wrap: wrap; gap: 0.45rem; }
      .feed-row__title, .feed-row__meta, .feed-row__note, .job-card__place, .job-card__subtitle, .job-card__meta, .job-card__description { margin: 0; }
      .feed-row__title { font-weight: 600; }
      .feed-row__meta { margin-top: 0.2rem; font-size: 0.92rem; }
      .feed-row__note { margin-top: 0.35rem; color: var(--text-soft); font-size: 0.9rem; line-height: 1.45; }
      .directory-grid, .openings-grid { display: grid; gap: 1rem; }
      .lane-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .lane-empty {
        margin: 0;
        padding: 1rem;
        border-radius: var(--radius-md);
        background: rgba(9, 17, 31, 0.7);
        color: var(--text-muted);
      }
      .toolbar {
        position: sticky;
        top: 4.8rem;
        z-index: 20;
        margin-bottom: 1rem;
        backdrop-filter: blur(16px);
      }
      .toolbar__search {
        width: min(100%, 28rem);
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.88rem 1rem;
        border-radius: 999px;
        background: rgba(7, 14, 27, 0.78);
        border: 1px solid rgba(132, 154, 193, 0.16);
      }
      .toolbar__search input { width: 100%; border: 0; outline: 0; background: transparent; color: var(--text); }
      .toolbar__hint { margin: 0.8rem 0 0; font-size: 0.9rem; }
      .job-card[hidden] { display: none !important; }
      .job-card__place {
        margin-top: 0.95rem;
        color: var(--cyan);
        font-size: 0.82rem;
        font-weight: 700;
        letter-spacing: 0.16em;
        text-transform: uppercase;
      }
      .job-card__title { margin-top: 0.45rem; font-size: 1.2rem; line-height: 1.12; }
      .job-card__title a { text-decoration: none; }
      .job-card__subtitle, .job-card__meta { margin-top: 0.45rem; font-size: 0.96rem; }
      .job-card__description { margin-top: 0.9rem; line-height: 1.52; }
      .job-card__facts { display: grid; gap: 0.7rem; margin: 0.95rem 0 0; }
      .job-card__facts div { display: grid; gap: 0.25rem; }
      .job-card__facts dt { color: var(--text-soft); font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.18em; }
      .job-card__facts dd { margin: 0; line-height: 1.45; }
      .job-card__reasons { margin-top: 0.95rem; }
      .job-card__footer { margin-top: 1rem; align-items: center; }
      .job-card__score { color: var(--text-soft); font-size: 0.9rem; }
      .job-card__details { margin-top: 0.9rem; border-top: 1px solid rgba(132, 154, 193, 0.12); padding-top: 0.8rem; }
      .job-card__details summary { cursor: pointer; }
      .job-card__details ul, .source-card__notes { margin: 0.7rem 0 0; padding-left: 1rem; display: grid; gap: 0.5rem; color: var(--text-muted); }
      .source-card__header { margin-top: 0.9rem; align-items: center; }
      .source-card__stats { margin: 0.7rem 0 0; line-height: 1.45; }
      .badge {
        display: inline-flex;
        align-items: center;
        min-height: 1.95rem;
        padding: 0.26rem 0.72rem;
        border-radius: 999px;
        border: 1px solid transparent;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.04em;
      }
      .badge-priority { color: #1b1300; background: linear-gradient(135deg, #fbbf24, #f59e0b); }
      .badge-watch { color: #d9f1ff; background: rgba(26, 65, 108, 0.8); border-color: rgba(125, 211, 252, 0.28); }
      .badge-status { color: #dcfce7; background: rgba(13, 82, 52, 0.85); border-color: rgba(154, 230, 180, 0.28); }
      .badge-source { color: #d8e2ff; background: rgba(35, 45, 78, 0.82); border-color: rgba(167, 139, 250, 0.22); }
      .badge-hub { color: #ecfeff; background: rgba(8, 73, 89, 0.82); border-color: rgba(125, 211, 252, 0.25); }
      .badge-regional { color: #e7f7ff; background: rgba(23, 63, 126, 0.85); border-color: rgba(125, 211, 252, 0.26); }
      .badge-warn { color: #fff7d1; background: rgba(90, 67, 8, 0.88); border-color: rgba(251, 191, 36, 0.28); }
      .badge-relocation { color: #f3e8ff; background: rgba(78, 32, 112, 0.85); border-color: rgba(167, 139, 250, 0.26); }
      .badge-expired { color: #ffe2e2; background: rgba(102, 22, 41, 0.88); border-color: rgba(251, 113, 133, 0.28); }
      .badge-stale { color: #ffe7c7; background: rgba(102, 61, 23, 0.88); border-color: rgba(251, 191, 36, 0.22); }
      .site-footer { margin-top: var(--section-space); color: var(--text-soft); font-size: 0.88rem; }
      @media (max-width: 960px) {
        .masthead__stats, .feed-grid, .lane-grid { grid-template-columns: 1fr 1fr; }
        .section-head, .lane-head, .source-card__header, .toolbar__top, .job-card__footer { flex-direction: column; align-items: start; }
      }
      @media (max-width: 720px) {
        .shell { width: min(var(--content), calc(100vw - 1.2rem)); padding-bottom: 4rem; }
        .masthead__stats, .feed-grid, .lane-grid { grid-template-columns: 1fr; }
        .view-nav { top: 0.4rem; }
        .toolbar { top: 4.4rem; }
        .toolbar__search { width: 100%; }
        .job-card__title { font-size: 1.12rem; }
      }
    """


def _page_script() -> str:
    return """
      (() => {
        const searchInput = document.querySelector("[data-search-input]");
        const filterButtons = [...document.querySelectorAll("[data-filter]")];
        const cards = [...document.querySelectorAll(".job-card")];
        const viewLinks = [...document.querySelectorAll("[data-view-link]")];
        const sections = [...document.querySelectorAll("[data-view-section]")];
        let activeFilter = "all";
        const westCoastLanes = new Set(["oregon-programs", "wa-pathways", "ca-pathways", "regional-jobs"]);
        const matchesFilter = (card, filter) => {
          switch (filter) {
            case "fresh": return card.dataset.stale !== "1";
            case "official": return card.dataset.official === "1";
            case "west-coast": return westCoastLanes.has(card.dataset.lane) || card.dataset.region === "1";
            case "priority": return card.dataset.bucket === "priority";
            case "relocation": return card.dataset.relocation === "1";
            case "stale": return card.dataset.stale === "1";
            default: return true;
          }
        };
        const applyFilters = () => {
          const query = (searchInput?.value || "").trim().toLowerCase();
          cards.forEach((card) => {
            const queryMatch = !query || (card.dataset.search || "").includes(query);
            const filterMatch = matchesFilter(card, activeFilter);
            card.hidden = !(queryMatch && filterMatch);
          });
        };
        searchInput?.addEventListener("input", applyFilters);
        filterButtons.forEach((button) => {
          button.addEventListener("click", () => {
            activeFilter = button.dataset.filter || "all";
            filterButtons.forEach((node) => node.classList.toggle("is-active", node === button));
            applyFilters();
          });
        });
        const observer = new IntersectionObserver((entries) => {
          const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
          if (!visible) return;
          const id = visible.target.getAttribute("data-view-section");
          viewLinks.forEach((link) => link.classList.toggle("is-active", link.getAttribute("data-view-link") === id));
        }, { threshold: [0.35, 0.55, 0.75], rootMargin: "-10% 0px -50% 0px" });
        sections.forEach((section) => observer.observe(section));
        applyFilters();
      })();
    """


def render_index(generated_at: str, jobs: list[JobLead], reports: list[SourceReport]) -> str:
    active_relevant = [
        job
        for job in jobs
        if job.status == "active" and job.bucket in {"priority", "watch"}
    ]
    expired_relevant = [
        job
        for job in jobs
        if job.status == "expired" and job.bucket in {"priority", "watch"}
    ]

    oregon_programs = sorted(
        [
            job
            for job in active_relevant
            if str(job.metadata.get("lead_type", "")).lower() == "program"
        ],
        key=lambda job: (-job.score, _primary_place(job), job.company.lower()),
    )
    washington_pathways = sorted(
        [
            job
            for job in active_relevant
            if str(job.metadata.get("lead_type", "")).lower() == "pathway"
            and job.source_key != "californiaapprenticeship"
        ],
        key=lambda job: (-job.score, _primary_place(job), job.company.lower()),
    )
    california_sponsors = sorted(
        [job for job in active_relevant if job.source_key == "californiaapprenticeship"],
        key=_california_pathway_sort_key,
    )
    contractor_openings = [
        job
        for job in active_relevant
        if str(job.metadata.get("lead_type", "")).lower() not in {"program", "pathway"}
    ]
    priority_jobs = sorted(
        [job for job in contractor_openings if job.bucket == "priority"],
        key=lambda job: (-job.score, _primary_place(job), job.title.lower()),
    )
    regional_jobs = sorted(
        [
            job
            for job in contractor_openings
            if job.bucket == "watch" and job.metadata.get("regional_matches")
        ],
        key=lambda job: (-job.score, _primary_place(job), job.title.lower()),
    )
    national_jobs = sorted(
        [
            job
            for job in contractor_openings
            if job.bucket == "watch" and not job.metadata.get("regional_matches")
        ],
        key=lambda job: (-job.score, _primary_place(job), job.title.lower()),
    )

    official_count = len(oregon_programs) + len(washington_pathways) + len(california_sponsors)
    fresh_count = sum(1 for job in active_relevant if not job.stale_source)
    stale_count = sum(1 for job in active_relevant if job.stale_source)
    relocation_count = sum(1 for job in active_relevant if job.metadata.get("relocation_assistance"))

    feed_new = [job for job in active_relevant if job.first_seen == job.last_seen][:6]
    stale_sources = [report for report in reports if report.serving_stale or report.status == "error"]
    stale_jobs = [job for job in active_relevant if job.stale_source][:2]

    change_items: list[str] = []
    for job in feed_new[:3]:
        label_text, _ = _lead_label(job)
        title = job.company if str(job.metadata.get("lead_type", "")).lower() in {"program", "pathway"} else job.title
        change_items.append(
            _change_line(
                f"New · {label_text}",
                title,
                f"{_primary_place(job)} · {_status_note(job)}",
                job.detail_url,
            )
        )
    for report in stale_sources[:2]:
        if report.stale_relevant_count:
            detail = f"{report.stale_relevant_count} last-known-good lead(s) still shown."
        else:
            detail = "No last-known-good leads are available yet."
        change_items.append(_change_line("Source status", report.source_name, detail, report.source_url))
    for job in expired_relevant[:2]:
        change_items.append(
            _change_line(
                "Removed recently",
                job.title,
                f"{_primary_place(job)} · No longer listed on source.",
                job.detail_url,
            )
        )
    if not change_items:
        for job in stale_jobs:
            change_items.append(
                _change_line(
                    "Stale hold",
                    job.company if str(job.metadata.get("lead_type", "")).lower() in {"program", "pathway"} else job.title,
                    f"{_primary_place(job)} · Last verified {_format_date_label(job.last_seen)}",
                    job.detail_url,
                )
            )

    feed_panels = "".join(
        [
            _feed_module(
                "Open now in Oregon",
                "Feed",
                f'<ol class="feed-list">{"".join(_feed_row(job) for job in oregon_programs[:4])}</ol>' if oregon_programs else "",
                "No Oregon inside-electrician intakes are currently visible.",
            ),
            _feed_module(
                "Nearby official pathways",
                "Directory",
                f'<ol class="feed-list">{"".join(_feed_row(job) for job in washington_pathways[:4])}</ol>' if washington_pathways else "",
                "No nearby official pathways are visible right now.",
            ),
            _feed_module(
                "Priority contractor jobs",
                "Openings",
                f'<ol class="feed-list">{"".join(_feed_row(job) for job in priority_jobs[:4])}</ol>' if priority_jobs else "",
                "No priority contractor jobs are visible right now.",
            ),
            _feed_module(
                "Board movement",
                "Changes",
                f'<ol class="feed-list">{"".join(change_items)}</ol>' if change_items else "",
                "No new or removed high-signal changes in this snapshot.",
            ),
        ]
    )

    oregon_cards = "".join(_job_card(job, "oregon-programs") for job in oregon_programs)
    washington_cards = "".join(_job_card(job, "wa-pathways") for job in washington_pathways)
    california_cards = "".join(_job_card(job, "ca-pathways") for job in california_sponsors)
    priority_cards = "".join(_job_card(job, "priority-jobs") for job in priority_jobs)
    regional_cards = "".join(_job_card(job, "regional-jobs") for job in regional_jobs)
    national_cards = "".join(_job_card(job, "national-jobs") for job in national_jobs)
    expired_cards = "".join(_job_card(job, "expired-jobs") for job in expired_relevant)
    source_cards = "".join(
        _source_card(report)
        for report in sorted(
            reports,
            key=lambda report: (
                0 if report.status == "error" else 1 if report.status == "warning" else 2,
                -report.total_relevant,
                report.source_name.lower(),
            ),
        )
    )

    latest_json = render_latest_json(generated_at, jobs, reports)
    safe_latest_json = latest_json.replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Donovan's Live Wire</title>
    <meta name="description" content="Daily apprenticeship lead board for Donovan. Oregon open intakes first, official nearby pathways second, broader contractor openings after that." />
    <meta name="theme-color" content="#081120" />
    <link rel="icon" href="{_favicon_data_uri()}" />
    <style>{_page_styles()}</style>
  </head>
  <body>
    <main class="shell">
      <header class="masthead" id="top">
        <p class="eyebrow">Daily Transmission</p>
        <h1>Donovan's Live Wire</h1>
        <p class="masthead__lede">A dark, phone-first lead board for Donovan's apprenticeship search. Oregon open intakes show up first, official nearby pathways stay clearly separated from broader job listings, and national opportunities stay visible when they look strong enough to matter.</p>
        <div class="masthead__meta">
          <span>Latest snapshot {escape(_format_datetime_label(generated_at))}</span>
          <span>{len(active_relevant)} active leads</span>
          <span>{official_count} official pathways or intakes</span>
          <span>{len(priority_jobs)} priority contractor jobs</span>
        </div>
        <div class="masthead__stats" aria-label="Snapshot metrics">
          <article class="stat-card"><div class="stat-card__value">{len(oregon_programs)}</div><div class="stat-card__label">Oregon open intakes</div></article>
          <article class="stat-card"><div class="stat-card__value">{len(washington_pathways) + len(california_sponsors)}</div><div class="stat-card__label">Official nearby directories</div></article>
          <article class="stat-card"><div class="stat-card__value">{len(priority_jobs) + len(regional_jobs) + len(national_jobs)}</div><div class="stat-card__label">Contractor openings</div></article>
          <article class="stat-card"><div class="stat-card__value">{stale_count}</div><div class="stat-card__label">Stale held during outages</div></article>
        </div>
        <nav class="view-nav" aria-label="Primary sections">
          <a class="view-link is-active" href="#feed" data-view-link="feed">Feed</a>
          <a class="view-link" href="#directory" data-view-link="directory">Directory</a>
          <a class="view-link" href="#openings" data-view-link="openings">Openings</a>
        </nav>
      </header>

      <section class="section" id="feed" data-view-section="feed">
        <div class="section-head">
          <div>
            <p class="eyebrow">Feed</p>
            <h2>Daily scan first, details after</h2>
            <p>This front section stays tight on purpose: top Oregon intakes, nearby official pathways, the strongest contractor jobs, and whatever changed enough to deserve Donovan's attention today.</p>
          </div>
        </div>
        <div class="feed-grid">{feed_panels}</div>
      </section>

      <section class="section" id="directory" data-view-section="directory">
        <div class="section-head">
          <div>
            <p class="eyebrow">Directory</p>
            <h2>Official apprenticeship routes</h2>
            <p>These are real committee, sponsor, or state directory records. Only Oregon entries that are explicitly open are shown as open intakes. Everything else is labeled as a pathway or sponsor record to check directly.</p>
          </div>
          <a class="section-link" href="#california-sponsors">Jump to California</a>
        </div>
        <div class="directory-grid">
          <section class="lane"><div class="lane-head"><div><h3>Oregon Open Intakes</h3><p>Confirmed statewide openings for Inside Electrician and closely aligned apprenticeship intake windows.</p></div></div><div class="lane-grid">{oregon_cards or '<p class="lane-empty">No Oregon intakes are visible in this snapshot.</p>'}</div></section>
          <section class="lane"><div class="lane-head"><div><h3>Washington Pathways</h3><p>Official nearby directories that connect into inside wireman pathways, especially where Oregon coverage or proximity exists.</p></div></div><div class="lane-grid">{washington_cards or '<p class="lane-empty">No nearby pathway records are visible right now.</p>'}</div></section>
          <section class="lane" id="california-sponsors"><div class="lane-head"><div><h3>California Sponsors</h3><p>Official California sponsor records to check directly for application timing, with northern and Oregon-adjacent options prioritized first.</p></div></div><div class="lane-grid">{california_cards or '<p class="lane-empty">No California sponsor records are visible right now.</p>'}</div></section>
        </div>
      </section>

      <section class="section" id="openings" data-view-section="openings">
        <div class="section-head">
          <div>
            <p class="eyebrow">Openings</p>
            <h2>Broader contractor jobs, kept separate</h2>
            <p>These are the wider contractor and project listings. Official intake routes still outrank them, but good national or relocation-friendly openings stay visible here when they look strong enough to matter.</p>
          </div>
        </div>
        <div class="toolbar" aria-label="Openings search and filters">
          <div class="toolbar__top">
            <label class="toolbar__search"><span class="sr-only">Search openings</span><input type="search" placeholder="Search title, company, location, or source" data-search-input /></label>
          </div>
          <div class="toolbar__filters" role="toolbar" aria-label="Openings filters">
            <button class="filter-chip is-active" type="button" data-filter="all">All</button>
            <button class="filter-chip" type="button" data-filter="fresh">Fresh</button>
            <button class="filter-chip" type="button" data-filter="official">Official</button>
            <button class="filter-chip" type="button" data-filter="west-coast">West Coast</button>
            <button class="filter-chip" type="button" data-filter="priority">Priority</button>
            <button class="filter-chip" type="button" data-filter="relocation">Relocation</button>
            <button class="filter-chip" type="button" data-filter="stale">Stale</button>
          </div>
          <p class="toolbar__hint">{fresh_count} fresh leads, {stale_count} stale holds, {relocation_count} relocation-tagged, {len(regional_jobs)} regional contractor openings.</p>
        </div>
        <div class="openings-grid">
          <section class="lane"><div class="lane-head"><div><h3>Priority Contractor Leads</h3><p>High-signal contractor jobs with stronger apprentice, mission-critical, or immediate-opportunity evidence.</p></div></div><div class="lane-grid">{priority_cards or '<p class="lane-empty">No priority contractor jobs are visible right now.</p>'}</div></section>
          <section class="lane"><div class="lane-head"><div><h3>West Coast And Nearby Openings</h3><p>Broader West Coast or nearby contractor openings that still look relevant for Donovan's search.</p></div></div><div class="lane-grid">{regional_cards or '<p class="lane-empty">No regional contractor openings are visible right now.</p>'}</div></section>
          <section class="lane"><div class="lane-head"><div><h3>National Openings</h3><p>Distant but still plausible leads, kept visible without overtaking local official entry routes.</p></div></div><div class="lane-grid">{national_cards or '<p class="lane-empty">No national contractor openings are visible right now.</p>'}</div></section>
        </div>
      </section>

      <section class="section" id="sources">
        <div class="section-head">
          <div>
            <p class="eyebrow">Source Health</p>
            <h2>What each source produced</h2>
            <p>Source cards show whether the board is fresh, warning, or serving stale last-known-good leads during an outage.</p>
          </div>
        </div>
        <div class="source-grid">{source_cards}</div>
      </section>

      <section class="section" id="removed">
        <div class="section-head">
          <div>
            <p class="eyebrow">Recently Removed</p>
            <h2>No longer seen on source</h2>
            <p>Items only move here when the source confirms removal instead of simply failing for a day.</p>
          </div>
        </div>
        <div class="openings-grid">
          <section class="lane"><div class="lane-grid">{expired_cards or '<p class="lane-empty">Nothing relevant has dropped off recently.</p>'}</div></section>
        </div>
      </section>

      <footer class="site-footer">Donovan's Live Wire is generated from state boards, official directories, and contractor sources. Official directories are labeled separately from confirmed openings on purpose.</footer>
    </main>

    <script id="latest-data" type="application/json">{safe_latest_json}</script>
    <script>{_page_script()}</script>
  </body>
</html>
"""


def render_latest_json(generated_at: str, jobs: list[JobLead], reports: list[SourceReport]) -> str:
    active_relevant = [
        job
        for job in jobs
        if job.status == "active" and job.bucket in {"priority", "watch"}
    ]
    payload = {
        "generated_at": generated_at,
        "counts": {
            "active_relevant": len(active_relevant),
            "fresh_active_relevant": sum(1 for job in active_relevant if not job.stale_source),
            "stale_active_relevant": sum(1 for job in active_relevant if job.stale_source),
            "expired_relevant": sum(
                1
                for job in jobs
                if job.status == "expired" and job.bucket in {"priority", "watch"}
            ),
        },
        "jobs": [job.to_dict() for job in jobs],
        "reports": [report.to_dict() for report in reports],
    }
    return json.dumps(payload, indent=2)
