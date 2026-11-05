from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def reservar_existentes(apps, schema_editor):
    Aviso = apps.get_model("notificaciones", "Notificacion")
    Clave = apps.get_model("notificaciones", "ClaveNotificacion")
    db = schema_editor.connection.alias
    for pk, usuario_id, clave in Aviso.objects.using(db).exclude(clave="").order_by("pk").values_list("pk", "usuario_id", "clave").iterator():
        Clave.objects.using(db).get_or_create(usuario_id=usuario_id, clave=clave, defaults={"notificacion_id": pk})


class Migration(migrations.Migration):
    dependencies = [("notificaciones", "0005_notificacion_ix_notif_usr_fecha"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="ClaveNotificacion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("clave", models.CharField(max_length=140)),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ("notificacion", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="reserva_clave", to="notificaciones.notificacion")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("usuario", "clave"), name="uq_notif_usuario_clave")]},
        ),
        migrations.RunPython(reservar_existentes, migrations.RunPython.noop),
    ]
