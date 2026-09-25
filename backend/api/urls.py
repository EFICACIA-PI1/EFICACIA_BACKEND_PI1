from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health),
    path("events/", views.EventListCreateView.as_view(), name="event-list-create"),
    path("events/<int:pk>/", views.EventDetailView.as_view(), name="event-detail"),
    path(
        "events/<int:event_id>/tasks/",
        views.TaskListCreateView.as_view(),
        name="task-list-create",
    ),
    path("tasks/<int:pk>/", views.TaskDetailView.as_view(), name="task-detail"),
]
