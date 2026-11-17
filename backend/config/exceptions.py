from rest_framework.exceptions import NotAuthenticated
from rest_framework.views import exception_handler

NOT_AUTHENTICATED_MESSAGE = "Необходимо е да влезете в профила си."


def _as_error_list(value):
    if isinstance(value, dict):
        return {key: _as_error_list(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_as_error_list(item) if isinstance(item, (dict, list)) else str(item) for item in value]
    return [str(value)]


def api_exception_handler(exc, context):
    """Wrap every DRF error into the single `{"errors": {field: [messages]}}` shape."""
    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(exc, NotAuthenticated):
        data = {"detail": NOT_AUTHENTICATED_MESSAGE}
    elif isinstance(data, list):
        data = {"non_field_errors": data}
    response.data = {"errors": _as_error_list(data)}
    return response
