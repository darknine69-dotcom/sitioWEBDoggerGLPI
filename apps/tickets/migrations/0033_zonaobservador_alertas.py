# Zona: interruptor de alertas ANS (resalta urgentes abiertos en la tarjeta).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0032_zonaobservador_perms'),
    ]

    operations = [
        migrations.AddField(
            model_name='zonaobservador',
            name='alertas_ans',
            field=models.BooleanField(db_column='AlertasAns', default=False, verbose_name='Alertas ANS'),
        ),
    ]
