from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health),
    path("auth/login/", views.LoginView.as_view(), name="auth-login"),
    path("auth/register/", views.RegisterView.as_view(), name="auth-register"),
    path("auth/me/", views.MeView.as_view(), name="auth-me"),
    path("auth/change-password/", views.ChangePasswordView.as_view(), name="auth-change-password"),
    path("auth/password-reset/", views.PasswordResetView.as_view(), name="auth-password-reset"),
    path(
        "auth/password-reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("hoy/", views.HoyView.as_view(), name="hoy"),
    path("events/", views.EventListCreateView.as_view(), name="event-list-create"),
    path("events/<int:pk>/", views.EventDetailView.as_view(), name="event-detail"),
    path(
        "events/<int:event_id>/tasks/",
        views.TaskListCreateView.as_view(),
        name="task-list-create",
    ),
    path("tasks/<int:pk>/", views.TaskDetailView.as_view(), name="task-detail"),
]
