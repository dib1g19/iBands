from django.db import connection, OperationalError

class ReconnectDBMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            connection.ensure_connection()
        except OperationalError:
            connection.close()
            connection.connect()
        return self.get_response(request)