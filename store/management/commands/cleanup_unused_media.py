import re
from typing import Iterable, List, Set, Tuple

import boto3
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models.fields.files import FieldFile
from django.utils.module_loading import import_string

from store.models import Category, Product, Gallery
from userauths.models import Profile


def normalize_key_from_field(field_file: FieldFile, media_prefix: str) -> str | None:
    """Return the full S3 object key (including media_prefix) for a File/ImageField.

    Example: field value "images/foo.jpg" -> "media/images/foo.jpg"
    Returns None if the field is empty.
    """
    if not field_file:
        return None
    name = getattr(field_file, "name", None)
    if not name:
        return None
    # Some fields might contain absolute URLs; ignore those
    if isinstance(name, str) and name.startswith("http"):
        return None
    return f"{media_prefix.rstrip('/')}/{name.lstrip('/')}"


def extract_media_keys_from_html(html: str, media_prefix: str) -> Set[str]:
    """Extract referenced media keys from HTML content.

    - Looks for src/href values that contain "/media/"
    - Returns keys in the form "media/..."
    """
    if not html:
        return set()
    keys: Set[str] = set()

    # Find all URL-like values inside src/href attributes
    for url in re.findall(r"(?:src|href)=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE):
        # Skip static or external content if it does not reference /media/
        if "/media/" not in url:
            continue
        # Extract the path starting from /media/
        try:
            start_idx = url.index("/media/") + 1  # include leading 'm' but remove leading '/'
            media_path = url[start_idx:]
            # Normalize to ensure it starts with media_prefix
            if not media_path.startswith(media_prefix):
                # If it starts with just 'media/', we're good
                if media_path.startswith("media/"):
                    pass
                else:
                    # If there's any other path, skip
                    continue
            # Ensure no leading slash remains
            media_path = media_path.lstrip("/")
            keys.add(media_path)
        except ValueError:
            continue
    return keys


def chunked(iterable: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


class Command(BaseCommand):
    help = "Find and optionally delete unused media files from the S3 bucket."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually delete the unused objects. By default, does a dry run.",
        )
        parser.add_argument(
            "--exclude-prefix",
            action="append",
            default=[],
            help="Exclude S3 keys that start with this prefix (relative to media/). Can be specified multiple times.",
        )
        parser.add_argument(
            "--reserve",
            action="append",
            default=[],
            help="Additional specific keys under media/ to reserve and never delete. Can be specified multiple times.",
        )

    def handle(self, *args, **options):
        # Determine media prefix from default storage
        media_prefix = "media"
        try:
            storage_class = import_string(settings.DEFAULT_FILE_STORAGE)
            location = getattr(storage_class, "location", None)
            if location:
                media_prefix = location.strip("/")
        except Exception:
            pass

        # Reserved default assets that should never be deleted
        reserved_keys: Set[str] = {
            f"{media_prefix}/default/default-image.avif",
            f"{media_prefix}/default/default-user.avif",
            f"{media_prefix}/gallery.jpg",
            f"{media_prefix}/category.jpg",
        }
        for extra in options.get("reserve", []) or []:
            extra = extra.strip("/")
            if not extra.startswith(media_prefix + "/"):
                extra = f"{media_prefix}/{extra}"
            reserved_keys.add(extra)

        exclude_prefixes: List[str] = []
        for p in options.get("exclude_prefix") or []:
            p = p.strip("/")
            if not p.startswith(media_prefix + "/"):
                p = f"{media_prefix}/{p}"
            exclude_prefixes.append(p)

        # Collect used keys from File/Image fields
        used_keys: Set[str] = set()

        # Categories
        for category in Category.objects.all().only("marketing_image", "hover_image", "description"):
            for field in (category.marketing_image, category.hover_image):
                key = normalize_key_from_field(field, media_prefix)
                if key:
                    used_keys.add(key)
            used_keys |= extract_media_keys_from_html(getattr(category, "description", ""), media_prefix)

        # Products and Galleries
        for product in Product.objects.all().only("image", "description"):
            key = normalize_key_from_field(product.image, media_prefix)
            if key:
                used_keys.add(key)
            used_keys |= extract_media_keys_from_html(getattr(product, "description", ""), media_prefix)

        for gallery in Gallery.objects.all().only("image"):
            key = normalize_key_from_field(gallery.image, media_prefix)
            if key:
                used_keys.add(key)

        # User profiles
        for profile in Profile.objects.all().only("image"):
            key = normalize_key_from_field(profile.image, media_prefix)
            if key:
                used_keys.add(key)

        used_keys |= reserved_keys

        # S3 client
        s3_client = boto3.client(
            "s3",
            region_name=getattr(settings, "AWS_S3_REGION_NAME", None),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
        )

        bucket_name = getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
        if not bucket_name:
            self.stderr.write(self.style.ERROR("AWS_STORAGE_BUCKET_NAME is not configured."))
            return

        # List all objects under media_prefix
        self.stdout.write(f"Scanning s3://{bucket_name}/{media_prefix}/ for objects...")
        paginator = s3_client.get_paginator("list_objects_v2")
        page_iter = paginator.paginate(Bucket=bucket_name, Prefix=f"{media_prefix}/")

        all_keys: Set[str] = set()
        total_objects = 0
        for page in page_iter:
            contents = page.get("Contents", [])
            total_objects += len(contents)
            for obj in contents:
                key = obj.get("Key")
                if key:
                    all_keys.add(key)

        # Compute unused keys
        def is_excluded(key: str) -> bool:
            for prefix in exclude_prefixes:
                if key.startswith(prefix):
                    return True
            return False

        unused_keys = [k for k in sorted(all_keys) if k not in used_keys and not is_excluded(k)]

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Summary"))
        self.stdout.write(f"Total objects under {media_prefix}/: {total_objects}")
        self.stdout.write(f"Referenced (kept) objects: {len(used_keys)}")
        self.stdout.write(f"Excluded by prefix: {len([k for k in all_keys if is_excluded(k)])}")
        self.stdout.write(self.style.WARNING(f"Candidates for deletion: {len(unused_keys)}"))
        if unused_keys:
            sample = "\n".join(unused_keys[:20])
            self.stdout.write("\nExamples of unused objects (first 20):\n" + sample)

        if not options.get("apply"):
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Dry run complete. No objects were deleted. Use --apply to delete."))
            return

        # Delete in batches
        deleted = 0
        for batch in chunked(unused_keys, 1000):
            to_delete = [{"Key": key} for key in batch]
            resp = s3_client.delete_objects(Bucket=bucket_name, Delete={"Objects": to_delete, "Quiet": True})
            deleted += len(resp.get("Deleted", []))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} unused objects."))


