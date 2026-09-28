from django.contrib.auth import authenticate
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.decorators import api_view
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Event, Task
from .serializers import (
    EventDetailSerializer,
    EventSerializer,
    HoyResponseSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    TaskSerializer,
)


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


class OrganizerAuthMixin:
    """Exige token y limita el alcance al organizador del usuario autenticado."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_organizer(self):
        try:
            return self.request.user.organizer
        except ObjectDoesNotExist:
            raise PermissionDenied("El usuario no está asociado a un organizador.")


@extend_schema(
    summary="Login local",
    description=(
        "US-11: valida usuario y contraseña contra el User de Django y "
        "devuelve un token de autenticación. Las rutas de eventos, tareas "
        "y Hoy requieren el encabezado `Authorization: Token <token>`."
    ),
    request=LoginSerializer,
    responses={
        200: LoginResponseSerializer,
        400: OpenApiTypes.OBJECT,
    },
)
class LoginView(APIView):
    """Autenticación local. Crea el token si el usuario aún no tiene uno."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Usuario o contraseña incorrectos."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        token, _created = Token.objects.get_or_create(user=user)
        return Response({"token": token.key}, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        summary="Listar eventos",
        description="Lista los eventos del organizador autenticado.",
    ),
    create=extend_schema(
        summary="Crear evento",
        description="US-01: crea un evento con su información básica.",
    ),
)
class EventListCreateView(OrganizerAuthMixin, generics.ListCreateAPIView):
    serializer_class = EventSerializer

    def get_queryset(self):
        return Event.objects.filter(organizer=self.get_organizer())

    def perform_create(self, serializer):
        serializer.save(organizer=self.get_organizer())


@extend_schema_view(
    retrieve=extend_schema(
        summary="Detalle de evento",
        description="US-01: detalle de un evento, incluye sus tareas anidadas (`tasks`).",
    ),
    update=extend_schema(summary="Editar evento (completo)", description="US-03."),
    partial_update=extend_schema(summary="Editar evento (parcial)", description="US-03."),
    destroy=extend_schema(summary="Eliminar evento", description="US-03."),
)
class EventDetailView(OrganizerAuthMixin, FriendlyNotFoundMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EventDetailSerializer
    not_found_message = "Evento no encontrado."

    def get_queryset(self):
        return Event.objects.filter(organizer=self.get_organizer())


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
class TaskListCreateView(OrganizerAuthMixin, generics.ListCreateAPIView):
    serializer_class = TaskSerializer

    def get_event(self):
        if not hasattr(self, "_event"):
            try:
                self._event = Event.objects.get(
                    pk=self.kwargs["event_id"], organizer=self.get_organizer()
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
class TaskDetailView(OrganizerAuthMixin, FriendlyNotFoundMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TaskSerializer
    not_found_message = "Tarea no encontrada."

    def get_queryset(self):
        return Task.objects.filter(organizer=self.get_organizer())


@extend_schema_view(
    get=extend_schema(
        summary="Vista Hoy: gestiones agrupadas",
        description=(
            "Agrupa las gestiones del organizador autenticado según la fecha "
            "de hoy del servidor: `vencidas` (due_date < hoy y no hechas, "
            "más antigua primero), `para_hoy` (due_date = hoy y no hechas) y "
            "`proximas` (due_date > hoy y no hechas, más cercana primero). "
            "Dentro de la misma fecha se desempatan por estimated_hours "
            "ascendente. Las tareas con state=\"hecha\" se excluyen de los "
            "tres grupos. Filtros opcionales: `event` (id del evento) y "
            "`state` (pendiente, hecha o pospuesta)."
        ),
        parameters=[
            OpenApiParameter(
                name="event",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filtra las gestiones de un evento del organizador.",
            ),
            OpenApiParameter(
                name="state",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=["pendiente", "hecha", "pospuesta"],
                description="Filtra por estado de la gestión.",
            ),
        ],
        responses={200: HoyResponseSerializer},
    )
)
class HoyView(OrganizerAuthMixin, APIView):
    """Vista Hoy: gestiones vencidas, para hoy y próximas del organizador."""

    def get(self, request):
        organizer = self.get_organizer()
        today = timezone.localdate()
        queryset = Task.objects.filter(organizer=organizer)

        event_id = request.query_params.get("event")
        if event_id is not None:
            try:
                event_pk = int(event_id)
            except (TypeError, ValueError):
                raise ValidationError({"event": "El id de evento debe ser un número entero."})
            if not Event.objects.filter(pk=event_pk, organizer=organizer).exists():
                raise NotFound("Evento no encontrado.")
            queryset = queryset.filter(event_id=event_pk)

        state = request.query_params.get("state")
        if state is not None:
            valid_states = set(Task.State.values)
            if state not in valid_states:
                raise ValidationError(
                    {"state": "Estado inválido. Use pendiente, hecha o pospuesta."}
                )
            queryset = queryset.filter(state=state)

        queryset = queryset.exclude(state=Task.State.HECHA)
        order = ("due_date", "estimated_hours")

        vencidas = queryset.filter(due_date__lt=today).order_by(*order)
        para_hoy = queryset.filter(due_date=today).order_by("estimated_hours")
        proximas = queryset.filter(due_date__gt=today).order_by(*order)

        payload = {
            "vencidas": TaskSerializer(vencidas, many=True).data,
            "para_hoy": TaskSerializer(para_hoy, many=True).data,
            "proximas": TaskSerializer(proximas, many=True).data,
        }
        return Response(payload)
