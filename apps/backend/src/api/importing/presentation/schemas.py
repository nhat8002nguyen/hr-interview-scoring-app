from pydantic import BaseModel


class ImportSummaryResponse(BaseModel):
    roles_created: int
    questions_created: int
    candidates_created: int
    answers_imported: int
    scoring_jobs_queued: int
    audio_answers_needing_person: int
