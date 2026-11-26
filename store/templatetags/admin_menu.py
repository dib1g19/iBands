import json
from datetime import timedelta

from django import template
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.db.models import Max
from django.urls import reverse
from django.utils import timezone

from ibands_site.admin_undo import expire_old_snapshots, undo_payload
from store.models import StaffUpdate

register = template.Library()

# Sidebar sections. Keys are Jazzmin's "app.model" strings, or a custom link name.
MENU_SECTIONS = [
    {
        "name": "Catalog",
        "icon": "fas fa-box",
        "open": True,
        "items": [
            "store.product",
            "store.productitem",
            "store.category",
            "store.categorylink",
            "store.gallery",
        ],
    },
    {
        "name": "Options",
        "icon": "fas fa-sliders",
        "items": [
            "store.variant",
            "store.variantitem",
            "store.color",
            "store.colorgroup",
            "store.size",
            "store.sizegroup",
            "store.devicemodel",
            "store.modelgroup",
        ],
    },
    {
        "name": "Orders",
        "icon": "fas fa-clipboard-list",
        "open": True,
        "items": [
            "store.order",
            "store.orderitem",
            "store.cart",
        ],
    },
    {
        "name": "Promotions",
        "icon": "fas fa-bullhorn",
        "items": [
            "store.coupon",
            "store.couponredemption",
            "store.bandoftheweek",
            "store.spinprize",
            "store.spinmilestone",
            "store.spinmilestoneaward",
            "store.spinentry",
        ],
    },
    {
        "name": "Site",
        "icon": "fas fa-gear",
        "items": [
            "store.staffupdate",
            "store.storethemesettings",
            "stats",
            "store.servererrorlog",
        ],
    },
    {
        "name": "Accounts",
        "icon": "fas fa-users",
        "items": [
            "userauths.user",
            "userauths.contactmessage",
            "userauths.newslettersubscription",
        ],
    },
    {
        "name": "Customers",
        "icon": "fas fa-address-book",
        "items": [
            "customer.address",
            "customer.wishlist",
        ],
    },
]


def _menu_key(item):
    model_str = item.get("model_str")
    if model_str:
        return model_str.lower()
    return (item.get("name") or "").strip().lower()


@register.simple_tag
def admin_menu_sections(side_menu_list):
    """Split the Jazzmin app menu into collapsible sections."""
    by_key = {}
    ordered = []
    for app in side_menu_list or []:
        for item in app.get("models", []):
            key = _menu_key(item)
            if not key or key in by_key:
                continue
            by_key[key] = item
            ordered.append(key)

    used = set()
    sections = []
    for section in MENU_SECTIONS:
        models = []
        for key in section["items"]:
            item = by_key.get(key.lower())
            if item:
                models.append(item)
                used.add(key.lower())
        if models:
            sections.append(
                {
                    "name": section["name"],
                    "icon": section["icon"],
                    "open": section.get("open", False),
                    "models": models,
                }
            )

    leftover = [by_key[key] for key in ordered if key not in used]
    if leftover:
        sections.append({"name": "More", "icon": "fas fa-ellipsis", "models": leftover})
    return sections


def _join(parts):
    parts = [part for part in parts if part]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def _fields_phrase(fields):
    words = []
    for field in fields or []:
        text = str(field).strip()
        if not text:
            continue
        if text.isupper():
            words.append(text)
        else:
            words.append(text[:1].lower() + text[1:])
    return _join(words)


def _article(name):
    return "an" if name[:1].lower() in "aeiou" else "a"


def _inline_label(part):
    name = str(part.get("name") or "item").strip() or "item"
    name = name[:1].lower() + name[1:]
    obj = part.get("object")
    if obj and str(obj) not in {"None", "null"}:
        return f"{name} {obj}"
    return f"{_article(name)} {name[:1].lower() + name[1:]}"


def _line_from_part(part):
    if "added" in part:
        added = part.get("added") or {}
        if added.get("name"):
            return f"Added {_inline_label(added)}"
        return "Added"
    if "deleted" in part:
        deleted = part.get("deleted") or {}
        if deleted.get("name"):
            return f"Deleted {_inline_label(deleted)}"
        return "Deleted"
    if "changed" in part:
        changed = part.get("changed") or {}
        fields = _fields_phrase(changed.get("fields"))
        if changed.get("name"):
            target = _inline_label(changed)
            if fields:
                return f"Changed {fields} on {target}"
            return f"Changed {target}"
        if fields:
            return f"Changed {fields}"
        return "Changed"
    return ""


def _change_lines(entry):
    if entry.is_deletion():
        return ["Deleted"]
    raw = entry.change_message or ""
    if raw.startswith("["):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return [raw]
        lines = [line for part in payload if (line := _line_from_part(part))]
        if lines:
            return lines
    elif raw:
        return [raw]
    if entry.is_addition():
        return ["Added"]
    return ["Changed"]


def _object_title(entry):
    content_type = entry.content_type
    model = content_type.model_class() if content_type else None
    if model:
        kind = str(model._meta.verbose_name)
    elif content_type:
        kind = content_type.model
    else:
        kind = "Item"
    kind = kind[:1].upper() + kind[1:]

    name = (entry.object_repr or "").strip() or "Untitled"
    extra = []
    if content_type and content_type.model == "product" and name.endswith(")"):
        short, _, sku = name.rpartition(" (")
        if short and sku.endswith(")"):
            name = short
            extra.append(f"SKU {sku[:-1]}")
    shown = name if len(name) <= 70 else name[:69].rstrip() + "…"
    if shown != name:
        extra.insert(0, name)
    return f"{kind} {shown}", extra


def _when(action_time):
    local = timezone.localtime(action_time)
    today = timezone.localdate()
    clock = local.strftime("%H:%M")
    if local.date() == today:
        return f"Today, {clock}"
    if local.date() == today - timedelta(days=1):
        return f"Yesterday, {clock}"
    return f"{local.day} {local.strftime('%b')}, {clock}"


def _actor(user):
    full_name = user.get_full_name().strip()
    return full_name or user.get_username()


def _latest_ids(entries):
    cts = {entry.content_type_id for entry in entries}
    oids = {entry.object_id for entry in entries}
    if not cts or not oids:
        return set()
    return {
        row["latest"]
        for row in LogEntry.objects.filter(content_type_id__in=cts, object_id__in=oids)
        .values("content_type_id", "object_id")
        .annotate(latest=Max("pk"))
    }


def _present_action(entry, request, latest_ids):
    title, extra = _object_title(entry)
    lines = _change_lines(entry)
    visible = lines[:2]
    details = lines[2:] + extra
    if entry.is_addition():
        verb = "added"
    elif entry.is_deletion():
        verb = "deleted"
    else:
        verb = "changed"
    undo_url = ""
    if entry.pk in latest_ids and undo_payload(entry):
        model = entry.content_type.model_class() if entry.content_type_id else None
        model_admin = admin.site._registry.get(model) if model else None
        if model_admin and model_admin.has_change_permission(request):
            undo_url = reverse("admin-undo", args=[entry.pk])
    return {
        "title": title,
        "url": "" if entry.is_deletion() else (entry.get_admin_url() or ""),
        "verb": verb,
        "lines": visible,
        "details": details,
        "actor": _actor(entry.user),
        "when": _when(entry.action_time),
        "undo_url": undo_url,
    }


ACTIONS_PAGE_PARAM = "actions_page"
UPDATES_PAGE_PARAM = "updates_page"
PAGE_MAX = 400


def _page_number(request, param):
    try:
        page = int(request.GET.get(param, 1))
    except (TypeError, ValueError):
        page = 1
    return min(max(page, 1), PAGE_MAX)


def _page_url(request, param, page):
    params = request.GET.copy()
    if page <= 1:
        params.pop(param, None)
    else:
        params[param] = str(page)
    query = params.urlencode()
    return f"{request.path}?{query}" if query else request.path


def _update_lines(details):
    lines = []
    for raw in (details or "").splitlines():
        line = raw.strip()
        if line.startswith("- ") or line == "-":
            line = line[1:].strip()
        if line:
            lines.append(line)
    return lines


def _present_update(note):
    lines = _update_lines(note.details)
    return {
        "title": note.summary,
        "url": reverse("admin:store_staffupdate_change", args=[note.pk]),
        "lines": lines[:6],
        "details": lines[6:],
        "actor": _actor(note.created_by) if note.created_by_id else "",
        "when": _when(note.created_at),
    }


@register.simple_tag(takes_context=True)
def recent_admin_actions(context, limit=20):
    """One page of admin edits. The next page is loaded only when requested."""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    limit = min(max(limit, 1), 50)
    request = context["request"]
    expire_old_snapshots()
    page = _page_number(request, ACTIONS_PAGE_PARAM)
    start = (page - 1) * limit
    rows = list(
        LogEntry.objects.select_related("user", "content_type").order_by("-action_time")[
            start : start + limit + 1
        ]
    )
    has_older = len(rows) > limit
    shown = rows[:limit]
    latest_ids = _latest_ids([entry for entry in shown if undo_payload(entry)])
    return {
        "actions": [_present_action(entry, request, latest_ids) for entry in shown],
        "newer_url": _page_url(request, ACTIONS_PAGE_PARAM, page - 1) if page > 1 else "",
        "older_url": _page_url(request, ACTIONS_PAGE_PARAM, page + 1) if has_older else "",
    }


@register.simple_tag(takes_context=True)
def recent_staff_updates(context, limit=20):
    """One page of What's new notes, newest first."""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    limit = min(max(limit, 1), 50)
    request = context["request"]
    page = _page_number(request, UPDATES_PAGE_PARAM)
    start = (page - 1) * limit
    rows = list(
        StaffUpdate.objects.select_related("created_by").order_by("-created_at", "-pk")[
            start : start + limit + 1
        ]
    )
    has_older = len(rows) > limit
    return {
        "notes": [_present_update(note) for note in rows[:limit]],
        "newer_url": _page_url(request, UPDATES_PAGE_PARAM, page - 1) if page > 1 else "",
        "older_url": _page_url(request, UPDATES_PAGE_PARAM, page + 1) if has_older else "",
    }
