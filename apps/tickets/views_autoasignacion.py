"""Configuración de autoasignación para administradores activos."""
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import redirect, render

from .models import Categoria, ConfiguracionAutoasignacion, DecisionAutoasignacion, PerfilAutoasignacion, Punto, Ticket


class ReglasForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionAutoasignacion
        fields = ("peso_urgente", "peso_alta", "peso_media", "peso_baja", "margen_puntos")
        labels = {"margen_puntos": "Margen de preferencia (puntos porcentuales)"}

    def clean(self):
        datos = super().clean()
        for campo in ("peso_urgente", "peso_alta", "peso_media", "peso_baja"):
            if datos.get(campo) is not None and datos[campo] < 1:
                self.add_error(campo, "El peso debe ser mayor que cero.")
        if datos.get("margen_puntos") is not None and datos["margen_puntos"] > 100:
            self.add_error("margen_puntos", "El margen no puede superar 100 puntos porcentuales.")
        return datos


class PerfilForm(forms.ModelForm):
    tecnico = forms.ModelChoiceField(queryset=get_user_model().objects.none(), label="Técnico o administrador")
    cuentas_cobertura = forms.ModelMultipleChoiceField(queryset=get_user_model().objects.none(), required=False, label="Cuentas y direcciones registradas")

    class Meta:
        model = PerfilAutoasignacion
        fields = ("tecnico", "habilitado", "capacidad", "cobertura_general", "puntos_cobertura", "cuentas_cobertura", "categorias")
        labels = {"capacidad": "Capacidad máxima en puntos", "puntos_cobertura": "Puntos del catálogo", "categorias": "Categorías y especialidades"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        elegibles = Q(rol__in=("admin", "tecnico"), activo=True, is_active=True)
        if self.instance.pk and self.instance.tecnico_id:
            elegibles |= Q(pk=self.instance.tecnico_id)
        self.fields["tecnico"].queryset = get_user_model().objects.filter(elegibles).order_by("nombre")
        categorias = Q(activo=True)
        puntos = Q(activo=True)
        if self.instance.pk:
            # Las opciones inactivas ya guardadas deben seguir visibles para
            # evitar que una edición convierta una especialidad en "todas".
            categorias |= Q(pk__in=self.instance.categorias.values_list("pk", flat=True))
            puntos |= Q(pk__in=self.instance.puntos_cobertura.values_list("pk", flat=True))
        self.fields["categorias"].queryset = Categoria.objects.filter(categorias)
        self.fields["puntos_cobertura"].queryset = Punto.objects.filter(puntos)
        cuentas = Q(rol="usuario", activo=True, is_active=True)
        if self.instance.pk:
            cuentas |= Q(pk__in=self.instance.cuentas_cobertura.values_list("pk", flat=True))
        self.fields["cuentas_cobertura"].queryset = get_user_model().objects.filter(cuentas).order_by("nombre", "email")
        self.fields["cuentas_cobertura"].label_from_instance = lambda cuenta: f"{cuenta.nombre} · {cuenta.ubicacion or 'Sin dirección'} · {cuenta.email}"
        self.fields["cuentas_cobertura"].help_text = "Selecciona las cuentas registradas que puede atender el técnico."
        self.fields["categorias"].help_text = "Se muestran todas las categorías activas. Sin selección, el técnico atiende todas. Usa Ctrl o Cmd para seleccionar varias."
        self.fields["puntos_cobertura"].help_text = "También puedes seleccionar puntos del catálogo; con cobertura restringida elige al menos un punto o cuenta activa."

    def clean(self):
        datos = super().clean()
        if datos.get("capacidad") is not None and datos["capacidad"] < 1:
            self.add_error("capacidad", "La capacidad debe ser mayor que cero.")
        tecnico = datos.get("tecnico")
        if datos.get("habilitado") and tecnico and (not tecnico.activo or not tecnico.is_active or tecnico.rol not in ("admin", "tecnico")):
            self.add_error("habilitado", "La cuenta debe estar activa y tener rol técnico o administrador.")
        puntos = datos.get("puntos_cobertura")
        cuentas = datos.get("cuentas_cobertura")
        puntos_activos = puntos is not None and puntos.filter(activo=True).exists()
        cuentas_activas = cuentas is not None and cuentas.filter(rol="usuario", activo=True, is_active=True).exists()
        if datos.get("habilitado") and not datos.get("cobertura_general") and not (puntos_activos or cuentas_activas):
            self.add_error("puntos_cobertura", "Selecciona puntos o habilita cobertura general.")
        return datos


@login_required
def configuracion_autoasignacion(request):
    if not (request.user.is_active and request.user.activo and request.user.rol == "admin"):
        raise PermissionDenied
    config = ConfiguracionAutoasignacion.objects.filter(pk=1).first()
    reglas_form = ReglasForm(instance=config)
    editar_id = request.GET.get("tecnico", "")
    editar = PerfilAutoasignacion.objects.filter(tecnico_id=int(editar_id)).first() if editar_id.isdigit() else None
    perfil_form = PerfilForm(instance=editar)
    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "activar":
            if not request.user.is_superuser:
                raise PermissionDenied
            from django.db import connection
            if not connection.features.has_select_for_update:
                messages.error(request, "No se puede activar: la base de datos no admite el bloqueo requerido.")
                return redirect("tickets:configuracion_autoasignacion")
            with transaction.atomic():
                actual, _ = ConfiguracionAutoasignacion.objects.get_or_create(pk=1)
                actual = ConfiguracionAutoasignacion.objects.select_for_update().get(pk=actual.pk)
                actual.activa = True
                actual.save(update_fields=["activa"])
            messages.warning(request, "Motor activado. La concurrencia en SQL Server aún debe validarse; verifica los perfiles habilitados y su cobertura.")
            return redirect("tickets:configuracion_autoasignacion")
        if accion == "desactivar":
            with transaction.atomic():
                actual = ConfiguracionAutoasignacion.objects.select_for_update().filter(pk=1).first()
                if actual and actual.activa:
                    actual.activa = False
                    actual.save(update_fields=["activa"])
            messages.success(request, "Motor de autoasignación desactivado.")
            return redirect("tickets:configuracion_autoasignacion")
        if accion == "reglas":
            reglas_form = ReglasForm(request.POST, instance=config)
            if reglas_form.is_valid():
                with transaction.atomic():
                    actual, _ = ConfiguracionAutoasignacion.objects.get_or_create(pk=1)
                    actual = ConfiguracionAutoasignacion.objects.select_for_update().get(pk=actual.pk)
                    for campo in ReglasForm.Meta.fields:
                        setattr(actual, campo, reglas_form.cleaned_data[campo])
                    actual.save(update_fields=ReglasForm.Meta.fields)
                messages.success(request, "Reglas de distribución guardadas.")
                return redirect("tickets:configuracion_autoasignacion")
        elif accion == "perfil":
            tecnico_id = request.POST.get("tecnico", "")
            existente = PerfilAutoasignacion.objects.filter(tecnico_id=int(tecnico_id)).first() if tecnico_id.isdigit() else None
            perfil_form = PerfilForm(request.POST, instance=existente)
            if perfil_form.is_valid():
                with transaction.atomic():
                    actual, _ = ConfiguracionAutoasignacion.objects.get_or_create(pk=1)
                    ConfiguracionAutoasignacion.objects.select_for_update().get(pk=actual.pk)
                    tecnico = perfil_form.cleaned_data["tecnico"]
                    perfil, _ = PerfilAutoasignacion.objects.select_for_update().get_or_create(tecnico=tecnico)
                    for campo in ("habilitado", "capacidad", "cobertura_general"):
                        setattr(perfil, campo, perfil_form.cleaned_data[campo])
                    perfil.save(update_fields=["habilitado", "capacidad", "cobertura_general"])
                    perfil.categorias.set(perfil_form.cleaned_data["categorias"])
                    perfil.puntos_cobertura.set(perfil_form.cleaned_data["puntos_cobertura"])
                    perfil.cuentas_cobertura.set(perfil_form.cleaned_data["cuentas_cobertura"])
                messages.success(request, "Perfil de asignación guardado.")
                return redirect("tickets:configuracion_autoasignacion")
        else:
            raise PermissionDenied

    pesos = {p: getattr(config, "peso_" + p, defecto) for p, defecto in (("urgente", 5), ("alta", 3), ("media", 2), ("baja", 1))}
    cargas = {}
    for fila in Ticket.objects.filter(estado__in=(Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO), tecnico_asignado__isnull=False).values("tecnico_asignado_id", "prioridad").annotate(total=Count("pk")):
        tecnico = fila["tecnico_asignado_id"]
        if fila["prioridad"] not in pesos:
            cargas[tecnico] = None
        elif cargas.get(tecnico, 0) is not None:
            cargas[tecnico] = cargas.get(tecnico, 0) + fila["total"] * pesos[fila["prioridad"]]
    perfiles = list(PerfilAutoasignacion.objects.select_related("tecnico").prefetch_related("categorias", "puntos_cobertura", "cuentas_cobertura").order_by("tecnico__nombre"))
    for perfil in perfiles:
        perfil.carga_actual = cargas.get(perfil.tecnico_id, 0)
        perfil.ocupacion_actual = round(100 * perfil.carga_actual / perfil.capacidad, 1) if perfil.carga_actual is not None and perfil.capacidad else None
    cuentas_seleccionadas = {str(valor) for valor in (perfil_form["cuentas_cobertura"].value() or [])}
    cuentas_disponibles = list(perfil_form.fields["cuentas_cobertura"].queryset)
    for cuenta in cuentas_disponibles:
        cuenta.seleccionada_en_cobertura = str(cuenta.pk) in cuentas_seleccionadas
    return render(request, "tickets/configuracion_autoasignacion.html", {
        "config": config, "reglas_form": reglas_form, "perfil_form": perfil_form,
        "perfiles": perfiles, "cuentas_disponibles": cuentas_disponibles,
        "decisiones": DecisionAutoasignacion.objects.select_related("ticket", "tecnico")[:50],
    })
