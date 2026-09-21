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
        proyecto: "i-folder",
        anuncio: "i-message"
    };
    var LABELS = {
        tarea: ["Tarea", "Tareas"],
        solicitud: ["Solicitud", "Solicitudes"],
        recordatorio: ["Recordatorio", "Recordatorios"],
        proyecto: ["Proyecto", "Proyectos"],
        anuncio: ["Anuncio", "Anuncios"]
    };

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
            })
            .catch(function () { toast("Error al cargar los datos", false); });
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
                cell.addEventListener("click", function () { abrirModalEvento(this.dataset.fecha); });

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
                    { accion: "tarea", cls: "q-tarea", icon: "i-wrench", title: "Agregar tarea" }
                ];
                qAcciones.forEach(function (q) {
                    var btn = document.createElement("button");
                    btn.type = "button";
                    btn.className = q.cls;
                    btn.title = q.title;
                    btn.innerHTML = '<svg class="icon"><use href="#' + q.icon + '"/></svg>';
                    btn.addEventListener("click", function (e) {
                        e.stopPropagation();
                        if (q.accion === "falta") abrirModalDisp(fecha, "falta");
                        else abrirModalEvento(fecha, q.accion);
                    });
                    quick.appendChild(btn);
                });
                cell.appendChild(quick);

                var chips = document.createElement("div");
                chips.className = "prog-day-chips";
                var conteo = {};
                (porFecha[fecha] || []).forEach(function (e) { conteo[e.tipo] = (conteo[e.tipo] || 0) + 1; });
                Object.keys(conteo).forEach(function (tipo) {
                    var chip = document.createElement("span");
                    chip.className = "prog-chip ct-" + tipo;
                    chip.innerHTML = '<svg class="icon"><use href="#' + ICON_BY_TIPO[tipo] + '"/></svg>' +
                        esc(plural(conteo[tipo], LABELS[tipo][0], LABELS[tipo][1]));
                    chips.appendChild(chip);
                });
                cell.appendChild(chips);

                var nota = "";
                if (data.festivos[fecha]) nota = "Festivo: " + data.festivos[fecha];
                else if (key) {
                    var desp = data.disponibilidad[key + "|" + fecha];
                    var tipos = { ausencia: "Ausencia", falta: "Falta de disponibilidad", no_ausencia: "No ausencia" };
                    if (desp) nota = desp.nota || tipos[desp.tipo] || "";
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

    function abrirModalEvento(fecha, tipo) {
        $("evFecha").value = fecha;
        $("evFechaShow").value = fecha;
        $("evTitulo").value = "";
        $("evHora").value = "";
        $("evSitio").value = "";
        $("evGrupo").value = "";
        $("evTicket").value = "";
        $("evTecnico").value = $("filtroTecnico").value || "";
        $("formEvento").querySelector("textarea[name=descripcion]").value = "";
        if (tipo) $("evTipo").value = tipo;
        var tipoSel = $("evTipo").value;
        $("evSolicitudWrap").hidden = tipoSel !== "solicitud";
        if (tipoSel === "solicitud") {
            $("evTicket").focus();
        } else {
            $("evTitulo").focus();
        }
        abrirModal("modalEvento");
    }

    function cargarDispLabel() {
        var key = $("dispTecnico").value + "|" + $("dispFecha").value;
        var disp = data.disponibilidad[key];
        marcarDisp(disp ? disp.tipo : "");
        $("dispNota").value = disp ? (disp.nota || "") : "";
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

        $("formEvento").addEventListener("submit", function (e) {
            e.preventDefault();
            if (!$("evTitulo").value.trim()) { toast("El título es obligatorio", false); return; }
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