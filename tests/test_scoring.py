from wireman_tracker.models import JobLead
from wireman_tracker.scoring import evaluate_job


def make_job(title: str, description: str = "", location: str = "", context: str = "") -> JobLead:
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
