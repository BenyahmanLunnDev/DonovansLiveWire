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
        labels.append("Official intake open")
        if str(job.metadata.get("program_status_source", "")).lower() == "committee site":
            labels.append("Committee-confirmed")
        else:
            labels.append("State-board opening")
    elif job.metadata.get("lead_type") == "pathway":
        labels.append("Official pathway")
        if job.metadata.get("regional_matches"):
            labels.append("Oregon-serving")
        labels.append("Check directly")

    if any("data center" in reason for reason in job.reasons):
        labels.append("Data center context")
    if any("mission critical" in reason for reason in job.reasons):
        labels.append("Mission-critical context")
    if any("regional apprentice opportunity" in reason for reason in job.reasons):
        labels.append("Regional opportunity")
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


def _job_blurb(job: JobLead) -> str:
    lead_type = str(job.metadata.get("lead_type", "")).lower()
    parts: list[str] = []

    if lead_type == "program":
        if str(job.metadata.get("program_status_source", "")).lower() == "committee site":
            parts.append("Committee page confirms this inside electrician intake is open now.")
        else:
            parts.append("Official Oregon apprenticeship board currently lists this inside electrician intake as open.")

        status_note = str(job.metadata.get("program_status_note", "")).strip()
        if status_note:
            parts.append(status_note)

        areas = str(job.metadata.get("areas", "")).strip()
        if areas:
            parts.append(f"Coverage: {areas}")

        counties = _list_preview(job.metadata.get("counties", []), limit=5)
        if counties:
            parts.append(f"Counties: {counties}")

        contact = str(job.metadata.get("contact", "")).strip()
        phone = str(job.metadata.get("phone", "")).strip()
        if contact and phone:
            parts.append(f"Contact: {contact} at {phone}")
        elif contact:
            parts.append(f"Contact: {contact}")
        elif phone:
            parts.append(f"Phone: {phone}")

        average_wage = str(job.metadata.get("average_wage", "")).strip()
        if average_wage:
            parts.append(f"Average journey wage: {average_wage}")
    elif lead_type == "pathway":
        if job.source_key == "californiaapprenticeship":
            parts.append("Official California apprenticeship sponsor listing to check directly.")
        else:
            parts.append("Official state apprenticeship pathway listing to check directly.")

        parts.append("The public directory does not confirm that applications are open right now.")

        regional = _list_preview(job.metadata.get("regional_matches", []), limit=2)
        if regional:
            parts.append(f"Best fit: {regional}")

        county_names = _list_preview(job.metadata.get("county_names", []), limit=6)
        if county_names:
            parts.append(f"Coverage: {county_names}")

        contact = str(job.metadata.get("contact", "")).strip()
        phone = str(job.metadata.get("phone", "")).strip()
        if contact and phone:
            parts.append(f"Contact: {contact} at {phone}")
        elif contact:
            parts.append(f"Contact: {contact}")
        elif phone:
            parts.append(f"Phone: {phone}")

        website = str(job.metadata.get("website", "")).strip()
        if website:
            parts.append(f"Website: {website}")
    else:
        description = job.description or "Description not captured for this listing yet."
        return _truncate(description, 300)

    return _truncate(" | ".join(part for part in parts if part), 280)


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


def _job_card(job: JobLead, lane: str) -> str:
    description = escape(_job_blurb(job))
    summary_reasons = "".join(_badge(label, "watch") for label in _reason_chips(job))
    hubs = "".join(_badge(hub, "hub") for hub in job.hub_matches)
    regional = "".join(
        _badge(match, "regional")
        for match in job.metadata.get("regional_matches", [])[:2]
    )

    if job.status == "expired":
        status_badge = _badge("No longer on source", "expired")
    elif job.stale_source:
        status_badge = _badge("Stale source", "stale")
    elif job.first_seen == job.last_seen:
        status_badge = _badge("New this run", "status")
    else:
        status_badge = _badge("Seen before", "source")

    relocation_badge = (
        _badge("Relocation listed", "relocation")
        if job.metadata.get("relocation_assistance")
        else ""
    )
    program_badge = (
        _badge("Program opening", "status")
        if job.metadata.get("lead_type") == "program"
        else ""
    )
    verification_badge = (
        _badge("Committee site", "hub")
        if str(job.metadata.get("program_status_source", "")).lower() == "committee site"
        else (
            _badge("State board", "watch")
            if job.metadata.get("lead_type") == "program"
            else (
                _badge("State directory", "watch")
                if job.metadata.get("lead_type") == "pathway"
                else ""
            )
        )
    )
    pathway_badge = (
        _badge("Regional pathway", "status")
        if job.metadata.get("lead_type") == "pathway"
        else ""
    )
    stale_note = (
        f'<p class="job-card__stale">Last verified on {escape(_format_date_label(job.last_seen))} before this source went stale.</p>'
        if job.stale_source and job.last_seen
        else ""
    )

    meta_bits = [
        escape(job.company),
        escape(_format_location(job.location)),
        escape(_format_date_label(job.posted_date)),
        escape(job.source_name),
    ]
    meta = " | ".join(bit for bit in meta_bits if bit)
    debug_reasons = "".join(f"<li>{escape(reason)}</li>" for reason in job.reasons)
    score_line = escape(f"Score {job.score}")
    search_text = " ".join(
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

    return f"""
    <article
      class="job-card"
      data-search="{escape(search_text)}"
      data-lane="{escape(lane)}"
      data-bucket="{escape(job.bucket)}"
      data-kind="{'program' if job.metadata.get('lead_type') == 'program' else ('pathway' if job.metadata.get('lead_type') == 'pathway' else 'job')}"
      data-region="{'1' if job.metadata.get('regional_matches') else '0'}"
      data-relocation="{'1' if job.metadata.get('relocation_assistance') else '0'}"
      data-new="{'1' if job.first_seen == job.last_seen and job.status == 'active' else '0'}"
      data-stale="{'1' if job.stale_source else '0'}"
      data-official="{'1' if job.metadata.get('lead_type') in {'program', 'pathway'} else '0'}"
    >
      <div class="job-card__badges">
        {status_badge}
        {program_badge}
        {pathway_badge}
        {verification_badge}
        {_badge(job.source_name, "source")}
        {hubs}
        {regional}
        {relocation_badge}
      </div>
      <h3 class="job-card__title">
        <a href="{escape(job.detail_url)}">{escape(job.title)}</a>
      </h3>
      <p class="job-card__meta">{meta}</p>
      <p class="job-card__description">{description}</p>
      {stale_note}
      <div class="job-card__reasons">{summary_reasons}</div>
      <div class="job-card__footer">
        <span class="job-card__score">{score_line}</span>
        <a class="job-card__link" href="{escape(job.detail_url)}">Open listing</a>
      </div>
      <details class="job-card__details">
        <summary>Why this matched</summary>
        <ul>{debug_reasons}</ul>
      </details>
    </article>
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
        Fetched {report.total_fetched} listings | Visible leads {report.total_relevant} | Stale holds {report.stale_relevant_count}
      </p>
      <p class="source-card__stats">{last_success}{' | ' + last_attempt if last_attempt else ''}</p>
      <ul class="source-card__notes">{notes_html}</ul>
    </article>
    """


def render_index(generated_at: str, jobs: list[JobLead], reports: list[SourceReport]) -> str:
    active = [job for job in jobs if job.status == "active"]
    relevant_active = [job for job in active if job.bucket in {"priority", "watch"}]
    program_jobs = [job for job in relevant_active if job.metadata.get("lead_type") == "program"]
    pathway_jobs = [job for job in relevant_active if job.metadata.get("lead_type") == "pathway"]
    standard_active = [
        job
        for job in relevant_active
        if job.metadata.get("lead_type") not in {"program", "pathway"}
    ]
    priority_jobs = [job for job in standard_active if job.bucket == "priority"]
    watch_jobs = [job for job in standard_active if job.bucket == "watch"]
    west_coast_watch = [job for job in watch_jobs if job.metadata.get("regional_matches")]
    national_watch = [job for job in watch_jobs if not job.metadata.get("regional_matches")]
    expired = [job for job in jobs if job.status == "expired" and job.bucket in {"priority", "watch"}]
    nearby_pathway_jobs = [
        job for job in pathway_jobs if job.source_key != "californiaapprenticeship"
    ]
    california_pathway_jobs = sorted(
        [job for job in pathway_jobs if job.source_key == "californiaapprenticeship"],
        key=_california_pathway_sort_key,
    )

    total_active = len(relevant_active)
    fresh_active = [job for job in relevant_active if not job.stale_source]
    stale_active = [job for job in relevant_active if job.stale_source]
    relocation_count = len([job for job in relevant_active if job.metadata.get("relocation_assistance")])
    regional_count = len([job for job in relevant_active if job.metadata.get("regional_matches")])
    national_count = len(national_watch)
    official_count = len(program_jobs) + len(pathway_jobs)
    source_health = "".join(_source_card(report) for report in reports)

    program_html = "".join(_job_card(job, "program") for job in program_jobs)
    pathway_html = "".join(_job_card(job, "pathway") for job in nearby_pathway_jobs)
    california_pathway_html = "".join(_job_card(job, "california-pathway") for job in california_pathway_jobs)
    priority_html = "".join(_job_card(job, "priority") for job in priority_jobs)
    west_coast_html = "".join(_job_card(job, "regional") for job in west_coast_watch)
    national_html = "".join(_job_card(job, "national") for job in national_watch)
    expired_html = "".join(_job_card(job, "expired") for job in expired[:12])

    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Donovan's Live Wire</title>
    <meta
      name="description"
      content="Daily apprentice electrician and inside wireman lead tracker focused on Oregon, the Pacific Northwest, California, and strong national project opportunities."
    />
    <link rel="icon" href="{_favicon_data_uri()}" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap" rel="stylesheet" />
    <style>
      :root {{
        --bg: #071120;
        --bg-soft: #0f1b31;
        --panel: rgba(8, 18, 32, 0.82);
        --panel-strong: rgba(7, 17, 32, 0.94);
        --border: rgba(148, 163, 184, 0.16);
        --border-strong: rgba(125, 211, 252, 0.18);
        --text: #e5eef9;
        --muted: #9fb2ca;
        --muted-strong: #c6d5e6;
        --cyan: #67e8f9;
        --amber: #fbbf24;
        --emerald: #6ee7b7;
        --sky: #7dd3fc;
        --fuchsia: #f0abfc;
        --shadow: 0 28px 70px rgba(2, 6, 23, 0.46);
        --radius: 24px;
        --radius-sm: 16px;
      }}

      * {{
        box-sizing: border-box;
      }}

      html {{
        scroll-behavior: smooth;
      }}

      body {{
        margin: 0;
        min-height: 100vh;
        background:
          radial-gradient(circle at top, rgba(34, 211, 238, 0.14), transparent 28%),
          radial-gradient(circle at 82% 16%, rgba(251, 191, 36, 0.12), transparent 22%),
          linear-gradient(180deg, #040b18 0%, #0c1628 38%, #101b31 100%);
        color: var(--text);
        font-family: "Space Grotesk", ui-sans-serif, sans-serif;
      }}

      a {{
        color: inherit;
      }}

      [hidden] {{
        display: none !important;
      }}

      .page {{
        width: min(1180px, calc(100% - 28px));
        margin: 0 auto;
        padding: 22px 0 72px;
      }}

      .panel {{
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        box-shadow: var(--shadow);
        backdrop-filter: blur(14px);
      }}

      .hero {{
        padding: 28px;
        display: grid;
        gap: 22px;
      }}

      .hero__eyebrow {{
        margin: 0;
        color: var(--cyan);
        font-size: 0.85rem;
        letter-spacing: 0.22em;
        text-transform: uppercase;
      }}

      .hero__title {{
        margin: 10px 0 0;
        max-width: 780px;
        font-size: clamp(2.2rem, 6vw, 4.6rem);
        line-height: 0.97;
        letter-spacing: -0.04em;
      }}

      .hero__copy {{
        margin: 16px 0 0;
        max-width: 760px;
        color: var(--muted-strong);
        font-size: 1.03rem;
        line-height: 1.8;
      }}

      .hero__row {{
        display: grid;
        gap: 20px;
        align-items: start;
      }}

      .hero__stats {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
      }}

      .stat {{
        border-radius: 20px;
        border: 1px solid var(--border);
        background: rgba(255, 255, 255, 0.04);
        padding: 14px 16px;
      }}

      .stat__label {{
        margin: 0;
        color: var(--muted);
        font-size: 0.74rem;
        text-transform: uppercase;
        letter-spacing: 0.16em;
      }}

      .stat__value {{
        margin: 10px 0 0;
        font-size: clamp(1.6rem, 5vw, 2.3rem);
        font-weight: 700;
      }}

      .hero__info {{
        border-radius: 22px;
        border: 1px solid var(--border);
        background: rgba(255, 255, 255, 0.04);
        padding: 18px 18px 16px;
      }}

      .hero__info h2,
      .toolbar__title,
      .section__title {{
        margin: 0;
        font-size: clamp(1.35rem, 3.2vw, 2rem);
      }}

      .hero__info p,
      .toolbar__copy,
      .section__copy,
      .empty-state,
      .source-card__stats,
      .source-card__notes,
      .job-card__description,
      .job-card__details {{
        color: var(--muted-strong);
      }}

      .hero__meta {{
        margin-top: 14px;
        color: var(--muted);
        font-size: 0.92rem;
        line-height: 1.7;
      }}

      .hero__links {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 18px;
      }}

      .jump-link,
      .filter-button {{
        appearance: none;
        border: 1px solid var(--border);
        background: rgba(255, 255, 255, 0.03);
        color: var(--text);
        border-radius: 999px;
        padding: 10px 14px;
        font: inherit;
        font-size: 0.92rem;
        font-weight: 600;
        cursor: pointer;
        transition: border-color 140ms ease, transform 140ms ease, background 140ms ease;
      }}

      .jump-link:hover,
      .filter-button:hover,
      .filter-button.is-active {{
        border-color: rgba(103, 232, 249, 0.38);
        background: rgba(103, 232, 249, 0.1);
      }}

      .toolbar {{
        margin-top: 18px;
        padding: 18px;
        position: sticky;
        top: 12px;
        z-index: 20;
      }}

      .toolbar__row {{
        display: grid;
        gap: 14px;
      }}

      .search-box input {{
        width: 100%;
        border: 1px solid var(--border);
        border-radius: 16px;
        background: rgba(5, 11, 23, 0.88);
        color: var(--text);
        padding: 14px 16px;
        font: inherit;
        font-size: 1rem;
      }}

      .search-box input::placeholder {{
        color: var(--muted);
      }}

      .filter-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }}

      .toolbar__summary {{
        color: var(--muted);
        font-size: 0.92rem;
      }}

      .section {{
        margin-top: 26px;
      }}

      .section__eyebrow {{
        margin: 0 0 8px;
        color: var(--muted);
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.22em;
      }}

      .section__copy {{
        margin: 10px 0 0;
        max-width: 760px;
        line-height: 1.7;
      }}

      .section__grid {{
        display: grid;
        gap: 16px;
        margin-top: 16px;
      }}

      .job-card,
      .source-card {{
        border-radius: 22px;
        border: 1px solid var(--border);
        background: var(--panel-strong);
        box-shadow: var(--shadow);
      }}

      .job-card {{
        padding: 18px;
      }}

      .job-card__badges,
      .source-card__badges {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }}

      .badge {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        border-radius: 999px;
        padding: 6px 10px;
        border: 1px solid transparent;
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }}

      .badge-priority {{
        background: rgba(251, 191, 36, 0.9);
        color: #111827;
      }}

      .badge-watch {{
        background: rgba(103, 232, 249, 0.12);
        color: #d9fbff;
        border-color: rgba(103, 232, 249, 0.2);
      }}

      .badge-status {{
        background: rgba(110, 231, 183, 0.14);
        color: #d9fff0;
        border-color: rgba(110, 231, 183, 0.18);
      }}

      .badge-source,
      .badge-expired {{
        background: rgba(255, 255, 255, 0.05);
        color: var(--text);
        border-color: rgba(255, 255, 255, 0.08);
      }}

      .badge-hub {{
        background: rgba(110, 231, 183, 0.13);
        color: #d8fff0;
        border-color: rgba(110, 231, 183, 0.18);
      }}

      .badge-regional {{
        background: rgba(125, 211, 252, 0.12);
        color: #dff6ff;
        border-color: rgba(125, 211, 252, 0.2);
      }}

      .badge-relocation {{
        background: rgba(240, 171, 252, 0.12);
        color: #ffe6ff;
        border-color: rgba(240, 171, 252, 0.22);
      }}

      .badge-warn {{
        background: rgba(251, 191, 36, 0.12);
        color: #ffe5a4;
        border-color: rgba(251, 191, 36, 0.2);
      }}

      .badge-stale {{
        background: rgba(248, 113, 113, 0.14);
        color: #ffe2e2;
        border-color: rgba(248, 113, 113, 0.22);
      }}

      .job-card__title {{
        margin: 14px 0 0;
        font-size: 1.22rem;
        line-height: 1.28;
      }}

      .job-card__title a {{
        color: #f8fbff;
        text-decoration: none;
      }}

      .job-card__title a:hover {{
        color: var(--cyan);
      }}

      .job-card__meta {{
        margin: 10px 0 0;
        color: var(--muted);
        font-size: 0.82rem;
        line-height: 1.6;
        text-transform: uppercase;
        letter-spacing: 0.12em;
      }}

      .job-card__description {{
        margin: 16px 0 0;
        line-height: 1.8;
      }}

      .job-card__stale {{
        margin: 12px 0 0;
        color: #ffd4d4;
        font-size: 0.92rem;
        line-height: 1.6;
      }}

      .job-card__reasons {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 16px;
      }}

      .job-card__footer {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-top: 16px;
        padding-top: 14px;
        border-top: 1px solid rgba(255, 255, 255, 0.08);
      }}

      .job-card__score {{
        color: var(--muted);
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
      }}

      .job-card__link,
      .source-card__header a {{
        color: var(--cyan);
        font-weight: 700;
        text-decoration: none;
      }}

      .job-card__details {{
        margin-top: 14px;
        padding-top: 12px;
        border-top: 1px dashed rgba(255, 255, 255, 0.08);
        font-size: 0.92rem;
      }}

      .job-card__details summary {{
        cursor: pointer;
        color: var(--muted);
        font-weight: 700;
      }}

      .job-card__details ul {{
        margin: 12px 0 0;
        padding-left: 18px;
      }}

      .empty-state {{
        margin-top: 16px;
        border-radius: 20px;
        border: 1px dashed rgba(125, 211, 252, 0.22);
        background: rgba(7, 17, 32, 0.6);
        padding: 18px;
        line-height: 1.8;
      }}

      .source-grid {{
        display: grid;
        gap: 16px;
        margin-top: 16px;
      }}

      .source-card {{
        padding: 18px;
      }}

      .source-card__header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-top: 14px;
      }}

      .source-card__header h3 {{
        margin: 0;
        font-size: 1.16rem;
      }}

      .source-card__stats {{
        margin: 10px 0 0;
        line-height: 1.7;
      }}

      .source-card__notes {{
        margin: 14px 0 0;
        padding-left: 18px;
        line-height: 1.8;
      }}

      @media (min-width: 760px) {{
        .hero {{
          padding: 30px;
        }}

        .hero__row,
        .toolbar__row {{
          grid-template-columns: minmax(0, 1.3fr) minmax(320px, 0.9fr);
        }}

        .hero__stats {{
          grid-template-columns: repeat(4, minmax(0, 1fr));
        }}

        .section__grid {{
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }}

        .source-grid {{
          grid-template-columns: repeat(3, minmax(0, 1fr));
        }}
      }}

      @media (max-width: 759px) {{
        .page {{
          width: min(100% - 18px, 760px);
          padding-top: 12px;
        }}

        .hero,
        .toolbar,
        .job-card,
        .source-card {{
          padding: 16px;
        }}

        .job-card__footer {{
          align-items: flex-start;
          flex-direction: column;
        }}

        .toolbar {{
          top: 8px;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="page">
      <section class="panel hero">
        <div>
          <p class="hero__eyebrow">Donovan's Live Wire</p>
          <h1 class="hero__title">Daily apprentice electrician leads with an Oregon-first lens.</h1>
          <p class="hero__copy">
            Cleaner trade-fit filtering, stronger West Coast monitoring, and a national lane for large-project opportunities that are worth traveling for.
          </p>
        </div>
        <div class="hero__row">
          <div class="hero__stats">
            <div class="stat">
              <p class="stat__label">Active Leads</p>
              <p class="stat__value">{total_active}</p>
            </div>
            <div class="stat">
              <p class="stat__label">Official Paths</p>
              <p class="stat__value">{official_count}</p>
            </div>
            <div class="stat">
              <p class="stat__label">West Coast Lane</p>
              <p class="stat__value">{regional_count}</p>
            </div>
            <div class="stat">
              <p class="stat__label">National Lane</p>
              <p class="stat__value">{national_count}</p>
            </div>
          </div>
          <aside class="hero__info">
            <h2>Latest Snapshot</h2>
            <p class="hero__meta"><strong>{escape(_format_datetime_label(generated_at))}</strong></p>
            <p class="hero__meta">
              {len(fresh_active)} fresh verified | {len(stale_active)} stale holdovers | {len(priority_jobs)} priority jobs | {relocation_count} mention relocation | {len(expired)} recently removed
            </p>
            <p class="hero__meta">
              Oregon intake windows lead the board first, then nearby official pathways, then contractor jobs. National cards stay visible for strong out-of-state opportunities.
            </p>
            <div class="hero__links">
              <a class="jump-link" href="#program-board">Jump to programs</a>
              <a class="jump-link" href="#pathway-board">Jump to pathways</a>
              <a class="jump-link" href="#california-board">Jump to California</a>
              <a class="jump-link" href="#priority-board">Jump to priority</a>
              <a class="jump-link" href="#west-coast-board">Jump to West Coast</a>
              <a class="jump-link" href="#national-board">Jump to national</a>
            </div>
          </aside>
        </div>
      </section>

      <section class="panel toolbar">
        <div class="toolbar__row">
          <div>
            <h2 class="toolbar__title">Scan Faster</h2>
            <p class="toolbar__copy">
              Search by city, company, source, or title. The quick buttons are designed for phone-sized scanning when Donovan wants to narrow the board fast.
            </p>
          </div>
          <div class="search-box">
            <input id="lead-search" type="search" placeholder="Search leads by city, company, source, or title" />
          </div>
        </div>
        <div class="filter-row" style="margin-top: 14px;">
          <button class="filter-button is-active" data-filter-button data-filter="all" type="button">All leads</button>
          <button class="filter-button" data-filter-button data-filter="fresh" type="button">Fresh</button>
          <button class="filter-button" data-filter-button data-filter="official" type="button">Official</button>
          <button class="filter-button" data-filter-button data-filter="priority" type="button">Priority only</button>
          <button class="filter-button" data-filter-button data-filter="regional" type="button">West Coast only</button>
          <button class="filter-button" data-filter-button data-filter="national" type="button">National only</button>
          <button class="filter-button" data-filter-button data-filter="relocation" type="button">Relocation</button>
          <button class="filter-button" data-filter-button data-filter="stale" type="button">Stale</button>
        </div>
        <p class="toolbar__summary" id="filter-summary">Showing {total_active} visible active leads.</p>
      </section>

      <section class="section" id="program-board" data-job-section>
        <p class="section__eyebrow">Direct Intake</p>
        <h2 class="section__title">Official Program Openings</h2>
        <p class="section__copy">
          These are apprenticeship intake windows and program-opening signals, not normal contractor job ads. For Donovan, this is the most important local lane when Oregon and regional entry points are tight.
        </p>
        <div class="section__grid">
          {program_html}
        </div>
        <p class="empty-state" data-empty-message{" hidden" if program_html else ""}>
          No official apprenticeship intake openings cleared the current filter in this run.
        </p>
      </section>

      <section class="section" id="pathway-board" data-job-section>
        <p class="section__eyebrow">Regional Backup</p>
        <h2 class="section__title">Official Nearby Apprenticeship Pathways</h2>
        <p class="section__copy">
          These are official state-directory programs that fit Donovan's inside wireman path but do not currently confirm an open application window. They stay separate so the board is honest about what is open now versus what is worth checking directly.
        </p>
        <div class="section__grid">
          {pathway_html}
        </div>
        <p class="empty-state" data-empty-message{" hidden" if pathway_html else ""}>
          No nearby official pathways cleared the current filter in this run.
        </p>
      </section>

      <section class="section" id="california-board" data-job-section>
        <p class="section__eyebrow">California Lane</p>
        <h2 class="section__title">California Official Sponsors To Check Directly</h2>
        <p class="section__copy">
          California DIR sponsor records stay in their own lane so they do not drown out Oregon and nearby pathways. These are official sponsor contacts worth checking directly, not confirmed-open intake windows.
        </p>
        <div class="section__grid">
          {california_pathway_html}
        </div>
        <p class="empty-state" data-empty-message{" hidden" if california_pathway_html else ""}>
          No California official sponsor records cleared the current filter in this run.
        </p>
      </section>

      <section class="section" id="priority-board" data-job-section>
        <p class="section__eyebrow">Best Bets</p>
        <h2 class="section__title">Priority Board</h2>
        <p class="section__copy">
          Highest-signal apprentice-track jobs with stronger hub alignment or clearer mission-critical context.
        </p>
        <div class="section__grid">
          {priority_html}
        </div>
        <p class="empty-state" data-empty-message hidden>No priority leads match the current filter.</p>
      </section>

      <section class="section" id="west-coast-board" data-job-section>
        <p class="section__eyebrow">Regional Lane</p>
        <h2 class="section__title">Oregon, Pacific Northwest, And California</h2>
        <p class="section__copy">
          These are the nearby or regionally aligned leads that should be the fastest to scan when local movement matters most.
        </p>
        <div class="section__grid">
          {west_coast_html}
        </div>
        <p class="empty-state" data-empty-message{" hidden" if west_coast_html else ""}>
          No Oregon, Washington, or California leads cleared the current threshold in this scrape. The tool is still monitoring regional boards so strong West Coast roles will surface here as soon as they appear.
        </p>
      </section>

      <section class="section" id="national-board" data-job-section>
        <p class="section__eyebrow">Broader Net</p>
        <h2 class="section__title">National Project Opportunities</h2>
        <p class="section__copy">
          National listings stay visible here for large-project, hub-based, or relocation-worthy leads that can still move Donovan forward.
        </p>
        <div class="section__grid">
          {national_html}
        </div>
        <p class="empty-state" data-empty-message hidden>No national leads match the current filter.</p>
      </section>

      <section class="section" id="source-health">
        <p class="section__eyebrow">Source Health</p>
        <h2 class="section__title">What Each Feed Produced</h2>
        <p class="section__copy">
          This is the monitor status for each official source. If a feed is temporarily down, the board keeps last-known-good leads visible and marks them clearly instead of pretending they disappeared.
        </p>
        <div class="source-grid">
          {source_health}
        </div>
      </section>

      <section class="section" id="recently-removed" data-job-section>
        <p class="section__eyebrow">Recently Removed</p>
        <h2 class="section__title">No Longer Seen</h2>
        <p class="section__copy">
          These were previously relevant but did not appear in the latest scrape.
        </p>
        <div class="section__grid">
          {expired_html}
        </div>
        <p class="empty-state" data-empty-message{" hidden" if expired_html else ""}>
          Nothing relevant has dropped off recently.
        </p>
      </section>
    </main>
    <script>
      const searchInput = document.getElementById('lead-search');
      const summary = document.getElementById('filter-summary');
      const filterButtons = Array.from(document.querySelectorAll('[data-filter-button]'));
      const cards = Array.from(document.querySelectorAll('.job-card'));
      let activeFilter = 'all';

      function matchesFilter(card) {{
        switch (activeFilter) {{
          case 'fresh':
            return card.dataset.lane !== 'expired' && card.dataset.stale === '0';
          case 'official':
            return card.dataset.official === '1';
          case 'priority':
            return card.dataset.bucket === 'priority';
          case 'regional':
            return card.dataset.region === '1';
          case 'national':
            return card.dataset.lane === 'national';
          case 'relocation':
            return card.dataset.relocation === '1';
          case 'stale':
            return card.dataset.stale === '1';
          default:
            return true;
        }}
      }}

      function applyFilters() {{
        const query = (searchInput.value || '').trim().toLowerCase();
        let visibleCount = 0;
        let visibleStale = 0;

        cards.forEach((card) => {{
          const searchText = card.dataset.search || '';
          const visible = matchesFilter(card) && (!query || searchText.includes(query));
          card.hidden = !visible;
          if (visible && card.dataset.lane !== 'expired') {{
            visibleCount += 1;
            if (card.dataset.stale === '1') {{
              visibleStale += 1;
            }}
          }}
        }});

        document.querySelectorAll('[data-job-section]').forEach((section) => {{
          const sectionCards = Array.from(section.querySelectorAll('.job-card'));
          const visibleCards = sectionCards.filter((card) => !card.hidden);
          const emptyMessage = section.querySelector('[data-empty-message]');

          if (emptyMessage) {{
            emptyMessage.hidden = visibleCards.length !== 0;
          }}
        }});

        summary.textContent = 'Showing ' + visibleCount + ' visible active leads' + (visibleStale ? ' (' + visibleStale + ' stale).' : '.');
      }}

      filterButtons.forEach((button) => {{
        button.addEventListener('click', () => {{
          activeFilter = button.dataset.filter || 'all';
          filterButtons.forEach((item) => item.classList.toggle('is-active', item === button));
          applyFilters();
        }});
      }});

      searchInput.addEventListener('input', applyFilters);
      applyFilters();
    </script>
  </body>
</html>
"""


def render_latest_json(generated_at: str, jobs: list[JobLead], reports: list[SourceReport]) -> str:
    active_jobs = [
        job.to_dict()
        for job in jobs
        if job.status == "active" and job.bucket in {"priority", "watch"}
    ]
    payload = {
        "generated_at": generated_at,
        "counts": {
            "active_relevant": len(active_jobs),
            "fresh_active_relevant": len(
                [
                    job
                    for job in jobs
                    if job.status == "active" and job.bucket in {"priority", "watch"} and not job.stale_source
                ]
            ),
            "stale_active_relevant": len(
                [
                    job
                    for job in jobs
                    if job.status == "active" and job.bucket in {"priority", "watch"} and job.stale_source
                ]
            ),
            "expired_relevant": len(
                [
                    job
                    for job in jobs
                    if job.status == "expired" and job.bucket in {"priority", "watch"}
                ]
            ),
        },
        "jobs": active_jobs,
        "reports": [report.to_dict() for report in reports],
    }
    return json.dumps(payload, indent=2)
