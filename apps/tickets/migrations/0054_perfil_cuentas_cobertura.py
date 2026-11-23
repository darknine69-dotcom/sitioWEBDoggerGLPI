from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0053_ticket_asignacion_manual_protegida"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="perfilautoasignacion",
            name="cuentas_cobertura",
            field=models.ManyToManyField(blank=True, related_name="perfiles_cobertura_autoasignacion", to=settings.AUTH_USER_MODEL),
        ),
    ]
