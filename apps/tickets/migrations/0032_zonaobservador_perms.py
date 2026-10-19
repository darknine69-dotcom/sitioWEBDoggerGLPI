# Zona: permisos exportar auditoría y consultar historial (lista con checkbox).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0031_zonaobservador_sup_equipo'),
    ]

    operations = [
        migrations.AddField(
            model_name='zonaobservador',
            name='perm_exportar',
            field=models.BooleanField(db_column='PermExportar', default=True, verbose_name='Exportar auditoría'),
        ),
        migrations.AddField(
            model_name='zonaobservador',
            name='perm_historial',
            field=models.BooleanField(db_column='PermHistorial', default=True, verbose_name='Consultar historial'),
        ),
    ]
