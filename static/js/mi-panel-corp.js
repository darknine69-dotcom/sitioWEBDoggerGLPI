/* Mi panel corporativo — panel de acciones in-page + mini chat GLPI */
(function () {
    "use strict";

    var csrf = null;
    var meta = document.querySelector('meta[name="csrfmiddlewaretoken"]');
    if (meta) csrf = meta.getAttribute("content");
    if (!csrf) {
        var inp = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (inp) csrf = inp.value;
    }

    var accionPanel = document.getElementById("accion-content");
    var accionTitulo = document.getElementById("accion-titulo");
    var accionIcon = document.getElementById("accion-icon");

    /* ---------- Mini chat ---------- */
    var miniChat = document.getElementById("mini-chat");
    var miniBody = document.getElementById("mini-chat-body");
    var miniCodigo = document.getElementById("mini-chat-codigo");
    var miniForm = document.getElementById("mini-chat-form");
    var miniText = document.getElementById("mini-chat-text");
    var currentChatPk = null;

    function esc(s) {
        return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
            .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    function postAsForm(url, data) {
        var fd = new URLSearchParams();
        Object.keys(data).forEach(function (k) { fd.append(k, data[k]); });
        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-CSRFToken": csrf
            },
            body: fd.toString()
        }).then(function (r) { return r.json().catch(function () { return { ok: false, error: "Respuesta no válida." }; }); });
    }

    function renderMensaje(item, append) {
        var rolLabel = item.rol === "sistema" ? "Sistema" : (item.rol === "soporte" ? "Soporte" : "Tú");
        var html =
            '<div class="chat-bubble chat-msg-' + esc(item.rol) + '">' +
            '<span class="chat-bubble-meta"><span class="resp-rol rol-' + esc(item.rol) + '">' + rolLabel + '</span>' +
            esc(item.autor) + ' · ' + esc(item.fecha_label || "") + '</span>' +
            '<div class="chat-bubble-text">' + esc(item.texto) + '</div>' +
            '</div>';
        if (append) miniBody.insertAdjacentHTML("beforeend", html);
        return html;
    }

    function openMiniChat(pk, codigo) {
        if (!miniChat) return;
        currentChatPk = pk;
        if (miniCodigo) miniCodigo.textContent = codigo || "";
        miniChat.hidden = false;
        miniBody.innerHTML = '<p class="empty-hint">Cargando conversación…</p>';
        if (miniText) miniText.value = "";
        fetch("/mi-panel/api/tickets/" + pk + "/info/", { headers: { "Accept": "application/json" } })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.ok) {
                    miniBody.innerHTML = '<p class="empty-hint">No se pudo cargar la conversación.</p>';
                    return;
                }
                miniBody.innerHTML = "";
                (data.respuestas || []).forEach(function (item) { renderMensaje(item, true); });
                if (!miniBody.children.length) miniBody.innerHTML = '<p class="empty-hint">Aún no hay mensajes. ¡Escríbele a la mesa de ayuda!</p>';
            })
            .catch(function () { miniBody.innerHTML = '<p class="empty-hint">Error de conexión.</p>'; });
    }

    /* Actividad reciente → mini chat (delegado) */
    document.addEventListener("click", function (e) {
        var item = e.target.closest(".glpi-clickable");
        if (item) {
            var pk = item.getAttribute("data-chat-pk");
            var codigo = item.getAttribute("data-chat-codigo") || "";
            if (pk) openMiniChat(pk, codigo);
            return;
        }
        var close = e.target.closest("#mini-chat-close");
        if (close && miniChat) { miniChat.hidden = true; currentChatPk = null; }
    });

    /* Enviar mensaje del mini chat (delegado) */
    document.addEventListener("submit", function (e) {
        var form = e.target;
        if (!form || form.id !== "mini-chat-form") return;
        e.preventDefault();
        if (!currentChatPk) return;
        var texto = (miniText.value || "").trim();
        if (!texto) return;
        miniText.value = "";
        postAsForm("/mi-panel/api/tickets/" + currentChatPk + "/responder/", { comentario: texto })
            .then(function (res) {
                if (res.ok) renderMensaje(res.mensaje, true);
                else {
                    miniBody.insertAdjacentHTML("beforeend",
                        '<p class="chat-error-hint">' + esc(res.error || "No se pudo enviar.") + '</p>');
                }
            })
            .catch(function () {
                miniBody.insertAdjacentHTML("beforeend", '<p class="chat-error-hint">Error de conexión.</p>');
            });
    });

    /* ---------- Panel de acciones in-page ---------- */
    function setAccion(iconHref, title) {
        if (accionIcon) accionIcon.setAttribute("href", iconHref);
        if (accionTitulo) accionTitulo.textContent = title;
    }

    /* Ver respuestas (en panel) */
    function showRespuestas(pk, codigo) {
        setAccion("#i-message", "Respuestas · " + codigo);
        accionPanel.innerHTML = '<p class="empty-hint">Cargando historial…</p>';
        fetch("/mi-panel/api/tickets/" + pk + "/info/", { headers: { "Accept": "application/json" } })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.ok || !data.respuestas || !data.respuestas.length) {
                    accionPanel.innerHTML = '<p class="empty-hint">Aún no hay respuestas registradas para esta solicitud.</p>';
                    return;
                }
                var html = '<div class="resp-thread">';
                data.respuestas.forEach(function (item) {
                    html += '<div class="resp-bubble resp-bubble-' + esc(item.rol) + '">' +
                        '<span class="resp-meta"><span class="resp-rol rol-' + esc(item.rol) + '">' +
                        (item.rol === "sistema" ? "Sistema" : (item.rol === "soporte" ? "Soporte" : "Tú")) + '</span>' +
                        esc(item.autor) + ' · ' + esc(item.fecha_label) + '</span>' +
                        '<div class="resp-body">' + esc(item.texto) + '</div></div>';
                });
                html += '</div>';
                accionPanel.innerHTML = html;
            })
            .catch(function () { accionPanel.innerHTML = '<p class="empty-hint">No se pudo cargar el historial.</p>'; });
    }

    var currentEditPk = null;
    var imagenParaEliminar = null;

    function showEditar(pk, codigo) {
        currentEditPk = pk;
        imagenParaEliminar = null;
        setAccion("#i-edit", "Editar solicitud · " + (codigo || ""));
        accionPanel.innerHTML =
            '<p class="modal-note">Puedes editar el nombre, las observaciones y la imagen. La prioridad y la categoría no se pueden modificar.</p>' +
            '<form id="form-editar" class="form-grid" novalidate>' +
            '<div class="form-group span-2"><label for="e-titulo">Nombre del ticket <span class="req">*</span></label>' +
            '<input type="text" name="titulo" class="edit-titulo" id="e-titulo" required maxlength="200"></div>' +
            '<div class="form-group"><label>Prioridad</label><input type="text" class="edit-prioridad-dis disabled-val" id="e-prioridad" disabled></div>' +
            '<div class="form-group"><label>Categoría</label><input type="text" class="edit-categoria-dis disabled-val" id="e-categoria" disabled></div>' +
            '<div class="form-group span-2"><label for="e-descripcion">Observaciones</label><textarea name="descripcion" id="e-descripcion" class="edit-descripcion" rows="4"></textarea></div>' +
            '<div class="form-group span-2" id="img-upload-wrap">' +
            '<label>Imagen adjunta <span class="hint">(máx. 5 MB)</span></label>' +
            '<input type="file" name="imagen" id="e-imagen" class="edit-imagen" accept="image/*">' +
            '<div id="img-preview-box" class="img-preview-box" hidden></div>' +
            '</div>' +
            '<p id="edit-error" class="form-error-line" hidden></p>' +
            '<div class="modal-actions span-2">' +
            '<button type="submit" class="btn btn-primary btn-sm">Guardar cambios</button>' +
            '<button type="button" class="btn btn-cancel btn-sm" id="btn-edit-cancel">Cancelar</button>' +
            '</div></form>';
        fetch("/mi-panel/api/tickets/" + pk + "/info/", { headers: { "Accept": "application/json" } })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.ok) {
                    document.getElementById("edit-error").textContent = data.error || "No se pudo cargar la solicitud.";
                    document.getElementById("edit-error").hidden = false;
                    return;
                }
                document.querySelector(".edit-titulo").value = data.ticket.titulo || "";
                document.querySelector(".edit-descripcion").value = data.ticket.descripcion || "";
                document.querySelector(".edit-prioridad-dis").value = data.ticket.prioridad_nombre || "";
                document.querySelector(".edit-categoria-dis").value = data.ticket.categoria_nombre || "";
                renderImagen(data.imagenes);
            })
            .catch(function () {
                document.getElementById("edit-error").textContent = "No se pudo cargar la solicitud.";
                document.getElementById("edit-error").hidden = false;
            });
    }

    function renderImagen(imagenes) {
        var box = document.getElementById("img-preview-box");
        if (!box) return;
        var lista = imagenes || [];
        if (!lista.length) {
            box.hidden = true;
            box.innerHTML = "";
            return;
        }
        var img = lista[0];
        box.hidden = false;
        box.innerHTML =
            '<div class="img-preview-item">' +
            '<img src="' + esc(img.url) + '" alt="' + esc(img.nombre) + '" />' +
            '<div class="img-preview-meta">' +
            '<span>' + esc(img.nombre) + '</span>' +
            '<button type="button" class="btn btn-cancel btn-sm" id="btn-del-img"><svg class="icon"><use href="#i-trash"/></svg> Eliminar imagen</button>' +
            '</div></div>';
        document.getElementById("btn-del-img").addEventListener("click", function () {
            imagenParaEliminar = img.pk;
            box.hidden = true;
            box.innerHTML = "";
            var file = document.getElementById("e-imagen");
            if (file) file.value = "";
        });
    }

    /* Previsualización local de la nueva imagen */
    document.addEventListener("change", function (e) {
        var file = e.target;
        if (!file || file.id !== "e-imagen") return;
        var box = document.getElementById("img-preview-box");
        if (!box) return;
        var f = file.files && file.files[0];
        if (!f || !f.type.startsWith("image/")) return;
        var reader = new FileReader();
        reader.onload = function (ev) {
            box.hidden = false;
            box.innerHTML =
                '<div class="img-preview-item">' +
                '<img src="' + ev.target.result + '" alt="Nueva imagen" />' +
                '<div class="img-preview-meta"><span>' + esc(f.name) + ' (nueva)</span></div></div>';
        };
        reader.readAsDataURL(f);
    });

    /* Cancelar edición */
    document.addEventListener("click", function (e) {
        if (e.target.closest("#btn-edit-cancel")) {
            accionPanel.innerHTML = '<p class="empty-hint">Edición cancelada. Selecciona otra acción.</p>';
            setAccion("#i-ticket", "Acción de la solicitud");
            currentEditPk = null;
        }
    });

    /* Guardar edición (delegado) — multipart para la imagen */
    document.addEventListener("submit", function (e) {
        var form = e.target;
        if (!form || form.id !== "form-editar") return;
        e.preventDefault();
        if (!currentEditPk) return;
        var errEl = document.getElementById("edit-error");
        errEl.hidden = true;
        var fd = new FormData();
        fd.append("titulo", form.querySelector(".edit-titulo").value);
        fd.append("descripcion", form.querySelector(".edit-descripcion").value);
        var imgFile = document.getElementById("e-imagen");
        if (imgFile && imgFile.files && imgFile.files[0]) fd.append("imagen", imgFile.files[0]);
        if (imagenParaEliminar) fd.append("eliminar_imagen", imagenParaEliminar);
        fetch("/mi-panel/api/tickets/" + currentEditPk + "/editar/", {
            method: "POST",
            headers: { "X-CSRFToken": csrf },
            body: fd
        })
            .then(function (r) { return r.json().catch(function () { return { ok: false, error: "Respuesta no válida." }; }); })
            .then(function (res) {
                if (res.ok) window.location.reload();
                else { errEl.textContent = res.error || "No se pudo guardar los cambios."; errEl.hidden = false; }
            })
            .catch(function () { errEl.textContent = "Error de conexión."; errEl.hidden = false; });
    });

    /* Cerrar / Eliminar (confirmación en panel) */
    function showConfirmar(kind, pk, codigo) {
        var esCerrar = (kind === "cerrar");
        setAccion(esCerrar ? "#i-ban" : "#i-trash", esCerrar ? "Cerrar solicitud" : "Eliminar solicitud");
        accionPanel.innerHTML =
            '<div class="confirm-box">' +
            '<p>' + (esCerrar
                ? '¿Confirmas que deseas cerrar la solicitud <strong>' + esc(codigo) + '</strong>?'
                : '¿Seguro que deseas <strong>eliminar</strong> la solicitud <strong>' + esc(codigo) + '</strong>?') + '</p>' +
            '<p class="modal-note">' + (esCerrar
                ? "Al cerrarla no podrás editarla; el historial se conserva."
                : "Esta acción es permanente y no se puede deshacer. Solo se puede eliminar mientras la solicitud está abierta.") + '</p>' +
            '<p id="confirm-error" class="form-error-line" hidden></p>' +
            '<div class="modal-actions">' +
            '<button type="button" class="btn btn-cancel btn-sm" id="btn-confirm-yes">' + (esCerrar ? "Sí, cerrar" : "Sí, eliminar") + '</button>' +
            '<button type="button" class="btn btn-outline btn-sm" id="btn-confirm-no">No, cancelar</button>' +
            '</div></div>';
        var yesBtn = document.getElementById("btn-confirm-yes");
        var noBtn = document.getElementById("btn-confirm-no");
        var errEl = document.getElementById("confirm-error");
        var url = "/mi-panel/api/tickets/" + pk + (esCerrar ? "/cerrar/" : "/eliminar/");
        function cancelar() {
            accionPanel.innerHTML = '<p class="empty-hint">Acción cancelada.</p>';
            setAccion("#i-ticket", "Acción de la solicitud");
        }
        noBtn.addEventListener("click", cancelar);
        yesBtn.addEventListener("click", function () {
            errEl.hidden = true;
            postAsForm(url, {})
                .then(function (res) {
                    if (res.ok) window.location.reload();
                    else { errEl.textContent = res.error || "No se pudo completar la acción."; errEl.hidden = false; }
                })
                .catch(function () { errEl.textContent = "Error de conexión."; errEl.hidden = false; });
        });
    }

    /* Delegación de acciones de fila de la tabla */
    document.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-action]");
        if (!btn) return;
        var accion = btn.getAttribute("data-action");
        var pk = btn.getAttribute("data-pk");
        var codigo = btn.getAttribute("data-codigo") || "";
        e.preventDefault();
        if (accion === "respuestas") showRespuestas(pk, codigo);
        else if (accion === "editar") showEditar(pk, codigo);
        else if (accion === "cerrar") showConfirmar("cerrar", pk, codigo);
        else if (accion === "eliminar") showConfirmar("eliminar", pk, codigo);
        // scroll al panel de acciones en móvil
        if (accionPanel && window.innerWidth < 900) accionPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
})();