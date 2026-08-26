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
