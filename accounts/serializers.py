from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Interest, Profile

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    display_name = serializers.CharField(write_only=True, max_length=50)
    age = serializers.IntegerField(write_only=True, min_value=13, max_value=120)
    gender = serializers.ChoiceField(write_only=True, choices=Profile.GENDER_CHOICES)

    class Meta:
        model = User
        fields = ["username", "email", "password", "display_name", "age", "gender"]

    def create(self, validated_data):
        profile_fields = {
            "display_name": validated_data.pop("display_name"),
            "age": validated_data.pop("age"),
            "gender": validated_data.pop("gender"),
        }
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )
        Profile.objects.create(user=user, **profile_fields)
        return user


class InterestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Interest
        fields = ["id", "name"]


class ProfileSerializer(serializers.ModelSerializer):
    interests = InterestSerializer(many=True, read_only=True)
    interest_ids = serializers.PrimaryKeyRelatedField(
        queryset=Interest.objects.all(), many=True, write_only=True,
        source="interests", required=False,
    )
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Profile
        fields = [
            "id", "username", "display_name", "age", "gender",
            "preferred_gender", "min_age_pref", "max_age_pref",
            "interests", "interest_ids", "is_online",
        ]
        read_only_fields = ["id", "username"]


class DiscoveryProfileSerializer(serializers.ModelSerializer):
    """Slim, public-safe view of a profile shown in discovery/search results."""
    username = serializers.CharField(source="user.username", read_only=True)
    interests = InterestSerializer(many=True, read_only=True)

    class Meta:
        model = Profile
        fields = ["id", "username", "display_name", "age", "gender", "interests", "is_online"]
