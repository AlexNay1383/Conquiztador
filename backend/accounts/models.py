from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField("имейл", unique=True)


class Avatar(models.TextChoices):
    KNIGHT_1 = "knight-1", "Рицар 1"
    KNIGHT_2 = "knight-2", "Рицар 2"
    KNIGHT_3 = "knight-3", "Рицар 3"
    KNIGHT_4 = "knight-4", "Рицар 4"


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="потребител",
    )
    nickname = models.CharField("прякор", max_length=30, unique=True)
    avatar_key = models.CharField(
        "аватар",
        max_length=30,
        choices=Avatar.choices,
        default=Avatar.KNIGHT_1,
    )

    class Meta:
        verbose_name = "профил"
        verbose_name_plural = "профили"

    def __str__(self):
        return self.nickname
