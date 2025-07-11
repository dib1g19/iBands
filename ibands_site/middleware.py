from django.db import connection
from django.db.utils import OperationalError

class ReconnectDBMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
        except OperationalError:
            connection.close()
            connection.connect()
            response = self.get_response(request)
        return response


class OperationalErrorCounterMiddleware:
    bot_request_count = 0
    user_request_count = 0
    bot_request_unique_count = 0
    user_request_unique_count = 0
    bot_error_count = 0
    user_error_count = 0
    bot_error_unique_count = 0
    user_error_unique_count = 0

    bot_ips = set()
    user_ips = set()
    bot_error_ips = set()
    user_error_ips = set()

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = self.get_client_ip(request)
        is_bot = self.is_bot_request(request)

        # Track all requests
        if is_bot:
            OperationalErrorCounterMiddleware.bot_request_count += 1
            if ip not in OperationalErrorCounterMiddleware.bot_ips:
                OperationalErrorCounterMiddleware.bot_request_unique_count += 1
                OperationalErrorCounterMiddleware.bot_ips.add(ip)
        else:
            OperationalErrorCounterMiddleware.user_request_count += 1
            if ip not in OperationalErrorCounterMiddleware.user_ips:
                OperationalErrorCounterMiddleware.user_request_unique_count += 1
                OperationalErrorCounterMiddleware.user_ips.add(ip)

        try:
            response = self.get_response(request)
        except OperationalError:
            connection.close()
            connection.connect()
            # Track errors
            if is_bot:
                OperationalErrorCounterMiddleware.bot_error_count += 1
                if ip not in OperationalErrorCounterMiddleware.bot_error_ips:
                    OperationalErrorCounterMiddleware.bot_error_unique_count += 1
                    OperationalErrorCounterMiddleware.bot_error_ips.add(ip)
            else:
                OperationalErrorCounterMiddleware.user_error_count += 1
                if ip not in OperationalErrorCounterMiddleware.user_error_ips:
                    OperationalErrorCounterMiddleware.user_error_unique_count += 1
                    OperationalErrorCounterMiddleware.user_error_ips.add(ip)
            response = self.get_response(request)
        return response

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def is_bot_request(self, request):
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        bot_signatures = ['bot', 'crawl', 'spider', 'slurp']
        return any(bot_sig in user_agent for bot_sig in bot_signatures)