# ANS: marca de cuándo se avisó por última vez de que un ticket iba a vencer.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0034_monitoreoauditoria_alertas'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='ans_alertado_en',
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='Aviso ANS enviado'),
        ),
    ]
