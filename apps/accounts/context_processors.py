"""Contexto de la cuenta: atajos rápidos del botón X."""
from .atajos import para_usuario


def atajos(request):
    usuario = getattr(request, "user", None)
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return {}
    try:
        return {"atajos_rapidos": para_usuario(usuario)}
    except Exception:  # noqa: BLE001 - sin atajos no se rompe la página
        return {"atajos_rapidos": []}
