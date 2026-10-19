# Marca los mensajes escritos con el botón de «presionar al técnico», para
# que el monitoreo del técnico pueda contarlos y mostrarlos aparte.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0035_ticket_ans_alertado_en'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticketcomentario',
            name='es_presion',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Si está activo, el mensaje fue escrito desde el botón de '
                    'presionar al técnico (observador o punto de venta).'
                ),
                verbose_name='Mensaje de presión',
            ),
        ),
    ]
