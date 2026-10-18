from api.config import Settings
from api.main import create_app


def test_app_has_all_routes() -> None:
    app = create_app(Settings(database_url="sqlite+aiosqlite://"))

    paths = set(app.openapi()["paths"].keys())

    expected = {
        "/health",
        "/auth/sign-in",
        "/auth/refresh-tokens",
        "/auth/sign-out",
        "/candidate/interview",
        "/candidate/interview/answers/{question_id}",
        "/hr/roles",
        "/hr/roles/{role_id}/candidates",
        "/hr/candidates",
        "/hr/candidates/{candidate_id}",
        "/hr/answers/{answer_id}",
        "/hr/answers/{answer_id}/score",
        "/hr/answers/{answer_id}/audio",
        "/hr/scoring-jobs",
        "/hr/scoring-jobs/{job_id}/retry",
        "/hr/import",
    }

    assert expected <= paths, f"missing routes: {sorted(expected - paths)}"
