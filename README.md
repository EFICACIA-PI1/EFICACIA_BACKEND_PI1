# EFICACIA — Backend (Organizador de Eventos Independientes)

API REST en Django + Django REST Framework para EFICACIA. Persistencia en PostgreSQL (Supabase). Los usuarios administran sus propios eventos, tareas y perfil; incluye registro, autenticación por token y recuperación de contraseña.

## Requisitos

- Python 3.12+
- Una base de datos PostgreSQL accesible (el proyecto usa Supabase)

## Arranque local

```bash
cd backend

# 1. Entorno virtual
python3 -m venv venv
source venv/bin/activate

# 2. Dependencias
pip install -r requirements.txt

# 3. Variables de entorno: crea backend/.env con
#    SECRET_KEY=una-clave-cualquiera-para-desarrollo
#    DEBUG=True
#    DATABASE_URL=postgresql://usuario:password@host:puerto/basededatos
#    CORS_ALLOWED_ORIGINS=http://localhost:5173
#    FRONTEND_URL=http://localhost:5173 (opcional; destino de recuperación)

# 4. Migraciones
python manage.py migrate

# 5. Datos demo (organizador + 1 evento + 3 subtareas de ejemplo)
python manage.py seed_demo

# 6. Levantar el servidor
python manage.py runserver
```

La API queda en `http://127.0.0.1:8000/api/`. El admin de Django en `http://127.0.0.1:8000/admin/` (crea un superusuario con `python manage.py createsuperuser` si lo necesitas).

## Documentación interactiva

- Swagger UI: `http://127.0.0.1:8000/api/docs/`
- ReDoc: `http://127.0.0.1:8000/api/redoc/`
- Esquema OpenAPI en crudo: `http://127.0.0.1:8000/api/schema/`

Se genera automáticamente (drf-spectacular) a partir de los serializers y vistas: siempre refleja el contrato real, sin mantenerla a mano.

## Pruebas

```bash
python manage.py test api --keepdb
```

Se usa `--keepdb`: al probar contra una base remota vía el *connection pooler* de Supabase, Django a veces no logra borrar la base de datos de prueba al final (el pooler mantiene una conexión colgada). Con `--keepdb` reutiliza la misma base de prueba entre corridas y evita ese problema.

## Autenticación y cuentas

Las rutas protegidas reciben `Authorization: Token <token>`. Cada usuario ve únicamente los eventos y tareas que le pertenecen. `POST /api/auth/register/` crea la cuenta y devuelve un token. Los usuarios creados desde el admin reciben un perfil automáticamente; el admin permite completar sus datos.

El correo de recuperación se imprime en la terminal por defecto. Para SMTP se configuran `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` y `EMAIL_USE_SSL`. El remitente se configura con `DEFAULT_FROM_EMAIL`.

## Endpoints

Todas las respuestas son JSON. Errores de validación devuelven `400` con un objeto `{campo: [mensajes]}`; recursos no encontrados devuelven `404` con `{"detail": "..."}`.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/health/` | Ping de salud de la API |
| POST | `/api/auth/register/` | Crea usuario, perfil y token |
| POST | `/api/auth/login/` | Inicia sesión con usuario y contraseña |
| GET/PATCH | `/api/auth/me/` | Consulta y edita el perfil autenticado |
| POST | `/api/auth/change-password/` | Cambia la contraseña y rota el token |
| POST | `/api/auth/password-reset/` | Solicita enlace de recuperación por correo |
| POST | `/api/auth/password-reset/confirm/` | Confirma el cambio con `uid` y `token` |
| POST | `/api/auth/logout/` | Invalida el token actual |
| GET | `/api/events/` | Lista los eventos del usuario autenticado |
| POST | `/api/events/` | Crea un evento (US-01) |
| GET | `/api/events/<id>/` | Detalle de un evento, incluye sus tareas (`tasks`) |
| PUT/PATCH | `/api/events/<id>/` | Edita un evento (US-03) |
| DELETE | `/api/events/<id>/` | Elimina un evento (US-03) |
| GET | `/api/events/<id>/tasks/` | Lista las tareas/subtareas de un evento |
| POST | `/api/events/<id>/tasks/` | Crea una tarea o subtarea (US-02) |
| GET | `/api/tasks/<id>/` | Detalle de una tarea |
| PUT/PATCH | `/api/tasks/<id>/` | Edita una tarea (US-03) |
| DELETE | `/api/tasks/<id>/` | Elimina una tarea (US-03) |

### Campos de Event

`name`, `event_type` (`boda`/`social`/`corporativo`/`cumpleanos`/`otro`), `client_contact`, `event_date` (ISO 8601), `location`. Todos obligatorios.

### Campos de Task

`name`, `due_date` (fecha), `estimated_hours` (> 0), `description` (opcional). `type` es `"task"` (gestión de nivel superior, valor por defecto) o `"subtask"` (paso dentro de una tarea); si es `"subtask"` requiere `parent` con el id de una tarea `"task"` del mismo evento. `state` (`pendiente`/`hecha`/`pospuesta`) y `event` no se envían al crear: los asigna el servidor. Las tareas heredan la propiedad del evento.

La recuperación y el contrato completo de request/response están documentados en Swagger (`/api/docs/`) y ReDoc (`/api/redoc/`).
