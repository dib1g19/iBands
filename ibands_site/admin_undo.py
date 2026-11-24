import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.admin.models import LogEntry
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.utils import timezone

UNDO_FOR = timedelta(hours=24)

# Password hashes stay out of the admin log.
SKIP_NAMES = {"password"}


def _dump(field, value):
    if isinstance(value, models.Model):
        value = value.pk
    if isinstance(field, models.DecimalField):
        return None if value is None else str(value)
    if isinstance(field, models.DateTimeField):
        return None if value is None else value.isoformat()
    if isinstance(field, models.DateField):
        return None if value is None else value.isoformat()[:10]
    if isinstance(field, models.JSONField):
        json.dumps(value)
        return value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(field.name)


def _load(field, raw):
    if raw is None:
        return None
    if isinstance(field, models.DecimalField):
        return Decimal(raw)
    if isinstance(field, models.DateTimeField):
        return datetime.fromisoformat(raw)
    if isinstance(field, models.DateField):
        return date.fromisoformat(raw)
    return raw


def _field(model, name):
    try:
        return model._meta.get_field(name)
    except FieldDoesNotExist:
        return None


def undo_snapshot(form):
    """Previous values of the columns and selections this form changed.

    File fields and anything that is not a column on this model are left out.
    Reads the form's initial data, which is already in memory.
    """
    instance = form.instance
    if not getattr(instance, "pk", None):
        return None
    changed = set(form.changed_data)
    initial = form.initial or {}
    model = type(instance)
    fields = {}
    m2m = {}
    for field in model._meta.get_fields():
        if getattr(field, "many_to_many", False):
            if field.auto_created or field.name not in changed or field.name not in initial:
                continue
            m2m[field.name] = [
                item.pk if isinstance(item, models.Model) else item
                for item in list(initial[field.name] or [])
            ]
            continue
        if not getattr(field, "concrete", False) or not field.editable:
            continue
        if field.name not in changed or field.name not in initial:
            continue
        if field.name in SKIP_NAMES or isinstance(field, models.FileField):
            continue
        try:
            fields[field.attname] = _dump(field, initial[field.name])
        except TypeError:
            continue
    if not fields and not m2m:
        return None
    return {"fields": fields, "m2m": m2m}


def _without_undo(raw):
    if not raw or not raw.startswith("["):
        return raw
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    kept = [part for part in payload if not (isinstance(part, dict) and "undo" in part)]
    if len(kept) == len(payload):
        return raw
    return json.dumps(kept)


def undo_still_kept(entry):
    return entry.action_time >= timezone.now() - UNDO_FOR


def expire_old_snapshots():
    """Drop stored previous values once they are older than 24 hours."""
    cutoff = timezone.now() - UNDO_FOR
    old = LogEntry.objects.filter(
        action_time__lt=cutoff,
        change_message__contains='"undo"',
    ).only("pk", "change_message")
    for entry in old.iterator():
        stripped = _without_undo(entry.change_message)
        if stripped != entry.change_message:
            LogEntry.objects.filter(pk=entry.pk).update(change_message=stripped)


def undo_payload(entry):
    raw = entry.change_message or ""
    if not raw.startswith("["):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    for part in payload:
        if not isinstance(part, dict):
            continue
        undo = part.get("undo")
        if isinstance(undo, dict) and (undo.get("fields") or undo.get("m2m")):
            return undo
    return None


def _kept_field(model, name):
    field = _field(model, name)
    if field is None or field.name in SKIP_NAMES or isinstance(field, models.FileField):
        return None
    return field


def field_labels(model, snapshot):
    labels = []
    for name in list((snapshot.get("fields") or {})) + list((snapshot.get("m2m") or {})):
        field = _field(model, name)
        if field is None:
            continue
        labels.append(str(field.verbose_name))
    return labels


def apply_snapshot(obj, snapshot):
    model = type(obj)
    changed = False
    for name, raw in (snapshot.get("fields") or {}).items():
        field = _kept_field(model, name)
        if field is None:
            continue
        setattr(obj, field.attname, _load(field, raw))
        changed = True
    obj._skip_order_email = True
    if changed:
        obj.save()
    for name, pks in (snapshot.get("m2m") or {}).items():
        field = _field(model, name)
        if field is None or not field.many_to_many:
            continue
        getattr(obj, name).set(list(pks))
