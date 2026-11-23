"""Cabeceras de seguridad que Django no pone solo.

Referrer-Policy evita filtrar URLs internas por referer y
Permissions-Policy cierra cámara/micrófono/geolocalización que la app
nunca usa.
"""


class CierreInactividadMiddleware:
    """Expira la sesión sin contar solicitudes automáticas como actividad."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        import time
        from django.contrib.auth import logout
        from django.http import JsonResponse
        from django.shortcuts import redirect

        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            prefs = user.preferencias_notificaciones or {}
            if prefs.get("cierre_inactividad") is True:
                minutos = prefs.get("cierre_inactividad_minutos", 30)
                if type(minutos) is not int or not 1 <= minutos <= 480:
                    minutos = 30
                ahora = int(time.time())
                anterior = request.session.get("ultima_actividad_usuario")
                if isinstance(anterior, (int, float)) and ahora - anterior >= minutos * 60:
                    logout(request)
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return JsonResponse({"error": "sesion_expirada"}, status=401)
                    return redirect("accounts:login")
                if anterior is None:
                    request.session["ultima_actividad_usuario"] = ahora
            else:
                request.session.pop("ultima_actividad_usuario", None)
        return self.get_response(request)


class RestriccionModulosMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        from django.http import HttpResponseForbidden
        from apps.accounts.modulos import modulo_ruta, restringidos

        if request.user.is_authenticated:
            modulo = modulo_ruta(request.resolver_match)
            if modulo and modulo in restringidos(request.user):
                return HttpResponseForbidden("No tienes acceso a este módulo. Contacta al administrador.")
        return None


class SeguridadHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        respuesta.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        respuesta.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        return respuesta


class RolSincronizadoMiddleware:
    """Si el admin cambió tu rol, no te deja varado en la página vieja.

    Guarda el rol en la sesión al navegar; si difiere del de la BD (el
    administrador lo movió de grupo en otra pestaña), actualiza la sesión,
    avisa y te lleva a la página de tu rol actual. Solo en navegaciones
    GET normales: nunca interrumpe AJAX, POST ni estáticos.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if (
            getattr(usuario, "is_authenticated", False)
            and request.method == "GET"
            and request.headers.get("x-requested-with") != "XMLHttpRequest"
            and not request.path.startswith(("/static/", "/media/", "/cuenta/logout"))
        ):
            rol_actual = getattr(usuario, "rol", "")
            rol_sesion = request.session.get("rol_sesion")
            if rol_sesion is None:
                request.session["rol_sesion"] = rol_actual
            elif rol_sesion != rol_actual:
                from django.contrib import messages

                from apps.accounts.routing import landing_por_rol

                request.session["rol_sesion"] = rol_actual
                try:
                    etiqueta = usuario.get_rol_display()
                except Exception:
                    etiqueta = rol_actual
                messages.info(
                    request,
                    f"Tu rol cambió a {etiqueta}: te llevamos a tu página.",
                )
                from django.shortcuts import redirect

                return redirect(landing_por_rol(usuario))
        return self.get_response(request)
