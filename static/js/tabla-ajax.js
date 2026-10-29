(function () {
    "use strict";
    var form = document.querySelector('[data-ajax-table-form="usuarios"]');
    if (!form) return;
    var region = document.querySelector('[data-ajax-table-region="usuarios"]');
    var search = form.querySelector('input[type="search"]');
    if (!region || !search) return;
    var timer = null, controller = null, secuencia = 0;
    function urlFormulario() {
        var url = new URL(form.getAttribute("action") || location.pathname, location.href);
        url.search = new URLSearchParams(new FormData(form)).toString();
        url.searchParams.delete("page");
        var perPage = region.querySelector("[data-per-page-param]");
        if (perPage) url.searchParams.set(perPage.dataset.perPageParam, perPage.value);
        return url;
    }
    function cargar(url, historial) {
        clearTimeout(timer); if (controller) controller.abort();
        controller = typeof AbortController === "function" ? new AbortController() : null;
        var actual = ++secuencia; region.setAttribute("aria-busy", "true");
        fetch(url, { credentials:"same-origin", headers:{"X-Requested-With":"XMLHttpRequest"}, signal:controller ? controller.signal : undefined })
            .then(function (r) { if (!r.ok || r.redirected) throw new Error("No se pudo actualizar la tabla"); return r.text(); })
            .then(function (html) {
                if (actual !== secuencia) return;
                var doc = new DOMParser().parseFromString(html, "text/html");
                var nueva = doc.querySelector('[data-ajax-table-region="usuarios"]');
                if (!nueva) throw new Error("Respuesta incompleta");
                region.innerHTML = nueva.innerHTML;
                var nuevoConteo = doc.querySelector('[data-ajax-table-form="usuarios"] .toolbar-count');
                var conteo = form.querySelector(".toolbar-count"); if (nuevoConteo && conteo) conteo.textContent = nuevoConteo.textContent;
                if (historial) history.pushState({tablaUsuarios:true}, "", url.pathname + url.search + url.hash);
                region.dispatchEvent(new CustomEvent("dogger:tabla-actualizada", {bubbles:true}));
            })
            .catch(function (error) { if (error.name !== "AbortError" && actual === secuencia) location.href = url.href; })
            .finally(function () { if (actual === secuencia) region.removeAttribute("aria-busy"); });
    }
    search.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(function () { cargar(urlFormulario(), true); }, 350); });
    form.addEventListener("submit", function (e) { e.preventDefault(); cargar(urlFormulario(), true); });
    form.addEventListener("click", function (e) {
        var enlace = e.target.closest(".users-clear-button[href]");
        if (!enlace || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
        e.preventDefault(); var url = new URL(enlace.href, location.href); sincronizarFormulario(url); cargar(url, true);
    });
    region.addEventListener("click", function (e) {
        var a = e.target.closest(".pagination-links a[href], .pagination-bar a.page-pill[href]");
        if (!a || e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || (a.target && a.target !== "_self")) return;
        var url = new URL(a.href, location.href); if (url.origin !== location.origin) return;
        e.preventDefault(); cargar(url, true);
    });
    region.addEventListener("change", function (e) {
        var select = e.target.closest("select[data-per-page-param]"); if (!select) return;
        e.stopImmediatePropagation(); var url = new URL(location.href);
        url.searchParams.set(select.dataset.perPageParam, select.value); url.searchParams.delete("page"); cargar(url, true);
    }, true);
    function sincronizarFormulario(url) {
        search.value = url.searchParams.get(search.name) || "";
        form.querySelectorAll("[data-toolbar-picker]").forEach(function (picker) {
            var campo = picker.querySelector('input[type="hidden"][name]'); if (!campo) return;
            campo.value = url.searchParams.get(campo.name) || "";
            picker.dataset.selectedValue = campo.value || "todos";
            picker.querySelectorAll("[data-picker-value]").forEach(function (opcion) {
                var seleccionado = opcion.dataset.pickerValue === campo.value;
                opcion.setAttribute("aria-selected", String(seleccionado));
                if (seleccionado) picker.querySelector("[data-picker-label]").textContent = opcion.textContent.trim();
            });
        });
        var rol = form.querySelector('input[name="rol"]'); if (rol) rol.value = url.searchParams.get("rol") || "";
    }
    window.addEventListener("popstate", function () { var url = new URL(location.href); sincronizarFormulario(url); cargar(url, false); });
})();

/* Regiones optativas: la respuesta sigue siendo la plantilla real de Django. */
(function () {
    "use strict";
    document.querySelectorAll("[data-ajax-list-region]").forEach(function (region) {
        var id = region.dataset.ajaxListRegion;
        var form = document.querySelector('[data-ajax-list-form="' + id + '"]');
        var search = form && form.querySelector('input[type="search"]');
        var timer, controller, version = 0;
        function cargar(url, guardar) {
            clearTimeout(timer); if (controller) controller.abort();
            controller = typeof AbortController === "function" ? new AbortController() : null;
            var actual = ++version; region.setAttribute("aria-busy", "true");
            fetch(url, {credentials:"same-origin", headers:{"X-Requested-With":"XMLHttpRequest"}, signal:controller ? controller.signal : undefined})
                .then(function (r) { if (!r.ok || r.redirected) throw new Error("Respuesta no disponible"); return r.text(); })
                .then(function (html) {
                    if (actual !== version) return;
                    var doc = new DOMParser().parseFromString(html, "text/html"), nuevo = doc.querySelector('[data-ajax-list-region="' + id + '"]');
                    if (!nuevo) throw new Error("Región no disponible");
                    region.innerHTML = nuevo.innerHTML;
                    if (guardar) history.pushState({tablaAjax:id}, "", url.pathname + url.search + url.hash);
                    region.dispatchEvent(new CustomEvent("dogger:tabla-actualizada", {bubbles:true}));
                })
                .catch(function (e) { if (e.name !== "AbortError" && actual === version) location.href = url.href; })
                .finally(function () { if (actual === version) region.removeAttribute("aria-busy"); });
        }
        function urlFormulario() { var url = new URL(form.action || location.pathname, location.href); url.search = new URLSearchParams(new FormData(form)).toString(); url.searchParams.delete("page"); return url; }
        if (form && search) {
            search.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(function () { cargar(urlFormulario(), true); }, 350); });
            form.addEventListener("submit", function (e) { e.preventDefault(); cargar(urlFormulario(), true); });
            form.addEventListener("click", function (e) { var link = e.target.closest("a.link-clear"); if (!link || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return; e.preventDefault(); search.value = ""; cargar(new URL(link.href, location.href), true); });
        }
        region.addEventListener("click", function (e) {
            var link = e.target.closest(".pagination-links a[href], .pap-empty a[href]");
            if (!link || e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || (link.target && link.target !== "_self")) return;
            var url = new URL(link.href, location.href); if (url.origin !== location.origin || url.pathname !== location.pathname) return;
            if (search && link.closest(".pap-empty")) search.value = url.searchParams.get(search.name) || "";
            e.preventDefault(); cargar(url, true);
        });
        region.addEventListener("change", function (e) {
            var select = e.target.closest("select[data-per-page-param]"); if (!select) return;
            e.stopImmediatePropagation(); var url = new URL(location.href); url.searchParams.set(select.dataset.perPageParam, select.value); url.searchParams.delete("page"); cargar(url, true);
        }, true);
        window.addEventListener("popstate", function () { var url = new URL(location.href); if (search) search.value = url.searchParams.get(search.name) || ""; cargar(url, false); });
    });
})();
