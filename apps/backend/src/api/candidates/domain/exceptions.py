class CandidateNotFoundError(Exception):
    def __init__(self, candidate_id: int) -> None:
        super().__init__(f"Candidate #{candidate_id} not found")
        self.candidate_id = candidate_id


class CandidateAlreadyExistsError(Exception):
    def __init__(self, email: str) -> None:
        super().__init__(f"Candidate with email {email} already exists")
        self.email = email


class AnswerNotFoundError(Exception):
    def __init__(self, answer_id: int) -> None:
        super().__init__(f"Answer #{answer_id} not found")
        self.answer_id = answer_id
