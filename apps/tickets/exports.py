"""Exportaciones a Excel con identidad corporativa Dogger.

Todas las descargas del proyecto salen de aquí: tickets (admin, mis
tickets, observador) y el reporte corporativo multi-hoja. El diseño sigue
la casa: banda de título negra, encabezados negros con texto blanco,
cebras cálidas, autofiltros, impresión apaisada ajustada a la página y
gráficas nativas de Excel (editables) para la trazabilidad.
"""

from collections import Counter
from io import BytesIO

from openpyxl import Workbook
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.marker import DataPoint
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties
from django.http import HttpResponse
from django.utils import timezone

# ---------------------------------------------------------------- paleta
DOGGER_RED = "D62B1F"
DOGGER_BLACK = "171412"
DOGGER_YELLOW = "FFC72C"
DOGGER_GREEN = "2F7D4F"
DOGGER_BLUE = "1D4ED8"
DOGGER_AMBER = "F2A900"
GRID = "D9CFC2"
ZEBRA = "FBF6EC"
GRIS_TXT = "666666"

PALETA_PIE = [DOGGER_RED, DOGGER_BLUE, DOGGER_AMBER, DOGGER_GREEN, "6B6259", "7C3AED"]

HEADER_FILL = PatternFill(start_color=DOGGER_BLACK, end_color=DOGGER_BLACK, fill_type="solid")
HEADER_FONT = Font(name="Arial", bold=True, color="FFFFFF", size=11)
BODY_FONT = Font(name="Arial", size=10)
TITLE_FILL = PatternFill(start_color=DOGGER_BLACK, end_color=DOGGER_BLACK, fill_type="solid")
TITLE_FONT = Font(name="Arial", bold=True, color="FFFFFF", size=14)
SECTION_FONT = Font(name="Arial", bold=True, color=DOGGER_BLACK, size=12)
SUB_FONT = Font(name="Arial", italic=True, size=9, color=GRIS_TXT)
LABEL_FONT = Font(name="Arial", bold=True, size=10)

BORDE_FINO = Side(style="thin", color=GRID)
BORDE_CELDA = Border(left=BORDE_FINO, right=BORDE_FINO, top=BORDE_FINO, bottom=BORDE_FINO)
BORDE_AMARILLO = Border(bottom=Side(style="medium", color=DOGGER_YELLOW))

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

MESES = ["ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]


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
    """Banda corporativa: título en negro con filo amarillo y fecha."""
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=span)
    for col in range(1, span + 1):
        celda = ws.cell(row=fila, column=col)
        celda.fill = TITLE_FILL
        celda.border = BORDE_AMARILLO
    ws.cell(row=fila, column=1, value=titulo).font = TITLE_FONT
    ws.cell(
        row=fila + 1, column=1,
        value=f"Dogger HelpDesk · Generado el "
              f"{timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M')}",
    ).font = SUB_FONT
    return fila + 3


def _pintar_cuerpo(ws, fila, columna, valor, cebra):
    celda = ws.cell(row=fila, column=columna, value=valor)
    celda.font = BODY_FONT
    celda.border = BORDE_CELDA
    celda.alignment = Alignment(vertical="center", wrap_text=True)
    if cebra:
        celda.fill = PatternFill(start_color=ZEBRA, end_color=ZEBRA, fill_type="solid")
    return celda


def _escribir_tabla(ws, headers, rows, start_row, widths):
    for col_idx, (label, width) in enumerate(headers, start=1):
        cell = ws.cell(row=start_row, column=col_idx, value=label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    for r, row in enumerate(rows, start=start_row + 1):
        for c, value in enumerate(row, start=1):
            _pintar_cuerpo(ws, r, c, value, cebra=(r % 2 == 0))
    if rows:
        ultima = get_column_letter(len(headers))
        ws.auto_filter.ref = f"A{start_row}:{ultima}{start_row + len(rows)}"
    ws.freeze_panes = f"A{start_row + 1}"
    _ajustar_impresion(ws)
    return start_row + len(rows)


def _escribir_tickets(ws, tickets, start_row, headers_row=4):
    for col_idx, (label, _, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=headers_row, column=col_idx, value=label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    tickets = list(tickets)
    for r, ticket in enumerate(tickets, start=headers_row + 1):
        for c, value in enumerate(_row_values(ticket), start=1):
            _pintar_cuerpo(ws, r, c, value, cebra=(r % 2 == 0))
    if tickets:
        ultima = get_column_letter(len(COLUMNS))
        ws.auto_filter.ref = f"A{headers_row}:{ultima}{headers_row + len(tickets)}"
    ws.freeze_panes = f"A{headers_row + 1}"
    _ajustar_impresion(ws)
    return tickets


def _ajustar_impresion(ws):
    """Apaisado, ajustado al ancho y pie corporativo."""
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.oddFooter.center.text = "Dogger HelpDesk · Reporte corporativo"


def _serie_con_color(chart, color):
    serie = chart.series[-1]
    serie.graphicalProperties.solidFill = color
    serie.graphicalProperties.line.solidFill = color
    return serie


def _barra_tickets(categorias, series, titulo):
    """Barras verticales con valores encima y colores Dogger.

    `series` es una lista de tuplas (referencia, color).
    """
    ch = BarChart()
    ch.type = "col"
    ch.style = 10
    ch.title = titulo
    ch.y_axis.title = "Tickets"
    ch.height = 8
    ch.width = 17
    ch.dataLabels = DataLabelList(showVal=True)
    ch.set_categories(categorias)
    for valores, color in series:
        ch.add_data(valores, titles_from_data=True)
        _serie_con_color(ch, color)
    return ch


def _torta(datos, titulo, paleta=PALETA_PIE):
    """Torta con rebanadas en paleta corporativa y % en cada parte."""
    ch = PieChart()
    ch.title = titulo
    ch.height = 8
    ch.width = 15
    ch.dataLabels = DataLabelList(showCatName=True, showPercent=True)
    ch.add_data(datos, titles_from_data=True)
    puntos = [DataPoint(idx=i) for i in range(len(paleta))]
    ch.series[0].dPt = puntos
    for punto, color in zip(puntos, paleta):
        punto.graphicalProperties.solidFill = color
    return ch


def _por_estado(tickets):
    conteo = Counter()
    nombre = {}
    for t in tickets:
        conteo[t.estado] += 1
        nombre[t.estado] = t.get_estado_display()
    orden = ["abierto", "en_progreso", "resuelto", "cerrado"]
    claves = [c for c in orden if c in conteo] + [c for c in conteo if c not in orden]
    return [(nombre[c], conteo[c]) for c in claves]


def _por_categoria(tickets, tope=8):
    conteo = Counter(
        t.categoria.nombre if t.categoria else "Sin categoría" for t in tickets
    )
    filas = conteo.most_common(tope)
    resto = sum(v for _, v in conteo.most_common()[tope:])
    if resto:
        filas = list(filas) + [("Otras", resto)]
    return filas


def _por_mes(tickets, n=6):
    hoy = timezone.localdate()
    base = hoy.year * 12 + hoy.month - 1
    claves = [base - i for i in range(n - 1, -1, -1)]
    en_rango = set(claves)
    conteo = Counter()
    for t in tickets:
        f = timezone.localtime(t.fecha_creacion)
        idx = f.year * 12 + f.month - 1
        if idx in en_rango:
            conteo[idx] += 1
    return [(f"{MESES[c % 12]} {c // 12}", conteo[c]) for c in claves]


def _mini_tabla(ws, fila, titulo, headers, filas):
    """Pequeña tabla de agregados para alimentar una gráfica."""
    ws.cell(row=fila, column=1, value=titulo).font = SECTION_FONT
    fila += 1
    for col_idx, (label, width) in enumerate(headers, start=1):
        cell = ws.cell(row=fila, column=col_idx, value=label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    for r, f in enumerate(filas, start=fila + 1):
        for c, value in enumerate(f, start=1):
            _pintar_cuerpo(ws, r, c, value, cebra=(r % 2 == 0))
    return fila, fila + len(filas)


def generar_excel_tickets(tickets, titulo="Tickets Dogger Helpdesk"):
    """
    Recibe un queryset/lista de Ticket (con select_related aplicado por el
    caller) y retorna un HttpResponse .xlsx listo para descargar, con
    resumen por estado y su torta al costado.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Tickets"
    header_row = _escribir_titulo(ws, titulo, len(COLUMNS))
    tickets = _escribir_tickets(ws, tickets, None, headers_row=header_row)

    estados = _por_estado(tickets)
    if estados:
        col = len(COLUMNS) + 2
        letra = get_column_letter(col)
        ws.cell(row=header_row, column=col, value="Resumen por estado").font = SECTION_FONT
        ws.cell(row=header_row + 1, column=col, value="Estado").font = HEADER_FONT
        ws.cell(row=header_row + 1, column=col).fill = HEADER_FILL
        ws.cell(row=header_row + 1, column=col + 1, value="Tickets").font = HEADER_FONT
        ws.cell(row=header_row + 1, column=col + 1).fill = HEADER_FILL
        ws.column_dimensions[letra].width = 20
        ws.column_dimensions[get_column_letter(col + 1)].width = 12
        for i, (nombre, cantidad) in enumerate(estados):
            r = header_row + 2 + i
            _pintar_cuerpo(ws, r, col, nombre, cebra=(i % 2 == 1))
            _pintar_cuerpo(ws, r, col + 1, cantidad, cebra=(i % 2 == 1))
        datos = Reference(ws, min_col=col + 1, min_row=header_row + 1,
                          max_row=header_row + 1 + len(estados))
        torta = _torta(datos, "Tickets por estado")
        torta.set_categories(Reference(ws, min_col=col, min_row=header_row + 2,
                                       max_row=header_row + 1 + len(estados)))
        ws.add_chart(torta, f"{get_column_letter(col + 3)}{header_row}")
    return _responder_xlsx(wb, "dogger_tickets")


def generar_excel_reportes(kpis, tecnicos, usuarios, tickets, filtros_txt="Sin filtros"):
    """
    Reporte corporativo multi-hoja: Resumen de KPIs (con barras), desempeño
    por técnico (con comparativo), producción por usuario, hoja de Gráficas
    (tortas por estado y categoría + barras por mes) y el detalle filtrado.
    """
    wb = Workbook()
    tickets = list(tickets)

    # ---- Hoja 1: Resumen de KPIs ----
    ws = wb.active
    ws.title = "Resumen"
    row = _escribir_titulo(ws, "Dogger · Reporte corporativo del helpdesk", 2)
    ws.cell(row=row, column=1, value="Filtros aplicados").font = LABEL_FONT
    ws.cell(row=row, column=2, value=filtros_txt).font = BODY_FONT
    row += 2
    ws.merge_cells(f"A{row}:B{row}")
    ws.cell(row=row, column=1, value="Resumen de indicadores").font = HEADER_FONT
    ws.cell(row=row, column=1).fill = HEADER_FILL
    row += 1
    inicio_kpis = row
    for k, v in kpis:
        ws.cell(row=row, column=1, value=k).font = LABEL_FONT
        _pintar_cuerpo(ws, row, 2, v, cebra=(row % 2 == 0))
        # La etiqueta también lleva borde para que la tabla se vea cerrada.
        ws.cell(row=row, column=1).border = BORDE_CELDA
        row += 1
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 24
    ws.freeze_panes = "A4"
    _ajustar_impresion(ws)
    # Barras con los estados (se salta el total, que aplastaría la escala).
    if len(kpis) >= 6:
        cats = Reference(ws, min_col=1, min_row=inicio_kpis + 1, max_row=inicio_kpis + 5)
        vals = Reference(ws, min_col=2, min_row=inicio_kpis, max_row=inicio_kpis + 5)
        barra = _barra_tickets(cats, [(vals, DOGGER_RED)], "Estado de los tickets")
        ws.add_chart(barra, "D5")

    # ---- Hoja 2: Por técnico (con comparativo en barras) ----
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
    fin2 = _escribir_tabla(ws2, tec_headers, tecnicos, r2, None)
    if tecnicos:
        cats = Reference(ws2, min_col=1, min_row=r2 + 1, max_row=fin2)
        asignados = Reference(ws2, min_col=2, min_row=r2, max_row=fin2)
        resueltos = Reference(ws2, min_col=3, min_row=r2, max_row=fin2)
        comp = _barra_tickets(cats, [(asignados, DOGGER_RED), (resueltos, DOGGER_GREEN)],
                              "Asignados vs resueltos por técnico")
        ws2.add_chart(comp, f"H{r2}")

    # ---- Hoja 3: Por usuario ----
    ws3 = wb.create_sheet("Por usuario")
    usu_headers = (
        ("Punto de venta", 26),
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

    # ---- Hoja 4: Gráficas de trazabilidad ----
    ws4 = wb.create_sheet("Gráficas")
    fila = _escribir_titulo(ws4, f"Gráficas · {filtros_txt}", 3)
    fila_actual = fila
    secciones = [
        ("Tickets por estado", [("Estado", 22), ("Tickets", 12)], _por_estado(tickets), "pie"),
        ("Tickets por categoría", [("Categoría", 26), ("Tickets", 12)],
         _por_categoria(tickets), "pie"),
        ("Tickets por mes (últimos 6)", [("Mes", 14), ("Tickets", 12)],
         _por_mes(tickets), "bar"),
    ]
    for titulo, headers, datos, tipo in secciones:
        if not datos:
            continue
        f_tit, f_fin = _mini_tabla(ws4, fila_actual, titulo, headers, datos)
        cats = Reference(ws4, min_col=1, min_row=f_tit + 1, max_row=f_fin)
        vals = Reference(ws4, min_col=2, min_row=f_tit, max_row=f_fin)
        if tipo == "pie":
            grafica = _torta(vals, titulo)
            grafica.set_categories(cats)
        else:
            grafica = _barra_tickets(cats, [(vals, DOGGER_RED)], titulo)
        ws4.add_chart(grafica, f"D{f_tit}")
        fila_actual = f_fin + 18
    _ajustar_impresion(ws4)

    # ---- Hoja 5: Tickets filtrados ----
    ws5 = wb.create_sheet("Tickets filtrados")
    r5 = _escribir_titulo(ws5, "Tickets incluidos en el reporte", len(COLUMNS))
    _escribir_tickets(ws5, tickets, None, headers_row=r5)

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
