from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Profile, User


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    list_display = ["username", "email", "nickname", "is_staff", "is_active"]
    search_fields = ["username", "email", "profile__nickname"]

    @admin.display(description="прякор", ordering="profile__nickname")
    def nickname(self, user):
        profile = getattr(user, "profile", None)
        return profile.nickname if profile else "—"


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["nickname", "user", "avatar_key"]
    list_filter = ["avatar_key"]
    search_fields = ["nickname", "user__username", "user__email"]
    autocomplete_fields = ["user"]
