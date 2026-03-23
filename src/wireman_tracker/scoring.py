from __future__ import annotations

from wireman_tracker.config import (
    DESCRIPTION_SIGNALS,
    NEGATIVE_DESCRIPTION_SIGNALS,
    NEGATIVE_TITLE_SIGNALS,
    PRIORITY_HUBS,
    REGIONAL_HUBS,
    RELOCATION_SIGNALS,
    SOURCE_CONTEXT_SIGNALS,
    STRONG_TITLE_SIGNALS,
    TITLE_SIGNALS,
    WEST_COAST_LOCATION_MARKERS,
)
from wireman_tracker.models import JobLead


def evaluate_job(job: JobLead) -> JobLead:
    title = job.title.lower()
    description = job.description.lower()
    location = job.location.lower()
    context = f"{job.source_context} {job.discovered_via}".lower()
    combined = f"{title} {description} {location} {context}"
    content_only = f"{title} {description} {location}"

    score = 0
    reasons: list[str] = []
    hub_matches: list[str] = []
    regional_matches: list[str] = []
    apprentice_like = any(term in content_only for term in ("apprentice", "trainee", "helper", "wireman"))
    electrical_like = any(term in content_only for term in ("electric", "electrical", "low voltage", "fiber"))
    helper_like = "helper" in title or "helper" in description
    generic_location = location.strip() in {"", "united states", "usa", "us"}
    relocation_phrase = next(
        (
            phrase
            for phrase in RELOCATION_SIGNALS
            if phrase in description or phrase in content_only or phrase in context
        ),
        "",
    )

    for phrase, points in STRONG_TITLE_SIGNALS.items():
        if phrase in title:
            score += points
            reasons.append(f"title matches '{phrase}'")

    for phrase, points in TITLE_SIGNALS.items():
        if phrase in title:
            score += points
            reasons.append(f"title includes '{phrase}'")

    for phrase, points in DESCRIPTION_SIGNALS.items():
        if phrase in description:
            score += points
            reasons.append(f"description includes '{phrase}'")

    for phrase, points in SOURCE_CONTEXT_SIGNALS.items():
        if phrase in context:
            score += points
            reasons.append(f"source context points to '{phrase}' work")

    if "trainee" in title and electrical_like:
        score += 30
        reasons.append("title includes electrical trainee signal")

    if "helper" in title and electrical_like:
        score += 24
        reasons.append("title includes electrical helper signal")

    for hub_name, hub_terms in PRIORITY_HUBS.items():
        if any(term in combined for term in hub_terms):
            score += 14
            hub_matches.append(hub_name)
            reasons.append(f"priority hub match: {hub_name}")

    for hub_name, hub_terms in REGIONAL_HUBS.items():
        if any(term in combined for term in hub_terms):
            score += 8
            regional_matches.append(hub_name)
            reasons.append(f"regional coverage match: {hub_name}")

    if (
        any(marker in location for marker in WEST_COAST_LOCATION_MARKERS)
        and not regional_matches
        and not hub_matches
    ):
        score += 6
        regional_matches.append("West Coast region")
        reasons.append("regional coverage match: West Coast region")

    if regional_matches and apprentice_like and electrical_like:
        score += 8
        reasons.append("regional apprentice opportunity")

    for phrase, points in NEGATIVE_TITLE_SIGNALS.items():
        if phrase in title:
            score += points
            reasons.append(f"title penalty for '{phrase}'")

    for phrase, points in NEGATIVE_DESCRIPTION_SIGNALS.items():
        if phrase in description:
            score += points
            reasons.append(f"description penalty for '{phrase}'")

    if not apprentice_like:
        score -= 38
        reasons.append("missing apprentice / trainee / helper / wireman signal")

    if not electrical_like:
        score -= 22
        reasons.append("missing clear electrical / apprentice signal")

    if "data center" in content_only and apprentice_like:
        score += 18
        reasons.append("data center plus apprentice combination")

    if "mission critical" in content_only and apprentice_like:
        score += 14
        reasons.append("mission critical plus apprentice combination")

    if relocation_phrase:
        job.metadata["relocation_assistance"] = True
        job.metadata["relocation_signal"] = relocation_phrase
        reasons.append("relocation assistance mentioned")
        if not any(marker in location for marker in WEST_COAST_LOCATION_MARKERS):
            score += 8
            reasons.append("relocation help makes out-of-region travel more realistic")
    else:
        job.metadata.pop("relocation_assistance", None)
        job.metadata.pop("relocation_signal", None)

    high_value_context = bool(hub_matches or regional_matches) or any(
        phrase in content_only or phrase in context
        for phrase in ("data center", "mission critical", "critical facilities", "hyperscale", "colocation")
    ) or bool(relocation_phrase)

    if helper_like and not high_value_context:
        score -= 45
        reasons.append("generic helper role without stronger project or location context")

    if generic_location:
        score -= 28
        reasons.append("location is too broad to be immediately actionable")

    if "job template" in combined:
        score -= 80
        reasons.append("templated listing is too generic to prioritize")

    if "electric" in title and any(
        phrase in title
        for phrase in ("manager", "superintendent", "director", "engineer", "commissioning")
    ):
        score -= 20
        reasons.append("electrical title appears to be senior / non-apprentice work")

    if not apprentice_like and any(
        phrase in title
        for phrase in ("manager", "superintendent", "director", "engineer", "coordinator", "lead")
    ):
        score -= 24
        reasons.append("title looks senior or professional rather than apprentice-track")

    unique_reasons = []
    seen = set()
    for reason in reasons:
        if reason not in seen:
            unique_reasons.append(reason)
            seen.add(reason)

    job.score = score
    job.reasons = unique_reasons[:8]
    job.hub_matches = sorted(set(hub_matches))
    if regional_matches:
        job.metadata["regional_matches"] = sorted(set(regional_matches))
    else:
        job.metadata.pop("regional_matches", None)
    priority_context = bool(job.hub_matches) or bool(relocation_phrase) or any(
        phrase in content_only or phrase in context
        for phrase in ("data center", "mission critical", "critical facilities", "hyperscale", "colocation")
    )

    if score >= 95 and priority_context:
        job.bucket = "priority"
    elif score >= 70:
        job.bucket = "watch"
    else:
        job.bucket = "discard"

    return job
