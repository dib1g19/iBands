import logging
from django.db import connection, OperationalError

logger = logging.getLogger(__name__)

def is_bot_request(request):
    user_agent = request.META.get("HTTP_USER_AGENT", "").lower()
    bot_keywords = [
        "bot", "crawl", "slurp", "spider", "mediapartners", "facebookexternalhit",
        "meta-externalagent", "twitterbot", "bingpreview", "yandex", "duckduckbot"
    ]
    return any(bot in user_agent for bot in bot_keywords)

class ReconnectDBMiddleware:
    bot_count = 0
    user_count = 0
    unique_bot_ips = set()
    unique_user_ips = set()
    db_error_bot_count = 0
    db_error_user_count = 0

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        ip = request.META.get("REMOTE_ADDR", "")

        if is_bot_request(request):
            ReconnectDBMiddleware.bot_count += 1
            ReconnectDBMiddleware.unique_bot_ips.add(ip)
            logger.info(
                f"Bot request detected: {user_agent} from {ip} (Total bot requests: {ReconnectDBMiddleware.bot_count}, Unique bots: {len(ReconnectDBMiddleware.unique_bot_ips)})"
            )
        else:
            ReconnectDBMiddleware.user_count += 1
            ReconnectDBMiddleware.unique_user_ips.add(ip)
            logger.info(
                f"User request detected: {user_agent} from {ip} (Total user requests: {ReconnectDBMiddleware.user_count}, Unique users: {len(ReconnectDBMiddleware.unique_user_ips)})"
            )
        try:
            connection.ensure_connection()
        except OperationalError:
            if is_bot_request(request):
                ReconnectDBMiddleware.db_error_bot_count += 1
                logger.error(
                    f"DB error detected for bot request from {ip} (DB errors for bots: {ReconnectDBMiddleware.db_error_bot_count}, Total DB errors: {ReconnectDBMiddleware.db_error_count})"
                )
            else:
                ReconnectDBMiddleware.db_error_user_count += 1
                logger.error(
                    f"DB error detected for user request from {ip} (DB errors for users: {ReconnectDBMiddleware.db_error_user_count}, Total DB errors: {ReconnectDBMiddleware.db_error_count})"
                )
            connection.close()
            connection.connect()
        return self.get_response(request)