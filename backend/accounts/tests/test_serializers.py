from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import Avatar
from accounts.serializers import ProfileUpdateSerializer, RegisterSerializer

from .factories import create_user

User = get_user_model()


def registration_data(**overrides):
    data = {
        "username": "player_one",
        "email": "player@example.com",
        "nickname": "MountainKnight",
        "password": "Strong-pass-2024",
        "password_confirm": "Strong-pass-2024",
    }
    data.update(overrides)
    return data


class RegisterSerializerTests(TestCase):
    def test_passwords_are_write_only(self):
        serializer = RegisterSerializer(data=registration_data())
        self.assertTrue(serializer.is_valid(), serializer.errors)

        serializer.save()

        self.assertNotIn("password", serializer.data)
        self.assertNotIn("password_confirm", serializer.data)

    def test_nickname_whitespace_is_normalized(self):
        serializer = RegisterSerializer(data=registration_data(nickname="  Mountain   Knight "))
        self.assertTrue(serializer.is_valid(), serializer.errors)

        user = serializer.save()

        self.assertEqual(user.profile.nickname, "Mountain Knight")

    def test_nickname_uniqueness_ignores_case(self):
        create_user("existing", nickname="MountainKnight")

        serializer = RegisterSerializer(data=registration_data(nickname="mountainknight"))

        self.assertFalse(serializer.is_valid())
        self.assertIn("nickname", serializer.errors)

    def test_weak_password_is_rejected(self):
        serializer = RegisterSerializer(data=registration_data(password="123", password_confirm="123"))

        self.assertFalse(serializer.is_valid())
        self.assertIn("password", serializer.errors)

    def test_user_is_rolled_back_when_profile_creation_fails(self):
        serializer = RegisterSerializer(data=registration_data())
        self.assertTrue(serializer.is_valid(), serializer.errors)

        with mock.patch("accounts.serializers.Profile.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                serializer.save()

        self.assertFalse(User.objects.exists())


class ProfileUpdateSerializerTests(TestCase):
    def test_rejects_fields_outside_the_profile(self):
        profile = create_user().profile

        serializer = ProfileUpdateSerializer(
            profile, data={"nickname": "New", "username": "hacker", "is_superuser": True}, partial=True
        )

        self.assertFalse(serializer.is_valid())
        self.assertEqual(set(serializer.errors), {"username", "is_superuser"})

    def test_rejects_unknown_avatar(self):
        profile = create_user().profile

        serializer = ProfileUpdateSerializer(profile, data={"avatar_key": "dragon"}, partial=True)

        self.assertFalse(serializer.is_valid())
        self.assertIn("avatar_key", serializer.errors)

    def test_keeping_own_nickname_is_allowed(self):
        profile = create_user(nickname="Knight").profile

        serializer = ProfileUpdateSerializer(
            profile, data={"nickname": "Knight", "avatar_key": Avatar.KNIGHT_2}, partial=True
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
