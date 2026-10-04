"""A qué vista entra cada cuenta.

Un solo sitio decide el destino. Antes el cálculo estaba repartido entre el
login, el portal y el aviso de bienvenida, y siempre terminaba en
`tickets:dashboard` para "cualquier otro rol": como esa vista es solo de
administrador, una cuenta con rol desconocido —o desactivada— entraba y
recibía un 403 Forbidden en `/panel/`. Aquí se resuelve una vez y siempre se
devuelve una vista que el rol puede abrir.
"""

from django.urls import reverse

# Rol -> vista de entrada. El orden no importa: cada rol tiene su propio caso.
_VISTA_POR_ROL = {
    "admin": "tickets:dashboard",
    "tecnico": "tickets:panel_tecnico",
    "usuario": "tickets:mi_panel",
    "observador": "tickets:obs_panel",
}

# Vista de reserva: `accounts:perfil` solo pide iniciar sesión, así que
# cualquier cuenta autenticada puede abrirla y tiene sus ajustes a un clic.
_VISTA_RESERVA = "accounts:perfil"


def landing_por_rol(user):
    """URL de entrada de `user`: la que su rol puede abrir, sin excepciones."""
    if user is None or not getattr(user, "is_authenticated", False):
        return reverse("tickets:portal")
    if not getattr(user, "activo", True):
        # Cuenta desactivada: el panel es solo de personal activo.
        return reverse(_VISTA_RESERVA)
    return reverse(_VISTA_POR_ROL.get(getattr(user, "rol", None), _VISTA_RESERVA))