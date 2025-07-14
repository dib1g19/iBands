from django.core.cache import cache

class RequestCounterMiddleware:
    """
    Middleware for counting requests and unique IP addresses for users and bots,
    using Redis for persistence across restarts and multiple processes.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Access the raw Redis client for set operations
        self.redis = cache.client.get_client(write=True)

    def safe_incr(self, key, amount=1):
        if cache.get(key) is None:
            cache.set(key, 0, timeout=None)
        cache.incr(key, amount)

    def __call__(self, request):
        ip = self.get_client_ip(request)
        is_bot = self.is_bot_request(request)

        if is_bot:
            self.safe_incr("bot_request_count")
            self.redis.sadd("bot_ips", ip)
        else:
            self.safe_incr("user_request_count")
            self.redis.sadd("user_ips", ip)

        return self.get_response(request)

    @staticmethod
    def get_bot_request_count():
        return cache.get("bot_request_count") or 0

    @staticmethod
    def get_user_request_count():
        return cache.get("user_request_count") or 0

    @staticmethod
    def get_bot_request_unique_count():
        # Use the Redis SCARD command for set cardinality
        redis = cache.client.get_client(write=True)
        return redis.scard("bot_ips") or 0

    @staticmethod
    def get_user_request_unique_count():
        redis = cache.client.get_client(write=True)
        return redis.scard("user_ips") or 0

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