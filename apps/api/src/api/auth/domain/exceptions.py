class UserNotFoundError(Exception):
    def __init__(self, user_id: int) -> None:
        super().__init__(f"User #{user_id} not found")
        self.user_id = user_id
