class RequestCounterMiddleware:
    """
    Middleware for counting requests and unique IP addresses for users and bots.
    """
    bot_request_count = 0
    user_request_count = 0
    bot_request_unique_count = 0
    user_request_unique_count = 0

    bot_ips = set()
    user_ips = set()

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """
        Counts each request and unique IP address for bots and users.
        """
        ip = self.get_client_ip(request)
        is_bot = self.is_bot_request(request)

        if is_bot:
            RequestCounterMiddleware.bot_request_count += 1
            if ip not in RequestCounterMiddleware.bot_ips:
                RequestCounterMiddleware.bot_request_unique_count += 1
                RequestCounterMiddleware.bot_ips.add(ip)
        else:
            RequestCounterMiddleware.user_request_count += 1
            if ip not in RequestCounterMiddleware.user_ips:
                RequestCounterMiddleware.user_request_unique_count += 1
                RequestCounterMiddleware.user_ips.add(ip)

        return self.get_response(request)

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