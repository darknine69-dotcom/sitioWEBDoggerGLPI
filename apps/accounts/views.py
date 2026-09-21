from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import redirect, render, reverse
from django.urls import reverse_lazy
from django.views import View
from django.views.decorators.http import require_POST
import logging

from .forms import (
    CambiarPasswordForzadoForm,
    CambiarPasswordForm,
    CodigoResetForm,
    LoginForm,
    PerfilForm,
    SolicitarResetForm,
    UserRegisterForm,
)
from .models import ResetPasswordToken, Usuario

logger = logging.getLogger(__name__)

User = Usuario


def _glpi_available():
    from django.conf import settings
    cfg = getattr(settings, "GLPI", {}) or {}
    return bool(cfg.get("enabled") and cfg.get("base_url"))


def _glpi_base_url():
    from django.conf import settings
    cfg = getattr(settings, "GLPI", {}) or {}
    url = cfg.get("base_url") or ""
    return url.split("/apirest.php")[0].rstrip("/") if url else ""


class BaseRoleLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True
    role_name = "staff"
    role_label = "Staff"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["login_role"] = self.role_label
        context["login_role_slug"] = self.role_name
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        if not form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(0)
        else:
            self.request.session.set_expiry(1209600)
        return response

    def get_success_url(self):
        user = self.request.user
        rol = getattr(user, "rol", None)
        if rol == "usuario":
            return reverse_lazy("tickets:mi_panel")
        if rol == "tecnico":
            return reverse_lazy("tickets:panel_tecnico")
        return reverse_lazy("tickets:dashboard")


class StaffLoginView(BaseRoleLoginView):
    role_name = "staff"
    role_label = "Staff"


class UserLoginView(BaseRoleLoginView):
    role_name = "usuario"
    role_label = "Usuario"


class UserRegisterView(View):
    template_name = "accounts/register.html"

    def get(self, request, *args, **kwargs):
        form = UserRegisterForm()
        return self.render_view(request, form)

    def post(self, request, *args, **kwargs):
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("tickets:mi_panel")
        return self.render_view(request, form)

    def render_view(self, request, form):
        return render(request, self.template_name, {"form": form, "login_role": "Usuario", "login_role_slug": "usuario"})


class StaffLogoutView(View):
    def post(self, request):
        logout(request)
        return redirect("tickets:portal")

    def get(self, request):
        logout(request)
        return redirect("tickets:portal")


@login_required
def ajustes_cuenta(request):
    user = request.user
    glpi_enabled = _glpi_available() and bool(getattr(user, "glpi_user_id", None))

    if request.method == "POST":
        es_staff = bool(getattr(user, "es_staff_helpdesk", False))
        if es_staff and request.POST.get("borrar_glpi_al_eliminar") in ("1", "on", "true"):
            user.borrar_glpi_al_eliminar = True
        elif es_staff:
            user.borrar_glpi_al_eliminar = False
        form = PerfilForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            # Sync Dogger → GLPI: perfil + avatar
            if glpi_enabled:
                try:
                    from apps.tickets.services.glpi_client import sync_perfil_to_glpi, sync_avatar_to_glpi
                    sync_perfil_to_glpi(user)
                    avatar_result = sync_avatar_to_glpi(user)
                    if avatar_result and not avatar_result.get("ok"):
                        messages.warning(request, f"Foto GLPI: {avatar_result.get('detalle', '')}")
                except Exception:
                    pass
            messages.success(request, "Perfil actualizado correctamente.")
            return redirect(reverse("accounts:ajustes") + "#perfil")
    else:
        form = PerfilForm(instance=user)

    return render(request, "accounts/ajustes.html", {
        "form": form,
        "glpi_enabled": glpi_enabled,
        "glpi_base_url": _glpi_base_url(),
    })


@login_required
def glpi_pull_perfil(request):
    """Descarga perfil y foto desde GLPI al usuario local."""
    user = request.user
    if not getattr(user, "glpi_user_id", None):
        messages.warning(request, "Tu cuenta no está vinculada a GLPI.")
        return redirect("accounts:ajustes")

    try:
        from apps.tickets.services.glpi_client import sync_perfil_from_glpi, sync_avatar_from_glpi
        perfil_ok = sync_perfil_from_glpi(user)
        avatar_ok = sync_avatar_from_glpi(user)
        if perfil_ok or avatar_ok:
            messages.success(request, "Datos actualizados desde GLPI correctamente.")
        else:
            messages.info(request, "No se encontraron cambios en GLPI.")
    except Exception as exc:
        messages.error(request, f"Error al sincronizar con GLPI: {exc}")

    return redirect("accounts:ajustes")


@login_required
def glpi_push_avatar(request):
    """Sube el avatar local a GLPI."""
    user = request.user
    if not getattr(user, "glpi_user_id", None):
        messages.warning(request, "Tu cuenta no está vinculada a GLPI.")
        return redirect("accounts:ajustes")

    if not user.avatar:
        messages.warning(request, "Primero sube una foto de perfil.")
        return redirect("accounts:ajustes")

    try:
        from apps.tickets.services.glpi_client import sync_avatar_to_glpi
        ok = sync_avatar_to_glpi(user)
        if ok:
            messages.success(request, "Foto subida a GLPI correctamente.")
        else:
            messages.error(request, "No se pudo subir la foto a GLPI.")
    except Exception as exc:
        messages.error(request, f"Error al subir foto a GLPI: {exc}")

    return redirect("accounts:ajustes")


@login_required
def cambiar_password(request):
    """Cambio de contraseña. El formulario vive en ajustes.html (pestaña Contraseña),
    por lo que ambas rutas GET/POST de esta vista redirigen siempre a ajustes."""
    if request.method == "POST":
        form = CambiarPasswordForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, request.user)
            request.session["pwd_cambiada_ok"] = True
        else:
            for err in form.non_field_errors():
                messages.error(request, err)
            for field, errs in form.errors.items():
                prefix = f"{form.fields[field].label}: " if field != "__all__" and field in form.fields else ""
                for err in errs:
                    messages.error(request, f"{prefix}{err}")
    return redirect(reverse("accounts:ajustes") + "#password")


def solicitar_reset(request):
    """Paso 1 — el usuario recibe un código de 6 dígitos.

    Cuando el correo ya se conoce (el del login con ?email=, el del usuario
    autenticado o el de un intento previo), la pantalla NO pide el correo:
    solo muestra "Enviar código". Si viene con ?manual= se vuelve a pedir.
    """
    if request.GET.get("manual"):
        pre = ""
    else:
        pre = (
            (request.GET.get("email") or "").strip()
            or (request.user.email if request.user.is_authenticated else "")
            or request.session.get("reset_pwd_email", "")
        )
    correo_fijado = bool(pre)
    correo_fijado_mostrado = _enmascarar_correo(pre) if correo_fijado else ""

    if request.method == "POST":
        form = SolicitarResetForm(request.POST)
        if correo_fijado:
            form.fields["email"].widget.attrs["readonly"] = True
        if form.is_valid():
            usuario = form.usuario
            if usuario is None:
                # No revelar si la cuenta existe: mismo mensaje general.
                messages.success(request, "Si el correo está registrado, recibirás un código.")
                return redirect("accounts:login")
            try:
                token = ResetPasswordToken.generar(usuario)
                request.session["reset_pwd_email"] = usuario.email
                _enviar_codigo_reset(request, usuario, token.codigo)
            except Exception as exc:
                logger.exception("Error enviando código de reset a %s", usuario.email)
                messages.error(
                    request,
                    "No pudimos enviar el correo con el código. Revisa la configuración SMTP o inténtalo más tarde.",
                )
                return render(
                    request,
                    "accounts/reset_solicitar.html",
                    {
                        "form": form,
                        "correo_fijado": correo_fijado,
                        "correo_fijado_mostrado": correo_fijado_mostrado,
                    },
                )
            messages.success(
                request,
                "Te enviamos un código de verificación a tu correo (revisa también el spam).",
            )
            return redirect(reverse("accounts:restablecer_password"))
        return render(
            request,
            "accounts/reset_solicitar.html",
            {
                "form": form,
                "correo_fijado": correo_fijado,
                "correo_fijado_mostrado": correo_fijado_mostrado,
            },
        )

    form = SolicitarResetForm(initial={"email": pre})
    if correo_fijado:
        form.fields["email"].widget.attrs["readonly"] = True
    return render(
        request,
        "accounts/reset_solicitar.html",
        {
            "form": form,
            "correo_fijado": correo_fijado,
            "correo_fijado_mostrado": correo_fijado_mostrado,
        },
    )


def restablecer_password(request):
    """Paso 2 — solo se ingresa el código; al validarlo se inicia sesión
    y se fuerza el cambio de contraseña con una ventana emergente."""
    email = request.session.get("reset_pwd_email")
    if not email:
        messages.info(request, "Primero solicita un código de verificación.")
        return redirect("accounts:reset_solicitar")

    correo_mascara = _enmascarar_correo(email)

    if request.method == "POST":
        form = CodigoResetForm(request.POST)
        if form.is_valid():
            codigo = form.cleaned_data["codigo"]
            usuario = User.objects.filter(email__iexact=email, activo=True).first()
            if usuario is None:
                messages.error(request, "El código no es válido para este correo.")
                request.session.pop("reset_pwd_email", None)
                return redirect("accounts:reset_solicitar")

            token = ResetPasswordToken.objects.filter(
                usuario=usuario, codigo=codigo, usado=False
            ).first()
            if not token:
                form.add_error("codigo", "El código es incorrecto.")
                return render(
                    request,
                    "accounts/reset_confirmar.html",
                    {"form": form, "correo_mascara": correo_mascara},
                )
            if token.expirado:
                token.delete()
                form.add_error("codigo", "El código ha expirado. Solicita uno nuevo.")
                return render(
                    request,
                    "accounts/reset_confirmar.html",
                    {"form": form, "correo_mascara": correo_mascara},
                )

            # El código es válido: hábilitalo y fuerza un cambio de contraseña
            token.usado = True
            token.save(update_fields=["usado"])
            usuario.set_unusable_password()
            usuario.save(update_fields=["password"])
            login(request, usuario)
            request.session.pop("reset_pwd_email", None)
            request.session["force_password_change"] = True
            return redirect(_landing_por_rol(usuario))

        return render(
            request,
            "accounts/reset_confirmar.html",
            {"form": form, "correo_mascara": correo_mascara},
        )

    return render(
        request,
        "accounts/reset_confirmar.html",
        {"form": CodigoResetForm(), "correo_mascara": correo_mascara},
    )


def _enmascarar_correo(email):
    """Muestra el correo casi completo (solo el dominio), suficiente para que
    el usuario confirme a qué cuenta se envió el código sin que se edite."""
    local, sep, dominio = email.partition("@")
    if not sep:
        return email
    oculto = f"{local[:2]}…" if len(local) > 2 else local
    return f"{oculto}@{dominio}"


def _enviar_codigo_reset(request, usuario, codigo):
    """Envía el correo del código con la plantilla HTML corporativa de Dogger."""
    from django.template.loader import render_to_string
    from django.templatetags.static import static

    texto_plano = (
        f"Hola {usuario.nombre}:\n\n"
        f"Tu código para restablecer la contraseña en Dogger HelpDesk es: {codigo}\n\n"
        "Este código es válido por 30 minutos.\n"
        "Si no solicitaste este cambio, ignora este mensaje."
    )
    html = render_to_string(
        "accounts/email_codigo_reset.html",
        {
            "usuario": usuario,
            "codigo": codigo,
            "logo_url": request.build_absolute_uri(static("images/dogger-logo.png")),
            "login_url": request.build_absolute_uri(reverse("accounts:login")),
        },
    )
    send_mail(
        "Dogger HelpDesk — Restablece tu contraseña",
        texto_plano,
        settings.DEFAULT_FROM_EMAIL,
        [usuario.email],
        html_message=html,
    )


def _landing_por_rol(user):
    rol = getattr(user, "rol", None)
    if rol == "usuario":
        return reverse("tickets:mi_panel")
    if rol == "tecnico":
        return reverse("tickets:panel_tecnico")
    return reverse("tickets:dashboard")


@login_required
def cambiar_password_forzado(request):
    """Vista que procesa el modal 'Debes actualizar tu contraseña'."""
    if not request.session.get("force_password_change"):
        return redirect(_landing_por_rol(request.user))

    if request.method == "POST":
        form = CambiarPasswordForzadoForm(request.POST)
        if form.is_valid():
            request.user.set_password(form.cleaned_data["password_nueva"])
            request.user.save(update_fields=["password"])
            update_session_auth_hash(request, request.user)
            request.session.pop("force_password_change", None)
            request.session.pop("force_password_error", None)
            request.session["pwd_cambiada_ok"] = True
            return redirect(_landing_por_rol(request.user))

        error_msg = next(
            (msg for msgs in form.errors.values() for msg in msgs),
            "No se pudo actualizar la contraseña.",
        )
        request.session["force_password_error"] = error_msg
        messages.error(request, "Revisa los errores en la ventana e inténtalo de nuevo.")
    return redirect(_landing_por_rol(request.user))


@require_POST
def descartar_aviso(request):
    """Cierra el aviso emergente 'contraseña cambiada' para no volver a mostrarlo."""
    request.session.pop("pwd_cambiada_ok", None)
    return JsonResponse({"ok": True})
