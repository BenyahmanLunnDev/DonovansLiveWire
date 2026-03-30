from wireman_tracker.models import JobLead, SourceReport
from wireman_tracker.render import render_index


def test_render_shows_stale_badges_and_filters() -> None:
    stale_job = JobLead(
        job_key="job-1",
        source_key="washingtonapprenticeship",
        source_name="Washington L&I Apprenticeship",
        company="Test Sponsor",
        title="Inside Wireman Apprenticeship Pathway",
        detail_url="https://example.com/job-1",
        source_url="https://example.com",
        location="Vancouver, WA",
        description="Official pathway to check directly.",
        bucket="watch",
        status="active",
        stale_source=True,
        stale_since="2026-03-29",
        first_seen="2026-03-20",
        last_seen="2026-03-28",
        metadata={"lead_type": "pathway", "regional_matches": ["Portland metro"]},
    )
    report = SourceReport(
        source_key="washingtonapprenticeship",
        source_name="Washington L&I Apprenticeship",
        source_url="https://example.com",
        status="error",
        total_relevant=1,
        stale_relevant_count=1,
        serving_stale=True,
        last_attempt_at="2026-03-29T06:07:00-07:00",
        last_success_at="2026-03-28T06:07:00-07:00",
    )

    html = render_index("2026-03-29T06:07:00-07:00", [stale_job], [report])

    assert "Stale source" in html
    assert "Serving stale" in html
    assert 'data-filter="fresh"' in html
    assert 'data-filter="official"' in html
    assert 'data-filter="stale"' in html


def test_render_separates_california_sponsor_lane() -> None:
    nearby_pathway = JobLead(
        job_key="wa-pathway",
        source_key="washingtonapprenticeship",
        source_name="Washington L&I Apprenticeship",
        company="Frontier Electric Apprenticeship & Training",
        title="Inside Wireman Apprenticeship Pathway",
        detail_url="https://example.com/wa",
        source_url="https://example.com/wa-source",
        location="Battle Ground, WA",
        description="Official pathway entry.",
        bucket="watch",
        status="active",
        first_seen="2026-03-20",
        last_seen="2026-03-29",
        metadata={"lead_type": "pathway", "regional_matches": ["Portland metro"]},
    )
    california_pathway = JobLead(
        job_key="ca-pathway",
        source_key="californiaapprenticeship",
        source_name="California DIR Apprenticeship",
        company="Santa Clara County Electrical JATC",
        title="Electrical & Electronic Apprenticeship Sponsor",
        detail_url="https://example.com/ca",
        source_url="https://example.com/ca-source",
        location="Milpitas, CA",
        description="Official California sponsor entry.",
        bucket="watch",
        status="active",
        first_seen="2026-03-20",
        last_seen="2026-03-29",
        metadata={"lead_type": "pathway", "regional_matches": ["Bay Area, CA"]},
    )

    html = render_index("2026-03-29T06:07:00-07:00", [nearby_pathway, california_pathway], [])

    assert "Official Nearby Apprenticeship Pathways" in html
    assert "California Official Sponsors To Check Directly" in html
    assert "Jump to California" in html
