"""Registros navegables según las vistas y el alcance efectivo del usuario."""
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse

from apps.tickets.models import Categoria, ZonaObservador


def buscar_registros(user, query):
    if not user.is_authenticated or not user.is_active or user.rol not in ("admin", "tecnico", "usuario", "observador"):
        return []
    groups = []
    # El catálogo de categorías es una vista de lectura disponible a todos.
    categorias = Categoria.objects.filter(activo=True).filter(
        Q(nombre__icontains=query) | Q(grupo__icontains=query)
    ).order_by("grupo", "nombre")[:6]
    for categoria in categorias:
        ruta = "tickets:categorias_arbol" if user.rol in ("admin", "tecnico") else "tickets:categorias_publico"
        groups.append({"nombre": categoria.nombre, "descripcion": categoria.grupo, "categoria": "Categorías", "url": reverse(ruta) + "#buscar-categoria-" + str(categoria.pk), "icono": "i-folder"})
    if user.rol == "admin":
        # La lista de cuentas y su campo de búsqueda son exclusivos del admin.
        cuentas = get_user_model().objects.filter(Q(nombre__icontains=query) | Q(email__icontains=query)).order_by("nombre", "pk")[:6]
        for cuenta in cuentas:
            groups.append({"nombre": cuenta.nombre or cuenta.email, "descripcion": cuenta.get_rol_display(), "categoria": "Usuarios", "url": reverse("tickets:usuarios") + "?" + urlencode({"q": cuenta.email, "abrir": cuenta.pk}), "icono": "i-user"})
    if user.rol == "observador":
        for zona in ZonaObservador.objects.filter(observador=user, nombre__icontains=query).order_by("nombre")[:6]:
            groups.append({"nombre": zona.nombre, "descripcion": "Zona de seguimiento", "categoria": "Zonas", "url": reverse("tickets:obs_zona_detalle", args=[zona.pk]), "icono": "i-map-pin"})
    return groups
