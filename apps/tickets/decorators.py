from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def staff_required(view_func):
    """Exige usuario autenticado con rol admin o técnico."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if not getattr(user, "es_staff_helpdesk", False):
            raise PermissionDenied("Se requiere rol de staff (admin/técnico).")
        return view_func(request, *args, **kwargs)

    return _wrapped


def user_required(view_func):
    """Exige usuario autenticado con rol usuario."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if getattr(user, "rol", None) != "usuario":
            raise PermissionDenied("Se requiere rol de usuario.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def admin_required(view_func):
    """Exige usuario autenticado con rol administrador."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if getattr(user, "rol", None) != "admin" or not getattr(user, "activo", False):
            raise PermissionDenied("Se requiere rol de administrador.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def sin_observador(view_func):
    """Bloquea al observador, que solo puede consultar.

    Se pone encima de las vistas que crean o editan tickets: el observador
    no crea, no edita y no responde. Si intenta entrar por la URL recibe un
    403 con el enlace a su propio panel.
    """

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if getattr(user, "rol", None) == "observador":
            raise PermissionDenied(
                "El rol observador solo consulta: no puede crear ni editar tickets."
            )
        return view_func(request, *args, **kwargs)

    return _wrapped
