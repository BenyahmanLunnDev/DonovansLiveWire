from wireman_tracker.sources import (
    _extract_turner_token,
    _parse_california_result_rows,
    _parse_oeg_opportunities,
)


def test_parse_oeg_structured_payload() -> None:
    payload = {
        "opportunities": [
            {
                "Id": "abc-123",
                "Title": "Apprentice Electrician",
                "JobCategoryName": "Trade",
                "PostedDate": "2026-03-28T18:22:13.402Z",
                "BriefDescription": "Entry-level electrical work supporting large projects.",
                "JobLocationType": 1,
                "Locations": [
                    {
                        "LocalizedDescription": "Headquarters",
                        "Address": {
                            "City": "Portland",
                            "State": {"Code": "OR"},
                            "Country": {"Code": "USA"},
                        },
                    }
                ],
            }
        ]
    }

    jobs = _parse_oeg_opportunities(payload)

    assert len(jobs) == 1
    assert jobs[0].title == "Apprentice Electrician"
    assert jobs[0].location == "Portland, OR"
    assert "OpportunityDetail?opportunityId=abc-123" in jobs[0].detail_url


def test_extract_turner_token_from_html() -> None:
    html = '<script>if(!csod.context) csod.context={"token":"abc.def.ghi","corp":"turnerconstruction"}</script>'
    assert _extract_turner_token(html) == "abc.def.ghi"


def test_parse_california_public_works_rows() -> None:
    html = """
    <form id="form1">
      <table>
        <tr>
          <td>Contact information: </td>
          <td><b>Alameda County Electrical Joint Apprenticeship And Training Committee (Jatc)</b><br />14600 Catalina Street<br />San Leandro, CA 94577</td>
        </tr>
        <tr>
          <td>Contact person: </td>
          <td>Jason Bates, Apprentice Coordinator</td>
        </tr>
        <tr>
          <td>Contact phone / e-mail: </td>
          <td>(510) 351-5282 <a href="mailto:info@595jatc.org">info@595jatc.org</a></td>
        </tr>
      </table>
    </form>
    """

    entries = _parse_california_result_rows(html, "Alameda", "https://example.com/results")

    assert len(entries) == 1
    assert entries[0]["company"] == "Alameda County Electrical Joint Apprenticeship And Training Committee (Jatc)"
    assert entries[0]["contact"] == "Jason Bates, Apprentice Coordinator"
    assert entries[0]["email"] == "info@595jatc.org"

