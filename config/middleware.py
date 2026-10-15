"""Cabeceras de seguridad que Django no pone solo.

Referrer-Policy evita filtrar URLs internas por referer y
Permissions-Policy cierra cámara/micrófono/geolocalización que la app
nunca usa.
"""


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
