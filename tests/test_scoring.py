from wireman_tracker.models import JobLead
from wireman_tracker.scoring import evaluate_job


def make_job(
    title: str,
    description: str = "",
    location: str = "",
    context: str = "",
    metadata: dict | None = None,
) -> JobLead:
    return JobLead(
        job_key="test",
        source_key="test",
        source_name="Test",
        company="Test Co",
        title=title,
        detail_url="https://example.com/job",
        source_url="https://example.com",
        description=description,
        location=location,
        source_context=context,
        metadata=metadata or {},
    )


def test_low_voltage_apprentice_scores_as_watch_or_better() -> None:
    job = make_job(
        "Low Voltage Integration Technician / Apprentice",
        description="Mission critical work installing low voltage and fiber optic systems.",
        location="Plain City, Ohio",
    )
    evaluated = evaluate_job(job)
    assert evaluated.bucket in {"watch", "priority"}
    assert evaluated.score >= 55


def test_non_electrical_apprentice_is_filtered_out() -> None:
    job = make_job(
        "Laborer Apprentice",
        description="General labor support on a commercial project.",
        location="Omaha, Nebraska",
    )
    evaluated = evaluate_job(job)
    assert evaluated.bucket == "discard"


def test_senior_data_center_role_without_apprentice_signal_is_filtered_out() -> None:
    job = make_job(
        "Traveling Senior Electrical Superintendent - MSG - Data Centers",
        description="Senior leadership role for large mission critical builds.",
        location="6 Locations Available",
    )
    evaluated = evaluate_job(job)
    assert evaluated.bucket == "discard"


def test_portland_apprentice_role_is_kept_in_watchlist() -> None:
    job = make_job(
        "Apprentice Electrician",
        description="Commercial electrical work on new construction projects.",
        location="Portland, OR",
    )
    evaluated = evaluate_job(job)
    assert evaluated.bucket == "watch"
    assert "Portland, OR" in evaluated.metadata.get("regional_matches", [])


def test_relocation_assistance_is_flagged() -> None:
    job = make_job(
        "Electrical Apprentice",
        description="Relocation assistance available for qualified candidates on this data center build.",
        location="Dallas, TX",
    )
    evaluated = evaluate_job(job)
    assert evaluated.metadata.get("relocation_assistance") is True
    assert any("relocation assistance" in reason for reason in evaluated.reasons)


def test_generic_california_role_gets_west_coast_region_tag() -> None:
    job = make_job(
        "Electrical Apprentice",
        description="Electrical work supporting utility-scale construction.",
        location="CA, United States",
    )
    evaluated = evaluate_job(job)
    assert "West Coast region" in evaluated.metadata.get("regional_matches", [])


def test_journeyman_role_is_filtered_out() -> None:
    job = make_job(
        "Journeyman Electrician",
        description="Install electrical systems on commercial construction sites.",
        location="Phoenix, AZ",
    )
    evaluated = evaluate_job(job)
    assert evaluated.bucket == "discard"


def test_job_template_is_filtered_out() -> None:
    job = make_job(
        "Ardent Services, LLC Job Template - Electrical Apprentice",
        description="Template listing for electrical apprentice candidates.",
        location="Houston, TX",
    )
    evaluated = evaluate_job(job)
    assert evaluated.bucket == "discard"


def test_generic_helper_without_context_is_filtered_out() -> None:
    job = make_job(
        "Power Electrical Helper I-US",
        description="Support electrical field work across the business.",
        location="United States",
    )
    evaluated = evaluate_job(job)
    assert evaluated.bucket == "discard"


def test_open_inside_electrician_program_scores_as_priority() -> None:
    job = make_job(
        "Inside Electrician Apprenticeship Intake Open",
        description="Official Oregon Apprenticeship openings board currently lists this committee as open.",
        location="Portland, OR; Areas 1 & 6",
        metadata={
            "lead_type": "program",
            "program_status": "open",
            "program_status_source": "committee site",
            "state_title": "Inside Electrician",
        },
    )
    evaluated = evaluate_job(job)
    assert evaluated.bucket == "priority"
    assert any("official apprenticeship intake" in reason for reason in evaluated.reasons)


def test_official_pathway_scores_as_watch_not_priority() -> None:
    job = make_job(
        "Inside Wireman / Inside Electrician Apprenticeship Pathway",
        description="Official Washington L&I apprenticeship directory entry with Oregon-facing coverage.",
        location="Battle Ground, WA; serves Clark, Multnomah, Clackamas, Lane, Linn",
        metadata={
            "lead_type": "pathway",
            "program_status": "directory",
            "program_status_source": "state apprenticeship directory",
            "occupation_names": ["Inside Wireman", "Inside Electrician"],
            "regional_matches": ["Portland metro", "Eugene corridor"],
        },
    )
    evaluated = evaluate_job(job)
    assert evaluated.bucket == "watch"
    assert "Portland metro" in evaluated.metadata.get("regional_matches", [])
    assert any("official apprenticeship pathway" in reason for reason in evaluated.reasons)


def test_location_mismatch_apprentice_role_is_filtered_when_context_is_weak() -> None:
    job = make_job(
        "Apprentice Electrician-Shreveport, LA",
        description="Function as an Apprentice Electrician under a licensed electrician.",
        location="US-TX-Dallas",
    )
    evaluated = evaluate_job(job)
    assert evaluated.bucket == "discard"
    assert any("title location does not match" in reason for reason in evaluated.reasons)
    assert any("too ambiguous" in reason for reason in evaluated.reasons)
