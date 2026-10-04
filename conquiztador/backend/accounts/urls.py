from django.urls import path
from .views import CSRFView, RegisterView, LoginView, LogoutView, CurrentUserView

urlpatterns = [
    path('auth/csrf/', CSRFView.as_view(), name='csrf'),
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/me/', CurrentUserView.as_view(), name='me'),
]
