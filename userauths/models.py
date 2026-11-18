from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

from ibands_site.images import convert_uploaded_images


class User(AbstractUser):
    username = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255, null=True, blank=True)
    mobile = models.CharField(max_length=255, null=True, blank=True)
    image = models.ImageField(
        upload_to="accounts/users",
        default="default/default-user.avif",
        null=True,
        blank=True,
    )
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email

    def get_full_name(self):
        name = (self.full_name or "").strip()
        return name or super().get_full_name()

    def save(self, *args, **kwargs):
        email_username, _ = self.email.split("@")
        if self.username == "" or self.username == None:
            self.username = email_username
        convert_uploaded_images(self, "image")
        super(User, self).save(*args, **kwargs)


class ContactMessage(models.Model):
    full_name = models.CharField(max_length=255, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)
    subject = models.CharField(max_length=255, null=True, blank=True)
    message = models.TextField(null=True, blank=True)
    date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.full_name

    class Meta:
        ordering = ["-date"]


class NewsletterSubscription(models.Model):
    email = models.EmailField(unique=True)
    date_subscribed = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.email

    class Meta:
        ordering = ["-date_subscribed"]