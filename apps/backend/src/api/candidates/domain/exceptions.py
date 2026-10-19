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


class AttemptsExhaustedError(Exception):
    def __init__(self, question_id: int, max_submissions: int) -> None:
        super().__init__(
            f"Maximum submissions ({max_submissions}) reached for question {question_id}"
        )
        self.question_id = question_id
        self.max_submissions = max_submissions
