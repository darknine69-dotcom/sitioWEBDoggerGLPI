from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("notificaciones", "0011_historialalerta_detalle"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="EntregaEscalamiento", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("creada_en", models.DateTimeField(auto_now_add=True)),
        ("alerta", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="escalamientos", to="notificaciones.alertaoperativa")),
        ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
    ], options={"constraints": [models.UniqueConstraint(fields=("alerta", "usuario"), name="uq_escalamiento_alerta_usuario")]})]
