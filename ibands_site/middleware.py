import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


class RequestCounterMiddleware:
    """
    Middleware for counting requests and unique IP addresses for users and bots,
    using Redis for persistence across restarts and multiple processes.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def _incr(self, key, amount=1):
        try:
            return cache.incr(key, amount)
        except ValueError:
            cache.set(key, amount, timeout=None)
        except Exception:
            logger.debug("Request counter incr failed for %s", key, exc_info=True)

    def _track_ip(self, key, ip):
        try:
            redis = cache.client.get_client(write=True)
            redis.sadd(key, ip)
        except Exception:
            logger.debug("Request counter sadd failed for %s", key, exc_info=True)

    def __call__(self, request):
        ip = self.get_client_ip(request)
        is_bot = self.is_bot_request(request)

        if is_bot:
            self._incr("bot_request_count")
            self._track_ip("bot_ips", ip)
        else:
            self._incr("user_request_count")
            self._track_ip("user_ips", ip)

        return self.get_response(request)

    @staticmethod
    def get_bot_request_count():
        try:
            return cache.get("bot_request_count") or 0
        except Exception:
            return 0

    @staticmethod
    def get_user_request_count():
        try:
            return cache.get("user_request_count") or 0
        except Exception:
            return 0

    @staticmethod
    def get_bot_request_unique_count():
        try:
            redis = cache.client.get_client(write=True)
            return redis.scard("bot_ips") or 0
        except Exception:
            return 0

    @staticmethod
    def get_user_request_unique_count():
        try:
            redis = cache.client.get_client(write=True)
            return redis.scard("user_ips") or 0
        except Exception:
            return 0

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
