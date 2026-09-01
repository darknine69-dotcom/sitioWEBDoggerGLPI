from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model

from .models import Categoria, Ticket, TicketComentario
from .sugerencia_categoria import sugerir_categoria

User = get_user_model()

ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
    "application/pdf",
}


def categorias_agrupadas():
    """
    Choices agrupadas por categoría principal para <optgroup>:
    [( 'Grupo', [Categoria, ...] ), ...]
    """
    cats = Categoria.objects.filter(activo=True).order_by("grupo", "nombre")
    grupos: dict[str, list[Categoria]] = {}
    for c in cats:
        grupos.setdefault(c.grupo, []).append(c)
    return [(grupo, subs) for grupo, subs in grupos.items()]


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(d, initial) for d in data]
        return [single(data, initial)]


class GroupedModelChoiceIterator(forms.models.ModelChoiceIterator):
    """Iterador que genera <optgroup> a partir de choices agrupadas."""

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)
        for grupo, subs in categorias_agrupadas():
            yield (grupo, [self.choice(sub) for sub in subs])


class GroupedCategoriaChoiceField(forms.ModelChoiceField):
    iterator = GroupedModelChoiceIterator

    def label_from_instance(self, obj):
        return obj.nombre


def _campo_categoria(**kwargs):
    campo = GroupedCategoriaChoiceField(
        queryset=Categoria.objects.filter(activo=True), **kwargs
    )
    return campo


class TicketForm(forms.ModelForm):
    adjuntos = MultipleFileField(
        required=False,
        label="Capturas / archivos",
        help_text="PNG, JPG, WEBP, GIF o PDF · max. 5 · 8 MB c/u",
    )

    class Meta:
        model = Ticket
        fields = [
            "titulo",
            "categoria",
            "descripcion",
            "solicitante_nombre",
            "solicitante_email",
            "solicitante_punto",
        ]
        widgets = {
            "titulo": forms.TextInput(
                attrs={"placeholder": "Ej: POS-FE no imprime / SIESA Access lento", "maxlength": 150}
            ),
            "descripcion": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Describe el problema. Incluye punto de venta, PC (ej. PC-P1 PC5) o modulo SIESA si aplica...",
                }
            ),
            "solicitante_nombre": forms.TextInput(attrs={"placeholder": "Tu nombre completo"}),
            "solicitante_email": forms.EmailInput(attrs={"placeholder": "correo@dogger.com.co"}),
            "solicitante_punto": forms.TextInput(
                attrs={"placeholder": "Ej: Envigado Caja 3 · PC-P1 · Server Principal"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"] = _campo_categoria(required=False)
        self.fields["categoria"].empty_label = "— Selecciona categoria —"
        self.fields["solicitante_email"].required = False
        self.fields["solicitante_punto"].required = False

    def clean_adjuntos(self):
        files = self.cleaned_data.get("adjuntos") or []
        files = [f for f in files if f]
        max_files = settings.DOGGER.get("max_adjuntos", 5)
        max_mb = settings.DOGGER.get("max_adjunto_mb", 8)
        max_bytes = max_mb * 1024 * 1024
        if len(files) > max_files:
            raise forms.ValidationError(f"Maximo {max_files} archivos por ticket.")
        for f in files:
            if f.content_type not in ALLOWED_CONTENT_TYPES:
                raise forms.ValidationError(
                    f"Tipo no permitido: {f.name}. Solo imagenes y PDF."
                )
            if f.size > max_bytes:
                raise forms.ValidationError(f'"{f.name}" supera el limite de {max_mb} MB.')
        return files

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("categoria"):
            sugerida = sugerir_categoria(
                titulo=cleaned.get("titulo", ""),
                descripcion=cleaned.get("descripcion", ""),
            )
            if sugerida:
                cleaned["categoria"] = sugerida
        return cleaned

    def save(self, commit=True):
        ticket = super().save(commit=False)
        # Auto-asignar prioridad según ANS de la categoría
        cat = ticket.categoria
        if cat and hasattr(cat, "prioridad_default"):
            ticket.prioridad = cat.prioridad_default
        if commit:
            ticket.save()
        return ticket


class TicketEdicionForm(forms.ModelForm):
    """Edición del ticket por su solicitante mientras está abierto."""

    class Meta:
        model = Ticket
        fields = ["titulo", "prioridad", "categoria", "descripcion", "solicitante_punto"]
        widgets = {
            "titulo": forms.TextInput(attrs={"maxlength": 150}),
            "descripcion": forms.Textarea(attrs={"rows": 4}),
            "solicitante_punto": forms.TextInput(
                attrs={"placeholder": "Ej: Envigado Caja 3 · PC-P1 · Server Principal"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"] = _campo_categoria(required=False)
        self.fields["categoria"].empty_label = "— Selecciona categoria —"


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["grupo", "nombre", "prioridad_default", "ans_horas", "glpi_category_id", "tecnico_default"]
        widgets = {
            "grupo": forms.TextInput(
                attrs={"list": "lista-grupos", "placeholder": "Ej: SIESA ERP"}
            ),
            "nombre": forms.TextInput(attrs={"placeholder": "Ej: POS-FE"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tecnico_default"].queryset = User.objects.filter(
            activo=True, rol__in=["admin", "tecnico"]
        ).order_by("nombre")
        self.fields["tecnico_default"].required = False
        self.fields["glpi_category_id"].required = False


class UsuarioPanelForm(forms.Form):
    """Alta/edición de cuentas desde el panel del administrador."""

    ROL_CHOICES = [
        ("usuario", "Usuario"),
        ("tecnico", "Técnico"),
        ("admin", "Administrador"),
    ]

    nombre = forms.CharField(max_length=100)
    email = forms.EmailField()
    rol = forms.ChoiceField(choices=ROL_CHOICES)
    glpi_user_id = forms.IntegerField(required=False, min_value=1)
    activo = forms.BooleanField(required=False, initial=True)
    password1 = forms.CharField(
        required=False,
        widget=forms.PasswordInput,
        label="Contraseña (vacía = sin cambios)",
    )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class ConsultaTicketForm(forms.Form):
    codigo = forms.CharField(
        max_length=12,
        label="Codigo del ticket",
        widget=forms.TextInput(attrs={"placeholder": "HD-0001", "style": "text-transform:uppercase"}),
    )


class ComentarioForm(forms.ModelForm):
    class Meta:
        model = TicketComentario
        fields = ["comentario", "es_interno"]
        widgets = {
            "comentario": forms.Textarea(attrs={"rows": 3, "placeholder": "Escribe un seguimiento..."}),
        }


class AsignarTecnicoForm(forms.Form):
    tecnico = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="— Sin asignar —",
        label="Tecnico asignado",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tecnico"].queryset = User.objects.filter(
            activo=True, rol__in=["admin", "tecnico"]
        ).order_by("nombre")
