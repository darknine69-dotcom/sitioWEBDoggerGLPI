from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.shortcuts import redirect, render, reverse
from django.urls import reverse_lazy
from django.views import View

from .forms import LoginForm, UserRegisterForm, PerfilForm, CambiarPasswordForm


def _glpi_available():
    from django.conf import settings
    cfg = getattr(settings, "GLPI", {}) or {}
    return bool(cfg.get("enabled") and cfg.get("base_url"))


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
        if getattr(user, "rol", None) == "usuario":
            return reverse_lazy("tickets:mi_panel")
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
            messages.success(request, "Contraseña cambiada correctamente.")
        else:
            for err in form.non_field_errors():
                messages.error(request, err)
            for field, errs in form.errors.items():
                prefix = f"{form.fields[field].label}: " if field != "__all__" and field in form.fields else ""
                for err in errs:
                    messages.error(request, f"{prefix}{err}")
    return redirect(reverse("accounts:ajustes") + "#password")
