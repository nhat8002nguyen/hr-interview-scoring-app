class RoleNotFoundError(Exception):
    def __init__(self, role_id: int) -> None:
        super().__init__(f"Role #{role_id} not found")
        self.role_id = role_id


class QuestionNotFoundError(Exception):
    def __init__(self, question_id: int) -> None:
        super().__init__(f"Question #{question_id} not found")
        self.question_id = question_id
