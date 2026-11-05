from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("notificaciones", "0007_notificacion_archivada_en"), ("tickets", "0042_tarea_diferida"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="AlertaOperativa", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("tipo", models.CharField(default="ans_vencido", max_length=30)),
            ("severidad", models.CharField(default="alta", max_length=16)),
            ("estado", models.CharField(choices=[("abierta", "Abierta"), ("reconocida", "Reconocida"), ("resuelta", "Resuelta")], default="abierta", max_length=16)),
            ("creada_en", models.DateTimeField(auto_now_add=True)),
            ("reconocida_en", models.DateTimeField(blank=True, null=True)),
            ("resuelta_en", models.DateTimeField(blank=True, null=True)),
            ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="alertas_operativas", to="tickets.ticket")),
            ("responsable", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="alertas_operativas", to=settings.AUTH_USER_MODEL)),
        ], options={"indexes": [models.Index(fields=["estado", "-creada_en"], name="alerta_estado_fecha_idx")], "constraints": [models.UniqueConstraint(fields=("ticket", "tipo"), name="uq_alerta_ticket_tipo")]}),
        migrations.CreateModel(name="HistorialAlerta", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("accion", models.CharField(max_length=24)),
            ("creada_en", models.DateTimeField(auto_now_add=True)),
            ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ("alerta", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="historial", to="notificaciones.alertaoperativa")),
        ], options={"ordering": ["-creada_en", "-pk"]}),
    ]
