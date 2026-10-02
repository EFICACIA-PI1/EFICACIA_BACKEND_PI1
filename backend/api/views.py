from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import Event, Task
from .serializers import (
    ChangePasswordSerializer,
    EventDetailSerializer,
    EventSerializer,
    HoyResponseSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetSerializer,
    RegisterResponseSerializer,
    RegisterSerializer,
    TaskSerializer,
    UserPublicSerializer,
)

User = get_user_model()

PASSWORD_RESET_MESSAGE = (
    "Si el correo está registrado, te enviamos las instrucciones."
)
PASSWORD_RESET_INVALID = "El enlace de recuperación no es válido o ya expiró."


@extend_schema(
    summary="Ping de salud",
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
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


class AuthenticatedUserMixin:
    """Exige token y limita el alcance al usuario autenticado."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]


class PublicAuthMixin:
    """Endpoints públicos de cuenta: ignoran un token inválido en el header."""

    authentication_classes = []
    permission_classes = [AllowAny]


class ThrottledPublicAuthMixin(PublicAuthMixin):
    """Aplica el límite compartido a login, registro y solicitud de reset."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


def user_public_payload(user):
    profile = user.profile
    return UserPublicSerializer(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": profile.full_name,
            "phone": profile.phone,
            "address": profile.address,
            "document_number": profile.document_number,
        }
    ).data


@extend_schema(
    summary="Login local",
    description=(
        "Valida usuario y contraseña contra el User de Django y devuelve un "
        "token. Las rutas de eventos, tareas, Hoy y perfil requieren el "
        "encabezado `Authorization: Token <token>`."
    ),
    request=LoginSerializer,
    responses={
        200: LoginResponseSerializer,
        400: OpenApiTypes.OBJECT,
    },
    examples=[
        OpenApiExample(
            "Login correcto",
            value={"username": "olivia", "password": "ClaveSegura123"},
            request_only=True,
        ),
        OpenApiExample(
            "Respuesta",
            value={"token": "0123456789abcdef0123456789abcdef01234567"},
            response_only=True,
        ),
    ],
)
class LoginView(ThrottledPublicAuthMixin, APIView):
    """Autenticación local. Crea el token si el usuario aún no tiene uno."""

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


@extend_schema(
    summary="Registro de usuario",
    description=(
        "Crea un User y su Profile en una transacción, y devuelve el token "
        "para iniciar sesión de inmediato. El correo no distingue mayúsculas. "
        "La cédula (`document_number`) y el nombre de usuario no se podrán "
        "cambiar después."
    ),
    request=RegisterSerializer,
    responses={
        201: RegisterResponseSerializer,
        400: OpenApiTypes.OBJECT,
    },
    examples=[
        OpenApiExample(
            "Registro",
            value={
                "username": "olivia",
                "email": "olivia@example.com",
                "password": "ClaveSegura123",
                "password_confirm": "ClaveSegura123",
                "full_name": "Olivia Ruiz",
                "phone": "3001234567",
                "document_number": "1020304050",
                "address": "Cali",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Registro exitoso",
            value={
                "token": "0123456789abcdef0123456789abcdef01234567",
                "user": {
                    "id": 1,
                    "username": "olivia",
                    "email": "olivia@example.com",
                    "full_name": "Olivia Ruiz",
                    "phone": "3001234567",
                    "address": "Cali",
                    "document_number": "1020304050",
                },
            },
            response_only=True,
            status_codes=["201"],
        ),
    ],
)
class RegisterView(ThrottledPublicAuthMixin, APIView):
    """Alta de cuenta: User + Profile y token de sesión."""

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            user = User.objects.create_user(
                username=data["username"],
                email=data["email"],
                password=data["password"],
            )
            profile = user.profile
            profile.full_name = data["full_name"]
            profile.phone = data["phone"]
            profile.document_number = data["document_number"]
            profile.address = data.get("address") or ""
            profile.save()
            token = Token.objects.create(user=user)
        return Response(
            {"token": token.key, "user": user_public_payload(user)},
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    get=extend_schema(
        summary="Ver perfil",
        description="Devuelve los datos de la cuenta autenticada.",
        responses={200: MeSerializer, 401: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample(
                "Perfil",
                value={
                    "id": 1,
                    "username": "olivia",
                    "email": "olivia@example.com",
                    "full_name": "Olivia Ruiz",
                    "phone": "3001234567",
                    "address": "Cali",
                    "document_number": "1020304050",
                },
                response_only=True,
            ),
        ],
    ),
    patch=extend_schema(
        summary="Editar perfil",
        description=(
            "Actualización parcial. Se pueden cambiar `full_name`, `phone`, "
            "`address` y `email`. `username` y `document_number` son de solo "
            "lectura: si se envían con otro valor, la API responde 400."
        ),
        request=MeSerializer,
        responses={200: MeSerializer, 400: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample(
                "Cambiar datos editables",
                value={
                    "full_name": "Olivia Ruiz Gómez",
                    "phone": "+573001234567",
                    "address": "Cali",
                    "email": "olivia.ruiz@example.com",
                },
                request_only=True,
            ),
        ],
    ),
)
class MeView(AuthenticatedUserMixin, APIView):
    """Consulta y edición del perfil del usuario autenticado."""

    http_method_names = ["get", "patch", "head", "options"]

    def get(self, request):
        return Response(MeSerializer(request.user).data)

    def patch(self, request):
        serializer = MeSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MeSerializer(request.user).data)


@extend_schema(
    summary="Cambiar contraseña",
    description=(
        "Exige la contraseña actual. Si el cambio es válido, invalida el "
        "token anterior y devuelve uno nuevo."
    ),
    request=ChangePasswordSerializer,
    responses={200: LoginResponseSerializer, 400: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT},
    examples=[
        OpenApiExample(
            "Cambio de contraseña",
            value={
                "old_password": "ClaveAnterior123",
                "new_password": "ClaveNueva456",
                "new_password_confirm": "ClaveNueva456",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Token renovado",
            value={"token": "89abcdef0123456789abcdef0123456789abcdef"},
            response_only=True,
        ),
    ],
)
class ChangePasswordView(AuthenticatedUserMixin, APIView):
    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            return Response(
                {"old_password": ["La contraseña actual es incorrecta."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)
        return Response({"token": token.key}, status=status.HTTP_200_OK)


@extend_schema(
    summary="Solicitar recuperación de contraseña",
    description=(
        "Siempre responde 200 con el mismo mensaje, exista o no el correo, "
        "para no revelar cuentas. Si el usuario existe y está activo, envía "
        "un correo con el enlace `{FRONTEND_URL}/reset-password?uid=&token=`."
    ),
    request=PasswordResetSerializer,
    responses={200: OpenApiTypes.OBJECT},
    examples=[
        OpenApiExample(
            "Solicitud",
            value={"email": "olivia@example.com"},
            request_only=True,
        ),
        OpenApiExample(
            "Respuesta",
            value={"detail": PASSWORD_RESET_MESSAGE},
            response_only=True,
        ),
    ],
)
class PasswordResetView(ThrottledPublicAuthMixin, APIView):
    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is not None:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = (
                f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
            )
            send_mail(
                subject="Recuperación de contraseña - EFICACIA",
                message=(
                    "Hola,\n\n"
                    "Recibimos una solicitud para restablecer tu contraseña. "
                    "Abre el siguiente enlace:\n\n"
                    f"{link}\n\n"
                    "Si no fuiste tú, ignora este mensaje.\n"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        return Response({"detail": PASSWORD_RESET_MESSAGE}, status=status.HTTP_200_OK)


@extend_schema(
    summary="Confirmar recuperación de contraseña",
    description=(
        "Recibe `uid`, `token`, `new_password` y `new_password_confirm`. "
        "El enlace solo sirve una vez. Si el token no es válido o ya se usó, "
        "responde 400."
    ),
    request=PasswordResetConfirmSerializer,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    examples=[
        OpenApiExample(
            "Confirmación",
            value={
                "uid": "MQ",
                "token": "set-password-token",
                "new_password": "ClaveNueva456",
                "new_password_confirm": "ClaveNueva456",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Contraseña actualizada",
            value={"detail": "La contraseña se actualizó correctamente."},
            response_only=True,
        ),
    ],
)
class PasswordResetConfirmView(PublicAuthMixin, APIView):
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user_id = force_str(urlsafe_base64_decode(serializer.validated_data["uid"]))
            user = User.objects.get(pk=user_id)
        except (ValueError, TypeError, OverflowError, User.DoesNotExist):
            return Response(
                {"detail": PASSWORD_RESET_INVALID},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not default_token_generator.check_token(user, serializer.validated_data["token"]):
            return Response(
                {"detail": PASSWORD_RESET_INVALID},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        Token.objects.filter(user=user).delete()
        return Response(
            {"detail": "La contraseña se actualizó correctamente."},
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Cerrar sesión",
    description="Elimina el token del usuario autenticado. Responde 204.",
    request=None,
    responses={204: None, 401: OpenApiTypes.OBJECT},
)
class LogoutView(AuthenticatedUserMixin, APIView):
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(
        summary="Listar eventos",
        description="Lista los eventos del usuario autenticado.",
    ),
    create=extend_schema(
        summary="Crear evento",
        description="US-01: crea un evento con su información básica.",
    ),
)
class EventListCreateView(AuthenticatedUserMixin, generics.ListCreateAPIView):
    serializer_class = EventSerializer

    def get_queryset(self):
        return Event.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


@extend_schema_view(
    retrieve=extend_schema(
        summary="Detalle de evento",
        description="US-01: detalle de un evento, incluye sus tareas anidadas (`tasks`).",
    ),
    update=extend_schema(summary="Editar evento (completo)", description="US-03."),
    partial_update=extend_schema(summary="Editar evento (parcial)", description="US-03."),
    destroy=extend_schema(summary="Eliminar evento", description="US-03."),
)
class EventDetailView(AuthenticatedUserMixin, FriendlyNotFoundMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EventDetailSerializer
    not_found_message = "Evento no encontrado."

    def get_queryset(self):
        return Event.objects.filter(user=self.request.user)


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
class TaskListCreateView(AuthenticatedUserMixin, generics.ListCreateAPIView):
    serializer_class = TaskSerializer

    def get_event(self):
        if not hasattr(self, "_event"):
            try:
                self._event = Event.objects.get(
                    pk=self.kwargs["event_id"], user=self.request.user
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
        serializer.save(event=self.get_event())


@extend_schema_view(
    retrieve=extend_schema(summary="Detalle de tarea"),
    update=extend_schema(summary="Editar tarea (completo)", description="US-03."),
    partial_update=extend_schema(summary="Editar tarea (parcial)", description="US-03."),
    destroy=extend_schema(summary="Eliminar tarea", description="US-03."),
)
class TaskDetailView(AuthenticatedUserMixin, FriendlyNotFoundMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TaskSerializer
    not_found_message = "Tarea no encontrada."

    def get_queryset(self):
        return Task.objects.filter(event__user=self.request.user)


@extend_schema_view(
    get=extend_schema(
        summary="Vista Hoy: gestiones agrupadas",
        description=(
            "Agrupa las gestiones del usuario autenticado según la fecha "
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
                description="Filtra las gestiones de un evento del usuario.",
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
class HoyView(AuthenticatedUserMixin, APIView):
    """Vista Hoy: gestiones vencidas, para hoy y próximas del usuario."""

    def get(self, request):
        today = timezone.localdate()
        queryset = Task.objects.filter(event__user=request.user)

        event_id = request.query_params.get("event")
        if event_id is not None:
            try:
                event_pk = int(event_id)
            except (TypeError, ValueError):
                raise ValidationError({"event": "El id de evento debe ser un número entero."})
            if not Event.objects.filter(pk=event_pk, user=request.user).exists():
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
