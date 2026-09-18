/* Dogger — Módulo corporativo "Mis solicitudes abiertas" (selección, orden, vistas, acciones en lote) */
(function () {
    "use strict";
    var table = document.getElementById("tablaAbiertas");
    if (!table) return;

    var checkAll = document.getElementById("chkAbiertasAll");
    var rows = Array.prototype.slice.call(table.querySelectorAll("tbody tr[data-pk]"));
    var csrf = document.querySelector('input[name="csrfmiddlewaretoken"]');
    var csrfVal = csrf ? csrf.value : "";
    var msgEl = document.getElementById("corpMsg");

    function selected() {
        return rows.filter(function (r) {
            var c = r.querySelector(".chk-abierta");
            return c && c.checked;
        });
    }
    function setMsg(texto, error) {
        if (!msgEl) return;
        msgEl.textContent = texto || "";
        msgEl.style.display = texto ? "block" : "none";
        msgEl.classList.toggle("corp-msg-error", !!error);
    }
    function marcarFila(r, on) {
        r.classList.toggle("corp-row-selected", on);
    }
    function refreshSelection() {
        var sel = selected();
        var n = sel.length;
        var botones = document.querySelectorAll("#corpActions [data-lote]");
        botones.forEach(function (b) {
            if (b.dataset.lote === "editar") return;
            b.disabled = n === 0;
        });
        var asignar = document.querySelector('#corpActions [data-open-modal="#modalAsignar"]');
        if (asignar) asignar.disabled = n === 0;
        if (checkAll) checkAll.checked = n === rows.length && n > 0;
        var editar = document.querySelector('#corpActions [data-lote="editar"]');
        if (editar) editar.disabled = n !== 1;
    }

    rows.forEach(function (r) {
        var cb = r.querySelector(".chk-abierta");
        if (!cb) return;
        cb.addEventListener("change", function () {
            marcarFila(r, cb.checked);
            refreshSelection();
        });
    });
    if (checkAll) checkAll.addEventListener("change", function () {
        rows.forEach(function (r) {
            var c = r.querySelector(".chk-abierta");
            if (c) {
                c.checked = checkAll.checked;
                marcarFila(r, c.checked);
            }
        });
        refreshSelection();
    });
    refreshSelection();

    /* ---- Click en fila → abrir el ticket ---- */
    table.querySelector("tbody").addEventListener("click", function (e) {
        var target = e.target;
        if (target.closest("input, button, a, th, .td-check")) return;
        var tr = target.closest("tr[data-url-detalle]");
        if (tr) window.location.href = tr.getAttribute("data-url-detalle");
    });

    /* ---- Pill "Combinada" → desplegar las solicitudes combinadas ---- */
    table.querySelector("tbody").addEventListener("click", function (e) {
        var btn = e.target.closest(".corp-combinadas");
        if (!btn) return;
        var wrap = btn.parentElement;
        var list = wrap ? wrap.querySelector(".corp-combinadas-list") : null;
        if (!list) return;
        var abrir = list.hidden;
        list.hidden = !abrir;
        btn.classList.toggle("is-open", abrir);
        btn.setAttribute("aria-expanded", abrir ? "true" : "false");
    });

    /* ---- Vista Lista / Cuadrícula ---- */
    var results = document.getElementById("corpResults");
    var viewBtns = document.querySelectorAll(".corp-view-btn[data-view]");
    viewBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
            var view = btn.getAttribute("data-view");
            viewBtns.forEach(function (b) { b.classList.toggle("is-active", b === btn); });
            if (results) results.setAttribute("data-view", view);
        });
    });

    /* ---- Ordenamiento por columna ---- */
    var sortState = {};
    table.querySelectorAll("th.sortable").forEach(function (th) {
        th.addEventListener("click", function () {
            var key = th.getAttribute("data-sort");
            if (!key) return;
            var dir = sortState[key] === "asc" ? "desc" : "asc";
            table.querySelectorAll("th.sortable").forEach(function (x) {
                x.classList.remove("sort-asc", "sort-desc");
            });
            th.classList.add("sort-" + dir);
            sortState = {}; sortState[key] = dir;
            rows.sort(function (a, b) {
                var av = (a.getAttribute("data-" + key) || "");
                var bv = (b.getAttribute("data-" + key) || "");
                if (key === "vencimiento" || key === "id" || key === "creado") {
                    if (key === "id") {
                        var m1 = av.match(/\d+/), m2 = bv.match(/\d+/);
                        av = m1 ? parseInt(m1[0], 10) : 0;
                        bv = m2 ? parseInt(m2[0], 10) : 0;
                    } else {
                        av = parseInt(av, 10) || 0;
                        bv = parseInt(bv, 10) || 0;
                    }
                    return dir === "asc" ? av - bv : bv - av;
                }
                if (!av && !bv) return 0;
                if (!av) return dir === "asc" ? 1 : -1;
                if (!bv) return dir === "asc" ? -1 : 1;
                return dir === "asc" ? av.localeCompare(bv, "es") : bv.localeCompare(av, "es");
            });
            var tbody = table.querySelector("tbody");
            rows.forEach(function (r) { tbody.appendChild(r); });
        });
    });

    /* ---- Acciones en lote ---- */
    function seleccionadas() {
        return selected().map(function (r) { return r.getAttribute("data-pk"); });
    }
    var actions = document.getElementById("corpActions");
    var urlLote = actions ? actions.getAttribute("data-url-lote") : "";
    function correr(accion, extra, confirma) {
        var ids = seleccionadas();
        if (!ids.length) { setMsg("Selecciona al menos una solicitud.", true); return; }
        var doIt = function () {
            var fd = new FormData();
            fd.append("csrfmiddlewaretoken", csrfVal);
            fd.append("accion", accion);
            fd.append("ids", ids.join(","));
            if (extra) Object.keys(extra).forEach(function (k) { fd.append(k, extra[k]); });
            setMsg("Procesando…");
            fetch(urlLote, {
                method: "POST",
                body: fd,
                headers: { "X-Requested-With": "XMLHttpRequest" }
            })
            .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
            .then(function (res) {
                if (res.ok && res.d.ok) {
                    setMsg(res.d.mensaje || "Solicitudes actualizadas.");
                    setTimeout(function () { location.reload(); }, 700);
                } else {
                    setMsg((res.d && res.d.error) || "No se pudieron actualizar las solicitudes.", true);
                }
            })
            .catch(function () { setMsg("Error de conexión al procesar la solicitud.", true); });
        };
        if (confirma) {
            if (window.DoggerConfirma) window.DoggerConfirma(confirma, doIt);
            else if (window.confirm(confirma)) doIt();
        } else { doIt(); }
    }

    document.querySelector('#corpActions [data-lote="recoger"]').addEventListener("click", function () {
        correr("recoger", null, "¿Recoger (tomar) las solicitudes seleccionadas?");
    });
    document.querySelector('#corpActions [data-lote="cerrar"]').addEventListener("click", function () {
        correr("cerrar", null, "¿Cerrar las solicitudes seleccionadas?");
    });
    document.querySelector('#corpActions [data-lote="eliminar"]').addEventListener("click", function () {
        correr("eliminar", null, "¿Eliminar definitivamente las solicitudes seleccionadas? Esta acción no se puede deshacer.");
    });
    document.querySelector('#corpActions [data-lote="editar"]').addEventListener("click", function () {
        var sel = seleccionadas();
        if (sel.length === 1) {
            var url = this.getAttribute("data-url-editar");
            if (url) window.location.href = url.replace("0", sel[0]);
        }
    });

    /* ---- Modales "Combinar solicitud" y "Vincular solicitud" ---- */
    function abrirModal(m) {
        if (m) { m.classList.add("open"); document.body.style.overflow = "hidden"; }
    }
    function cerrarModalX(m) {
        if (m) { m.classList.remove("open"); document.body.style.overflow = ""; }
    }
    function montarModal(m, btnCerrar) {
        var close = m.querySelector(".modal-close");
        if (close) close.addEventListener("click", function () { cerrarModalX(m); });
        m.addEventListener("click", function (e) { if (e.target === m) cerrarModalX(m); });
    }

    var modalCombinar = document.getElementById("modalCombinar");
    if (modalCombinar) {
        var combSelect = document.getElementById("combinarPrincipal");
        montarModal(modalCombinar);
        var combCancelar = modalCombinar.querySelector("[data-combinar-cancelar]");
        if (combCancelar) combCancelar.addEventListener("click", function () { cerrarModalX(modalCombinar); });
        document.querySelector('#corpActions [data-lote="combinar"]').addEventListener("click", function () {
            var sel = selected();
            if (sel.length < 2) {
                setMsg("Selecciona al menos dos solicitudes para combinar.", true);
                return;
            }
            combSelect.innerHTML = "";
            var porDefecto = null, masAntigua = Infinity;
            sel.forEach(function (r) {
                var opt = document.createElement("option");
                var ts = parseInt(r.getAttribute("data-creado"), 10) || 0;
                opt.value = r.getAttribute("data-pk");
                opt.textContent = (r.getAttribute("data-codigo") || "#") + " - " + (r.getAttribute("data-asunto") || "Sin asunto");
                combSelect.appendChild(opt);
                if (ts < masAntigua) { masAntigua = ts; porDefecto = opt.value; }
            });
            if (porDefecto) combSelect.value = porDefecto;
            abrirModal(modalCombinar);
        });
        modalCombinar.querySelector("[data-combinar-guardar]").addEventListener("click", function () {
            if (!combSelect.value) {
                setMsg("Selecciona la solicitud principal.", true);
                return;
            }
            cerrarModalX(modalCombinar);
            correr("combinar", { principal: combSelect.value });
        });
    }

    var modalVincular = document.getElementById("modalVincular");
    if (modalVincular) {
        var vinTxt = document.getElementById("vincularComentario");
        montarModal(modalVincular);
        var vinDescartar = modalVincular.querySelector("[data-vincular-descartar]");
        if (vinDescartar) vinDescartar.addEventListener("click", function () { cerrarModalX(modalVincular); });
        document.querySelector('#corpActions [data-lote="vincular"]').addEventListener("click", function () {
            var sel = selected();
            if (sel.length < 2) {
                setMsg("Selecciona al menos dos solicitudes para vincular.", true);
                return;
            }
            if (vinTxt) vinTxt.value = "";
            abrirModal(modalVincular);
        });
        modalVincular.querySelector("[data-vincular-guardar]").addEventListener("click", function () {
            cerrarModalX(modalVincular);
            correr("vincular", { comentario: vinTxt ? vinTxt.value.trim() : "" });
        });
    }

    /* ---- Modal de asignación (lista de técnicos con punto verde) ---- */
    var modal = document.getElementById("modalAsignar");
    if (modal) {
        var abrir = document.querySelector('#corpActions [data-open-modal="#modalAsignar"]');
        var guardarBtn = modal.querySelector("[data-asignar-guardar]");
        var cancelarBtn = modal.querySelector("[data-asignar-cancelar]");
        var contN = document.getElementById("asignarN");
        var tecSelect = modal.querySelector('[name="tecnico"]');
        var tecList = document.getElementById("corpTecList");
        var tecItems = [];

        function listaTecnicos() {
            var agree = true;
            var pk = null;
            selected().forEach(function (r) {
                var v = r.getAttribute("data-tecnico-pk") || "";
                if (pk === null) pk = v;
                else if (pk !== v) agree = false;
            });
            return agree ? pk : "";
        }
        function marcarAsignado(pk) {
            tecItems.forEach(function (item) {
                item.classList.toggle("is-asignado", item.getAttribute("data-tec-pk") === pk);
                item.classList.toggle("corp-tec-selected", item.getAttribute("data-tec-pk") === pk);
            });
        }
        if (tecList) {
            tecItems = Array.prototype.slice.call(tecList.querySelectorAll(".corp-tec-item"));
            tecItems.forEach(function (item) {
                item.addEventListener("click", function () {
                    var pk = item.getAttribute("data-tec-pk");
                    if (tecSelect) tecSelect.value = pk;
                    marcarAsignado(pk);
                });
            });
        }
        function abrirModal() {
            var ids = seleccionadas();
            if (!ids.length) { setMsg("Selecciona al menos una solicitud para asignar.", true); return; }
            if (contN) contN.textContent = ids.length;
            if (tecSelect) {
                tecSelect.value = "";
                marcarAsignado(listaTecnicos() || "");
            }
            modal.classList.add("open");
            document.body.style.overflow = "hidden";
        }
        function cerrarModal() {
            modal.classList.remove("open");
            document.body.style.overflow = "";
        }
        abrir.addEventListener("click", abrirModal);
        modal.querySelector(".modal-close").addEventListener("click", cerrarModal);
        if (cancelarBtn) cancelarBtn.addEventListener("click", cerrarModal);
        modal.addEventListener("click", function (e) {
            if (e.target === modal) cerrarModal();
        });
        if (guardarBtn) guardarBtn.addEventListener("click", function () {
            var sitio = modal.querySelector('[name="sitio"]').value.trim();
            var grupo = modal.querySelector('[name="grupo"]').value;
            var tecnico = tecSelect ? tecSelect.value : "";
            if (!sitio && !grupo && !tecnico) {
                setMsg("Completa al menos un campo de asignación.", true);
                return;
            }
            cerrarModal();
            correr("asignar", { sitio: sitio, grupo: grupo, tecnico: tecnico });
        });
    }
})();