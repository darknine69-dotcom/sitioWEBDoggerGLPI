/* =====================================================================
   DOGGER HELPDesk — PROGRAMADOR
   Calendario mensual, disponibilidad de técnicos y agenda de eventos.
   ===================================================================== */
(function () {
    "use strict";

    var app = document.getElementById("programadorApp");
    if (!app) return;

    var U = {
        datos: app.dataset.urlDatos,
        agregar: app.dataset.urlAgregar,
        eliminar: app.dataset.urlEliminar,
        completado: app.dataset.urlCompletado,
        disp: app.dataset.urlDisp,
        dispLeida: app.dataset.urlDispLeida,
        eventoLeido: app.dataset.urlEventoLeido,
        festivo: app.dataset.urlFestivo,
        detalle: app.dataset.urlDetalle
    };

    var ICON_BY_TIPO = {
        tarea: "i-wrench",
        solicitud: "i-ticket",
        recordatorio: "i-bell",
        anuncio: "i-message",
        proyecto: "i-calendar"
    };
    var LABELS = {
        tarea: ["Tarea", "Tareas"],
        solicitud: ["Solicitud", "Solicitudes"],
        recordatorio: ["Recordatorio", "Recordatorios"],
        anuncio: ["Anuncio", "Anuncios"]
    };
    // Qué tipo "pinta" más el cuadro del día cuando hay varios registrados.
    var PRIORIDAD_TIPO = {
        solicitud: 1,
        recordatorio: 2,
        tarea: 3,
        anuncio: 4
    };
    var TIPOS_EVENTO = ["tarea", "solicitud", "recordatorio", "proyecto", "anuncio"];

    var state = {
        anio: parseInt(app.dataset.anio, 10),
        mes: parseInt(app.dataset.mes, 10),
        tecnicoDef: app.dataset.tecDef || "",
        vista: "mes",
        fechaActiva: "",
        resumenTecnico: ""
    };
    var data = { eventos: [], disponibilidad: {}, festivos: {} };
    var MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];
    var NOMBRES_DIA = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"];

    /* ---------- utilidades ---------- */
    function esc(s) {
        return String(s == null ? "" : s)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }
    function iso(d) {
        var mm = ("0" + (d.getMonth() + 1)).slice(-2);
        var dd = ("0" + d.getDate()).slice(-2);
        return d.getFullYear() + "-" + mm + "-" + dd;
    }
    function plural(n, sing, plur) { return n + " " + (n === 1 ? sing : plur); }
    function $(id) { return document.getElementById(id); }
    function formatFecha(isoStr) {
        var p = isoStr.split("-");
        return p[2] + "/" + p[1] + "/" + p[0];
    }

    function filtros() {
        return {
            anio: state.anio,
            mes: state.mes,
            tecnico_id: $("filtroTecnico").value
        };
    }
    function query(params) {
        var p = new URLSearchParams();
        Object.keys(params).forEach(function (k) { p.set(k, params[k]); });
        return "?" + p.toString();
    }
    function csrf() {
        var el = document.querySelector("input[name=csrfmiddlewaretoken]");
        return el ? el.value : "";
    }
    function post(url, body, cb, finalizar) {
        return fetch(url, { method: "POST", body: new URLSearchParams(body), headers: { "X-CSRFToken": csrf() } })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (res.ok) { if (cb) cb(res); }
                else toast(res.error || "Error inesperado", false);
            })
            .catch(function () { toast("Error de conexión. No se pudo guardar.", false); })
            .finally(function () { if (finalizar) finalizar(); });
    }
    function toast(msg, ok) {
        var stack = $("progToasts");
        var duplicado = Array.from(stack.querySelectorAll(".toast")).find(function (aviso) { return aviso.dataset.mensaje === msg; });
        if (duplicado) return;
        var t = document.createElement("div");
        t.className = "toast toast-" + (ok ? "success" : "error");
        t.dataset.mensaje = msg;
        t.setAttribute("role", ok ? "status" : "alert");
        t.innerHTML =
            '<span class="toast-accent"></span>' +
            '<span class="toast-icon"><svg class="icon icon-sm"><use href="#' + (ok ? "i-check-circle" : "i-alert") + '"/></svg></span>' +
            '<span class="toast-body"><span class="toast-title">' + (ok ? "Completado" : "Revisa la información") + '</span><span class="toast-text">' + esc(msg) + "</span></span>" +
            '<button type="button" class="toast-close" aria-label="Cerrar">&times;</button>';
        stack.appendChild(t);
        t.querySelector(".toast-close").addEventListener("click", function () { t.remove(); });
        if (ok) setTimeout(function () {
            t.style.opacity = "0";
            setTimeout(function () { t.remove(); }, 300);
        }, 3800);
    }

    /* ---------- carga de datos ---------- */
    function load() {
        fetch(U.datos + query(filtros()), { headers: { Accept: "application/json" } })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (!res.ok) { toast(res.error || "Error al cargar", false); return; }
                data = res;
                renderCalendario();
                renderMatrix();
                renderListas();
                renderDispOtros();
                if (state.fechaActiva) {
                    var celdaActiva = document.querySelector('.prog-day[data-fecha="' + state.fechaActiva + '"]');
                    if (celdaActiva) celdaActiva.click();
                }
                abrir_destacado();
            })
            .catch(function () { toast("Error al cargar los datos", false); });
    }

    /* ---------- aviso que llega con el evento a destacar ----------
       La notificación "Ver" abre /programador/?anio=..&mes=..&ev=PK: aquí se
       abre la ficha de ese evento para que no haya que buscarlo a mano. */
    function abrir_destacado() {
        var pk = app.getAttribute("data-destacado");
        if (!pk) { return; }
        var encontrado = (data.eventos || []).filter(function (x) {
            return String(x.id) === String(pk);
        })[0];
        if (!encontrado) { return; }
        app.removeAttribute("data-destacado");
        abrirModalDetalle(encontrado, encontrado.fecha);
    }

    /* ---------- calendario ---------- */
    function estadoDia(d, key) {
        var is = iso(d);
        if (data.festivos[is]) return "is-festivo";
        var dow = d.getDay();
        if (dow === 0 || dow === 6) return "is-findesemana";
        if (key) {
            var disp = data.disponibilidad[key + "|" + is];
            if (disp && disp.tipo === "ausencia") return "is-ausencia";
            if (disp && disp.tipo === "falta") return "is-falta";
            if (disp && disp.tipo === "no_ausencia") return "is-noausencia";
        } else {
            var marca = Object.keys(data.disponibilidad).filter(function (clave) { return clave.slice(-11) === "|" + is; })
                .map(function (clave) { return data.disponibilidad[clave]; })[0];
            if (marca && marca.tipo === "ausencia") return "is-ausencia";
            if (marca && marca.tipo === "falta") return "is-falta";
            if (marca && marca.tipo === "no_ausencia") return "is-noausencia";
        }
        return "";
    }

    function detalleDisponibilidad(d, key) {
        var estado = estadoDia(d, key);
        var fecha = iso(d);
        var marca = key ? data.disponibilidad[key + "|" + fecha] : Object.keys(data.disponibilidad).filter(function (clave) {
            return clave.slice(-(fecha.length + 1)) === "|" + fecha;
        }).map(function (clave) { return data.disponibilidad[clave]; })[0];
        var detalles = {
            "is-noausencia": { texto: "Disponible", icono: "i-check-circle", tipo: "disponible" },
            "is-falta": { texto: "Ocupado", icono: "i-clock", tipo: "ocupado" },
            "is-ausencia": { texto: "No disponible", icono: "i-alert", tipo: "ausencia" },
            "is-festivo": { texto: "Festivo", icono: "i-calendar", tipo: "festivo" },
            "is-findesemana": { texto: "No disponible", icono: "i-clock", tipo: "fin" }
        };
        if (!detalles[estado]) return null;
        return {
            texto: detalles[estado].texto,
            icono: detalles[estado].icono,
            tipo: detalles[estado].tipo,
            marca: marca || null
        };
    }

    function renderCalendario() {
        var grid = $("calGrid");
        var primer = new Date(state.anio, state.mes - 1, 1);
        var diasMes = new Date(state.anio, state.mes, 0).getDate();
        var offset = primer.getDay(); // Dom = 0 → alineación domingo a sábado
        var hoy = new Date();
        var hoyIso = iso(hoy);
        var key = String($("filtroTecnico").value);

        $("mesTitulo").textContent = MESES[state.mes - 1] + " " + state.anio;

        var porFecha = {};
        data.eventos.forEach(function (e) {
            (porFecha[e.fecha] = porFecha[e.fecha] || []).push(e);
        });

        grid.innerHTML = "";
        var total = offset + diasMes;
        var filas = Math.ceil(total / 7) * 7;
        var inicioVista = null;
        if (state.vista !== "mes") {
            var referencia = state.fechaActiva ? new Date(state.fechaActiva + "T12:00:00") : new Date(state.anio, state.mes - 1, 1);
            if (state.vista === "semana") {
                inicioVista = new Date(referencia);
                inicioVista.setDate(referencia.getDate() - referencia.getDay());
                filas = 7;
                var finSemana = new Date(inicioVista);
                finSemana.setDate(inicioVista.getDate() + 6);
                $("mesTitulo").textContent = inicioVista.getDate() + "–" + finSemana.getDate() + " " + MESES[referencia.getMonth()] + " " + referencia.getFullYear();
            } else {
                inicioVista = referencia;
                filas = 1;
                $("mesTitulo").textContent = referencia.toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });
            }
        }
        grid.classList.toggle("is-week-view", state.vista === "semana");
        grid.classList.toggle("is-day-view", state.vista === "dia");
        grid.parentElement.classList.toggle("is-day-view", state.vista === "dia");

        for (var i = 0; i < filas; i++) {
            var num = i - offset + 1;
            var enMes = num >= 1 && num <= diasMes;
            let d = new Date(state.anio, state.mes - 1, num);
            if (inicioVista) {
                d = new Date(inicioVista);
                d.setDate(inicioVista.getDate() + i);
                num = d.getDate();
                enMes = true;
            }
            let fecha = iso(d);

            let cell = document.createElement("div");
            var cls = "prog-day" + (enMes ? "" : " out" + (i < offset || num > diasMes ? " empty" : ""));
            if (enMes) {
                var st = estadoDia(d, key);
                if (st) cls += " " + st;
                if (fecha === hoyIso) cls += " is-today";
            }
            cell.className = cls;

            if (enMes) {
                cell.dataset.fecha = fecha;
                // Seleccionar un día actualiza el detalle sin recargar el calendario.
                cell.addEventListener("click", function () {
                    document.querySelectorAll(".prog-day.is-selected").forEach(function (item) { item.classList.remove("is-selected"); });
                    cell.classList.add("is-selected");
                    state.fechaActiva = fecha;
                    var eventosDia = data.eventos.filter(function (evento) { return evento.fecha === fecha; });
                    var sideDate = $("progSideDate"), sideCount = $("progSideCount"), sideEvents = $("progSideEvents"), sideSummary = $("progSideSummary");
                    var sideNum = $("progSideNum"), sideMonth = $("progSideMonth"), sideState = $("progSideState"), sideEventLabel = $("progSideEventLabel");
                    if (sideDate) sideDate.textContent = d.toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
                    var sidePanel = $("progDaySide");
                    if (sidePanel) { sidePanel.hidden = false; sidePanel.dataset.fecha = fecha; }
                    var disponibilidadDia = detalleDisponibilidad(d, key);
                    if (sideCount) sideCount.textContent = eventosDia.length + " evento" + (eventosDia.length === 1 ? "" : "s");
                    if (sideNum) sideNum.textContent = d.getDate();
                    if (sideMonth) sideMonth.textContent = d.toLocaleDateString("es-CO", { month: "long" });
                    if ($("progSideYear")) $("progSideYear").textContent = d.getFullYear();
                    if (sideState) sideState.textContent = eventosDia.length ? "Con eventos" : (disponibilidadDia ? disponibilidadDia.texto : "Disponible");
                    if (sideState) sideState.className = "is-" + (eventosDia.length ? "eventos" : (disponibilidadDia ? disponibilidadDia.tipo : "disponible"));
                    if (sideEventLabel) sideEventLabel.textContent = eventosDia.length + " evento" + (eventosDia.length === 1 ? " programado" : "s programados");
                    var pendientes = eventosDia.filter(function (evento) { return evento.tipo === "tarea" && !evento.completado; }).length;
                    var marcasDia = marcasDisponibilidad(fecha);
                    if (key) marcasDia = marcasDia.filter(function (marca) { return String(marca.tecnicoId) === key; });
                    var stats = $("progSideMiniStats");
                    if (stats) stats.innerHTML = '<span><svg class="icon"><use href="#i-calendar"/></svg><b>' + eventosDia.length + '</b><small>Eventos programados</small></span><span><svg class="icon"><use href="#i-clock"/></svg><b>' + pendientes + '</b><small>Tareas pendientes</small></span><span><svg class="icon"><use href="#i-check-circle"/></svg><b>' + marcasDia.length + '</b><small>Disponibilidad marcada</small></span>';
                    if (sideEvents) {
                        var tarjetasEventos = eventosDia.length ? eventosDia.map(function (evento) {
                            return '<article class="prog-side-event is-' + esc(evento.tipo) + '">' +
                                '<span class="prog-side-event-icon"><svg class="icon"><use href="#' + (ICON_BY_TIPO[evento.tipo] || "i-calendar") + '"/></svg></span>' +
                                '<div><span class="prog-side-event-time"><svg class="icon"><use href="#i-clock"/></svg>' + esc(evento.hora || "Sin hora") + '</span><b>' + esc(evento.titulo) + '</b><small>' + esc(evento.descripcion || evento.tecnico || "Sin descripción") + '</small><em>' + esc(evento.tipo_label) + '</em></div>' +
                                '<button type="button" class="prog-side-event-menu" data-side-event="' + esc(evento.id) + '" aria-label="Opciones de ' + esc(evento.titulo) + '" aria-haspopup="menu" aria-expanded="false"><svg class="icon"><use href="#i-ellipsis"/></svg></button></article>';
                        }).join("") : '<p class="prog-side-empty">No hay eventos programados para este día.</p>';
                        sideEvents.innerHTML = tarjetasEventos;
                        sideEvents.querySelectorAll("[data-side-event]").forEach(function (boton) {
                            boton.addEventListener("click", function () {
                                var evento = data.eventos.filter(function (item) { return String(item.id) === boton.dataset.sideEvent; })[0];
                                if (evento) abrirMenuEvento(boton, evento, fecha);
                            });
                        });
                    }
                    if (sideSummary) sideSummary.innerHTML = '<span><svg class="icon"><use href="#i-calendar"/></svg><span><small>Total de eventos</small><b>' + eventosDia.length + '</b></span></span><span><svg class="icon"><use href="#i-list-todo"/></svg><span><small>Tareas pendientes</small><b>' + pendientes + '</b></span></span>';
                    var verDia = $("progSideFull");
                    if (verDia) verDia.onclick = function () { abrirModalDetalle(null, fecha, eventosDia); };
                });

                var head = document.createElement("div");
                head.className = "prog-day-head";
                var numEl = document.createElement("span");
                numEl.className = "prog-day-num";
                numEl.textContent = num;
                head.appendChild(numEl);
                cell.appendChild(head);

                // Burbuja de accesos rápidos (falta de disponibilidad, recordatorio, tarea)
                var quick = document.createElement("div");
                quick.className = "prog-day-quick";
                var qAcciones = [
                    { accion: "falta", cls: "q-falta", icon: "i-clock", title: "Marcar falta de disponibilidad" },
                    { accion: "recordatorio", cls: "q-recordatorio", icon: "i-bell", title: "Agregar recordatorio" },
                    { accion: "tarea", cls: "q-tarea", icon: "i-wrench", title: "Agregar tarea" },
                    { accion: "evento", cls: "q-evento", icon: "i-calendar", title: "Crear evento o reunión" },
                    { accion: "anuncio", cls: "q-anuncio", icon: "i-message", title: "Publicar un anuncio" }
                ];
                qAcciones.forEach(function (q) {
                    var btn = document.createElement("button");
                    btn.type = "button";
                    btn.className = q.cls;
                    btn.title = q.title;
                    btn.setAttribute("aria-label", q.title);
                    btn.innerHTML = '<svg class="icon"><use href="#' + q.icon + '"/></svg>';
                    btn.addEventListener("click", function (e) {
                        e.stopPropagation();
                        if (q.accion === "falta") abrirModalDisp(fecha, "falta");
                        else abrirModalEvento(fecha, q.accion === "evento" ? "proyecto" : q.accion);
                    });
                    quick.appendChild(btn);
                });
                cell.appendChild(quick);

                // Los chips seleccionan el día; el detalle se abre desde el panel lateral.
                var chips = document.createElement("div");
                chips.className = "prog-day-chips";
                var delDia = porFecha[fecha] || [];
                // El cuadro toma un color según lo que tenga registrado.
                if (delDia.length) {
                    var peor = delDia.slice().sort(function (a, b) {
                        return (PRIORIDAD_TIPO[b.tipo] || 9) - (PRIORIDAD_TIPO[a.tipo] || 9);
                    })[0];
                    cell.classList.add("has-events", "has-" + (peor.tipo || "tarea"));
                }
                delDia.slice(0, 4).forEach(function (ev) {
                    var chip = document.createElement("button");
                    chip.type = "button";
                    chip.className = "prog-chip ct-" + ev.tipo + (ev.completado ? " done" : "");
                    chip.title = (ev.hora ? ev.hora + " · " : "") + ev.titulo;
                    chip.innerHTML = '<svg class="icon"><use href="#' + (ICON_BY_TIPO[ev.tipo] || "i-bell") + '"/></svg>' +
                        esc(ev.titulo) + indicadorLecturas(ev);
                    chips.appendChild(chip);
                });
                if (delDia.length > 4) {
                    var mas = document.createElement("button");
                    mas.type = "button";
                    mas.className = "prog-chip ct-mas";
                    mas.textContent = "+" + (delDia.length - 4);
                    mas.title = "Ver los " + delDia.length + " eventos del día";
                    chips.appendChild(mas);
                }
                var disponibilidad = detalleDisponibilidad(d, key);
                if (disponibilidad && (disponibilidad.tipo === "ocupado" || disponibilidad.tipo === "ausencia" || disponibilidad.tipo === "disponible")) {
                    var marcaChip = document.createElement("span");
                    marcaChip.className = "prog-chip ct-disponibilidad cd-" + disponibilidad.tipo;
                    marcaChip.title = "Disponibilidad: " + disponibilidad.texto;
                    marcaChip.innerHTML = '<svg class="icon"><use href="#' + disponibilidad.icono + '"/></svg>' + disponibilidad.texto;
                    chips.appendChild(marcaChip);
                }
                cell.appendChild(chips);

                var nota = "";
if (data.festivos[fecha]) nota = "Festivo: " + data.festivos[fecha];
                else {
                    var desp = data.disponibilidad[key + "|" + fecha];
                    var tipos = { ausencia: "Ausencia", falta: "Falta de disponibilidad", no_ausencia: "No ausencia" };
                    if (desp) {
                        var partes = [];
                        if (desp.hora) partes.push(desp.hora + " h");
                        partes.push(desp.nota || tipos[desp.tipo] || "");
                        nota = partes.join(" · ");
                    }
                }
                if (nota) {
                    var note = document.createElement("div");
                    note.className = "prog-day-note";
                    note.textContent = nota;
                    cell.appendChild(note);
                }
            }
            grid.appendChild(cell);
        }
    }

    /* ---------- matriz mensual de disponibilidad ---------- */
    var LETRAS = ["D", "L", "M", "X", "J", "V", "S"];
    var ESTADO_TITULO = {
        festivo: "Día festivo de la empresa",
        fin: "Fin de semana",
        online: "Técnico en línea",
        offline: "Técnico sin conexión",
        ausencia: "Abandono / ausencia",
        noausencia: "No ausencia",
        falta: "Falta de disponibilidad"
    };

    function estadoCelda(tec, d) {
        var is = iso(d);
        if (data.festivos[is]) return "festivo";
        var dow = d.getDay();
        if (dow === 0 || dow === 6) return "fin";
        var disp = data.disponibilidad[tec.id + "|" + is];
        if (disp) {
            if (disp.tipo === "ausencia") return "ausencia";
            if (disp.tipo === "falta") return "falta";
            if (disp.tipo === "no_ausencia") return "noausencia";
        }
        if (!tec.activo) return "offline";
        return "online";
    }

    function perfilTecnico(tec, clase) {
        var iniciales = String(tec.nombre || "?").split(/\s+/).slice(0, 2)
            .map(function (parte) { return parte.charAt(0); }).join("").toUpperCase();
        var avatar = tec.avatar
            ? '<img src="' + esc(tec.avatar) + '" alt="Foto de ' + esc(tec.nombre) + '">'
            : esc(iniciales);
        return '<span class="' + clase + '">' + avatar + '</span>';
    }

    function estadoActualTecnico(tec) {
        var est = estadoCelda(tec, new Date());
        var etiquetas = {
            online: "Disponible", noausencia: "Disponible", falta: "Ocupado",
            ausencia: "Ausencia", offline: "No disponible", fin: "No disponible", festivo: "No disponible"
        };
        return { clave: est, texto: etiquetas[est] || "Disponible" };
    }

    function tieneEventoDia(tec, fecha) {
        return (data.eventos || []).some(function (evento) {
            return String(evento.tecnico_id || "") === String(tec.id) && evento.fecha === fecha;
        });
    }

    function renderResumenMes(tec, dias) {
        var box = $("monthSummary");
        if (!box) return;
        if (!tec) {
            box.innerHTML = '<div class="month-summary-empty">Selecciona un técnico para ver su resumen mensual.</div>';
            return;
        }
        var conteo = { online: 0, eventos: 0, falta: 0, ausencia: 0, noDisponible: 0 };
        for (var d = 1; d <= dias; d++) {
            var fecha = new Date(state.anio, state.mes - 1, d);
            var est = estadoCelda(tec, fecha);
            if (est === "online" || est === "noausencia") conteo.online += 1;
            else if (est === "falta") conteo.falta += 1;
            else if (est === "ausencia") conteo.ausencia += 1;
            else conteo.noDisponible += 1;
            if (tieneEventoDia(tec, iso(fecha))) conteo.eventos += 1;
        }
        var estado = estadoActualTecnico(tec);
        box.innerHTML =
            '<div class="month-summary-profile">' + perfilTecnico(tec, "month-summary-avatar") +
                '<div><strong>' + esc(tec.nombre) + '</strong><small>' + esc(tec.rol_label || "Técnico") + '</small>' +
                '<span class="month-summary-status is-' + esc(estado.clave) + '"><i></i>' + esc(estado.texto) + '</span></div>' +
            '</div>' +
            '<div class="month-summary-stats"><span class="month-summary-title">Resumen del mes</span>' +
                '<div class="month-summary-metric available"><i></i><b>' + conteo.online + '</b><small>Días disponibles</small></div>' +
                '<div class="month-summary-metric events"><i></i><b>' + conteo.eventos + '</b><small>Con eventos</small></div>' +
                '<div class="month-summary-metric busy"><i></i><b>' + conteo.falta + '</b><small>Ocupados</small></div>' +
                '<div class="month-summary-metric absent"><i></i><b>' + conteo.ausencia + '</b><small>Ausencias</small></div>' +
                '<div class="month-summary-metric unavailable"><i></i><b>' + conteo.noDisponible + '</b><small>No disponibles</small></div>' +
            '</div>';
    }

    function renderMatrix() {
        var tbody = $("matrixTecnicos").querySelector("tbody");
        var theadTr = $("matrixTecnicos").querySelector("thead tr");
        var dias = new Date(state.anio, state.mes, 0).getDate();
        var sel = $("filtroTecnico").value;
        var tecs = data.tecnicos || [];
        if (sel) tecs = tecs.filter(function (t) { return String(t.id) === sel; });

        $("chartResumen").textContent = tecs.length + " técnico(s) · " + MESES[state.mes - 1] + " " + state.anio;

        // encabezado con letras de día y numeración
        var headerHtml = '<th class="mx-tec">Técnico</th>';
        for (var h = 1; h <= dias; h++) {
            var hd = new Date(state.anio, state.mes - 1, h);
            var hl = LETRAS[hd.getDay()];
            headerHtml += '<th class="mx-dia-hd' + (hl === "S" || hl === "D" ? " is-fin" : "") + '" title="' + NOMBRES_DIA[hd.getDay()] + ' ' + h + '">' +
                '<span class="mx-letra">' + hl + "</span><span class='mx-numero'>" + h + "</span></th>";
        }
        theadTr.innerHTML = headerHtml;

        // filas: un técnico por fila
        if (!tecs.length) {
            tbody.innerHTML = '<tr><td class="mx-empty" colspan="' + (dias + 1) + '">No hay técnicos que mostrar.</td></tr>';
            renderResumenMes(null, dias);
            return;
        }
        var rows = "";
        tecs.forEach(function (tec) {
            var estado = estadoActualTecnico(tec);
            rows += '<tr class="mx-row' + (tec.activo ? "" : " is-offline") + '">' +
                '<td class="mx-tec mx-profile" data-resumen-tecnico="' + esc(tec.id) + '" tabindex="0" role="button" title="Ver resumen de ' + esc(tec.nombre) + '">' +
                    perfilTecnico(tec, "mx-avatar") +
                    '<span class="mx-profile-copy"><strong>' + esc(tec.nombre) + '</strong><small>' + esc(tec.rol_label || "Técnico") + '</small></span>' +
                    '<span class="mx-row-status is-' + esc(estado.clave) + '"><i></i>' + esc(estado.texto) + '</span>' +
                "</td>";
            for (var d = 1; d <= dias; d++) {
                var dd = new Date(state.anio, state.mes - 1, d);
                var est = estadoCelda(tec, dd);
                rows += '<td class="mx-cel td-' + est + '" data-tec="' + tec.id + '" data-fecha="' + iso(dd) + '" title="' +
                    esc(NOMBRES_DIA[dd.getDay()]) + " " + d + " · " + esc(tec.nombre) + " — " + ESTADO_TITULO[est] + '"></td>';
            }
            rows += "</tr>";
        });
        tbody.innerHTML = rows;

        // clic en celda → marcar disponibilidad para ese técnico/fecha
        tbody.querySelectorAll(".mx-cel").forEach(function (cel) {
            cel.addEventListener("click", function () {
                abrirModalDisp(this.dataset.fecha, null, this.dataset.tec);
            });
        });
        tbody.querySelectorAll(".mx-profile").forEach(function (perfil) {
            function seleccionarPerfil() {
                state.resumenTecnico = this.dataset.resumenTecnico;
                var tecnico = (data.tecnicos || []).filter(function (t) {
                    return String(t.id) === String(state.resumenTecnico);
                })[0];
                renderResumenMes(tecnico, dias);
                tbody.querySelectorAll(".mx-profile").forEach(function (el) { el.classList.remove("is-summary-selected"); });
                this.classList.add("is-summary-selected");
            }
            perfil.addEventListener("click", seleccionarPerfil);
            perfil.addEventListener("keydown", function (event) {
                if (event.key === "Enter" || event.key === " ") { event.preventDefault(); seleccionarPerfil.call(this); }
            });
        });
        var resumenId = sel || state.resumenTecnico || (tecs[0] && tecs[0].id);
        var resumenTec = tecs.filter(function (t) { return String(t.id) === String(resumenId); })[0] || tecs[0];
        state.resumenTecnico = resumenTec ? String(resumenTec.id) : "";
        renderResumenMes(resumenTec, dias);
        var perfilActivo = tbody.querySelector('[data-resumen-tecnico="' + state.resumenTecnico + '"]');
        if (perfilActivo) perfilActivo.classList.add("is-summary-selected");
    }

    /* ---------- disponibilidad de los demás técnicos ----------
       El mismo mes que se está mirando en el calendario: para cada técnico
       que no es el que entró se listan sus marcas del mes (ausencia, falta
       o no ausencia) y sus días sin ninguna marca. Lo abre y lo cierra el
       botón «Disponibilidad de los demás» de los filtros de arriba. */
    var DISP_LABEL = {
        ausencia: "Ausencia",
        falta: "Falta de disponibilidad",
        no_ausencia: "No ausencia"
    };
    var DISP_CLASE = {
        ausencia: "d-ausencia",
        falta: "d-falta",
        no_ausencia: "d-noausencia"
    };

    function renderDispOtros() {
        var box = $("dispOtrosLista");
        if (!box) return;
        var resumen = $("dispOtrosCount");
        /* «Los demás» es respecto a quien tiene el panel abierto: si es un
           técnico se excluye a él (y al que tenga filtrado no le estorba);
           el administrador no tiene «yo», así que ve a todos. */
        var mio = state.tecnicoDef || String($("filtroTecnico").value || "");
        var tecs = (data.tecnicos || []).filter(function (t) { return String(t.id) !== mio; });
        if (resumen) {
            resumen.textContent =
                plural(tecs.length, "técnico", "técnicos") +
                " · " + MESES[state.mes - 1] + " " + state.anio;
        }
        if (!tecs.length) {
            box.innerHTML = '<div class="prog-event-empty">No hay otros técnicos que mostrar.</div>';
            return;
        }
        var dias = new Date(state.anio, state.mes, 0).getDate();
        var html = '<div class="disp-otros-scroll"><table class="disp-otros-matriz"><thead><tr><th scope="col">Técnico</th>';
        for (var h = 1; h <= dias; h++) {
            var hd = new Date(state.anio, state.mes - 1, h);
            html += '<th scope="col" title="' + esc(NOMBRES_DIA[hd.getDay()]) + '"><span>' + LETRAS[hd.getDay()] + '</span><br>' + h + '</th>';
        }
        html += '</tr></thead><tbody>';
        tecs.forEach(function (tec) {
            html += '<tr><th scope="row"><span class="disp-otros-persona">' + perfilTecnico(tec, "mx-avatar") + '<span>' + esc(tec.nombre) + '</span></span></th>';
            var d;
            for (d = 1; d <= dias; d++) {
                var dd = new Date(state.anio, state.mes - 1, d);
                var disp = data.disponibilidad[tec.id + "|" + iso(dd)];
                var est = estadoCelda(tec, dd);
                var detalle = disp ? (DISP_LABEL[disp.tipo] || disp.tipo || "Novedad") : (ESTADO_TITULO[est] || "Sin marca");
                var titulo = NOMBRES_DIA[dd.getDay()] + " " + d + " · " + tec.nombre + " — " + detalle + (disp && disp.hora ? " · " + disp.hora : "") + (disp && disp.nota ? " · " + disp.nota : "");
                html += '<td class="mx-cel td-' + esc(est) + '" title="' + esc(titulo) + '" aria-label="' + esc(titulo) + '">' + (disp ? '<span class="disp-otros-marca" aria-hidden="true">' + esc(disp.tipo === "ausencia" ? "A" : disp.tipo === "falta" ? "F" : disp.tipo === "no_ausencia" ? "D" : "•") + '</span>' : '') + '</td>';
            }
            html += '</tr>';
        });
        box.innerHTML = html + '</tbody></table></div><p class="disp-otros-ayuda">Pasa el cursor sobre cada día para ver su estado y novedades. La cuadrícula es de consulta.</p>';
    }

    /* ---------- listas ---------- */
    function renderListas() {
        construirLista({ tipo: "tarea", box: "listaTareas", cont: "tareasCount", check: true });
        construirLista({ tipo: "recordatorio", box: "listaRecordatorios", cont: "recordatoriosCount", check: false });
        construirLista({ tipo: "anuncio", box: "listaAnuncios", cont: "anunciosCount", check: false });
        asegurarAccionesSubvistas();
    }

    function asegurarAccionesSubvistas() {
        var acciones = [
            { panel: "panel-disponibilidad", tipo: "disponibilidad", texto: "Programar disponibilidad", icono: "i-clock" },
            { panel: "panel-tareas", tipo: "tarea", texto: "Nueva tarea", icono: "i-plus" },
            { panel: "panel-recordatorios", tipo: "recordatorio", texto: "Crear recordatorio", icono: "i-plus" },
            { panel: "panel-anuncios", tipo: "anuncio", texto: "Publicar anuncio", icono: "i-plus" }
        ];
        acciones.forEach(function (accion) {
            var panel = $(accion.panel);
            var cabecera = panel && panel.querySelector(".prog-list-head, .prog-chart-head");
            if (!cabecera || cabecera.querySelector(".prog-subview-action")) return;
            var boton = document.createElement("button");
            boton.type = "button";
            boton.className = "btn btn-primary btn-sm prog-subview-action";
            boton.innerHTML = '<svg class="icon"><use href="#' + accion.icono + '"/></svg> ' + accion.texto;
            boton.addEventListener("click", function () {
                var fecha = state.fechaActiva || iso(new Date(state.anio, state.mes - 1, 1));
                if (accion.tipo === "disponibilidad") abrirModalDisp(fecha);
                else abrirModalEvento(fecha, accion.tipo);
            });
            cabecera.appendChild(boton);
        });
    }

    function construirLista(cfg) {
        var box = $(cfg.box);
        $(cfg.cont).textContent = plural(
            data.eventos.filter(function (e) { return e.tipo === cfg.tipo; }).length, "elemento", "elementos");
        var items = data.eventos.filter(function (e) { return e.tipo === cfg.tipo; });
        if (!items.length) {
            box.innerHTML = '<div class="prog-event-empty">Sin ' + cfg.tipo + "s en este mes.</div>";
            return;
        }
        box.innerHTML = "";
        items.forEach(function (e) {
            var fecha = new Date(e.fecha + "T00:00:00");
            var detalleUrl = e.ticket_id ? U.detalle.replace(/0(?=\/?$)/, e.ticket_id) : null;
            if (detalleUrl) detalleUrl = U.detalle.replace(/\/0\/?$/, "/" + e.ticket_id + "/");

            var ic = '<span class="prog-ev-ic t-' + e.tipo + '"><svg class="icon"><use href="#' + ICON_BY_TIPO[e.tipo] + '"/></svg></span>';
            var titulo =
                "<strong>" +
                (detalleUrl ? '<a href="' + esc(detalleUrl) + '">' + esc(e.titulo) + "</a>" : esc(e.titulo)) +
                (e.completado ? ' <span class="prog-chip ct-tarea done">Completada</span>' : "") +
                "</strong>";

            var meta = "<b>" + NOMBRES_DIA[fecha.getDay()] + "</b> " + fecha.getDate() + " de " + MESES[fecha.getMonth()] +
                (e.hora ? " · <b>" + esc(e.hora) + "</b>" : "") +
                (e.tecnico ? " · " + esc(e.tecnico) : ' · <span style="font-style:italic">General</span>') +
                (e.sitio ? " · " + esc(e.sitio) : "") +
                (e.grupo ? " · " + esc(e.grupo) : "");

            var item = document.createElement("div");
            item.className = "prog-ev-item";
            item.innerHTML =
                ic +
                '<div class="prog-ev-body"><div class="prog-ev-title">' + titulo + "</div>" +
                '<div class="prog-ev-meta">' + meta + "</div>" +
                (e.descripcion ? '<div class="prog-ev-desc">' + esc(e.descripcion) + "</div>" : "") +
                "</div>" +
                '<div class="prog-ev-actions">' +
                (cfg.check ? '<input type="checkbox" class="prog-ev-check" ' + (e.completado ? "checked" : "") + ' data-evento="' + e.id + '" title="Marcar completada">' : "") +
                (e.puede_editar ? '<button type="button" class="prog-ev-del" data-eliminar="' + e.id + '" title="Eliminar"><svg class="icon"><use href="#i-trash"/></svg></button>' : "") +
                "</div>";
            box.appendChild(item);
        });

        box.querySelectorAll(".prog-ev-check").forEach(function (cb) {
            cb.addEventListener("change", function () {
                post(U.completado, { id: this.dataset.evento, completado: this.checked ? "1" : "0" }, load);
            });
        });
        box.querySelectorAll(".prog-ev-del").forEach(function (btn) {
            btn.addEventListener("click", function () {
                if (!confirm("¿Eliminar este evento?")) return;
                post(U.eliminar, { id: this.dataset.eliminar }, function () { toast("Evento eliminado", true); load(); });
            });
        });
    }

    /* ---------- modales ---------- */
    var focoAnterior = null;
    var estadoInicial = "";
    function firmaFormulario(form) { return form ? new URLSearchParams(new FormData(form)).toString() : ""; }
    function abrirModal(id) {
        focoAnterior = document.activeElement;
        var modal = $(id);
        modal.classList.add("open");
        if (id === "modalEvento" || id === "modalDisp") {
            estadoInicial = firmaFormulario(modal.querySelector("form"));
            document.body.classList.add("prog-modal-abierto");
        }
    }
    function cerrarModales() {
        cerrarSelector(false);
        document.querySelectorAll(".modal-overlay.open").forEach(function (m) { m.classList.remove("open"); });
        document.body.classList.remove("prog-modal-abierto");
        if (focoAnterior && focoAnterior.isConnected) focoAnterior.focus();
    }

    function mostrarDialogo(titulo, mensaje, detalles, acciones, tono) {
        var overlay = document.createElement("div");
        overlay.className = "prog-confirm-overlay";
        overlay.setAttribute("role", "dialog");
        overlay.setAttribute("aria-modal", "true");
        overlay.setAttribute("aria-labelledby", "prog-confirm-titulo");
        var iconoDialogo = tono === "danger" ? "i-trash" : tono === "warning" ? "i-alert" : "i-check-circle";
        overlay.innerHTML = '<div class="prog-confirm-box" data-tono="' + esc(tono || "success") + '"><span class="prog-confirm-icon"><svg class="icon"><use href="#' + iconoDialogo + '"/></svg></span><h2 id="prog-confirm-titulo">' + esc(titulo) + '</h2><p>' + esc(mensaje) + '</p>' + (detalles.length ? '<dl>' + detalles.map(function (dato) { return '<div><dt>' + esc(dato[0]) + '</dt><dd>' + esc(dato[1] || "—") + '</dd></div>'; }).join("") + '</dl>' : "") + '<div class="prog-confirm-actions">' + acciones.map(function (accion, i) { return '<button type="button" class="btn ' + (accion.primaria ? 'btn-primary' : 'btn-outline') + '" data-confirm-action="' + i + '">' + esc(accion.texto) + '</button>'; }).join("") + '</div></div>';
        document.body.appendChild(overlay);
        document.body.classList.add("prog-modal-abierto");
        function cerrar() { overlay.remove(); if (!document.querySelector(".prog-modal.open")) document.body.classList.remove("prog-modal-abierto"); }
        overlay.addEventListener("click", function (e) {
            var boton = e.target.closest("[data-confirm-action]");
            if (!boton) return;
            var accion = acciones[Number(boton.dataset.confirmAction)];
            cerrar();
            if (accion.callback) accion.callback();
        });
        overlay.addEventListener("keydown", function (e) {
            if (e.key === "Escape") { e.stopPropagation(); cerrar(); if (focoAnterior && focoAnterior.isConnected) focoAnterior.focus(); }
            if (e.key === "Tab") {
                var botones = Array.from(overlay.querySelectorAll("button"));
                if (e.shiftKey && document.activeElement === botones[0]) { e.preventDefault(); botones[botones.length - 1].focus(); }
                else if (!e.shiftKey && document.activeElement === botones[botones.length - 1]) { e.preventDefault(); botones[0].focus(); }
            }
        });
        overlay.querySelector("button").focus();
    }
    function solicitarCierre(modal) {
        if (modal && modal.dataset.guardando === "1") return;
        var form = modal && modal.querySelector("form");
        if (form && (modal.id === "modalEvento" || modal.id === "modalDisp") && firmaFormulario(form) !== estadoInicial) {
            mostrarDialogo("¿Descartar cambios?", "Hay cambios sin guardar en este formulario.", [], [
                { texto: "Continuar editando", callback: function () { var campo = form.querySelector("input:not([type=hidden]), select, textarea"); if (campo) campo.focus(); } },
                { texto: "Descartar cambios", primaria: true, callback: function () { cerrarModales(); toast("Cambios descartados", true); } }
            ], "warning");
            return;
        }
        cerrarModales();
    }
    function errorCampo(campo, mensaje) {
        var etiqueta = campo && campo.closest(".corp-field");
        if (!etiqueta) return;
        var error = etiqueta.querySelector(".prog-field-error");
        if (!error) { error = document.createElement("small"); error.className = "prog-field-error"; error.setAttribute("role", "alert"); etiqueta.appendChild(error); }
        error.textContent = mensaje || "";
        error.hidden = !mensaje;
        campo.setAttribute("aria-invalid", mensaje ? "true" : "false");
    }

    /* Cada tipo de evento tiene su propio formulario: se zien distintos
       campos, con otras etiquetas y otras ayudas. Los campos viven en
       #evBiblioteca (fuera del <form>) y aqui se meten solo los del tipo
       elegido, para que lo que no aplica no se envie al servidor. */
    var FORM_TIPO = {
        tarea: {
            campos: ["titulo", "visibilidad", "tecnico", "ticket", "grupo", "prioridad", "estado", "hora", "fecha_fin", "hora_fin", "descripcion"],
            pista: "Una labor concreta para alguien, en una fecha.",
            tituloLabel: "Título", tituloPh: "Ej: Configuración de Caja 3",
            tituloAyuda: "Qué hay que hacer, en una línea.",
            tecnicoLabel: "Se asigna a", descLabel: "Detalles de la tarea",
            descPh: "Pasos, repuestos o lo que haga falta saber…",
            descAyuda: "Lo que necesite quien la atienda.", requerido: ["titulo"]
        },
        solicitud: {
            campos: ["ticket", "hora", "tecnico", "descripcion"],
            pista: "Una atención programada a partir de un ticket abierto.",
            tituloLabel: "", tituloPh: "", tituloAyuda: "",
            tecnicoLabel: "Atiende", descLabel: "Motivo de la visita",
            descPh: "Por qué se agenda esa atención…",
            descAyuda: "El título y el punto salen del ticket.",
            requerido: ["ticket"], foco: "ticket"
        },
        recordatorio: {
            campos: ["titulo", "visibilidad", "tecnico", "hora", "anticipacion", "repeticion", "descripcion"],
            pista: "Un aviso para no dejar pasar algo en esa fecha.",
            tituloLabel: "Qué recordar", tituloPh: "Ej: Renovar el antivirus del punto",
            tituloAyuda: "El asunto del recordatorio.",
            tecnicoLabel: "Se le recuerda a", descLabel: "Qué tener presente",
            descPh: "Antecedentes, fecha límite, contraseña…",
            descAyuda: "Lo que debe tener en mente ese día.",
            requerido: ["titulo", "tecnico"], foco: "titulo"
        },
        proyecto: {
            campos: ["titulo", "grupo", "visibilidad", "tecnico", "participantes", "sitio", "hora", "fecha_fin", "hora_fin", "repeticion", "descripcion"],
            pista: "Una reunión, capacitación, visita o evento de equipo.",
            tituloLabel: "Nombre del evento", tituloPh: "Ej: Capacitación de inventario",
            tituloAyuda: "Indica el asunto principal del evento.",
            tecnicoLabel: "Técnico organizador", descLabel: "Descripción y participantes",
            descPh: "Objetivo, asistentes, ubicación o enlace de reunión…",
            descAyuda: "Incluye los datos prácticos para los participantes.",
            requerido: ["titulo"], foco: "titulo"
        },
        anuncio: {
            campos: ["titulo", "descripcion", "fecha_fin", "destinatarios", "importancia"],
            pista: "Un aviso para todo el equipo, visible para todos.",
            tituloLabel: "Título del aviso", tituloPh: "Ej: Cambio de horario de soporte",
            tituloAyuda: "La idea en una línea.",
            tecnicoLabel: "", descLabel: "Mensaje",
            descPh: "Escribe el mensaje completo…",
            descAyuda: "Lo leerán todos los usuarios del panel.",
            requerido: ["titulo", "descripcion"], foco: "titulo"
        }
    };

    var MODAL_TIPO = {
        tarea: { titulo: "Programar tarea", sub: "Asigna una labor o mantenimiento", icon: "i-wrench", boton: "Crear tarea", color: "green" },
        solicitud: { titulo: "Programar atención", sub: "Vincula y agenda un ticket", icon: "i-ticket", boton: "Guardar atención", color: "red" },
        recordatorio: { titulo: "Crear recordatorio", sub: "Programa un aviso para un técnico", icon: "i-bell", boton: "Programar", color: "amber" },
        proyecto: { titulo: "Crear evento", sub: "Programa una reunión, visita o capacitación", icon: "i-calendar", boton: "Crear evento", color: "blue" },
        anuncio: { titulo: "Publicar anuncio", sub: "Comunicación visible en la agenda", icon: "i-message", boton: "Publicar anuncio", color: "violet" }
    };

    function iconoCampo(campo) {
        var etiqueta = campo.closest("[data-campo]");
        var nombre = ((etiqueta && etiqueta.dataset.campo) || "") + " " + (campo.name || "") + " " + (campo.id || "");
        if (/fecha/.test(nombre)) return "i-calendar";
        if (/hora|anticipacion/.test(nombre)) return "i-clock";
        if (/tecnico|participantes|destinatarios/.test(nombre)) return "i-users";
        if (/ticket/.test(nombre)) return "i-ticket";
        if (/prioridad/.test(nombre)) return "i-alert";
        if (/estado/.test(nombre)) return "i-check-circle";
        if (/grupo|categoria/.test(nombre)) return "i-chart";
        if (/sitio/.test(nombre)) return "i-home";
        return "i-message";
    }

    // Añade iconografía a los controles existentes sin cambiar sus names ni su envío.
    function decorarCamposModal(contenedor) {
        if (!contenedor) return;
        contenedor.querySelectorAll(".corp-field input, .corp-field select, .corp-field textarea").forEach(function (campo) {
            if (campo.closest(".prog-control-wrap")) return;
            var envoltura = document.createElement("span");
            envoltura.className = "prog-control-wrap";
            campo.parentNode.insertBefore(envoltura, campo);
            envoltura.appendChild(campo);
            envoltura.insertAdjacentHTML("afterbegin", '<span class="prog-control-icon" aria-hidden="true"><svg class="icon"><use href="#' + iconoCampo(campo) + '"/></svg></span>');
        });
    }

    var selectorAbierto = null;
    function cerrarSelector(devolverFoco) {
        if (!selectorAbierto) return;
        var actual = selectorAbierto;
        selectorAbierto = null;
        actual.menu.remove();
        actual.boton.setAttribute("aria-expanded", "false");
        if (devolverFoco && actual.boton.isConnected) actual.boton.focus();
    }
    function prepararSelectores(contenedor) {
        contenedor.querySelectorAll("select").forEach(function (select) {
            var wrap = select.closest(".prog-control-wrap");
            if (!wrap || wrap.querySelector(".prog-select-trigger")) return;
            var boton = document.createElement("button");
            boton.type = "button";
            boton.className = "prog-select-trigger";
            boton.setAttribute("aria-haspopup", "listbox");
            boton.setAttribute("aria-expanded", "false");
            var etiqueta = select.closest("label");
            boton.setAttribute("aria-label", (etiqueta && etiqueta.childNodes[0].textContent.trim()) || "Seleccionar opción");
            boton.innerHTML = '<span class="prog-select-value"></span><svg class="icon prog-select-arrow" aria-hidden="true"><use href="#i-chevron-down"/></svg>';
            wrap.appendChild(boton);
            select.classList.add("prog-select-native");
            if (select.required) { select.dataset.progRequired = "1"; select.required = false; }
            select.tabIndex = -1;
            select.setAttribute("aria-hidden", "true");
            function sincronizar() { boton.querySelector(".prog-select-value").textContent = select.selectedOptions[0] ? select.selectedOptions[0].textContent : "Seleccionar"; boton.disabled = select.disabled; }
            select.addEventListener("change", sincronizar);
            boton.addEventListener("click", function () {
                if (selectorAbierto && selectorAbierto.boton === boton) { cerrarSelector(false); return; }
                cerrarSelector(false);
                var menu = document.createElement("div");
                menu.className = "prog-select-popup";
                menu.dataset.tono = (select.closest(".prog-modal") || {}).dataset.tipo || "red";
                var opciones = Array.from(select.options);
                var buscador = opciones.length > 6 ? '<input class="prog-select-search" type="search" aria-label="Buscar opción" placeholder="Buscar…">' : "";
                menu.innerHTML = buscador + '<div class="prog-select-options" role="listbox" aria-label="' + esc(boton.getAttribute("aria-label")) + '"></div>';
                var lista = menu.querySelector(".prog-select-options");
                opciones.forEach(function (opcion, index) {
                    var elemento = document.createElement("button");
                    elemento.type = "button"; elemento.setAttribute("role", "option"); elemento.setAttribute("aria-selected", String(opcion.selected));
                    elemento.disabled = opcion.disabled; elemento.dataset.index = index;
                    elemento.innerHTML = '<span>' + esc(opcion.textContent) + '</span><span aria-hidden="true">' + (opcion.selected ? "✓" : "") + '</span>';
                    lista.appendChild(elemento);
                });
                document.body.appendChild(menu);
                var rect = boton.getBoundingClientRect();
                menu.style.width = Math.min(rect.width, window.innerWidth - 16) + "px";
                menu.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - menu.offsetWidth - 8)) + "px";
                var alto = Math.min(menu.offsetHeight, 300);
                menu.style.top = (window.innerHeight - rect.bottom >= alto || rect.top < alto ? Math.min(rect.bottom + 4, window.innerHeight - alto - 8) : rect.top - alto - 4) + "px";
                boton.setAttribute("aria-expanded", "true");
                selectorAbierto = { menu: menu, boton: boton };
                menu.addEventListener("click", function (e) {
                    var elegido = e.target.closest('[role="option"]');
                    if (!elegido || elegido.disabled) return;
                    select.selectedIndex = Number(elegido.dataset.index);
                    select.dispatchEvent(new Event("change", { bubbles:true }));
                    cerrarSelector(true);
                });
                var buscar = menu.querySelector("input");
                if (buscar) buscar.addEventListener("input", function () { lista.querySelectorAll('[role="option"]').forEach(function (opcion) { opcion.hidden = opcion.textContent.toLocaleLowerCase().indexOf(buscar.value.toLocaleLowerCase()) === -1; }); });
                menu.addEventListener("keydown", function (e) {
                    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cerrarSelector(true); return; }
                    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
                    e.preventDefault();
                    var visibles = Array.from(lista.querySelectorAll('[role="option"]')).filter(function (nodo) { return !nodo.hidden && !nodo.disabled; });
                    if (!visibles.length) return;
                    var indice = visibles.indexOf(document.activeElement);
                    visibles[(indice + (e.key === "ArrowDown" ? 1 : -1) + visibles.length) % visibles.length].focus();
                });
                if (buscar) buscar.focus(); else { var activo = lista.querySelector('[aria-selected="true"]:not(:disabled)') || lista.querySelector('[role="option"]:not(:disabled)'); if (activo) activo.focus(); }
            });
            boton.addEventListener("keydown", function (e) {
                if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); if (!selectorAbierto) boton.click(); }
            });
            boton.sincronizar = sincronizar;
            sincronizar();
        });
    }
    function sincronizarSelectores(contenedor) { contenedor.querySelectorAll(".prog-select-trigger").forEach(function (boton) { if (boton.sincronizar) boton.sincronizar(); }); }
    function actualizarDestinatarios() {
        var cuerpo = $("evCuerpo");
        var selector = cuerpo.querySelector('[name="meta_visibilidad"]');
        var tecnico = cuerpo.querySelector('[data-campo="tecnico"]');
        if (!selector || !tecnico) { if (tecnico) { tecnico.hidden = false; $("evTecnico").disabled = false; sincronizarSelectores(tecnico); } return; }
        var todos = selector.value === "todos";
        tecnico.hidden = todos;
        $("evTecnico").disabled = todos;
        if (todos) errorCampo($("evTecnico"), "");
        sincronizarSelectores(tecnico);
    }

    function pintarFormTipo(tipo) {
        var cfg = FORM_TIPO[tipo] || FORM_TIPO.tarea;
        var cuerpo = $("evCuerpo");
        var biblio = $("evBiblioteca");

        // Se vacía el cuerpo y se devuelven todos los campos a la biblioteca.
        while (cuerpo.firstChild) biblio.appendChild(cuerpo.firstChild);

        cfg.campos.forEach(function (nombre) {
            var nodo = biblio.querySelector('[data-campo="' + nombre + '"]');
            if (nodo) cuerpo.appendChild(nodo);
        });

        // La tarea usa dos columnas reales: responsable/solicitud y
        // categoría/prioridad. Los otros formularios conservan el ancho total
        // del selector cuando corresponde.
        var vinculo = cuerpo.querySelector('[data-campo="ticket"]');
        if (vinculo) vinculo.classList.toggle("corp-field-full", tipo !== "tarea");

        // Etiquetas y ayudas propias de cada tipo.
        $("evPista").textContent = cfg.pista;
        $("evTituloLabel").textContent = cfg.tituloLabel || "Título";
        $("evTitulo").placeholder = cfg.tituloPh || "";
        $("evTituloAyuda").textContent = cfg.tituloAyuda || "";
        $("evTecnicoLabel").textContent = cfg.tecnicoLabel || "Técnico";
        $("evDescLabel").textContent = cfg.descLabel || "Descripción";
        $("evDescAyuda").textContent = cfg.descAyuda || "";
        $("evCuerpo").querySelector("textarea").placeholder = cfg.descPh || "";

        var wrapFecha = $("evFechaWrap");
        wrapFecha.childNodes[0].nodeValue = tipo === "anuncio" ? "Visible desde" : "Fecha";

        $("evGrupoLabel").textContent = tipo === "proyecto" ? "Tipo de evento" : "Categoría";

        cuerpo.dataset.requerido = (cfg.requerido || []).join(",");
        cuerpo.dataset.foco = cfg.foco || "titulo";
        cuerpo.querySelectorAll("[data-campo]").forEach(function (nodo) { nodo.classList.remove("is-required"); });
        (cfg.requerido || []).forEach(function (nombre) {
            var requerido = cuerpo.querySelector('[data-campo="' + nombre + '"]');
            if (requerido) requerido.classList.add("is-required");
        });
        var visual = MODAL_TIPO[tipo] || MODAL_TIPO.tarea;
        $("eventoTitulo").textContent = visual.titulo;
        $("eventoSub").textContent = visual.sub;
        $("evModalIcon").innerHTML = '<svg class="icon"><use href="#' + visual.icon + '"/></svg>';
        $("modalEvento").dataset.tipo = visual.color;
        $("evGuardar").innerHTML = '<svg class="icon"><use href="#' + (tipo === "recordatorio" ? "i-bell" : tipo === "anuncio" ? "i-send" : "i-check") + '"/></svg> ' + visual.boton;
        decorarCamposModal(cuerpo);
        decorarCamposModal(wrapFecha.parentNode);
        prepararSelectores($("formEvento"));
        actualizarDestinatarios();
        return cfg;
    }

    function abrirModalEvento(fecha, tipo) {
        $("formEvento").dataset.editarId = "";
        $("evFecha").value = fecha;
        $("evFechaShow").value = fecha;
        if (tipo && TIPOS_EVENTO.indexOf(tipo) !== -1) $("evTipo").value = tipo;

        var tipoSel = $("evTipo").value;
        var cfg = pintarFormTipo(tipoSel);
        $("modalEvento").classList.toggle("is-type-fixed", Boolean(tipo));

        // Se limpian solo los campos que este tipo usa.
        $("evTitulo").value = "";
        $("evHora").value = "";
        $("evSitio").value = "";
        $("evGrupo").value = "";
        $("evTicket").value = "";
        $("evTecnico").value = tipoSel === "anuncio" ? "" : ($("filtroTecnico").value || "");
        $("evCuerpo").querySelector("textarea").value = "";
        document.querySelectorAll('#evBiblioteca [name^="meta_"], #evCuerpo [name^="meta_"]').forEach(function (campo) {
            if (campo.tagName === "SELECT") campo.selectedIndex = 0;
            else campo.value = "";
        });
        sincronizarSelectores($("formEvento"));
        actualizarDestinatarios();

        abrirModal("modalEvento");
        var foco = $("evCuerpo").querySelector('[data-campo="' + (cfg.foco || "titulo") + '"]');
        if (foco) {
            var input = foco.querySelector("input:not([type=hidden]), .prog-select-trigger, textarea, select:not(.prog-select-native)");
            if (input) input.focus();
        }
    }

    /* ---------- detalle completo de un día o de un evento ---------- */
    function marcasDisponibilidad(fecha) {
        return Object.keys(data.disponibilidad || {}).filter(function (clave) {
            return clave.slice(-(fecha.length + 1)) === "|" + fecha;
        }).map(function (clave) {
            var marca = data.disponibilidad[clave] || {};
            var tecnicoId = clave.slice(0, clave.lastIndexOf("|"));
            var tecnico = (data.tecnicos || []).filter(function (item) { return String(item.id) === String(tecnicoId); })[0];
            return {
                id: marca.id,
                tecnicoId: tecnicoId,
                tecnico: tecnico ? tecnico.nombre : "Técnico asignado",
                tipo: marca.tipo || "",
                hora: marca.hora || "",
                nota: marca.nota || "",
                creadoPor: marca.creado_por || "",
                lecturas: marca.lecturas || [],
                raw: marca
            };
        });
    }

    function estadoEvento(ev) {
        return ev.completado ? "Completado" : "Pendiente";
    }

    var menuEventoAbierto = null;
    function cerrarMenuEvento(enfocar) {
        if (!menuEventoAbierto) return;
        var menu = menuEventoAbierto;
        menuEventoAbierto = null;
        menu.panel.remove();
        menu.boton.setAttribute("aria-expanded", "false");
        if (enfocar && menu.boton.isConnected) menu.boton.focus();
    }
    function abrirMenuEvento(boton, evento, fecha) {
        if (menuEventoAbierto && menuEventoAbierto.boton === boton) { cerrarMenuEvento(true); return; }
        cerrarMenuEvento(false);
        var panel = document.createElement("div");
        panel.className = "prog-side-action-popover";
        panel.setAttribute("role", "menu");
        panel.setAttribute("aria-label", "Opciones del evento");
        var items = [{ id:"detalle", icono:"i-eye", texto:"Ver detalle" }];
        if (evento.tipo === "anuncio" && evento.puede_editar_anuncio) items.push({ id:"editar", icono:"i-edit", texto:"Editar anuncio" });
        if (evento.puede_editar) items.push({ id:"eliminar", icono:"i-trash", texto:"Eliminar evento" });
        panel.innerHTML = items.map(function (item) { return '<button type="button" role="menuitem" data-action="' + item.id + '" class="' + (item.id === "eliminar" ? "is-danger" : "") + '"><svg class="icon" aria-hidden="true"><use href="#' + item.icono + '"/></svg>' + esc(item.texto) + '</button>'; }).join("");
        document.body.appendChild(panel);
        var caja = boton.getBoundingClientRect();
        panel.style.left = Math.max(8, Math.min(caja.right - panel.offsetWidth, window.innerWidth - panel.offsetWidth - 8)) + "px";
        panel.style.top = (caja.bottom + panel.offsetHeight + 8 <= window.innerHeight ? caja.bottom + 4 : Math.max(8, caja.top - panel.offsetHeight - 4)) + "px";
        boton.setAttribute("aria-expanded", "true");
        menuEventoAbierto = { panel: panel, boton: boton };
        panel.addEventListener("click", function (e) {
            var opcion = e.target.closest("[data-action]");
            if (!opcion) return;
            cerrarMenuEvento(false);
            if (opcion.dataset.action === "detalle") abrirModalDetalle(evento, fecha);
            if (opcion.dataset.action === "editar") {
                abrirModalDetalle(evento, fecha);
                var editar = $("detalleEventoAcciones").querySelector("[data-det-editar]");
                if (editar) editar.click();
            }
            if (opcion.dataset.action === "eliminar") mostrarDialogo("¿Eliminar este evento?", "El registro se eliminará del calendario. Esta acción no se puede deshacer.", [["Título", evento.titulo], ["Tipo", evento.tipo_label || "Evento"], ["Fecha", evento.fecha ? formatFecha(evento.fecha) : "Sin fecha"], ["Hora", evento.hora || "Sin hora definida"]], [
                { texto:"Cancelar", callback:function () { if (boton.isConnected) boton.focus(); } },
                { texto:"Eliminar", primaria:true, callback:function () { post(U.eliminar, { id:evento.id }, function () { toast("Evento eliminado", true); load(); }); } }
            ], "danger");
        });
        panel.addEventListener("keydown", function (e) {
            var botones = Array.from(panel.querySelectorAll('[role="menuitem"]'));
            if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cerrarMenuEvento(true); }
            else if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); var index = botones.indexOf(document.activeElement); botones[(index + (e.key === "ArrowDown" ? 1 : -1) + botones.length) % botones.length].focus(); }
            else if (e.key === "Tab") cerrarMenuEvento(false);
        });
        panel.querySelector("button").focus();
    }

    function indicadorLecturas(ev) {
        var lectores = ev.lecturas || [];
        if (!lectores.length) return '<span class="prog-det-leidos" data-evento-lecturas="' + esc(ev.id) + '" hidden></span>';
        var texto = lectores.length === 1 ? "Leído por " + lectores[0] : "Leído por " + lectores.length + " técnicos";
        return '<span class="prog-det-leidos" data-evento-lecturas="' + esc(ev.id) + '" title="' + esc(texto) + '"><svg class="icon"><use href="#i-check-circle"/></svg><span>' + lectores.length + '</span></span>';
    }

    function registrarLecturaEvento(ev) {
        if (!ev || !ev.id || !U.eventoLeido) return;
        post(U.eventoLeido, { id: ev.id }, function (res) {
            ev.lecturas = res.lecturas || [];
            document.querySelectorAll('[data-evento-lecturas="' + ev.id + '"]').forEach(function (nodo) {
                nodo.outerHTML = indicadorLecturas(ev);
            });
        });
    }

    function indicadorLecturasDisponibilidad(marca) {
        if (!marca || !marca.id) return "";
        var lectores = marca.lecturas || [];
        if (!lectores.length) return '<span class="prog-det-leidos" data-disponibilidad-lecturas="' + esc(marca.id) + '" hidden></span>';
        var texto = lectores.length === 1 ? "Leída por " + lectores[0] : "Leída por " + lectores.length + " técnicos";
        return '<span class="prog-det-leidos" data-disponibilidad-lecturas="' + esc(marca.id) + '" title="' + esc(texto) + '"><svg class="icon"><use href="#i-check-circle"/></svg><span>' + lectores.length + '</span></span>';
    }

    function registrarLecturaDisponibilidad(marca) {
        if (!marca || !marca.id || !U.dispLeida) return;
        post(U.dispLeida, { id: marca.id }, function (res) {
            marca.lecturas = res.lecturas || [];
            document.querySelectorAll('[data-disponibilidad-lecturas="' + marca.id + '"]').forEach(function (nodo) {
                nodo.outerHTML = indicadorLecturasDisponibilidad(marca);
            });
        });
    }

    function metadatosEvento(ev) {
        var etiquetas = { prioridad: "Prioridad", estado: "Estado", repeticion: "Repetición", anticipacion: "Anticipación", participantes: "Participantes", fecha_fin: "Fecha límite", hora_fin: "Hora final", destinatarios: "Destinatarios", importancia: "Importancia" };
        return Object.keys(ev.metadatos || {}).filter(function (clave) { return ev.metadatos[clave] !== "" && etiquetas[clave]; }).map(function (clave) {
            return '<dt>' + etiquetas[clave] + '</dt><dd>' + esc(ev.metadatos[clave]) + '</dd>';
        }).join("");
    }

    function filaDetalleEvento(ev, incluirConfirmacion) {
        var recibido = !!ev.completado;
        var estado = estadoEvento(ev);
        return '<article class="prog-det-evento ct-' + esc(ev.tipo) + (recibido ? " is-recibido" : "") + '">' +
            '<button type="button" class="prog-det-abrir" data-det-id="' + esc(ev.id) + '"><span class="prog-det-evento-icon"><svg class="icon"><use href="#' + (ICON_BY_TIPO[ev.tipo] || "i-calendar") + '"/></svg></span><span><strong>' + esc(ev.titulo) + '</strong><small>' + esc(ev.tipo_label || "Evento") + (ev.hora ? " · " + esc(ev.hora) : " · Sin hora") + (ev.tecnico ? " · " + esc(ev.tecnico) : " · General") + '</small></span>' + indicadorLecturas(ev) + '</button>' +
            '<span class="prog-det-estado' + (recibido ? " is-recibido" : "") + '"><svg class="icon"><use href="#' + (recibido ? "i-check-circle" : "i-clock") + '"/></svg>' + estado + '</span>' +
        '</article>';
    }

    function bloqueDisponibilidad(fecha) {
        var marcas = marcasDisponibilidad(fecha);
        var festivo = (data.festivos || {})[fecha];
        var contenido = marcas.length ? '<ul class="prog-det-disponibilidad-lista">' + marcas.map(function (marca) {
            var etiqueta = DISP_LABEL[marca.tipo] || "Marca registrada";
            var icono = marca.tipo === "ausencia" ? "i-alert" : marca.tipo === "falta" ? "i-clock" : "i-check-circle";
            return '<li class="is-' + esc(marca.tipo) + '"><span><svg class="icon"><use href="#' + icono + '"/></svg></span><div><strong>' + esc(marca.tecnico) + '</strong><small>' + esc(etiqueta) + (marca.hora ? " · Desde " + esc(marca.hora) : " · Todo el día") + (marca.nota ? " · " + esc(marca.nota) : "") + (marca.creadoPor ? " · Registrada por " + esc(marca.creadoPor) : "") + '</small></div>' + indicadorLecturasDisponibilidad(marca.raw) + '</li>';
        }).join("") + '</ul>' : '<p class="prog-det-vacio">No hay marcas de disponibilidad registradas para esta fecha.</p>';
        return '<section class="prog-det-bloque"><div class="prog-det-bloque-head"><span class="prog-det-bloque-icon"><svg class="icon"><use href="#i-calendar-check"/></svg></span><div><b>Disponibilidad</b><small>' + (marcas.length ? marcas.length + " marca" + (marcas.length === 1 ? "" : "s") + " registrada" + (marcas.length === 1 ? "" : "s") : "Sin marcas") + '</small></div></div>' + (festivo ? '<p class="prog-det-festivo"><svg class="icon"><use href="#i-calendar"/></svg> Festivo: ' + esc(festivo) + '</p>' : "") + contenido + '</section>';
    }

    function abrirModalDetalle(evento, fecha, lista) {
        var overlay = $("modalDetalleEvento");
        var cuerpo = $("detalleEventoCuerpo");
        var titulo = $("detalleEventoTitulo");
        var pie = $("detalleEventoAcciones");
        var esDiaCompleto = !evento && Array.isArray(lista);
        overlay.classList.toggle("is-announcement-detail", !!evento && evento.tipo === "anuncio");
        overlay.hidden = false;

        if (esDiaCompleto) {
            var eventosDia = lista || [];
            titulo.textContent = "Día completo · " + formatFecha(fecha);
            cuerpo.innerHTML = (eventosDia.length ? '<div class="prog-det-resumen"><span><b>' + eventosDia.length + '</b><small>Eventos</small></span><span><b>' + eventosDia.filter(function (ev) { return ev.tipo === "tarea" && !ev.completado; }).length + '</b><small>Tareas pendientes</small></span><span><b>' + eventosDia.filter(function (ev) { return ev.completado; }).length + '</b><small>Confirmados</small></span></div>' : '') + bloqueDisponibilidad(fecha) + (eventosDia.length ? '<section class="prog-det-bloque"><div class="prog-det-bloque-head"><span class="prog-det-bloque-icon is-evento"><svg class="icon"><use href="#i-calendar"/></svg></span><div><b>Eventos del día</b><small>Abre un evento para ver toda su información</small></div></div><div class="prog-det-eventos">' + eventosDia.map(function (ev) { return filaDetalleEvento(ev, true); }).join("") + '</div></section>' : '');
            pie.innerHTML = '<button type="button" class="btn btn-ghost btn-sm" data-det-cerrar>Cerrar</button>';
        } else if (evento && evento.tipo === "anuncio") {
            var anuncio = evento, meta = anuncio.metadatos || {};
            var fechas = /^\d{4}-\d{2}-\d{2}$/;
            var importancia = { normal: "Normal", importante: "Importante", urgente: "Urgente", baja: "Baja", alta: "Alta" };
            var destinos = { todos: "Todos", tecnicos: "Técnicos específicos", administradores: "Administradores" };
            function fila(icono, etiqueta, valor, clase) { return '<dt><svg class="icon"><use href="#' + icono + '"/></svg>' + esc(etiqueta) + '</dt><dd' + (clase ? ' class="' + esc(clase) + '"' : '') + '>' + valor + '</dd>'; }
            titulo.textContent = "Anuncio";
            cuerpo.innerHTML = '<div class="prog-anuncio-status"><svg class="icon"><use href="#i-check-circle"/></svg><span><strong>Anuncio registrado</strong><small>Información guardada en el calendario.</small></span>' + indicadorLecturas(anuncio) + '</div><h4 class="prog-anuncio-title">' + esc(anuncio.titulo || "Sin título") + '</h4><dl class="prog-anuncio-data">' + fila("i-calendar", "Fecha y hora", esc(formatFecha(anuncio.fecha || fecha) + (anuncio.hora ? " · " + anuncio.hora : " · Sin hora definida"))) + fila("i-user", "Responsable", esc(anuncio.tecnico || "Evento general")) + fila("i-clock", "Estado", '<span class="prog-det-estado' + (anuncio.completado ? ' is-recibido' : '') + '">' + esc(estadoEvento(anuncio)) + '</span>') + fila("i-calendar-check", "Fecha límite", esc(meta.fecha_fin ? (fechas.test(meta.fecha_fin) ? formatFecha(meta.fecha_fin) : meta.fecha_fin) : "No definida")) + fila("i-users", "Destinatarios", esc(destinos[meta.destinatarios] || meta.destinatarios || "No especificados")) + fila("i-alert", "Importancia", esc(importancia[meta.importancia] || meta.importancia || "No especificada"), "importance-" + (meta.importancia || "normal")) + fila("i-file", "Detalle", esc(anuncio.descripcion || "Sin detalle"), "prog-anuncio-description") + '</dl>';
            pie.innerHTML = (anuncio.puede_editar_anuncio ? '<button type="button" class="btn btn-outline" data-det-editar="' + esc(anuncio.id) + '"><svg class="icon"><use href="#i-edit"/></svg> Editar registro</button>' : '') + '<button type="button" class="btn prog-anuncio-add" data-det-otro="anuncio" data-det-fecha="' + esc(fecha) + '"><svg class="icon"><use href="#i-plus"/></svg> Agregar otro</button><button type="button" class="btn btn-ghost" data-det-cerrar>Cerrar</button>';
        } else {
            var ev = evento || (lista && lista[0]) || {};
            var recibido = !!ev.completado;
            titulo.textContent = ev.tipo_label || "Evento";
            cuerpo.innerHTML = '<p class="prog-det-titulo">' + esc(ev.titulo || "Sin título") + indicadorLecturas(ev) + '</p><dl class="prog-det-datos"><dt>Fecha y hora</dt><dd>' + esc(formatFecha(ev.fecha || fecha)) + (ev.hora ? " · " + esc(ev.hora) : " · Sin hora definida") + '</dd>' + (ev.tecnico ? '<dt>Técnico</dt><dd>' + esc(ev.tecnico) + '</dd>' : '<dt>Responsable</dt><dd>Evento general</dd>') + (ev.sitio ? '<dt>Punto de venta</dt><dd>' + esc(ev.sitio) + '</dd>' : '') + (ev.grupo ? '<dt>Grupo</dt><dd>' + esc(ev.grupo) + '</dd>' : '') + (ev.ticket_codigo ? '<dt>Solicitud</dt><dd>' + esc(ev.ticket_codigo) + '</dd>' : '') + '<dt>Estado</dt><dd><span class="prog-det-estado' + (recibido ? " is-recibido" : "") + '"><svg class="icon"><use href="#' + (recibido ? "i-check-circle" : "i-clock") + '"/></svg>' + estadoEvento(ev) + '</span></dd>' + metadatosEvento(ev) + (ev.descripcion ? '<dt>Detalle</dt><dd class="prog-det-descripcion">' + esc(ev.descripcion) + '</dd>' : '') + '</dl>';
            pie.innerHTML = (ev.ticket_id ? '<a class="btn btn-ghost btn-sm" href="' + U.detalle.replace("/0/", "/" + ev.ticket_id + "/") + '" target="_blank" rel="noopener">Ver solicitud</a>' : "") + '<button type="button" class="btn btn-accent btn-sm" data-det-otro="' + esc(ev.tipo || "") + '" data-det-fecha="' + esc(fecha) + '">Agregar otro</button><button type="button" class="btn btn-ghost btn-sm" data-det-cerrar>Cerrar</button>';
        }
        overlay.classList.add("open");
        if (evento) registrarLecturaEvento(evento);
        if (esDiaCompleto) marcasDisponibilidad(fecha).forEach(function (marca) {
            registrarLecturaDisponibilidad(marca.raw);
        });
    }

    function cerrarDetalle() {
        $("modalDetalleEvento").classList.remove("open");
    }

    function cargarDispLabel() {
        var key = $("dispTecnico").value + "|" + $("dispFecha").value;
        var disp = data.disponibilidad[key];
        marcarDisp(disp ? disp.tipo : "");
        $("dispQuitar").hidden = !disp;
        $("dispNota").value = disp ? (disp.nota || "") : "";
        $("dispHora").value = disp ? (disp.hora || "") : "";
    }
    function marcarDisp(tipo) {
        $("dispTipo").value = tipo || "";
        $("dispGuardarBtn").disabled = !tipo;
        document.querySelectorAll(".prog-disp-tipo").forEach(function (b) {
            b.classList.toggle("is-selected", b.dataset.tipo === tipo);
            b.setAttribute("aria-pressed", String(b.dataset.tipo === tipo));
        });
    }
    function abrirModalDisp(fecha, tipo, tecId) {
        $("dispFecha").value = fecha;
        var tec = tecId || $("filtroTecnico").value;
        $("dispTecnico").value = tec || ($("dispTecnico").options.length > 1 ? $("dispTecnico").options[1].value : "");
        cargarDispLabel();
        if (tipo) marcarDisp(tipo);
        sincronizarSelectores($("formDisp"));
        abrirModal("modalDisp");
        var focoDisp = $("formDisp").querySelector(".prog-select-trigger, input:not([type=hidden])");
        if (focoDisp) focoDisp.focus();
    }
    function abrirModalFestivo(fecha) {
        $("festivoFecha").value = fecha;
        $("festivoFechaShow").textContent = formatFecha(fecha);
        $("festivoNombre").value = data.festivos[fecha] || "";
        abrirModal("modalFestivo");
    }

    /* ---------- bindings ---------- */
    function bind() {
        decorarCamposModal($("modalDisp"));
        prepararSelectores($("formDisp"));
        document.addEventListener("pointerdown", function (e) { if (selectorAbierto && !selectorAbierto.menu.contains(e.target) && !selectorAbierto.boton.contains(e.target)) cerrarSelector(false); });
        document.addEventListener("pointerdown", function (e) { if (menuEventoAbierto && !menuEventoAbierto.panel.contains(e.target) && !menuEventoAbierto.boton.contains(e.target)) cerrarMenuEvento(false); });
        window.addEventListener("resize", function () { cerrarMenuEvento(false); });
        document.addEventListener("scroll", function (e) { if (menuEventoAbierto && !menuEventoAbierto.panel.contains(e.target)) cerrarMenuEvento(false); }, true);
        window.addEventListener("resize", function () { cerrarSelector(false); });
        document.addEventListener("scroll", function (e) { if (selectorAbierto && !selectorAbierto.menu.contains(e.target)) cerrarSelector(false); }, true);
        function actualizarLeyendaCalendario(tabActiva) {
            var leyenda = $("matrixLegend");
            if (!leyenda) { return; }
            /* La leyenda describe los colores de las celdas del calendario y
               de la matriz de disponibilidad; no aplica a las listas de
               tareas, recordatorios ni anuncios. */
            leyenda.hidden = tabActiva !== "programador" && tabActiva !== "disponibilidad";
        }
        document.querySelectorAll(".prog-tab").forEach(function (tab) {
            tab.addEventListener("click", function () {
                var name = this.dataset.tab;
                document.querySelectorAll(".prog-tab").forEach(function (t) {
                    t.classList.toggle("is-active", t === tab);
                });
                document.querySelectorAll(".prog-panel").forEach(function (p) {
                    p.classList.toggle("is-active", p.dataset.tabpanel === name);
                });
                actualizarLeyendaCalendario(name);
            });
        });
        actualizarLeyendaCalendario("programador");

        var filtroTecnico = $("filtroTecnico");
        var techPicker = $("techPicker"), techMenu = $("techPickerMenu"), techName = $("techPickerName");
        var solicitudEstadosTecnicos = 0;
        function cargarEstadosTecnicos() {
            var fecha = state.fechaActiva || iso(new Date());
            var partes = fecha.split("-");
            var solicitud = ++solicitudEstadosTecnicos;
            var items = techMenu.querySelectorAll('[data-tech-value]:not([data-tech-value=""])');
            items.forEach(function (item) {
                var estado = item.querySelector('.prog-tech-option-status');
                if (!estado) { estado = document.createElement('span'); estado.className = 'prog-tech-option-status'; item.appendChild(estado); }
                estado.textContent = 'Consultando…'; estado.dataset.estado = 'sin-marca';
            });
            fetch(U.datos + query({ anio: partes[0], mes: partes[1], tecnico_id: '' }), { headers: { Accept: 'application/json' } })
                .then(function (r) { if (!r.ok) throw new Error('No disponible'); return r.json(); })
                .then(function (res) {
                    if (solicitud !== solicitudEstadosTecnicos) return;
                    if (!res.ok) throw new Error('No se pudo consultar');
                    items.forEach(function (item) {
                        var marca = (res.disponibilidad || {})[item.dataset.techValue + '|' + fecha];
                        var estados = { ausencia: ['No disponible', 'ausencia'], falta: ['Ocupado', 'ocupado'], no_ausencia: ['Disponible', 'disponible'] };
                        var tecnico = (res.tecnicos || []).find(function (t) { return String(t.id) === item.dataset.techValue; });
                        var diaSemana = new Date(Number(partes[0]), Number(partes[1]) - 1, Number(partes[2])).getDay();
                        var valor = (res.festivos || {})[fecha] || diaSemana === 0 || diaSemana === 6
                            ? ['No disponible', 'ausencia']
                            : marca && estados[marca.tipo] ? estados[marca.tipo]
                            : !tecnico ? ['Sin datos', 'sin-marca']
                            : tecnico.activo ? ['Disponible', 'disponible'] : ['No disponible', 'ausencia'];
                        var estado = item.querySelector('.prog-tech-option-status');
                        estado.textContent = valor[0]; estado.dataset.estado = valor[1];
                        estado.title = 'Disponibilidad para ' + formatFecha(fecha);
                    });
                }).catch(function () {
                    if (solicitud !== solicitudEstadosTecnicos) return;
                    items.forEach(function (item) { item.querySelector('.prog-tech-option-status').textContent = 'Sin conexión'; });
                });
        }
        function sincronizarSelectorTecnico() {
            var opcion = filtroTecnico.options[filtroTecnico.selectedIndex];
            if (techName) techName.textContent = opcion ? opcion.textContent : "Todos los técnicos";
            if (techMenu) techMenu.querySelectorAll("[data-tech-value]").forEach(function (item) {
                item.classList.toggle("is-selected", item.dataset.techValue === filtroTecnico.value);
                item.setAttribute("aria-selected", String(item.dataset.techValue === filtroTecnico.value));
            });
        }
        filtroTecnico.addEventListener("change", function () { sincronizarSelectorTecnico(); load(); });
        if (techPicker && techMenu) {
            techPicker.addEventListener("click", function () {
                var abierto = !techMenu.hidden;
                techMenu.hidden = abierto;
                techPicker.setAttribute("aria-expanded", String(!abierto));
                if (!abierto) cargarEstadosTecnicos();
            });
            techMenu.querySelectorAll("[data-tech-value]").forEach(function (item) {
                item.addEventListener("click", function () {
                    filtroTecnico.value = item.dataset.techValue;
                    techMenu.hidden = true;
                    techPicker.setAttribute("aria-expanded", "false");
                    filtroTecnico.dispatchEvent(new Event("change"));
                });
            });
            document.addEventListener("click", function (event) {
                if (!event.target.closest(".prog-tech-control")) {
                    techMenu.hidden = true;
                    techPicker.setAttribute("aria-expanded", "false");
                }
            });
            sincronizarSelectorTecnico();
        }

        /* Campo de disponibilidad de los demás: se abre con el botón de los
           filtros y se repinta solo al cambiar de mes o de técnico. */
        var dispOtrosBtn = $("dispOtrosBtn");
        if (dispOtrosBtn) {
            var panelDisponibilidad = $("panel-disponibilidad");
            var cabeceraDisponibilidad = panelDisponibilidad && panelDisponibilidad.querySelector(".prog-chart-head");
            var cajaDisponibilidad = $("dispOtros");
            if (document.body.classList.contains("admin-shell")) {
                // El administrador ya tiene la matriz completa; no se duplica con otra lista.
                dispOtrosBtn.remove();
                if (cajaDisponibilidad) cajaDisponibilidad.remove();
            } else {
                if (cabeceraDisponibilidad) cabeceraDisponibilidad.appendChild(dispOtrosBtn);
                if (panelDisponibilidad && cajaDisponibilidad) {
                    var matriz = panelDisponibilidad.querySelector(".tec-matrix-scroll");
                    panelDisponibilidad.insertBefore(cajaDisponibilidad, matriz || null);
                }
                dispOtrosBtn.addEventListener("click", function () {
                    var caja = $("dispOtros");
                    if (!caja) return;
                    var abrir = caja.hidden;
                    caja.hidden = !abrir;
                    dispOtrosBtn.setAttribute("aria-expanded", String(abrir));
                    if (abrir) renderDispOtros();
                });
            }
        }

        $("mesPrev").addEventListener("click", function () { moverCalendario(-1); });
        $("mesNext").addEventListener("click", function () { moverCalendario(1); });
        $("mesHoy").addEventListener("click", function () {
            var hoy = new Date();
            state.anio = hoy.getFullYear();
            state.mes = hoy.getMonth() + 1;
            state.fechaActiva = iso(hoy);
            load();
        });
        document.querySelectorAll("[data-calendar-view]").forEach(function (boton) {
            boton.addEventListener("click", function () {
                document.querySelectorAll("[data-calendar-view]").forEach(function (item) {
                    item.classList.toggle("is-active", item === boton);
                });
                state.vista = boton.dataset.calendarView;
                app.dataset.calendarView = state.vista;
                renderCalendario();
            });
        });
        var filtrosCalendario = $("progCalendarFilters");
        if (filtrosCalendario) filtrosCalendario.addEventListener("click", function () {
            $("filtroTecnico").focus();
        });
        var crearEvento = $("progCreateEvent");
        if (crearEvento) crearEvento.addEventListener("click", function () {
            abrirModalEvento(iso(new Date()), "proyecto");
        });
        var cerrarLateral = $("progSideClose");
        if (cerrarLateral) cerrarLateral.addEventListener("click", function () {
            $("progDaySide").hidden = true;
        });

        document.querySelectorAll(".modal-close, .modal-close-cancel").forEach(function (b) {
            b.addEventListener("click", function () { solicitarCierre(b.closest(".modal-overlay")); });
        });
        document.querySelectorAll(".modal-overlay").forEach(function (ov) {
            ov.addEventListener("click", function (e) { if (e.target === ov && (ov.id === "modalEvento" || ov.id === "modalDisp")) solicitarCierre(ov); });
        });
        document.addEventListener("keydown", function (event) {
            if (event.key !== "Escape") return;
            if (selectorAbierto) { event.preventDefault(); cerrarSelector(true); return; }
            var abierto = document.querySelector(".prog-modal.open");
            if (abierto && !document.querySelector(".prog-confirm-overlay")) solicitarCierre(abierto);
        });
        document.addEventListener("keydown", function (event) {
            if (event.key !== "Tab" || selectorAbierto || document.querySelector(".prog-confirm-overlay")) return;
            var modal = document.querySelector("#modalEvento.open, #modalDisp.open");
            if (!modal) return;
            var elementos = Array.from(modal.querySelectorAll('button:not([disabled]),input:not([type="hidden"]):not([disabled]):not(.prog-select-native),textarea:not([disabled]),select:not(.prog-select-native):not([disabled]),a[href]')).filter(function (el) { return el.getClientRects().length && !el.closest("[hidden]"); });
            if (!elementos.length) return;
            var primero = elementos[0], ultimo = elementos[elementos.length - 1];
            if (event.shiftKey && document.activeElement === primero) { event.preventDefault(); ultimo.focus(); }
            else if (!event.shiftKey && document.activeElement === ultimo) { event.preventDefault(); primero.focus(); }
        });

        $("evFechaShow").addEventListener("change", function () { $("evFecha").value = this.value; });

        // --- Modal de detalle del evento ---
        var detalleOv = $("modalDetalleEvento");
        if (detalleOv) {
            detalleOv.addEventListener("click", function (e) {
                if (e.target === detalleOv) { cerrarDetalle(); return; }
                if (e.target.closest("[data-det-cerrar]")) { cerrarDetalle(); return; }
                var editar = e.target.closest("[data-det-editar]");
                if (editar) {
                    var anuncioEditar = data.eventos.find(function (item) { return String(item.id) === editar.dataset.detEditar && item.tipo === "anuncio" && item.puede_editar_anuncio; });
                    if (!anuncioEditar) return;
                    cerrarDetalle();
                    abrirModalEvento(anuncioEditar.fecha, "anuncio");
                    $("formEvento").dataset.editarId = anuncioEditar.id;
                    $("evTitulo").value = anuncioEditar.titulo;
                    $("evCuerpo").querySelector('textarea[name="descripcion"]').value = anuncioEditar.descripcion || "";
                    ["fecha_fin", "destinatarios", "importancia"].forEach(function (nombre) { var campo = $("evCuerpo").querySelector('[name="meta_' + nombre + '"]'); if (campo && anuncioEditar.metadatos && anuncioEditar.metadatos[nombre] != null) campo.value = anuncioEditar.metadatos[nombre]; });
                    sincronizarSelectores($("formEvento"));
                    estadoInicial = firmaFormulario($("formEvento"));
                    $("eventoTitulo").textContent = "Editar anuncio";
                    $("evGuardar").textContent = "Guardar cambios";
                    return;
                }
                var otro = e.target.closest("[data-det-otro]");
                if (otro) {
                    // "Agregar otro": abre la creación con el mismo tipo.
                    cerrarDetalle();
                    abrirModalEvento(otro.getAttribute("data-det-fecha"), otro.getAttribute("data-det-otro"));
                    return;
                }
                var abrir = e.target.closest("[data-det-id]");
                if (abrir) {
                    var id = abrir.getAttribute("data-det-id");
                    var encontrado = (data.eventos || []).filter(function (x) {
                        return String(x.id) === id;
                    })[0];
                    if (encontrado) { abrirModalDetalle(encontrado, encontrado.fecha); }
                }
            });
        }
        $("evDispBtn").addEventListener("click", function () {
            cerrarModales();
            abrirModalDisp($("evFecha").value);
        });
        var festBtn = $("evFestivoBtn");
        if (festBtn) festBtn.addEventListener("click", function () {
            cerrarModales();
            abrirModalFestivo($("evFecha").value);
        });

        $("dispTecnico").addEventListener("change", cargarDispLabel);
        $("dispFecha").addEventListener("change", cargarDispLabel);
        document.querySelectorAll(".prog-disp-tipo").forEach(function (b) {
            b.addEventListener("click", function () { marcarDisp(this.dataset.tipo); });
        });

        $("evTipo").addEventListener("change", function () {
            pintarFormTipo(this.value);
        });
        $("evCuerpo").addEventListener("change", function (e) {
            if (e.target.name === "meta_visibilidad") actualizarDestinatarios();
        });
        [$("formEvento"), $("formDisp")].forEach(function (form) {
            form.addEventListener("input", function (e) { if (e.target.matches("input,select,textarea")) errorCampo(e.target, ""); });
            form.addEventListener("change", function (e) { if (e.target.matches("input,select,textarea")) errorCampo(e.target, ""); });
            form.addEventListener("focusout", function (e) {
                var campo = e.target;
                if (!campo.matches("input,textarea,select") || campo.type === "hidden") return;
                var etiqueta = campo.closest("[data-campo]");
                var obligatorio = campo.required || campo.dataset.progRequired === "1" || (etiqueta && etiqueta.classList.contains("is-required"));
                if (obligatorio) errorCampo(campo, String(campo.value).trim() ? "" : "Completa este campo.");
            });
        });

        $("formEvento").addEventListener("submit", function (e) {
            e.preventDefault();
            var guardarEvento = $("evGuardar");
            if (guardarEvento.disabled) return;
            var cuerpo = $("evCuerpo");
            var cfg = FORM_TIPO[$("evTipo").value] || FORM_TIPO.tarea;
            var fechaFinal = cuerpo.querySelector('[name="meta_fecha_fin"]');
            var horaFinal = cuerpo.querySelector('[name="meta_hora_fin"]');
            if (fechaFinal && fechaFinal.value && fechaFinal.value < $("evFecha").value) {
                errorCampo(fechaFinal, "La fecha final no puede ser anterior a la inicial.");
                toast("La fecha final no puede ser anterior a la fecha inicial", false);
                fechaFinal.focus();
                return;
            }
            if (horaFinal && horaFinal.value && fechaFinal && fechaFinal.value === $("evFecha").value && $("evHora").value && horaFinal.value <= $("evHora").value) {
                errorCampo(horaFinal, "La hora final debe ser posterior a la inicial.");
                toast("La hora final debe ser posterior a la inicial", false);
                horaFinal.focus();
                return;
            }

            // Solo se exigen los campos que el tipo chosen muestra.
            var faltan = [];
            (cfg.requerido || []).forEach(function (nombre) {
                var nodo = cuerpo.querySelector('[data-campo="' + nombre + '"]');
                var input = nodo && nodo.querySelector("input, select, textarea");
                if ((!input || !String(input.value).trim()) && !(nombre === "tecnico" && input && input.disabled)) {
                    if (input) errorCampo(input, "Completa este campo.");
                    var et = nodo && nodo.querySelector("span");
                    faltan.push(et ? et.textContent.trim() : nombre);
                }
            });
            var visibilidad = cuerpo.querySelector('[name="meta_visibilidad"]');
            if (visibilidad && visibilidad.value === "persona" && !$('evTecnico').value && faltan.indexOf("Destinatario") === -1) {
                errorCampo($("evTecnico"), "Selecciona una persona.");
                faltan.push("Destinatario");
            }
            if (faltan.length) {
                toast("Completa: " + faltan.join(", "), false);
                return;
            }
            guardarEvento.disabled = true;
            $("modalEvento").dataset.guardando = "1";
            var textoGuardarEvento = guardarEvento.innerHTML;
            guardarEvento.innerHTML = '<span class="prog-save-spinner" aria-hidden="true"></span> Guardando…';
            var formularioEvento = new FormData(this);
            if (this.dataset.editarId) formularioEvento.set("editar_id", this.dataset.editarId);
            var tipoEvento = formularioEvento.get("tipo");
            var detalles = [["Título", formularioEvento.get("titulo")], ["Fecha", formularioEvento.get("fecha")], ["Hora", formularioEvento.get("hora")], ["Técnico", $("evTecnico").selectedOptions[0] ? $("evTecnico").selectedOptions[0].textContent : "General"]];
            if (tipoEvento === "tarea") detalles.push(["Prioridad", formularioEvento.get("meta_prioridad")]);
            if (tipoEvento === "proyecto") detalles.push(["Participantes", formularioEvento.get("meta_participantes")]);
            if (tipoEvento === "anuncio") detalles = [["Título", formularioEvento.get("titulo")], ["Destinatarios", formularioEvento.get("meta_destinatarios")], ["Visible desde", formularioEvento.get("fecha")], ["Vigencia hasta", formularioEvento.get("meta_fecha_fin")]];
            var confirmaciones = { recordatorio: ["Recordatorio creado", "Tu recordatorio se ha programado correctamente."], tarea: ["Tarea programada", "La tarea se ha asignado correctamente."], proyecto: ["Evento creado", "El evento se ha registrado en el calendario."], anuncio: ["Anuncio publicado", "El anuncio se ha publicado correctamente."], solicitud: ["Atención programada", "La atención se ha registrado correctamente."] };
            post(U.agregar, formularioEvento, function () {
                var confirmacion = formularioEvento.get("editar_id") ? ["Anuncio actualizado", "Los cambios se guardaron correctamente."] : (confirmaciones[tipoEvento] || confirmaciones.proyecto);
                state.fechaActiva = formularioEvento.get("fecha");
                cerrarModales();
                mostrarDialogo(confirmacion[0], confirmacion[1], detalles, [{ texto: "Entendido", primaria: true, callback: function () { if (focoAnterior && focoAnterior.isConnected) focoAnterior.focus(); } }, { texto: "Ver en calendario", callback: function () { document.querySelector('[data-tab="programador"]').click(); var celda = document.querySelector('.prog-day[data-fecha="' + state.fechaActiva + '"]'); if (celda) celda.scrollIntoView({ behavior: "smooth", block: "center" }); } }], tipoEvento);
                load();
            }, function () { delete $("modalEvento").dataset.guardando; guardarEvento.disabled = false; guardarEvento.innerHTML = textoGuardarEvento; });
        });

        $("formDisp").addEventListener("submit", function (e) {
            e.preventDefault();
            var guardarDisponibilidad = $("dispGuardarBtn");
            if (guardarDisponibilidad.disabled) return;
            var fd = new FormData(this);
            if (!fd.get("tecnico_id")) { toast("Selecciona un técnico", false); return; }
            if (!fd.get("tipo")) { toast("Selecciona un tipo de disponibilidad", false); return; }
            guardarDisponibilidad.disabled = true;
            $("modalDisp").dataset.guardando = "1";
            var textoGuardarDisp = guardarDisponibilidad.innerHTML;
            guardarDisponibilidad.innerHTML = '<span class="prog-save-spinner" aria-hidden="true"></span> Guardando…';
            var nombreTecnico = $("dispTecnico").selectedOptions[0].textContent;
            var estadoDisp = DISP_LABEL[fd.get("tipo")] || fd.get("tipo");
            post(U.disp, fd, function () {
                state.fechaActiva = fd.get("fecha");
                cerrarModales();
                mostrarDialogo("Disponibilidad programada", "La disponibilidad del técnico se registró correctamente.", [["Técnico", nombreTecnico], ["Fecha", fd.get("fecha")], ["Estado", estadoDisp]], [{ texto: "Entendido", primaria: true, callback: function () { if (focoAnterior && focoAnterior.isConnected) focoAnterior.focus(); } }, { texto: "Ver en calendario", callback: function () { document.querySelector('[data-tab="programador"]').click(); var celda = document.querySelector('.prog-day[data-fecha="' + state.fechaActiva + '"]'); if (celda) celda.scrollIntoView({ behavior: "smooth", block: "center" }); } }], "disponibilidad");
                load();
            }, function () { delete $("modalDisp").dataset.guardando; guardarDisponibilidad.disabled = !$('dispTipo').value; guardarDisponibilidad.innerHTML = textoGuardarDisp; });
        });
        $("dispQuitar").addEventListener("click", function () {
            var fd = new FormData($("formDisp"));
            fd.set("tipo", "");
            post(U.disp, fd, function () {
                cerrarModales();
                toast("Marca quitada", true);
                if (fd.get("tecnico_id")) $("filtroTecnico").value = fd.get("tecnico_id");
                $("filtroTecnico").dispatchEvent(new Event("change"));
            });
        });

        var fF = $("formFestivo");
        if (fF) {
            fF.addEventListener("submit", function (e) {
                e.preventDefault();
                if (!$("festivoNombre").value.trim()) { toast("Indica el nombre del festivo", false); return; }
                post(U.festivo, new FormData(this), function () {
                    cerrarModales();
                    toast("Festivo guardado", true);
                    load();
                });
            });
            $("festivoQuitar").addEventListener("click", function () {
                var fd = new FormData($("formFestivo"));
                fd.set("quitar", "1");
                post(U.festivo, fd, function () {
                    cerrarModales();
                    toast("Festivo quitado", true);
                    load();
                });
            });
        }
    }

    function movMes(delta) {
        state.mes += delta;
        if (state.mes < 1) { state.mes = 12; state.anio--; }
        if (state.mes > 12) { state.mes = 1; state.anio++; }
        load();
    }

    function moverCalendario(delta) {
        if (state.vista === "mes") { movMes(delta); return; }
        var base = state.fechaActiva ? new Date(state.fechaActiva + "T12:00:00") : new Date(state.anio, state.mes - 1, 1);
        base.setDate(base.getDate() + (state.vista === "semana" ? 7 * delta : delta));
        state.fechaActiva = iso(base);
        state.anio = base.getFullYear();
        state.mes = base.getMonth() + 1;
        load();
    }

    /* ---------- init ---------- */
    if (state.tecnicoDef && $("filtroTecnico").querySelector('option[value="' + state.tecnicoDef + '"]')) {
        $("filtroTecnico").value = state.tecnicoDef;
    }
    bind();
    load();
})();
