"""DRF serializers for the Epic connector API (ported from FastAPI schemas)."""
from rest_framework import serializers


class OrganizationOutSerializer(serializers.Serializer):
    alias = serializers.CharField()
    title = serializers.CharField()
    endpoint_url = serializers.CharField()


class StartRequestSerializer(serializers.Serializer):
    organization_alias = serializers.CharField(
        help_text="Alias of an organization registered in organizations.json",
    )


class StartResponseSerializer(serializers.Serializer):
    authorization_url = serializers.CharField()
    state = serializers.CharField()


class FinishRequestSerializer(serializers.Serializer):
    code = serializers.CharField()
    state = serializers.CharField()


class FinishResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField(allow_null=True, required=False)
    id_token = serializers.CharField(allow_null=True, required=False)
    expires_in = serializers.IntegerField()
    scope = serializers.CharField(allow_null=True, required=False)
    patient = serializers.CharField(
        allow_null=True, required=False,
        help_text="SMART-on-FHIR patient launch context, if returned",
    )
