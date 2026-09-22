from scripts.maintenance import review_open_prs


def test_review_open_prs_reports_failed_and_pending_checks(monkeypatch):
    responses = {
        "/repos/acme/widgets/pulls?state=open&per_page=100": [
            {"number": 7},
        ],
        "/repos/acme/widgets/pulls/7": {
            "number": 7,
            "title": "Repair widget",
            "head": {"ref": "fix/widget", "sha": "abc123"},
            "mergeable": False,
            "mergeable_state": "dirty",
            "html_url": "https://github.com/acme/widgets/pull/7",
        },
        "/repos/acme/widgets/commits/abc123/check-runs?per_page=100": {
            "check_runs": [
                {"name": "unit", "status": "completed", "conclusion": "failure"},
                {"name": "integration", "status": "in_progress", "conclusion": None},
                {"name": "optional", "status": "completed", "conclusion": "skipped"},
            ]
        },
    }
    monkeypatch.setattr(review_open_prs, "_get", lambda path, token: responses[path])

    assert review_open_prs.review_open_prs("acme/widgets") == [
        {
            "number": 7,
            "title": "Repair widget",
            "head": "fix/widget",
            "mergeable": False,
            "mergeable_state": "dirty",
            "failed_checks": ["unit"],
            "pending_checks": ["integration"],
            "url": "https://github.com/acme/widgets/pull/7",
        }
    ]
