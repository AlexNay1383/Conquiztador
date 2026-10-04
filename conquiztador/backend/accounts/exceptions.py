from rest_framework.views import exception_handler

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None and isinstance(response.data, dict):
        # DRF puts field errors in a dict
        if 'detail' in response.data:
            # Maybe keep it as is, or wrap it
            pass
        response.data = {"errors": response.data}
    elif response is not None and isinstance(response.data, list):
        response.data = {"errors": {"non_field_errors": response.data}}
    return response
