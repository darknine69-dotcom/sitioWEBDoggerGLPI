"""Avisa de los tickets que se están pasando del ANS.

    python manage.py avisar_ans_por_vencer
    python manage.py avisar_ans_por_vencer --limite 200
    python manage.py avisar_ans_por_vencer --seco

Pensado para el cron. Cada ejecución manda los avisos que falten y se queda
callada si no hay nada nuevo: la marca `Ticket.ans_alertado_en` evita repetir
el mismo correo. Con `--seco` no manda nada, solo imprime lo que mandaría.

También se puede llamar desde el panel del observador, para que el sistema no
dependa de que alguien programe la tarea.
"""

from django.core.management.base import BaseCommand

from apps.tickets.ans_avisos import (
    observadores_de,
    por_vencer,
    revisar_y_avisar,
)


class Command(BaseCommand):
    help = (
        "Avisa una sola vez de cada ticket cuyo ANS está por vencer o vencido: "
        "correo al técnico y a la persona que lo abrió, y campana al "
        "observador que lo supervisa."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limite",
            type=int,
            default=500,
            help="Máximo de tickets que se miran en esta pasada (por defecto 500).",
        )
        parser.add_argument(
            "--seco",
            action="store_true",
            help="No manda nada: solo lista lo que se mandaría.",
        )

    def handle(self, *args, **opciones):
        limite = max(1, int(opciones["limite"]))
        candidatos = por_vencer(limite=limite)

        if not candidatos:
            self.stdout.write(
                self.style.SUCCESS("Ningún ticket por vencer sin avisar.")
            )
            return

        if opciones["seco"]:
            self.stdout.write(
                f"{len(candidatos)} ticket{len(candidatos) != 1 and 's' or ''} "
                "por avisar (modo seco, no se mandó nada):"
            )
            for ticket in candidatos:
                observadores = observadores_de(ticket)
                tec = getattr(ticket.tecnico_asignado, "nombre", "sin técnico")
                self.stdout.write(
                    f"  {ticket.codigo} · {ticket.ans_estado} · "
                    f"{ticket.ans_texto} · {tec} · "
                    f"observadores: {len(observadores)}"
                )
            return

        avisados = revisar_y_avisar(limite=limite)
        for ticket in avisados:
            self.stdout.write(
                f"  {ticket.codigo} · {ticket.ans_estado} · {ticket.ans_texto}"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Avisado{len(avisados) != 1 and 's' or ''} "
                f"{len(avisados)} ticket{len(avisados) != 1 and 's' or ''}."
            )
        )
