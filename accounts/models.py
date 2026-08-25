from django.conf import settings
from django.db import models


class Interest(models.Model):
    """A taggable interest/topic used for preference-based discovery."""
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Profile(models.Model):
    GENDER_CHOICES = [("M", "Male"), ("F", "Female"), ("O", "Other")]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    display_name = models.CharField(max_length=50)
    age = models.PositiveSmallIntegerField()
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)

    # Preference fields used by the discovery/matching queries below.
    preferred_gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    min_age_pref = models.PositiveSmallIntegerField(default=18)
    max_age_pref = models.PositiveSmallIntegerField(default=99)

    interests = models.ManyToManyField(Interest, related_name="profiles", blank=True)

    is_online = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            # Composite index: the discovery endpoint filters on exactly these
            # columns together (gender + age range + online status), so a
            # single composite index serves that query far better than
            # separate single-column indexes.
            models.Index(fields=["gender", "age", "is_online"], name="idx_profile_discovery"),
        ]

    def __str__(self):
        return self.display_name


class Block(models.Model):
    """Lets a user exclude someone from ever being matched to them again."""
    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="blocking", on_delete=models.CASCADE
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="blocked_by", on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # FK columns are indexed by default in Django, but we make the pair
        # unique + indexed together since every match-eligibility check
        # queries "is (A, B) blocked?" as a unit.
        unique_together = ("blocker", "blocked")
        indexes = [models.Index(fields=["blocker", "blocked"], name="idx_block_pair")]
