from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from django.http import HttpResponse
from django.utils import timezone

HEADER_FILL = PatternFill(start_color="1D3557", end_color="1D3557", fill_type="solid")
HEADER_FONT = Font(name="Arial", bold=True, color="FFFFFF", size=11)
BODY_FONT = Font(name="Arial", size=10)
TITLE_FONT = Font(name="Arial", bold=True, size=14, color="D62B1F")

COLUMNS = [
    ("Código", "codigo", 12),
    ("Título", "titulo", 34),
    ("Solicitante", "solicitante_nombre", 22),
    ("Correo", "solicitante_email", 26),
    ("Punto / equipo", "solicitante_punto", 22),
    ("Categoría", "_categoria", 20),
    ("Prioridad", "_prioridad", 12),
    ("Estado", "_estado", 14),
    ("Técnico asignado", "_tecnico", 20),
    ("GLPI #", "glpi_id", 8),
    ("Fecha creación", "_fecha_creacion", 18),
    ("Fecha cierre", "_fecha_cierre", 18),
]


def _row_values(ticket):
    return [
        ticket.codigo,
        ticket.titulo,
        ticket.solicitante_nombre,
        ticket.solicitante_email or "",
        ticket.solicitante_punto or "",
        ticket.categoria.nombre if ticket.categoria else "Sin categoría",
        ticket.get_prioridad_display(),
        ticket.get_estado_display(),
        ticket.tecnico_asignado.nombre if ticket.tecnico_asignado else "",
        ticket.glpi_id or "",
        timezone.localtime(ticket.fecha_creacion).strftime("%d/%m/%Y %H:%M"),
        timezone.localtime(ticket.fecha_cierre).strftime("%d/%m/%Y %H:%M") if ticket.fecha_cierre else "",
    ]


def _escribir_titulo(ws, titulo, span, fila=1):
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=span)
    ws.cell(row=fila, column=1, value=titulo).font = TITLE_FONT
    ws.cell(row=fila + 1, column=1, value=f"Generado el {timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M')}").font = Font(
        name="Arial", italic=True, size=9, color="666666"
    )
    return fila + 3


def _escribir_tabla(ws, headers, rows, start_row, widths):
    for col_idx, (label, width) in enumerate(headers, start=1):
        cell = ws.cell(row=start_row, column=col_idx, value=label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    for r, row in enumerate(rows, start=start_row + 1):
        for c, value in enumerate(row, start=1):
            ws.cell(row=r, column=c, value=value).font = BODY_FONT
    ws.freeze_panes = f"A{start_row + 1}"
    return start_row + len(rows)


def _escribir_tickets(ws, tickets, start_row, headers_row=4):
    for col_idx, (label, _, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=headers_row, column=col_idx, value=label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    for r, ticket in enumerate(tickets, start=headers_row + 1):
        for c, value in enumerate(_row_values(ticket), start=1):
            ws.cell(row=r, column=c, value=value).font = BODY_FONT
    ws.freeze_panes = f"A{headers_row + 1}"


def generar_excel_tickets(tickets, titulo="Tickets Dogger Helpdesk"):
    """
    Recibe un queryset/lista de Ticket (con select_related aplicado por el
    caller) y retorna un HttpResponse .xlsx listo para descargar.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Tickets"
    header_row = _escribir_titulo(ws, titulo, len(COLUMNS))
    _escribir_tickets(ws, tickets, None, headers_row=header_row)
    return _responder_xlsx(wb, "dogger_tickets")


def generar_excel_reportes(kpis, tecnicos, usuarios, tickets, filtros_txt="Sin filtros"):
    """
    Reporte corporativo multi-hoja: Resumen de KPIs, desempeño por técnico,
    producción por usuario y el detalle de tickets filtrados.
    """
    wb = Workbook()

    # ---- Hoja 1: Resumen de KPIs ----
    ws = wb.active
    ws.title = "Resumen"
    row = _escribir_titulo(ws, "Dogger · Reporte corporativo del helpdesk", 2)
    ws.cell(row=row, column=1, value="Filtros aplicados").font = Font(name="Arial", bold=True, size=10)
    ws.cell(row=row, column=2, value=filtros_txt).font = BODY_FONT
    row += 2
    ws.merge_cells(f"A{row}:B{row}")
    ws.cell(row=row, column=1, value="Ticker principal").font = HEADER_FONT
    ws.cell(row=row, column=1).fill = HEADER_FILL
    row += 1
    for k, v in kpis:
        ws.cell(row=row, column=1, value=k).font = Font(name="Arial", bold=True, size=10)
        ws.cell(row=row, column=2, value=v).font = BODY_FONT
        row += 1
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 24

    # ---- Hoja 2: Por técnico ----
    ws2 = wb.create_sheet("Por técnico")
    tec_headers = (
        ("Técnico", 24),
        ("Asignados", 14),
        ("Resueltos/Cerrados", 18),
        ("Abiertos en curso", 16),
        ("T. prom. resolución (h)", 22),
        ("% Resueltos", 12),
    )
    r2 = _escribir_titulo(ws2, f"Desempeño por técnico · {filtros_txt}", len(tec_headers))
    _escribir_tabla(ws2, tec_headers, tecnicos, r2, None)

    # ---- Hoja 3: Por usuario ----
    ws3 = wb.create_sheet("Por usuario")
    usu_headers = (
        ("Usuario", 26),
        ("Correo", 28),
        ("Creados", 10),
        ("Abiertos", 10),
        ("Resueltos", 10),
        ("Cerrados", 10),
        ("Último estado", 16),
        ("T. prom. resolución (h)", 22),
    )
    r3 = _escribir_titulo(ws3, f"Producción por usuario · {filtros_txt}", len(usu_headers))
    _escribir_tabla(ws3, usu_headers, usuarios, r3, None)

    # ---- Hoja 4: Tickets filtrados ----
    ws4 = wb.create_sheet("Tickets filtrados")
    r4 = _escribir_titulo(ws4, "Tickets incluidos en el reporte", len(COLUMNS))
    _escribir_tickets(ws4, tickets, None, headers_row=r4)

    return _responder_xlsx(wb, "dogger_reporte")


def _responder_xlsx(wb, prefijo):
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    filename = f"{prefijo}_{timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')}.xlsx"
    response = HttpResponse(
        buffer.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
