# Auditoría: nueva acción "Alertas ANS" (solo catálogo de choices).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0033_zonaobservador_alertas'),
    ]

    operations = [
        migrations.AlterField(
            model_name='monitoreoauditoria',
            name='accion',
            field=models.CharField(choices=[('crear_zona', 'Zona creada'), ('renombrar_zona', 'Zona renombrada'), ('eliminar_zona', 'Zona eliminada'), ('agregar_miembro', 'Cuenta agregada a zona'), ('quitar_miembro', 'Cuenta sacada de zona'), ('asignar_punto', 'Punto asignado'), ('quitar_punto', 'Punto quitado'), ('agregar_lista', 'Cuenta agregada a la lista'), ('quitar_lista', 'Cuenta sacada de la lista'), ('alertas_ans', 'Alertas ANS')], db_column='Accion', max_length=20, verbose_name='Acción'),
        ),
    ]
