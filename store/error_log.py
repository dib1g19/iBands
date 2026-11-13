import ipaddress
import logging
import traceback

from django.core.exceptions import BadRequest, PermissionDenied, SuspiciousOperation
from django.http import Http404
from django.urls import reverse

from store.utils import increment_500_error_count

logger = logging.getLogger(__name__)

IGNORED_EXCEPTIONS = (Http404, PermissionDenied, SuspiciousOperation, BadRequest)


def should_record(exception):
    return exception is not None and not isinstance(exception, IGNORED_EXCEPTIONS)


def is_admin_request(request):
    path = getattr(request, "path", "") or ""
    return path.startswith(_admin_prefix())


def admin_error_return_url(request):
    """Where to send an admin user so the error can show as a notice on a working page."""
    from urllib.parse import urlparse

    index = _admin_prefix()
    current = getattr(request, "path", "") or ""
    if request.method == "POST":
        return request.get_full_path() or index

    referer = request.META.get("HTTP_REFERER", "")
    if referer:
        parsed = urlparse(referer)
        try:
            host = request.get_host()
        except Exception:
            host = ""
        same_host = parsed.netloc in ("", host)
        if same_host and parsed.path.startswith(index) and parsed.path != current:
            query = f"?{parsed.query}" if parsed.query else ""
            return f"{parsed.path}{query}"
    if current != index:
        return index
    return None


def _admin_prefix():
    try:
        return reverse("admin:index")
    except Exception:
        return "/admin/"


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def _valid_ip(ip):
    try:
        ipaddress.ip_address(ip)
    except Exception:
        return None
    return ip


def _is_bot(request):
    user_agent = request.META.get("HTTP_USER_AGENT", "").lower()
    bot_keywords = (
        "bot", "crawl", "slurp", "spider", "mediapartners", "facebookexternalhit",
        "meta-externalagent", "twitterbot", "bingpreview", "yandex", "duckduckbot",
    )
    return any(keyword in user_agent for keyword in bot_keywords)


def record_server_error(request, exception):
    """Store an unhandled error once per request. Returns the saved row, or None."""
    if getattr(request, "_server_error_recorded", False):
        return getattr(request, "_server_error_log", None)
    request._server_error_recorded = True

    logger.error(
        "Unhandled server error on %s %s",
        getattr(request, "method", ""),
        getattr(request, "path", ""),
        exc_info=exception,
    )

    from store.models import ServerErrorLog

    user = getattr(request, "user", None)
    user_obj = None
    user_label = ""
    is_staff = False
    try:
        if user is not None and user.is_authenticated:
            user_obj = user
            user_label = getattr(user, "email", "") or str(user)
            is_staff = bool(user.is_staff)
    except Exception:
        user_obj = None

    ip = _client_ip(request)
    is_bot = _is_bot(request)
    try:
        increment_500_error_count(is_bot=is_bot, ip=ip or None)
    except Exception:
        logger.debug("Could not update the 500 counter", exc_info=True)

    try:
        log = ServerErrorLog.objects.create(
            exception_type=type(exception).__name__[:200],
            message=str(exception)[:5000],
            traceback="".join(
                traceback.format_exception(type(exception), exception, exception.__traceback__)
            )[:20000],
            method=(getattr(request, "method", "") or "")[:10],
            path=(getattr(request, "path", "") or "")[:500],
            query_string=(request.META.get("QUERY_STRING", "") or "")[:1000],
            user=user_obj,
            user_label=user_label[:255],
            is_staff=is_staff,
            is_bot=is_bot,
            ip_address=_valid_ip(ip),
            user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:500],
        )
    except Exception:
        logger.exception("Could not store the server error")
        return None

    request._server_error_log = log
    return log


def admin_error_notice(exception, log):
    """Short admin banner, with a link to the stored traceback."""
    from django.utils.html import format_html

    text = f"{type(exception).__name__}: {exception}"
    if len(text) > 300:
        text = f"{text[:297]}..."
    if log is None:
        return text
    try:
        url = reverse("admin:store_servererrorlog_change", args=[log.pk])
    except Exception:
        return text
    return format_html(
        '{} <a class="btn btn-sm btn-light ml-2" href="{}">See more</a>',
        text,
        url,
    )
