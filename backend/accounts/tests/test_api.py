from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import Avatar, Profile

from .factories import DEFAULT_PASSWORD, create_user

User = get_user_model()

REGISTER_URL = reverse("auth-register")
LOGIN_URL = reverse("auth-login")
LOGOUT_URL = reverse("auth-logout")
ME_URL = reverse("auth-me")
CSRF_URL = reverse("auth-csrf")


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


class RegistrationTests(APITestCase):
    def test_successful_registration(self):
        response = self.client.post(REGISTER_URL, registration_data(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="player_one")
        self.assertEqual(user.profile.nickname, "MountainKnight")
        self.assertTrue(user.check_password("Strong-pass-2024"))
        self.assertEqual(
            response.json(),
            {
                "id": user.id,
                "username": "player_one",
                "email": "player@example.com",
                "profile": {"nickname": "MountainKnight", "avatar_key": Avatar.KNIGHT_1},
            },
        )
        self.assertNotIn("password", response.content.decode())

    def test_registration_logs_the_user_in(self):
        self.client.post(REGISTER_URL, registration_data(), format="json")

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_invalid_registration(self):
        create_user("taken", email="taken@example.com", nickname="TakenNick")
        cases = {
            "username": registration_data(username="taken"),
            "email": registration_data(email="taken@example.com"),
            "nickname": registration_data(nickname="TakenNick"),
            "password_confirm": registration_data(password_confirm="Other-pass-2024"),
        }

        for field, data in cases.items():
            with self.subTest(field=field):
                response = self.client.post(REGISTER_URL, data, format="json")

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.json()["errors"])
                self.assertEqual(User.objects.count(), 1)


class LoginTests(APITestCase):
    def setUp(self):
        self.user = create_user("player_one")

    def test_successful_login(self):
        response = self.client.post(
            LOGIN_URL, {"username": "player_one", "password": DEFAULT_PASSWORD}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("sessionid", response.cookies)
        me = self.client.get(ME_URL)
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.json()["id"], self.user.id)

    def test_failed_login(self):
        response = self.client.post(
            LOGIN_URL, {"username": "player_one", "password": "wrong-password"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", response.json()["errors"])
        self.assertNotIn("sessionid", response.cookies)
        self.assertEqual(self.client.get(ME_URL).status_code, status.HTTP_401_UNAUTHORIZED)


class MePermissionTests(APITestCase):
    def test_anonymous_access_is_denied(self):
        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("detail", response.json()["errors"])

    def test_authenticated_user_sees_only_own_data(self):
        create_user("someone_else")
        user = create_user("player_one")
        self.client.force_authenticate(user)

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["username"], "player_one")
        self.assertEqual(response.json()["id"], user.id)


class ProfileUpdateTests(APITestCase):
    def setUp(self):
        self.user = create_user("player_one", nickname="OldKnight")
        self.client.force_authenticate(self.user)

    def test_update_nickname_and_avatar(self):
        response = self.client.patch(
            ME_URL, {"nickname": "NewKnight", "avatar_key": Avatar.KNIGHT_3}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["profile"], {"nickname": "NewKnight", "avatar_key": "knight-3"})
        profile = Profile.objects.get(user=self.user)
        self.assertEqual((profile.nickname, profile.avatar_key), ("NewKnight", Avatar.KNIGHT_3))

    def test_protected_field_cannot_be_changed(self):
        response = self.client.patch(ME_URL, {"is_staff": True}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_staff", response.json()["errors"])
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)


class LogoutTests(APITestCase):
    def test_logout_ends_the_session(self):
        create_user("player_one")
        self.client.post(LOGIN_URL, {"username": "player_one", "password": DEFAULT_PASSWORD}, format="json")

        response = self.client.post(LOGOUT_URL)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.get(ME_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_anonymous_logout_is_denied(self):
        response = self.client.post(LOGOUT_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class CsrfTests(APITestCase):
    def setUp(self):
        self.csrf_client = APIClient(enforce_csrf_checks=True)

    def get_csrf_token(self):
        response = self.csrf_client.get(CSRF_URL)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        return response.cookies["csrftoken"].value

    def test_session_request_requires_csrf_token(self):
        create_user("player_one")
        token = self.get_csrf_token()
        self.csrf_client.post(
            LOGIN_URL,
            {"username": "player_one", "password": DEFAULT_PASSWORD},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        token = self.csrf_client.cookies["csrftoken"].value

        without_token = self.csrf_client.patch(ME_URL, {"nickname": "Changed"}, format="json")
        with_token = self.csrf_client.patch(
            ME_URL, {"nickname": "Changed"}, format="json", HTTP_X_CSRFTOKEN=token
        )

        self.assertEqual(without_token.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("detail", without_token.json()["errors"])
        self.assertEqual(with_token.status_code, status.HTTP_200_OK)

    def test_anonymous_login_requires_csrf_token(self):
        create_user("player_one")
        credentials = {"username": "player_one", "password": DEFAULT_PASSWORD}

        without_token = self.csrf_client.post(LOGIN_URL, credentials, format="json")
        token = self.get_csrf_token()
        with_token = self.csrf_client.post(LOGIN_URL, credentials, format="json", HTTP_X_CSRFTOKEN=token)

        self.assertEqual(without_token.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(with_token.status_code, status.HTTP_200_OK)
