from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from rest_framework import status
from django.test import Client

User = get_user_model()

class AuthAPITests(APITestCase):
    def setUp(self):
        self.register_url = '/api/auth/register/'
        self.login_url = '/api/auth/login/'
        self.logout_url = '/api/auth/logout/'
        self.me_url = '/api/auth/me/'
        self.csrf_url = '/api/auth/csrf/'
        
        self.user_data = {
            "username": "player_one",
            "email": "player@example.com",
            "nickname": "MountainKnight",
            "password": "example-password",
            "password_confirm": "example-password"
        }

    def test_1_successful_registration(self):
        response = self.client.post(self.register_url, self.user_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("profile", response.data)
        self.assertEqual(response.data["profile"]["nickname"], "MountainKnight")
        self.assertNotIn("password", response.data)
        
        user = User.objects.get(username="player_one")
        self.assertTrue(user.check_password("example-password"))
        self.assertEqual(user.profile.nickname, "MountainKnight")

    def test_2_invalid_registration(self):
        # Missing fields
        response = self.client.post(self.register_url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Passwords mismatch
        bad_data = self.user_data.copy()
        bad_data["password_confirm"] = "different-password"
        response = self.client.post(self.register_url, bad_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_3_successful_login(self):
        self.client.post(self.register_url, self.user_data)
        
        login_data = {
            "username": "player_one",
            "password": "example-password"
        }
        response = self.client.post(self.login_url, login_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test subsequent /me/ request
        me_response = self.client.get(self.me_url)
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data["username"], "player_one")

    def test_4_invalid_login(self):
        self.client.post(self.register_url, self.user_data)
        
        login_data = {
            "username": "player_one",
            "password": "wrong-password"
        }
        response = self.client.post(self.login_url, login_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Test subsequent /me/ request is rejected
        me_response = self.client.get(self.me_url)
        self.assertEqual(me_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_5_permissions_me(self):
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        self.client.post(self.register_url, self.user_data)
        self.client.post(self.login_url, {
            "username": "player_one",
            "password": "example-password"
        })
        
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_6_edit_profile(self):
        self.client.post(self.register_url, self.user_data)
        self.client.post(self.login_url, {
            "username": "player_one",
            "password": "example-password"
        })
        
        patch_data = {
            "nickname": "NewKnight",
            "avatar_key": "knight-3"
        }
        response = self.client.patch(self.me_url, patch_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        user = User.objects.get(username="player_one")
        self.assertEqual(user.profile.nickname, "NewKnight")
        self.assertEqual(user.profile.avatar_key, "knight-3")

    def test_7_logout(self):
        self.client.post(self.register_url, self.user_data)
        self.client.post(self.login_url, {
            "username": "player_one",
            "password": "example-password"
        })
        
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        
        me_response = self.client.get(self.me_url)
        self.assertEqual(me_response.status_code, status.HTTP_403_FORBIDDEN)

class CSRFTests(APITestCase):
    def test_8_csrf_protection(self):
        user_data = {
            "username": "player_one",
            "email": "player@example.com",
            "nickname": "MountainKnight",
            "password": "example-password",
            "password_confirm": "example-password"
        }
        self.client.post('/api/auth/register/', user_data)
        self.client.post('/api/auth/login/', {
            "username": "player_one",
            "password": "example-password"
        })
        
        # Enforce CSRF checks by using a standard Django client
        # wait, DRF APITestCase forces CSRF off by default unless enforce_csrf_checks=True
        from rest_framework.test import APIClient
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.login(username="player_one", password="example-password")
        
        # without token
        response = csrf_client.patch('/api/auth/me/', {"nickname": "Hacker"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # with token
        csrf_client.get('/api/auth/csrf/')
        token = csrf_client.cookies['csrftoken'].value
        response = csrf_client.patch('/api/auth/me/', {"nickname": "Hacker"}, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
