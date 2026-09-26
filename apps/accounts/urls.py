from django.urls import path
from .views import (
    StaffLoginView,
    StaffLogoutView,
    UserLoginView,
    UserRegisterView,
    ajustes_cuenta,
    cambiar_password,
    cambiar_password_forzado,
    descartar_aviso,
    glpi_pull_perfil,
    glpi_push_avatar,
    perfil_usuario,
    restablecer_password,
    solicitar_reset,
)

app_name = "accounts"

urlpatterns = [
    path("login/", StaffLoginView.as_view(), name="login"),
    path("login/staff/", StaffLoginView.as_view(), name="login_staff"),
    path("login/usuario/", UserLoginView.as_view(), name="login_usuario"),
    path("registro/", UserRegisterView.as_view(), name="registro"),
    path("logout/", StaffLogoutView.as_view(), name="logout"),
    path("ajustes/", ajustes_cuenta, name="ajustes"),
    path("perfil/", perfil_usuario, name="perfil"),
    path("cambiar-password/", cambiar_password, name="cambiar_password"),
    path("cambiar-password-forzado/", cambiar_password_forzado, name="cambiar_password_forzado"),
    path("descartar-aviso/", descartar_aviso, name="descartar_aviso"),
    path("reset/solicitar/", solicitar_reset, name="reset_solicitar"),
    path("reset/confirmar/", restablecer_password, name="restablecer_password"),
    path("glpi/pull-perfil/", glpi_pull_perfil, name="glpi_pull_perfil"),
    path("glpi/push-avatar/", glpi_push_avatar, name="glpi_push_avatar"),
]
