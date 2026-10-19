# Zona: notificaciones por correo y emergentes (toggles del modal de creación).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0029_zonaobservador_version_sistema'),
    ]

    operations = [
        migrations.AddField(
            model_name='zonaobservador',
            name='notif_correo',
            field=models.BooleanField(db_column='NotifCorreo', default=True, verbose_name='Notificaciones por correo'),
        ),
        migrations.AddField(
            model_name='zonaobservador',
            name='notif_popup',
            field=models.BooleanField(db_column='NotifPopup', default=True, verbose_name='Notificaciones emergentes'),
        ),
    ]
