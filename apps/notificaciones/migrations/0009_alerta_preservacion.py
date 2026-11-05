from django.db import migrations, models
import django.db.models.deletion


def completar_claves(apps, schema_editor):
    Alerta = apps.get_model("notificaciones", "AlertaOperativa")
    db = schema_editor.connection.alias
    for alerta in Alerta.objects.using(db).select_related("ticket").iterator():
        alerta.clave_origen = f"ticket:{alerta.ticket_id}:{alerta.tipo}"
        alerta.codigo_ticket = alerta.ticket.codigo or ""
        alerta.titulo_ticket = (alerta.ticket.titulo or "")[:200]
        alerta.save(using=db, update_fields=["clave_origen", "codigo_ticket", "titulo_ticket"])


class Migration(migrations.Migration):
    dependencies = [("notificaciones", "0008_alertas_operativas")]
    operations = [
        migrations.AddField(model_name="alertaoperativa", name="clave_origen", field=models.CharField(max_length=160, null=True)),
        migrations.AddField(model_name="alertaoperativa", name="codigo_ticket", field=models.CharField(blank=True, default="", max_length=40)),
        migrations.AddField(model_name="alertaoperativa", name="titulo_ticket", field=models.CharField(blank=True, default="", max_length=200)),
        migrations.RunPython(completar_claves, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="alertaoperativa", name="uq_alerta_ticket_tipo"),
        migrations.AlterField(model_name="alertaoperativa", name="ticket", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="alertas_operativas", to="tickets.ticket")),
        migrations.AlterField(model_name="alertaoperativa", name="clave_origen", field=models.CharField(max_length=160, unique=True)),
    ]
