from rest_framework.authentication import SessionAuthentication


class SessionAuthenticationWith401(SessionAuthentication):
    """Session authentication that answers missing credentials with 401 instead of 403."""

    def authenticate_header(self, request):
        return "Session"
