from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm

from .models import ResetPasswordToken

User = get_user_model()


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="Correo corporativo",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "correo@dogger.com.co",
                "autocomplete": "username",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(
            attrs={"placeholder": "••••••••", "autocomplete": "current-password"}
        ),
    )
    remember_me = forms.BooleanField(
        label="Recordarme",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "checkbox-recordar"}),
    )

    error_messages = {
        "invalid_login": "Correo o contraseña incorrectos.",
        "inactive": "Esta cuenta está desactivada.",
    }


class UserRegisterForm(forms.Form):
    nombre = forms.CharField(
        label="Nombre completo",
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "Tu nombre completo", "autofocus": True}),
    )
    email = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(attrs={"placeholder": "usuario@correo.com"}),
    )
    genero = forms.ChoiceField(
        label="Género",
        choices=User.Genero.choices,
        widget=forms.Select,
    )
    password1 = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••"}),
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={"placeholder": "Repite tu contraseña"}),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Este correo ya está registrado. Intenta iniciar sesión.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        return cleaned_data

    def save(self):
        user = User.objects.create_user(
            email=self.cleaned_data["email"],
            nombre=self.cleaned_data["nombre"],
            genero=self.cleaned_data["genero"],
            password=self.cleaned_data["password1"],
            rol="usuario",
            is_staff=False,
        )
        return user


class PerfilForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["nombre", "email", "telefono", "avatar"]
        widgets = {
            "nombre": forms.TextInput(attrs={"placeholder": "Tu nombre completo"}),
            "email": forms.EmailInput(attrs={"placeholder": "correo@dogger.com.co"}),
            "telefono": forms.TextInput(attrs={"placeholder": "Ej: 310 371 6129"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Este correo ya está en uso por otra cuenta.")
        return email


class CambiarPasswordForm(forms.Form):
    password_actual = forms.CharField(
        label="Contraseña actual",
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••", "autocomplete": "current-password"}),
    )
    password_nueva = forms.CharField(
        label="Nueva contraseña",
        widget=forms.PasswordInput(attrs={"placeholder": "Mínimo 8 caracteres"}),
        min_length=8,
    )
    password_confirmar = forms.CharField(
        label="Confirmar nueva contraseña",
        widget=forms.PasswordInput(attrs={"placeholder": "Repite la nueva contraseña"}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password_actual(self):
        password = self.cleaned_data.get("password_actual")
        if not self.user.check_password(password):
            raise forms.ValidationError("La contraseña actual es incorrecta.")
        return password

    def clean(self):
        cleaned_data = super().clean()
        nueva = cleaned_data.get("password_nueva")
        confirmar = cleaned_data.get("password_confirmar")
        if nueva and confirmar and nueva != confirmar:
            self.add_error("password_confirmar", "Las contraseñas no coinciden.")
        return cleaned_data

    def save(self):
        self.user.set_password(self.cleaned_data["password_nueva"])
        self.user.save()
        return self.user


class SolicitarResetForm(forms.Form):
    email = forms.EmailField(
        label="Correo corporativo",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "correo@dogger.com.co",
                "autocomplete": "username",
                "autofocus": True,
            }
        ),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        # No revelar si la cuenta existe o no (seguridad).
        self.usuario = User.objects.filter(email__iexact=email, activo=True).first()
        return email


class RestablecerPasswordForm(forms.Form):
    email = forms.EmailField(
        label="Correo corporativo",
        widget=forms.EmailInput(
            attrs={"placeholder": "correo@dogger.com.co", "autocomplete": "username"}
        ),
    )
    codigo = forms.CharField(
        label="Código de verificación",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={"placeholder": "000000", "autocomplete": "one-time-code", "inputmode": "numeric"}
        ),
    )
    password_nueva = forms.CharField(
        label="Nueva contraseña",
        widget=forms.PasswordInput(attrs={"placeholder": "Mínimo 8 caracteres", "autocomplete": "new-password"}),
        min_length=8,
    )
    password_confirmar = forms.CharField(
        label="Confirmar nueva contraseña",
        widget=forms.PasswordInput(attrs={"placeholder": "Repite la nueva contraseña", "autocomplete": "new-password"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email", "").strip().lower()
        self.usuario = User.objects.filter(email__iexact=email).first()

        if self.usuario is None:
            self.add_error("codigo", "El código no es válido para este correo.")
            return cleaned_data

        token = ResetPasswordToken.objects.filter(
            usuario=self.usuario, codigo=cleaned_data.get("codigo", ""), usado=False
        ).first()
        if not token:
            self.add_error("codigo", "El código es incorrecto.")
            return cleaned_data
        if token.expirado:
            token.delete()
            self.add_error("codigo", "El código ha expirado. Solicita uno nuevo.")
            return cleaned_data
        self.token = token

        password_nueva = cleaned_data.get("password_nueva")
        password_confirmar = cleaned_data.get("password_confirmar")
        if password_nueva and password_confirmar and password_nueva != password_confirmar:
            self.add_error("password_confirmar", "Las contraseñas no coinciden.")
        return cleaned_data

    def save(self):
        self.token.usado = True
        self.token.save(update_fields=["usado"])
        self.usuario.set_password(self.cleaned_data["password_nueva"])
        self.usuario.save(update_fields=["password"])
        return self.usuario
