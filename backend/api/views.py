from django.http import Http404
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from .demo import get_demo_organizer
from .models import Event, Task
from .serializers import EventDetailSerializer, EventSerializer, TaskSerializer


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


class FriendlyNotFoundMixin:
    """Django/DRF arman el 404 de get_object() en ingles y no lo traducen.
    Lo reemplazamos por un mensaje propio, claro y en espanol."""

    not_found_message = "No se encontró el recurso solicitado."

    def get_object(self):
        try:
            return super().get_object()
        except Http404:
            raise NotFound(self.not_found_message)


class EventListCreateView(generics.ListCreateAPIView):
    """GET /api/events/ lista los eventos del organizador demo.
    POST /api/events/ crea un evento nuevo (US-01).
    """

    serializer_class = EventSerializer

    def get_queryset(self):
        return Event.objects.filter(organizer=get_demo_organizer())

    def perform_create(self, serializer):
        serializer.save(organizer=get_demo_organizer())


class EventDetailView(FriendlyNotFoundMixin, generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/events/<id>/ (US-01 detalle, US-03 editar/eliminar).

    El detalle incluye las tareas del evento (EventDetailSerializer) para
    poder pintar /evento/:id sin una segunda llamada.
    """

    serializer_class = EventDetailSerializer
    not_found_message = "Evento no encontrado."

    def get_queryset(self):
        return Event.objects.filter(organizer=get_demo_organizer())


class TaskListCreateView(generics.ListCreateAPIView):
    """GET /api/events/<event_id>/tasks/ lista las tareas de ese evento.
    POST /api/events/<event_id>/tasks/ crea una tarea/subtarea (US-02).
    """

    serializer_class = TaskSerializer

    def get_event(self):
        if not hasattr(self, "_event"):
            try:
                self._event = Event.objects.get(
                    pk=self.kwargs["event_id"], organizer=get_demo_organizer()
                )
            except Event.DoesNotExist:
                raise NotFound("Evento no encontrado.")
        return self._event

    def get_queryset(self):
        return Task.objects.filter(event=self.get_event())

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["event"] = self.get_event()
        return context

    def perform_create(self, serializer):
        event = self.get_event()
        serializer.save(event=event, organizer=event.organizer)


class TaskDetailView(FriendlyNotFoundMixin, generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/tasks/<id>/ (US-03 editar/eliminar subtarea)."""

    serializer_class = TaskSerializer
    not_found_message = "Tarea no encontrada."

    def get_queryset(self):
        return Task.objects.filter(organizer=get_demo_organizer())
