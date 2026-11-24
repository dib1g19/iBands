from django.contrib import admin, messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from ibands_site.admin_undo import (
    apply_snapshot,
    expire_old_snapshots,
    field_labels,
    undo_payload,
    undo_still_kept,
)
from ibands_site.middleware import RequestCounterMiddleware
from store.utils import get_500_error_stats


def stats_view(request):
    stats = {
        "user_request_count": RequestCounterMiddleware.get_user_request_count(),
        "user_request_unique_count": RequestCounterMiddleware.get_user_request_unique_count(),
        "bot_request_count": RequestCounterMiddleware.get_bot_request_count(),
        "bot_request_unique_count": RequestCounterMiddleware.get_bot_request_unique_count(),
    }
    stats.update(get_500_error_stats())
    context = dict(admin.site.each_context(request), stats=stats)
    return TemplateResponse(request, "admin/stats.html", context)


def undo_admin_change(request, entry_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    entry = get_object_or_404(LogEntry, pk=entry_id)
    snapshot = undo_payload(entry)
    model = entry.content_type.model_class() if entry.content_type_id else None
    model_admin = admin.site._registry.get(model) if model else None
    if model_admin is None or not model_admin.has_change_permission(request):
        raise PermissionDenied
    if snapshot and not undo_still_kept(entry):
        expire_old_snapshots()
        messages.error(request, "This undo has expired.")
        return redirect("admin:index")
    if not snapshot:
        messages.error(request, "A later edit was saved, so this one can no longer be undone.")
        return redirect("admin:index")
    latest = (
        LogEntry.objects.filter(
            content_type_id=entry.content_type_id,
            object_id=entry.object_id,
        )
        .order_by("-pk")
        .values_list("pk", flat=True)
        .first()
    )
    if latest != entry.pk:
        messages.error(request, "A later edit was saved, so this one can no longer be undone.")
        return redirect("admin:index")
    obj = model.objects.filter(pk=entry.object_id).first()
    if obj is None:
        messages.error(request, "That item no longer exists.")
        return redirect("admin:index")
    try:
        with transaction.atomic():
            apply_snapshot(obj, snapshot)
            LogEntry.objects.log_actions(
                user_id=request.user.pk,
                queryset=[obj],
                action_flag=CHANGE,
                change_message=[{"changed": {"fields": field_labels(model, snapshot)}}],
                single_object=True,
            )
    except (IntegrityError, ValueError):
        messages.error(request, "Those previous values could not be restored.")
        return redirect("admin:index")
    messages.success(request, "Restored the previous values.")
    return redirect("admin:index")