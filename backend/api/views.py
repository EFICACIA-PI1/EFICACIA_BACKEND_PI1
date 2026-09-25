from django.http import Http404
from drf_spectacular.utils import OpenApiTypes, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from .demo import get_demo_organizer
from .models import Event, Task
from .serializers import EventDetailSerializer, EventSerializer, TaskSerializer


@extend_schema(
    summary="Ping de salud",
    responses={200: OpenApiTypes.OBJECT},
)
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


@extend_schema_view(
    list=extend_schema(
        summary="Listar eventos",
        description="Lista los eventos del organizador demo (Sprint 1-2, sin login).",
    ),
    create=extend_schema(
        summary="Crear evento",
        description="US-01: crea un evento con su información básica.",
    ),
)
class EventListCreateView(generics.ListCreateAPIView):
    serializer_class = EventSerializer

    def get_queryset(self):
        return Event.objects.filter(organizer=get_demo_organizer())

    def perform_create(self, serializer):
        serializer.save(organizer=get_demo_organizer())


@extend_schema_view(
    retrieve=extend_schema(
        summary="Detalle de evento",
        description="US-01: detalle de un evento, incluye sus tareas anidadas (`tasks`).",
    ),
    update=extend_schema(summary="Editar evento (completo)", description="US-03."),
    partial_update=extend_schema(summary="Editar evento (parcial)", description="US-03."),
    destroy=extend_schema(summary="Eliminar evento", description="US-03."),
)
class EventDetailView(FriendlyNotFoundMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EventDetailSerializer
    not_found_message = "Evento no encontrado."

    def get_queryset(self):
        return Event.objects.filter(organizer=get_demo_organizer())


@extend_schema_view(
    list=extend_schema(
        summary="Listar tareas de un evento",
        description="Lista las tareas y subtareas de un evento (US-02).",
    ),
    create=extend_schema(
        summary="Crear tarea o subtarea",
        description=(
            "US-02: crea una gestión (`type=\"task\"`, por defecto) o un paso "
            "dentro de una gestión (`type=\"subtask\"`, requiere `parent` con el "
            "id de una tarea de tipo `task` del mismo evento)."
        ),
    ),
)
class TaskListCreateView(generics.ListCreateAPIView):
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


@extend_schema_view(
    retrieve=extend_schema(summary="Detalle de tarea"),
    update=extend_schema(summary="Editar tarea (completo)", description="US-03."),
    partial_update=extend_schema(summary="Editar tarea (parcial)", description="US-03."),
    destroy=extend_schema(summary="Eliminar tarea", description="US-03."),
)
class TaskDetailView(FriendlyNotFoundMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TaskSerializer
    not_found_message = "Tarea no encontrada."

    def get_queryset(self):
        return Task.objects.filter(organizer=get_demo_organizer())
