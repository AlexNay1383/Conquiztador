from django.contrib.auth import get_user_model

from accounts.models import Profile

DEFAULT_PASSWORD = "Strong-pass-2024"


def create_user(username="player_one", email=None, nickname=None, password=DEFAULT_PASSWORD):
    user = get_user_model().objects.create_user(
        username=username,
        email=email or f"{username}@example.com",
        password=password,
    )
    Profile.objects.create(user=user, nickname=nickname or username)
    return user
