class UserNotFoundError(Exception):
    def __init__(self, user_id: int) -> None:
        super().__init__(f"User #{user_id} not found")
        self.user_id = user_id


class EmailAlreadyExistsError(Exception):
    def __init__(self, email: str) -> None:
        super().__init__(f"Email {email} is already registered")
        self.email = email


class WeakPasswordError(Exception):
    def __init__(self, min_length: int) -> None:
        super().__init__(f"Password must be at least {min_length} characters long")
        self.min_length = min_length


class RateLimitExceededError(Exception):
    def __init__(self) -> None:
        super().__init__("Too many requests")
