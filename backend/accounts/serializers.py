from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import password_validation
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from .models import Avatar, Profile

User = get_user_model()


def normalize_nickname(value):
    return " ".join(value.split())


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["nickname", "avatar_key"]


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "profile"]
        read_only_fields = fields


class NicknameValidationMixin:
    def validate_nickname(self, value):
        value = normalize_nickname(value)
        if not value:
            raise serializers.ValidationError("Прякорът не може да бъде празен.")
        taken = Profile.objects.filter(nickname__iexact=value)
        profile = getattr(self, "instance", None)
        if isinstance(profile, Profile):
            taken = taken.exclude(pk=profile.pk)
        if taken.exists():
            raise serializers.ValidationError("Този прякор вече е зает.")
        return value


class RegisterSerializer(NicknameValidationMixin, serializers.ModelSerializer):
    nickname = serializers.CharField(max_length=30)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = ["username", "email", "nickname", "password", "password_confirm"]
        extra_kwargs = {
            "username": {"validators": [UnicodeUsernameValidator()]},
            "email": {"required": True, "allow_blank": False, "validators": []},
        }

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Потребител с това име вече съществува.")
        return value

    def validate_email(self, value):
        value = User.objects.normalize_email(value).strip()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Потребител с този имейл вече съществува.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": ["Паролите не съвпадат."]})

        candidate = User(username=attrs["username"], email=attrs["email"])
        try:
            password_validation.validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": list(error.messages)})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )
        Profile.objects.create(user=user, nickname=validated_data["nickname"])
        return user

    def to_representation(self, instance):
        return UserSerializer(instance).data


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = authenticate(
            self.context.get("request"),
            username=attrs["username"],
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError("Невалидно потребителско име или парола.")
        attrs["user"] = user
        return attrs


class ProfileUpdateSerializer(NicknameValidationMixin, serializers.ModelSerializer):
    avatar_key = serializers.ChoiceField(choices=Avatar.choices, required=False)

    class Meta:
        model = Profile
        fields = ["nickname", "avatar_key"]

    def to_internal_value(self, data):
        if isinstance(data, dict):
            forbidden = sorted(set(data) - set(self.fields))
            if forbidden:
                raise serializers.ValidationError(
                    {field: ["Това поле не може да бъде променяно."] for field in forbidden}
                )
        return super().to_internal_value(data)
