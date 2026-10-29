/* Selector visual de categorías. Conserva el select de Django sincronizado. */
(function () {
    "use strict";
    function esc(v) { return String(v || "").replace(/[&<>"]/g, function (c) { return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]; }); }
    function icono(t) {
        if (window.DoggerCategoryIcons) return window.DoggerCategoryIcons.resolve(t).icon;
        t = String(t || "").toLowerCase();
        if (/ventas|pedido/.test(t)) return "ShoppingCart";
        if (/producci|bodega/.test(t)) return "Package";
        if (/contabil|pago/.test(t)) return "Calculator";
        if (/factur/.test(t)) return "FileText";
        if (/reporte|tablero/.test(t)) return "ChartColumnIncreasing";
        if (/nomina/.test(t)) return "UsersRound";
        if (/autogesti/.test(t)) return "UserRoundCheck";
        if (/access|permiso/.test(t)) return "KeyRound";
        if (/cloud/.test(t)) return "Cloud";
        if (/cajon|monedero/.test(t)) return "Package";
        if (/impres|escan/.test(t)) return "Printer";
        if (/inventario|precio|lector|balanza/.test(t)) return "ScanLine";
        if (/sincron|dato/.test(t)) return "Database";
        if (/pos.*hard|pc|laptop/.test(t)) return "Laptop";
        if (/pos.*soft|software|aplicaci/.test(t)) return "Layers";
        if (/perifer/.test(t)) return "Usb";
        if (/red|switch|wifi|internet/.test(t)) return "Network";
        if (/firewall|watchguard|antivirus/.test(t)) return "ShieldAlert";
        if (/server|servidor|terminal/.test(t)) return "Server";
        if (/backup/.test(t)) return "HardDriveDownload";
        if (/marcacion|horario/.test(t)) return "Clock";
        if (/transfer|integracion/.test(t)) return "Activity";
        if (/web service|navegador|web/.test(t)) return "Globe2";
        if (/correo|mail/.test(t)) return "BellRing";
        if (/hardware/.test(t)) return "Wrench";
        if (/instal/.test(t)) return "Download";
        if (/actualiza|parche/.test(t)) return "RefreshCw";
        if (/creacion.*usuario|solicitud.*equipo/.test(t)) return "UserPlus";
        if (/acceso|usuario/.test(t)) return "ShieldCheck";
        return "FolderClosed";
    }
    function tono(t) {
        if (window.DoggerCategoryIcons) return window.DoggerCategoryIcons.resolve(t).tone;
        t = String(t || "").toLowerCase();
        if (/acceso|usuario|permiso|nomina|autogesti/.test(t)) return "violet";
        if (/red|switch|firewall|watchguard|server|backup|antivirus/.test(t)) return "blue";
        if (/pos|cajon|impres|lector|balanza|inventario/.test(t)) return "orange";
        if (/siesa|software|web|cloud|integracion/.test(t)) return "teal";
        if (/factur|contabil|venta|pedido|producci/.test(t)) return "rose";
        return "slate";
    }
    function svg(nombre) { return window.DoggerIcons ? window.DoggerIcons.icon(nombre) : '<svg class="icon" aria-hidden="true"><use href="#i-folder"/></svg>'; }
    function iniciar(contenedor) {
        var select = contenedor.querySelector("select");
        if (!select || select.disabled || contenedor.dataset.pickerReady === "1") return;
        contenedor.dataset.pickerReady = "1";
        select.classList.add("category-picker-native"); select.tabIndex = -1;
        var actual = document.createElement("button");
        actual.type = "button"; actual.className = "category-picker-current";
        actual.setAttribute("aria-haspopup", "listbox"); actual.setAttribute("aria-expanded", "false");
        actual.setAttribute("aria-label", "Cambiar categoría de la solicitud");
        var menu = document.createElement("section");
        menu.className = "category-picker-menu"; menu.hidden = true;
        menu.innerHTML = '<div class="category-picker-search">' + svg("Search") + '<input type="search" placeholder="Buscar categoría…" aria-label="Buscar categoría"></div><div class="category-picker-options" role="listbox"></div>';
        contenedor.appendChild(actual); contenedor.appendChild(menu);
        var busqueda = menu.querySelector("input"), opciones = menu.querySelector(".category-picker-options"), items = [];
        select.querySelectorAll("optgroup").forEach(function (grupo) {
            Array.prototype.forEach.call(grupo.querySelectorAll("option"), function (opcion) { items.push({ valor: opcion.value, nombre: opcion.textContent.trim(), grupo: grupo.label.trim() }); });
        });
        function elegido() { return items.filter(function (item) { return item.valor === select.value; })[0]; }
        function pintarActual() {
            var item = elegido();
            actual.innerHTML = item
                ? '<span class="category-picker-current-icon cat-tone-' + tono(item.grupo + " " + item.nombre) + '">' + svg(icono(item.grupo + " " + item.nombre)) + '</span><span><small>' + esc(item.grupo) + '</small><strong>' + esc(item.nombre) + '</strong></span>' + svg("ChevronDown")
                : '<span class="category-picker-current-icon">' + svg("FolderClosed") + '</span><span><small>Selecciona una categoría</small><strong>Elige el tipo de incidencia</strong></span>' + svg("ChevronDown");
            var encabezado = contenedor.parentElement.querySelector("[data-category-picker-heading]");
            if (encabezado && item) {
                var iconoEncabezado = encabezado.querySelector(".category-heading-icon");
                iconoEncabezado.className = "category-heading-icon cat-tone-" + tono(item.grupo + " " + item.nombre);
                iconoEncabezado.innerHTML = svg(icono(item.grupo + " " + item.nombre));
                encabezado.querySelector(".category-heading-copy").textContent = "Categoría: " + item.nombre;
            }
        }
        function pintarOpciones() {
            var q = busqueda.value.trim().toLowerCase(), grupoActual = "";
            var visibles = items.filter(function (item) { return !q || (item.nombre + " " + item.grupo).toLowerCase().indexOf(q) !== -1; });
            opciones.innerHTML = "";
            visibles.forEach(function (item) {
                if (item.grupo !== grupoActual) { grupoActual = item.grupo; var titulo = document.createElement("p"); titulo.className = "category-picker-group"; titulo.innerHTML = svg(icono(item.grupo)) + esc(item.grupo); opciones.appendChild(titulo); }
                var boton = document.createElement("button"); boton.type = "button";
                boton.className = "category-picker-option" + (item.valor === select.value ? " is-selected" : "");
                boton.setAttribute("role", "option"); boton.setAttribute("aria-selected", item.valor === select.value ? "true" : "false");
                boton.innerHTML = '<span class="category-picker-option-icon cat-tone-' + tono(item.grupo + " " + item.nombre) + '">' + svg(icono(item.grupo + " " + item.nombre)) + '</span><span><strong>' + esc(item.nombre) + '</strong><small>' + esc(item.grupo) + '</small></span>' + (item.valor === select.value ? svg("Check") : "");
                boton.addEventListener("click", function () { select.value = item.valor; select.dispatchEvent(new Event("change", { bubbles: true })); cerrar(); }); opciones.appendChild(boton);
            });
            if (!visibles.length) opciones.innerHTML = '<p class="category-picker-empty">No encontramos una categoría con ese nombre.</p>';
        }
        function abrir() { menu.hidden = false; actual.setAttribute("aria-expanded", "true"); pintarOpciones(); busqueda.focus(); }
        function cerrar() { menu.hidden = true; actual.setAttribute("aria-expanded", "false"); actual.focus(); }
        actual.addEventListener("click", function () { menu.hidden ? abrir() : cerrar(); });
        busqueda.addEventListener("input", pintarOpciones);
        select.addEventListener("change", function () { pintarActual(); pintarOpciones(); });
        document.addEventListener("click", function (event) { if (!contenedor.contains(event.target) && !menu.hidden) cerrar(); });
        document.addEventListener("keydown", function (event) { if (event.key === "Escape" && !menu.hidden) cerrar(); });
        pintarActual();
    }
    document.addEventListener("DOMContentLoaded", function () { document.querySelectorAll("[data-category-picker]").forEach(iniciar); });
})();
