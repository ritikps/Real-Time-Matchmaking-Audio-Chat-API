from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Block, Profile
from .serializers import DiscoveryProfileSerializer, ProfileSerializer, RegisterSerializer


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/  -> creates User + Profile in one call."""
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer


class MeProfileView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/profile/me/  -> the authenticated user's own profile."""
    serializer_class = ProfileSerializer

    def get_object(self):
        return self.request.user.profile


class DiscoveryView(APIView):
    """
    GET /api/discovery/

    Preference-based discovery: returns online profiles matching the
    caller's stated gender/age preferences, excluding themself and anyone
    they've blocked (or who has blocked them).

    Query optimization notes:
      - filters hit the composite index on (gender, age, is_online)
        defined in Profile.Meta.indexes, so this stays a single index
        scan instead of a full table scan as the profile table grows.
      - select_related('user') avoids an extra query per row for username.
      - prefetch_related('interests') avoids N+1 queries for the
        many-to-many interest list on every profile in the page.
      - blocked-pair lookups hit idx_block_pair rather than scanning
        the Block table.
    """
    def get(self, request):
        me = request.user.profile

        blocked_user_ids = set(
            Block.objects.filter(blocker=request.user).values_list("blocked_id", flat=True)
        ) | set(
            Block.objects.filter(blocked=request.user).values_list("blocker_id", flat=True)
        )

        qs = (
            Profile.objects
            .select_related("user")
            .prefetch_related("interests")
            .filter(is_online=True, age__gte=me.min_age_pref, age__lte=me.max_age_pref)
            .exclude(user_id__in=blocked_user_ids | {request.user.id})
        )

        if me.preferred_gender:
            qs = qs.filter(gender=me.preferred_gender)

        qs = qs.order_by("-created_at")[:50]
        return Response(DiscoveryProfileSerializer(qs, many=True).data)
