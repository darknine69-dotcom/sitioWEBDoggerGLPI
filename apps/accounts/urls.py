from django.urls import path
from .views import StaffLoginView, StaffLogoutView, UserLoginView, UserRegisterView, ajustes_cuenta, cambiar_password, glpi_pull_perfil, glpi_push_avatar

app_name = "accounts"

urlpatterns = [
    path("login/", StaffLoginView.as_view(), name="login"),
    path("login/staff/", StaffLoginView.as_view(), name="login_staff"),
    path("login/usuario/", UserLoginView.as_view(), name="login_usuario"),
    path("registro/", UserRegisterView.as_view(), name="registro"),
    path("logout/", StaffLogoutView.as_view(), name="logout"),
    path("ajustes/", ajustes_cuenta, name="ajustes"),
    path("cambiar-password/", cambiar_password, name="cambiar_password"),
    path("glpi/pull-perfil/", glpi_pull_perfil, name="glpi_pull_perfil"),
    path("glpi/push-avatar/", glpi_push_avatar, name="glpi_push_avatar"),
]
