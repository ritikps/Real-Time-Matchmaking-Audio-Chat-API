from django.conf import settings
from django.db import models


class Match(models.Model):
    user_a = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="matches_as_a", on_delete=models.CASCADE
    )
    user_b = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="matches_as_b", on_delete=models.CASCADE
    )
    room_name = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user_a", "user_b"], name="idx_match_pair"),
        ]

    def __str__(self):
        return f"{self.room_name} ({self.user_a_id} <-> {self.user_b_id})"
