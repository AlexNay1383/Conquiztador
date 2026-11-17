class GameError(Exception):
    """A refused game operation. `code` is a stable identifier of the reason; `message` is user-facing."""

    def __init__(self, message, code):
        super().__init__(message)
        self.message = message
        self.code = code

    def __repr__(self):
        return f"{type(self).__name__}(code={self.code!r})"


class NotFoundError(GameError):
    """A referenced record does not exist."""


class InvalidInputError(GameError):
    """The arguments are invalid regardless of the current game state."""


class InvalidStateError(GameError):
    """The arguments are valid, but the operation is not allowed in the current state."""
