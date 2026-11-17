from django.db import IntegrityError
from django.test import TestCase

from accounts.models import Avatar, Profile

from .factories import create_user


class ProfileModelTests(TestCase):
    def test_new_profile_gets_default_avatar(self):
        user = create_user()

        self.assertEqual(user.profile.avatar_key, Avatar.KNIGHT_1)

    def test_nickname_is_unique(self):
        create_user("first", nickname="Knight")
        other = create_user("second", nickname="Other")

        with self.assertRaises(IntegrityError):
            Profile.objects.filter(user=other).update(nickname="Knight")

    def test_profile_is_deleted_with_user(self):
        user = create_user()

        user.delete()

        self.assertFalse(Profile.objects.exists())
