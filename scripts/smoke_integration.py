#!/usr/bin/env python3
"""Exercise the deployed API end to end.

Run this from the backend workspace so `httpx` resolves:

    (cd apps/backend && uv run python ../../scripts/smoke_integration.py ...)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, NoReturn

import httpx

QUESTIONS_TOTAL = 6
PACK_ANSWERS = 35
PACK_TEXT_JOBS = 30
PACK_AUDIO_ANSWERS = 5


def fail(message: str) -> NoReturn:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def expect_status(response: httpx.Response, expected: int, label: str) -> None:
    if response.status_code != expected:
        fail(
            f"{label}: expected HTTP {expected}, got {response.status_code}: "
            f"{response.text[:500]}"
        )


def expect_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        fail(f"{label}: expected {expected!r}, got {actual!r}")


def expect_cors(response: httpx.Response, origin: str, label: str) -> None:
    expect_equal(
        response.headers.get("access-control-allow-origin"),
        origin,
        f"{label}: CORS allow-origin",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://localhost:3000")
    parser.add_argument("--candidate-origin", default="http://localhost:3001")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--hr-email", default="hr@talotrace.ai")
    parser.add_argument("--hr-password", default="change-me")
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    api_url = args.api_url.rstrip("/")
    candidate_origin = args.candidate_origin.rstrip("/")
    pack = Path(args.pack)
    audio = Path(args.audio)

    if not pack.is_file():
        fail(f"pack not found: {pack}")
    if not audio.is_file():
        fail(f"audio file not found: {audio}")

    with httpx.Client(base_url=api_url, timeout=30.0) as client:
        response = client.post(
            "/auth/sign-in",
            json={"email": args.hr_email, "password": args.hr_password},
        )
        expect_status(response, 200, "HR sign-in")
        token = response.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        with pack.open("rb") as handle:
            response = client.post(
                "/hr/import",
                headers=auth,
                files={"file": (pack.name, handle, "application/zip")},
            )
        expect_status(response, 200, "import pack")
        summary = response.json()

        if summary["answers_imported"] == PACK_ANSWERS:
            expect_equal(summary["scoring_jobs_queued"], PACK_TEXT_JOBS, "import text jobs")
            expect_equal(
                summary["audio_answers_needing_person"],
                PACK_AUDIO_ANSWERS,
                "import audio answers",
            )
        elif summary["answers_imported"] == 0:
            expect_equal(summary["scoring_jobs_queued"], 0, "repeat import text jobs")
            expect_equal(
                summary["audio_answers_needing_person"],
                0,
                "repeat import audio answers",
            )
        else:
            fail(f"unexpected import summary: {summary}")

        response = client.get("/hr/roles", headers=auth)
        expect_status(response, 200, "list roles")
        roles = response.json()
        expect_equal(len(roles), 5, "role count")
        role_id = roles[0]["id"]

        email = f"smoke+{int(time.time())}@talotrace.ai"
        response = client.post(
            "/hr/candidates",
            headers=auth,
            json={"name": "Deployment Smoke", "email": email, "role_id": role_id},
        )
        expect_status(response, 201, "create candidate")
        candidate = response.json()
        candidate_id = candidate["id"]
        candidate_headers = {"X-Candidate-Token": candidate["session_token"]}

        response = client.get("/candidate/interview", headers=candidate_headers)
        expect_status(response, 200, "candidate interview")
        interview = response.json()
        expect_equal(len(interview["questions"]), QUESTIONS_TOTAL, "question count")
        first_question = interview["questions"][0]
        second_question = interview["questions"][1]

        response = client.options(
            "/candidate/interview",
            headers={
                "Origin": candidate_origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-candidate-token",
            },
        )
        expect_status(response, 200, "candidate CORS preflight")
        expect_cors(response, candidate_origin, "candidate CORS preflight")

        answer_text = (
            "I led a payments reliability fix that removed duplicate charges. "
            "I designed the idempotency key, shipped the migration and tests, "
            "and measured zero repeats over the next quarter."
        )
        response = client.post(
            f"/candidate/interview/answers/{first_question['id']}",
            headers={**candidate_headers, "Origin": candidate_origin},
            json={"answer_type": "text", "text": answer_text},
        )
        expect_status(response, 201, "text answer")
        expect_equal(response.json()["unchanged"], False, "text answer changed")
        expect_cors(response, candidate_origin, "text answer")

        response = client.post(
            f"/candidate/interview/answers/{first_question['id']}",
            headers={**candidate_headers, "Origin": candidate_origin},
            json={"answer_type": "text", "text": answer_text},
        )
        expect_status(response, 200, "identical text answer")
        expect_equal(response.json()["unchanged"], True, "identical text answer")

        with audio.open("rb") as handle:
            response = client.post(
                f"/candidate/interview/answers/{second_question['id']}/audio",
                headers={**candidate_headers, "Origin": candidate_origin},
                files={"file": (audio.name, handle, "audio/mp4")},
            )
        expect_status(response, 201, "audio answer")
        expect_cors(response, candidate_origin, "audio answer")

        response = client.get(f"/hr/candidates/{candidate_id}", headers=auth)
        expect_status(response, 200, "candidate detail")
        detail = response.json()
        expect_equal(len(detail["answers"]), 2, "candidate answer count")

        first_answer = next(
            answer
            for answer in detail["answers"]
            if answer["question_id"] == first_question["id"]
        )
        audio_answer = next(
            answer
            for answer in detail["answers"]
            if answer["question_id"] == second_question["id"]
        )
        expect_equal(
            audio_answer["scoring"]["status"],
            "needs_a_person",
            "audio scoring status",
        )

        deadline = time.monotonic() + args.timeout
        last_status = None
        while time.monotonic() < deadline:
            response = client.get(
                f"/hr/answers/{first_answer['id']}",
                headers=auth,
            )
            expect_status(response, 200, "answer detail")
            scoring = response.json()["scoring"]
            if scoring["status"] != last_status:
                print(f"q1 scoring status: {scoring['status']}", flush=True)
                last_status = scoring["status"]
            if scoring["status"] == "scored":
                score = scoring["suggested_score"]
                if not isinstance(score, int) or not 1 <= score <= 4:
                    fail(f"invalid suggested score: {score!r}")
                break
            if scoring["status"] == "failed":
                fail(f"scoring failed: {scoring.get('last_error')}")
            time.sleep(2)
        else:
            fail(f"timed out waiting for q1 to score; last status={last_status}")

        print(f"import summary: {summary}")
        print(f"smoke candidate: id={candidate_id} email={email}")
        print(f"q1 scored: {scoring['suggested_score']}")
        print(f"q2 audio: {audio_answer['scoring']['status']}")
        print("smoke integration ok")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
