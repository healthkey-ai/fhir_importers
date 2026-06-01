from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Identity


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={"input_type": "password"},
    )

    def validate_email(self, value):
        if Identity.objects.filter(issuer="urn:local", email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def create(self, validated_data):
        return Identity.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
        )


class IdentitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Identity
        fields = ("id", "email", "issuer", "is_local", "created_at")
        read_only_fields = fields


# Kept for backwards compat with PartnerTokenView response
UserSerializer = IdentitySerializer
