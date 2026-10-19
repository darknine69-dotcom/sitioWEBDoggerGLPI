# Zona con versión del sistema asociada (la define el admin al crearla).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0028_monitoreoauditoria_comentarios_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='zonaobservador',
            name='version_sistema',
            field=models.CharField(blank=True, db_column='VersionSistema', default='', max_length=30, verbose_name='Versión del sistema'),
        ),
    ]
