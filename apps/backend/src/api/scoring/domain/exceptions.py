class ScoringJobNotFoundError(Exception):
    def __init__(self, job_id: int) -> None:
        super().__init__(f"Scoring job #{job_id} not found")
        self.job_id = job_id


class ScoringJobInvalidTransitionError(Exception):
    def __init__(self, job_id: int, status: str) -> None:
        super().__init__(f"Scoring job #{job_id} cannot transition from status '{status}'")
        self.job_id = job_id
        self.status = status
