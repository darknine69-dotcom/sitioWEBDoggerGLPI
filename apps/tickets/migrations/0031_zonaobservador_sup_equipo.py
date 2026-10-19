# Zona: Windows e IP del supervisor (se actualizan cuando actúa en su zona).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0030_zonaobservador_notifs'),
    ]

    operations = [
        migrations.AddField(
            model_name='zonaobservador',
            name='sup_ip',
            field=models.CharField(blank=True, db_column='SupIp', default='', max_length=45, verbose_name='IP del supervisor'),
        ),
        migrations.AddField(
            model_name='zonaobservador',
            name='sup_version',
            field=models.CharField(blank=True, db_column='SupVersion', default='', max_length=30, verbose_name='Windows del supervisor'),
        ),
    ]
