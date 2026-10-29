(function () {
    "use strict";
    var pagina = document.getElementById("pagina"), form = document.getElementById("pagina-config-form");
    if (!pagina || !form) return;
    var estado = document.getElementById("pagina-save-status"), guardando = false;
    function mensaje(texto, error) {
        estado.textContent = texto; estado.classList.toggle("is-error", !!error);
        if (/Guardando/.test(texto)) return;
        var pila = document.getElementById("pagina-toast-stack");
        var aviso = document.createElement("div"); aviso.className = "pagina-toast" + (error ? " is-error" : "");
        aviso.setAttribute("role", error ? "alert" : "status");
        var icono = document.createElementNS("http://www.w3.org/2000/svg", "svg"); icono.setAttribute("class", "icon"); icono.setAttribute("aria-hidden", "true");
        var uso = document.createElementNS("http://www.w3.org/2000/svg", "use"); uso.setAttribute("href", error ? "#i-alert" : "#i-check"); icono.appendChild(uso);
        var contenido = document.createElement("span"); contenido.textContent = texto;
        var cerrar = document.createElement("button"); cerrar.type = "button"; cerrar.setAttribute("aria-label", "Cerrar notificación"); cerrar.textContent = "×";
        cerrar.addEventListener("click", function () { aviso.remove(); }); aviso.append(icono, contenido, cerrar); pila.appendChild(aviso);
        if (!error) setTimeout(function () { aviso.remove(); }, 4000);
    }
    async function enviar(formulario, datos) {
        var respuesta = await fetch(formulario.action, { method:"POST", body:datos, headers:{"X-Requested-With":"XMLHttpRequest"}, credentials:"same-origin" });
        var resultado = await respuesta.json();
        if (!respuesta.ok || !resultado.ok) throw new Error(resultado.error || "No fue posible guardar los cambios.");
    }
    form.querySelectorAll("[onchange]").forEach(function (campo) { campo.removeAttribute("onchange"); });
    form.addEventListener("submit", async function (evento) {
        evento.preventDefault(); if (guardando || !form.reportValidity()) return;
        guardando = true; var boton = form.querySelector('button[type="submit"]'); boton.disabled = true; mensaje("Guardando…");
        try { await enviar(form, new FormData(form)); mensaje("Configuración actualizada correctamente."); }
        catch (error) { mensaje(error.message || "Error de conexión. Inténtalo nuevamente.", true); }
        finally { guardando = false; boton.disabled = false; }
    });
    form.querySelectorAll('input[type="checkbox"]').forEach(function (campo) {
        var descripcion = campo.closest(".cfg-row");
        if (descripcion && descripcion.querySelector(".cfg-label")) campo.setAttribute("aria-label", descripcion.querySelector(".cfg-label").firstChild.textContent.trim());
        campo.addEventListener("change", async function () {
            var anterior = !campo.checked;
            if (guardando || !form.reportValidity()) { campo.checked = anterior; return; }
            guardando = true; form.querySelectorAll('input[type="checkbox"]').forEach(function (c) { c.disabled = true; });
            // Disabled controls are omitted from FormData, so restore them before collecting it.
            form.querySelectorAll('input[type="checkbox"]').forEach(function (c) { c.disabled = false; });
            var datos = new FormData(form); form.querySelectorAll('input[type="checkbox"]').forEach(function (c) { c.disabled = true; }); mensaje("Guardando…");
            try { await enviar(form, datos); mensaje(campo.checked ? "La función se ha activado correctamente." : "La función se ha desactivado correctamente."); }
            catch (error) { campo.checked = anterior; mensaje(error.message || "Error de conexión. Inténtalo nuevamente.", true); }
            finally { guardando = false; form.querySelectorAll('input[type="checkbox"]').forEach(function (c) { c.disabled = false; }); }
        });
    });
    var permisos = pagina.querySelector('form[action*="permisos"]');
    if (!permisos) return;
    var toggleBusqueda = document.getElementById("pagina-search-toggle"), campoBusqueda = document.getElementById("pagina-search-input");
    var panelBusqueda = document.getElementById("pagina-search-field"), contadorBusqueda = document.getElementById("pagina-search-count");
    var sinResultados = document.getElementById("pagina-search-empty"), filas = Array.from(permisos.querySelectorAll("[data-permiso-cuenta]"));
    function normalizar(texto) { return texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase(); }
    function filtrarCuentas() {
        var termino = normalizar(campoBusqueda.value.trim()), visibles = 0;
        filas.forEach(function (fila) { var datos = fila.cells[0].textContent + " " + fila.cells[1].textContent; var visible = normalizar(datos).includes(termino); fila.hidden = !visible; if (visible) visibles++; });
        sinResultados.hidden = !termino || visibles > 0 || filas.length === 0;
        contadorBusqueda.textContent = termino ? visibles + (visibles === 1 ? " cuenta encontrada" : " cuentas encontradas") : "";
    }
    toggleBusqueda.addEventListener("click", function () { var abrir = panelBusqueda.hidden; panelBusqueda.hidden = !abrir; toggleBusqueda.setAttribute("aria-expanded", String(abrir)); if (abrir) campoBusqueda.focus(); else { campoBusqueda.value = ""; filtrarCuentas(); toggleBusqueda.focus(); } });
    campoBusqueda.addEventListener("input", filtrarCuentas);
    campoBusqueda.addEventListener("keydown", function (evento) { if (evento.key === "Enter") evento.preventDefault(); if (evento.key === "Escape") { evento.preventDefault(); toggleBusqueda.click(); } });
    campoBusqueda.addEventListener("search", filtrarCuentas);
    permisos.querySelectorAll('input[type="checkbox"]').forEach(function (campo) {
        campo.removeAttribute("onchange");
        campo.addEventListener("change", function () {
            var nuevo = campo.checked, fila = campo.closest("tr"); campo.checked = !nuevo;
            if (!window.DoggerConfirma) { mensaje("No se pudo abrir la confirmación.", true); return; }
            window.DoggerConfirma((nuevo ? "Conceder " : "Revocar ") + campo.getAttribute("aria-label") + ".", async function () {
                if (guardando) return; guardando = true; campo.disabled = true; mensaje("Guardando permiso…");
                var datos = new FormData(); datos.append("csrfmiddlewaretoken", permisos.querySelector('[name="csrfmiddlewaretoken"]').value);
                datos.append("uid", fila.querySelector('[name="uid"]').value);
                datos.append("permiso_unico", campo.name.replace(/^perm_\d+_/, "")); datos.append("valor", nuevo ? "1" : "0");
                try { await enviar(permisos, datos); campo.checked = nuevo; mensaje("Permiso actualizado correctamente."); }
                catch (error) { mensaje(error.message || "Error de conexión. Inténtalo nuevamente.", true); }
                finally { campo.disabled = false; guardando = false; }
            }, "Confirmar cambio", { titulo:"¿Confirmar cambio de permiso?", icono:"#i-shield" });
        });
    });
})();
