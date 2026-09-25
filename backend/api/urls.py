from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health),
    path("events/", views.EventListCreateView.as_view(), name="event-list-create"),
    path("events/<int:pk>/", views.EventDetailView.as_view(), name="event-detail"),
]
