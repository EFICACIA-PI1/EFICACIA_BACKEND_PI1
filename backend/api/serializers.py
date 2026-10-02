from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Event, Profile, Task
from .validators import (
    normalize_email,
    validate_document_number,
    validate_email_unique,
    validate_full_name,
    validate_phone,
)

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    """Credenciales de acceso local (usuario de Django)."""

    username = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class LoginResponseSerializer(serializers.Serializer):
    token = serializers.CharField()


class UserPublicSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    phone = serializers.CharField()
    address = serializers.CharField(allow_blank=True)
    document_number = serializers.CharField(allow_null=True)


class RegisterResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    user = UserPublicSerializer()


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    password_confirm = serializers.CharField(write_only=True, style={"input_type": "password"})
    full_name = serializers.CharField()
    phone = serializers.CharField()
    document_number = serializers.CharField()
    address = serializers.CharField(required=False, allow_blank=True, default="", max_length=255)

    def validate_username(self, value):
        username = value.strip()
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError("Ya existe un usuario con ese nombre.")
        return username

    def validate_email(self, value):
        return validate_email_unique(normalize_email(value))

    def validate_full_name(self, value):
        return validate_full_name(value)

    def validate_phone(self, value):
        return validate_phone(value)

    def validate_document_number(self, value):
        number = validate_document_number(value)
        if Profile.objects.filter(document_number=number).exists():
            raise serializers.ValidationError("Ya existe una cuenta con ese número de documento.")
        return number

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Las contraseñas no coinciden."}
            )
        return attrs


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(required=False)
    full_name = serializers.CharField(required=False)
    phone = serializers.CharField(required=False)
    address = serializers.CharField(required=False, allow_blank=True, max_length=255)
    document_number = serializers.CharField(read_only=True, allow_null=True)

    def to_representation(self, instance):
        profile = instance.profile
        return {
            "id": instance.id,
            "username": instance.username,
            "email": instance.email,
            "full_name": profile.full_name,
            "phone": profile.phone,
            "address": profile.address,
            "document_number": profile.document_number,
        }

    def validate_full_name(self, value):
        return validate_full_name(value)

    def validate_phone(self, value):
        return validate_phone(value)

    def validate_email(self, value):
        return validate_email_unique(normalize_email(value), exclude_user=self.instance)

    def validate_address(self, value):
        return value or ""

    def validate(self, attrs):
        user = self.instance
        profile = user.profile
        incoming = self.initial_data or {}

        if "username" in incoming:
            if str(incoming.get("username")) != str(user.username):
                raise serializers.ValidationError(
                    {"username": "El nombre de usuario no se puede modificar."}
                )
            attrs.pop("username", None)

        if "document_number" in incoming:
            current = "" if profile.document_number is None else str(profile.document_number)
            if str(incoming.get("document_number")) != current:
                raise serializers.ValidationError(
                    {"document_number": "El número de documento no se puede modificar."}
                )
            attrs.pop("document_number", None)

        return attrs

    def update(self, instance, validated_data):
        profile = instance.profile
        if "email" in validated_data:
            instance.email = validated_data["email"]
            instance.save(update_fields=["email"])
        profile_fields = []
        for field in ("full_name", "phone", "address"):
            if field in validated_data:
                setattr(profile, field, validated_data[field])
                profile_fields.append(field)
        if profile_fields:
            profile.save(update_fields=profile_fields + ["updated_at"])
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password_confirm = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_new_password(self, value):
        user = self.context["request"].user
        try:
            validate_password(value, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Las contraseñas no coinciden."}
            )
        return attrs


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password_confirm = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Las contraseñas no coinciden."}
            )
        return attrs


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            "id",
            "name",
            "event_type",
            "client_contact",
            "event_date",
            "location",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("El nombre del evento no puede estar vacío.")
        return value


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = [
            "id",
            "name",
            "description",
            "due_date",
            "estimated_hours",
            "state",
            "type",
            "parent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "state", "created_at", "updated_at"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("El nombre de la gestión no puede estar vacío.")
        return value

    def validate_estimated_hours(self, value):
        if value <= 0:
            raise serializers.ValidationError("Las horas estimadas deben ser mayores a 0.")
        return value

    def validate(self, attrs):
        task_type = attrs.get("type", getattr(self.instance, "type", None) or Task.TaskType.TASK)
        parent = attrs.get("parent", getattr(self.instance, "parent", None))

        if task_type == Task.TaskType.SUBTASK and parent is None:
            raise serializers.ValidationError(
                {"parent": "Una subtarea debe indicar a qué tarea pertenece."}
            )
        if task_type == Task.TaskType.TASK and parent is not None:
            raise serializers.ValidationError(
                {"parent": "Una tarea de nivel superior no puede tener una tarea padre."}
            )
        if parent is not None and parent.type != Task.TaskType.TASK:
            raise serializers.ValidationError(
                {"parent": "La tarea padre debe ser una tarea de nivel superior, no otra subtarea."}
            )

        event = self.context.get("event") or getattr(self.instance, "event", None)
        if parent is not None and event is not None and parent.event_id != event.id:
            raise serializers.ValidationError(
                {"parent": "La tarea padre debe pertenecer al mismo evento."}
            )

        return attrs


class EventDetailSerializer(EventSerializer):
    tasks = TaskSerializer(many=True, read_only=True)

    class Meta(EventSerializer.Meta):
        fields = EventSerializer.Meta.fields + ["tasks"]


class HoyResponseSerializer(serializers.Serializer):
    """Agrupación de gestiones para la vista Hoy."""

    vencidas = TaskSerializer(many=True)
    para_hoy = TaskSerializer(many=True)
    proximas = TaskSerializer(many=True)
