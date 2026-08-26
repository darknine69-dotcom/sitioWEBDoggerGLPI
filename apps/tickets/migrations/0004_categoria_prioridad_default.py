from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0003_categoria_tecnico_default_ticket_asignacion_automatica'),
    ]

    operations = [
        migrations.AddField(
            model_name='categoria',
            name='prioridad_default',
            field=models.CharField(
                choices=[('baja', 'Baja'), ('media', 'Media'), ('alta', 'Alta'), ('urgente', 'Urgente')],
                default='media',
                help_text='Prioridad que se asigna automáticamente según el ANS de esta categoría',
                max_length=20,
                verbose_name='Prioridad por defecto (ANS)',
            ),
        ),
    ]
