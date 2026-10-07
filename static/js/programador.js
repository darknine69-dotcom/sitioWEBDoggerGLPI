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
        festivo: app.dataset.urlFestivo,
        detalle: app.dataset.urlDetalle
    };

    var ICON_BY_TIPO = {
        tarea: "i-wrench",
        solicitud: "i-ticket",
        recordatorio: "i-bell",
        anuncio: "i-message",
        // Ya no se puede crear, pero se pintan los que quedaron en la base.
        proyecto: "i-folder"
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
    var TIPOS_EVENTO = ["tarea", "solicitud", "recordatorio", "anuncio"];

    var state = {
        anio: parseInt(app.dataset.anio, 10),
        mes: parseInt(app.dataset.mes, 10),
        tecnicoDef: app.dataset.tecDef || ""
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
    function post(url, body, cb) {
        fetch(url, { method: "POST", body: new URLSearchParams(body), headers: { "X-CSRFToken": csrf() } })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (res.ok) { if (cb) cb(res); }
                else toast(res.error || "Error inesperado", false);
            })
            .catch(function () { toast("No se pudo guardar", false); });
    }
    function toast(msg, ok) {
        var stack = $("progToasts");
        var t = document.createElement("div");
        t.className = "toast toast-" + (ok ? "success" : "error");
        t.setAttribute("role", "status");
        t.innerHTML =
            '<span class="toast-accent"></span>' +
            '<span class="toast-ic"><svg class="icon icon-sm"><use href="#' + (ok ? "i-check-circle" : "i-alert") + '"/></svg></span>' +
            '<span class="toast-body"><span class="toast-text">' + esc(msg) + "</span></span>" +
            '<button type="button" class="toast-close" aria-label="Cerrar">&times;</button>';
        stack.appendChild(t);
        t.querySelector(".toast-close").addEventListener("click", function () { t.remove(); });
        setTimeout(function () {
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
        }
        return "";
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

        for (var i = 0; i < filas; i++) {
            var num = i - offset + 1;
            var enMes = num >= 1 && num <= diasMes;
            var d = new Date(state.anio, state.mes - 1, num);
            var fecha = iso(d);

            var cell = document.createElement("div");
            var cls = "prog-day" + (enMes ? "" : " out" + (i < offset || num > diasMes ? " empty" : ""));
            if (enMes) {
                var st = estadoDia(d, key);
                if (st) cls += " " + st;
                if (fecha === hoyIso) cls += " is-today";
            }
            cell.className = cls;

            if (enMes) {
                cell.dataset.fecha = fecha;
                // Clic en el fondo del cuadro: abre el formulario de evento.
                // Si se hace clic sobre un chip, ese chip detiene la
                // propagacion y gana su propio modal de detalle.
                cell.addEventListener("click", function () {
                    abrirModalEvento(fecha, "");
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
                    { accion: "solicitud", cls: "q-solicitud", icon: "i-ticket", title: "Vincular una solicitud" },
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
                        else abrirModalEvento(fecha, q.accion);
                    });
                    quick.appendChild(btn);
                });
                cell.appendChild(quick);

                // Eventos registrados: cada chip abre el modal de ese evento.
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
                        esc(ev.titulo);
                    chip.addEventListener("click", function (e) {
                        e.stopPropagation();
                        abrirModalDetalle(ev, fecha);
                    });
                    chips.appendChild(chip);
                });
                if (delDia.length > 4) {
                    var mas = document.createElement("button");
                    mas.type = "button";
                    mas.className = "prog-chip ct-mas";
                    mas.textContent = "+" + (delDia.length - 4);
                    mas.title = "Ver los " + delDia.length + " eventos del día";
                    mas.addEventListener("click", function (e) {
                        e.stopPropagation();
                        abrirModalDetalle(null, fecha, delDia);
                    });
                    chips.appendChild(mas);
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
            return;
        }
        var rows = "";
        tecs.forEach(function (tec) {
            rows += '<tr class="mx-row' + (tec.activo ? "" : " is-offline") + '">' +
                '<td class="mx-tec"' + (tec.activo ? "" : ' title="Sin conexión"') + ">" +
                '<span class="mx-avatar">' + esc(tec.nombre.slice(0, 2).toUpperCase()) + "</span>" +
                esc(tec.nombre) +
                (tec.activo ? "" : ' <span class="mx-offline-tag">sin conexión</span>') +
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
    }

    /* ---------- listas ---------- */
    function renderListas() {
        construirLista({ tipo: "tarea", box: "listaTareas", cont: "tareasCount", check: true });
        construirLista({ tipo: "recordatorio", box: "listaRecordatorios", cont: "recordatoriosCount", check: false });
        construirLista({ tipo: "anuncio", box: "listaAnuncios", cont: "anunciosCount", check: false });
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
    function abrirModal(id) { $(id).classList.add("open"); }
    function cerrarModales() {
        document.querySelectorAll(".modal-overlay.open").forEach(function (m) { m.classList.remove("open"); });
    }

    /* Cada tipo de evento tiene su propio formulario: se zien distintos
       campos, con otras etiquetas y otras ayudas. Los campos viven en
       #evBiblioteca (fuera del <form>) y aqui se meten solo los del tipo
       elegido, para que lo que no aplica no se envie al servidor. */
    var FORM_TIPO = {
        tarea: {
            campos: ["titulo", "hora", "tecnico", "sitio", "grupo", "descripcion"],
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
            campos: ["titulo", "hora", "tecnico", "descripcion"],
            pista: "Un aviso para no dejar pasar algo en esa fecha.",
            tituloLabel: "Qué recordar", tituloPh: "Ej: Renovar el antivirus del punto",
            tituloAyuda: "El asunto del recordatorio.",
            tecnicoLabel: "Se le recuerda a", descLabel: "Qué tener presente",
            descPh: "Antecedentes, fecha límite, contraseña…",
            descAyuda: "Lo que debe tener en mente ese día.",
            requerido: ["titulo", "tecnico"], foco: "titulo"
        },
        anuncio: {
            campos: ["titulo", "sitio", "grupo", "descripcion"],
            pista: "Un aviso para todo el equipo, visible para todos.",
            tituloLabel: "Título del aviso", tituloPh: "Ej: Cambio de horario de soporte",
            tituloAyuda: "La idea en una línea.",
            tecnicoLabel: "", descLabel: "Mensaje",
            descPh: "Escribe el mensaje completo…",
            descAyuda: "Lo leerán todos los usuarios del panel.",
            requerido: ["titulo", "descripcion"], foco: "titulo"
        }
    };

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

        cuerpo.dataset.requerido = (cfg.requerido || []).join(",");
        cuerpo.dataset.foco = cfg.foco || "titulo";
        return cfg;
    }

    function abrirModalEvento(fecha, tipo) {
        $("evFecha").value = fecha;
        $("evFechaShow").value = fecha;
        if (tipo && TIPOS_EVENTO.indexOf(tipo) !== -1) $("evTipo").value = tipo;

        var tipoSel = $("evTipo").value;
        var cfg = pintarFormTipo(tipoSel);

        // Se limpian solo los campos que este tipo usa.
        $("evTitulo").value = "";
        $("evHora").value = "";
        $("evSitio").value = "";
        $("evGrupo").value = "";
        $("evTicket").value = "";
        $("evTecnico").value = tipoSel === "anuncio" ? "" : ($("filtroTecnico").value || "");
        $("evCuerpo").querySelector("textarea").value = "";

        abrirModal("modalEvento");
        var foco = $("evCuerpo").querySelector('[data-campo="' + (cfg.foco || "titulo") + '"]');
        if (foco) {
            var input = foco.querySelector("input, select, textarea");
            if (input) input.focus();
        }
    }

    /* ---------- modal de un evento ya registrado ---------- */
    function abrirModalDetalle(evento, fecha, lista) {
        var overlay = $("modalDetalleEvento");
        var cuerpo = $("detalleEventoCuerpo");
        var titulo = $("detalleEventoTitulo");
        var pie = $("detalleEventoAcciones");
        overlay.hidden = false;

        // Sin evento concreto (el chip "+N"): se listan todos los del día.
        var eventos = lista || (evento ? [evento] : []);
        var esVarios = !evento && lista && lista.length > 1;

        if (esVarios) {
            titulo.textContent = "Eventos del " + formatFecha(fecha);
            cuerpo.innerHTML = '<ul class="prog-det-lista">' + lista.map(function (ev) {
                return '<li class="prog-det-item ct-' + esc(ev.tipo) + (ev.completado ? " done" : "") + '">' +
                    '<button type="button" class="prog-det-abrir" data-det-id="' + ev.id + '">' +
                    '<svg class="icon"><use href="#' + (ICON_BY_TIPO[ev.tipo] || "i-bell") + '"/></svg>' +
                    '<span><strong>' + esc(ev.titulo) + '</strong>' +
                    '<small>' + esc(ev.tipo_label || "") + (ev.hora ? " · " + esc(ev.hora) : "") +
                    (ev.tecnico ? " · " + esc(ev.tecnico) : "") + '</small></span></button></li>';
            }).join("") + "</ul>";
        } else {
            var ev = eventos[0] || {};
            titulo.textContent = ev.tipo_label || "Evento";
            cuerpo.innerHTML =
                '<p class="prog-det-titulo">' + esc(ev.titulo || "") + '</p>' +
                '<dl class="prog-det-datos">' +
                '<dt>Fecha</dt><dd>' + esc(formatFecha(ev.fecha || fecha)) +
                    (ev.hora ? " · " + esc(ev.hora) : "") + '</dd>' +
                (ev.tecnico ? '<dt>Técnico</dt><dd>' + esc(ev.tecnico) + '</dd>' : '') +
                (ev.sitio ? '<dt>Punto</dt><dd>' + esc(ev.sitio) + '</dd>' : '') +
                (ev.grupo ? '<dt>Grupo</dt><dd>' + esc(ev.grupo) + '</dd>' : '') +
                (ev.ticket_codigo ? '<dt>Solicitud</dt><dd>' + esc(ev.ticket_codigo) + '</dd>' : '') +
                '<dt>Estado</dt><dd>' + (ev.completado ? "Completado" : "Pendiente") + '</dd>' +
                (ev.descripcion ? '<dt>Detalle</dt><dd>' + esc(ev.descripcion) + '</dd>' : '') +
                '</dl>';
        }

        // Pie: "Ver" lo que hay y "Agregar otro" del mismo tipo.
        var tipoAgregar = evento ? evento.tipo : "";
        pie.innerHTML =
            (evento && evento.ticket_id
                ? '<a class="btn btn-ghost btn-sm" href="' + U.detalle.replace("/0/", "/" + evento.ticket_id + "/") +
                  '" target="_blank" rel="noopener">Ver solicitud</a>'
                : "") +
            (tipoAgregar
                ? '<button type="button" class="btn btn-accent btn-sm" data-det-otro="' + esc(tipoAgregar) +
                  '" data-det-fecha="' + esc(fecha) + '">Agregar otro</button>'
                : '<button type="button" class="btn btn-accent btn-sm" data-det-otro="" data-det-fecha="' +
                  esc(fecha) + '">Agregar otro</button>') +
            '<button type="button" class="btn btn-ghost btn-sm" data-det-cerrar>Cerrar</button>';

        overlay.classList.add("open");
    }

    function cerrarDetalle() {
        $("modalDetalleEvento").classList.remove("open");
    }

    function cargarDispLabel() {
        var key = $("dispTecnico").value + "|" + $("dispFecha").value;
        var disp = data.disponibilidad[key];
        marcarDisp(disp ? disp.tipo : "");
        $("dispNota").value = disp ? (disp.nota || "") : "";
        $("dispHora").value = disp ? (disp.hora || "") : "";
    }
    function marcarDisp(tipo) {
        $("dispTipo").value = tipo || "";
        $("dispGuardarBtn").disabled = !tipo;
        document.querySelectorAll(".prog-disp-tipo").forEach(function (b) {
            b.classList.toggle("is-selected", b.dataset.tipo === tipo);
        });
    }
    function abrirModalDisp(fecha, tipo, tecId) {
        $("dispFecha").value = fecha;
        $("dispFechaShow").textContent = formatFecha(fecha);
        var tec = tecId || $("filtroTecnico").value;
        $("dispTecnico").value = tec || ($("dispTecnico").options.length > 1 ? $("dispTecnico").options[1].value : "");
        cargarDispLabel();
        if (tipo) marcarDisp(tipo);
        abrirModal("modalDisp");
    }
    function abrirModalFestivo(fecha) {
        $("festivoFecha").value = fecha;
        $("festivoFechaShow").textContent = formatFecha(fecha);
        $("festivoNombre").value = data.festivos[fecha] || "";
        abrirModal("modalFestivo");
    }

    /* ---------- bindings ---------- */
    function bind() {
        document.querySelectorAll(".prog-tab").forEach(function (tab) {
            tab.addEventListener("click", function () {
                var name = this.dataset.tab;
                document.querySelectorAll(".prog-tab").forEach(function (t) {
                    t.classList.toggle("is-active", t === tab);
                });
                document.querySelectorAll(".prog-panel").forEach(function (p) {
                    p.classList.toggle("is-active", p.dataset.tabpanel === name);
                });
            });
        });

        $("filtroTecnico").addEventListener("change", load);

        $("mesPrev").addEventListener("click", function () { movMes(-1); });
        $("mesNext").addEventListener("click", function () { movMes(1); });
        $("mesHoy").addEventListener("click", function () {
            var hoy = new Date();
            state.anio = hoy.getFullYear();
            state.mes = hoy.getMonth() + 1;
            load();
        });

        document.querySelectorAll(".modal-close, .modal-close-cancel").forEach(function (b) {
            b.addEventListener("click", cerrarModales);
        });
        document.querySelectorAll(".modal-overlay").forEach(function (ov) {
            ov.addEventListener("click", function (e) { if (e.target === ov) ov.classList.remove("open"); });
        });

        $("evTipo").addEventListener("change", function () {
            $("evSolicitudWrap").hidden = this.value !== "solicitud";
        });
        $("evFechaShow").addEventListener("change", function () { $("evFecha").value = this.value; });

        // --- Modal de detalle del evento ---
        var detalleOv = $("modalDetalleEvento");
        if (detalleOv) {
            detalleOv.addEventListener("click", function (e) {
                if (e.target === detalleOv) { cerrarDetalle(); return; }
                if (e.target.closest("[data-det-cerrar]")) { cerrarDetalle(); return; }
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
        document.querySelectorAll(".prog-disp-tipo").forEach(function (b) {
            b.addEventListener("click", function () { marcarDisp(this.dataset.tipo); });
        });

        $("evTipo").addEventListener("change", function () {
            pintarFormTipo(this.value);
        });

        $("formEvento").addEventListener("submit", function (e) {
            e.preventDefault();
            var cuerpo = $("evCuerpo");
            var cfg = FORM_TIPO[$("evTipo").value] || FORM_TIPO.tarea;

            // Solo se exigen los campos que el tipo chosen muestra.
            var faltan = [];
            (cfg.requerido || []).forEach(function (nombre) {
                var nodo = cuerpo.querySelector('[data-campo="' + nombre + '"]');
                var input = nodo && nodo.querySelector("input, select, textarea");
                if (!input || !String(input.value).trim()) {
                    var et = nodo && nodo.querySelector("span");
                    faltan.push(et ? et.textContent.trim() : nombre);
                }
            });
            if (faltan.length) {
                toast("Completa: " + faltan.join(", "), false);
                return;
            }
            post(U.agregar, new FormData(this), function () {
                cerrarModales();
                toast("Evento guardado", true);
                load();
            });
        });

        $("formDisp").addEventListener("submit", function (e) {
            e.preventDefault();
            var fd = new FormData(this);
            if (!fd.get("tecnico_id")) { toast("Selecciona un técnico", false); return; }
            if (!fd.get("tipo")) { toast("Selecciona un tipo de disponibilidad", false); return; }
            post(U.disp, fd, function () {
                cerrarModales();
                toast("Disponibilidad guardada", true);
                load();
            });
        });
        $("dispQuitar").addEventListener("click", function () {
            var fd = new FormData($("formDisp"));
            fd.set("tipo", "");
            post(U.disp, fd, function () {
                cerrarModales();
                toast("Marca quitada", true);
                load();
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

    /* ---------- init ---------- */
    if (state.tecnicoDef && $("filtroTecnico").querySelector('option[value="' + state.tecnicoDef + '"]')) {
        $("filtroTecnico").value = state.tecnicoDef;
    }
    bind();
    load();
})();