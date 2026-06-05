from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.common.models import UUIDTimestampedModel


class UserManager(BaseUserManager):
    def normalize_email(self, email: str | None) -> str:
        normalized = super().normalize_email(email)
        return normalized.casefold()

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superusers must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superusers must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(UUIDTimestampedModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    github_user_id = models.PositiveBigIntegerField(null=True, blank=True, unique=True)
    github_login = models.CharField(max_length=255, blank=True)
    github_avatar_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        ordering = ["email"]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = type(self).objects.normalize_email(self.email)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.email


class CustomerOrganizationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(deactivated_at__isnull=True)


class CustomerOrganization(UUIDTimestampedModel):
    class GitHubAccountType(models.TextChoices):
        ORGANIZATION = "organization", "Organization"
        USER = "user", "User"

    name = models.CharField(max_length=255)
    github_account_id = models.PositiveBigIntegerField(unique=True)
    github_login = models.CharField(max_length=255)
    github_account_type = models.CharField(max_length=32, choices=GitHubAccountType.choices)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    objects = CustomerOrganizationQuerySet.as_manager()

    class Meta:
        ordering = ["github_login"]
        indexes = [
            models.Index(fields=["github_login"]),
            models.Index(fields=["deactivated_at"]),
        ]

    @property
    def is_active(self) -> bool:
        return self.deactivated_at is None

    def __str__(self) -> str:
        return self.github_login


class MembershipQuerySet(models.QuerySet):
    def active(self):
        return self.filter(
            deactivated_at__isnull=True,
            user__is_active=True,
            organization__deactivated_at__isnull=True,
        )


class Membership(UUIDTimestampedModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MAINTAINER = "maintainer", "Maintainer"
        REVIEWER = "reviewer", "Reviewer"
        VIEWER = "viewer", "Viewer"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(
        CustomerOrganization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=32, choices=Role.choices)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    objects = MembershipQuerySet.as_manager()

    class Meta:
        ordering = ["organization__github_login", "user__email"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                condition=Q(deactivated_at__isnull=True),
                name="unique_active_membership_per_user_org",
            )
        ]
        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["deactivated_at"]),
        ]

    @property
    def is_active(self) -> bool:
        return (
            self.deactivated_at is None
            and self.user.is_active
            and self.organization.deactivated_at is None
        )

    def __str__(self) -> str:
        return f"{self.user.email} in {self.organization.github_login}"
