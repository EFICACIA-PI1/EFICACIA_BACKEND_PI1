from django.http import Http404
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from .demo import get_demo_organizer
from .models import Event
from .serializers import EventDetailSerializer, EventSerializer


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
