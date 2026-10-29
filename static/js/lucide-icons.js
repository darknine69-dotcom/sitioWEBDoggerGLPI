/*
 * Dogger Icons · subconjunto local de Lucide Icons.
 *
 * El proyecto usa un sprite SVG local para funcionar sin red. Este adaptador
 * conserva esa ventaja y ofrece los nombres oficiales de Lucide a plantillas
 * y contenido insertado por fetch: <span data-lucide="Search"></span>.
 * No usa MutationObserver: quien agregue contenido dinámico puede ejecutar
 * DoggerIcons.hydrate(contenedor) una sola vez después de insertarlo.
 */
(function () {
    "use strict";
    var nombres = {
        LayoutDashboard: "grid", Ticket: "ticket", ChartColumnIncreasing: "chart",
        Monitor: "monitor", Users: "users", FolderClosed: "folder", Layers: "layers",
        CalendarDays: "calendar", CalendarClock: "calendar-clock",
        ShieldCheck: "shield-check", Trash2: "trash", History: "history",
        Settings: "settings", CircleHelp: "help", CircleAlert: "circle-alert",
        Wrench: "wrench", CircleCheckBig: "check-circle", LockKeyhole: "lock",
        ClockAlert: "clock-alert", Hourglass: "hourglass", TriangleAlert: "alert",
        UserRoundCheck: "user-round-check", MapPin: "map-pin", Eye: "eye",
        UsersRound: "users", Activity: "activity", TrendingUp: "trending-up",
        ShieldAlert: "shield-alert", Plus: "plus", Pencil: "pencil",
        Download: "download", FileSpreadsheet: "excel", Search: "search",
        Filter: "filter", RefreshCw: "refresh", EllipsisVertical: "ellipsis",
        ChevronDown: "chevron-down", X: "x", Check: "check",
        MessageCircle: "message", Bell: "bell", CalendarCheck: "calendar-check",
        BellRing: "bell-ring", ListTodo: "list-todo", MessagesSquare: "messages-square",
        CalendarX: "calendar-x", Clock: "clock", Megaphone: "megaphone",
        Send: "send", Paperclip: "paperclip", Smile: "smile", FileText: "file",
        KeyRound: "key-round", Server: "server", Database: "database",
        HardDriveDownload: "hard-drive", Usb: "usb", Package: "package",
        Globe2: "globe", Calculator: "calculator", Cloud: "cloud",
        UserPlus: "user-plus", ScanLine: "scan-line", ShoppingCart: "shopping-cart",
        Printer: "printer", Laptop: "monitor", Network: "ip", LockKeyhole: "lock"
    };

    function icono(nombre, clase, etiqueta) {
        var id = nombres[nombre] || nombre || "circle-alert";
        var aria = etiqueta ? ' role="img" aria-label="' + escapar(etiqueta) + '"' : ' aria-hidden="true"';
        return '<svg class="icon lucide-icon ' + escapar(clase || "") + '"' + aria + '><use href="#i-' + escapar(id) + '"/></svg>';
    }
    function escapar(valor) {
        return String(valor || "").replace(/[&<>"]/g, function (caracter) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[caracter];
        });
    }
    function hidratar(raiz) {
        (raiz || document).querySelectorAll("[data-lucide]").forEach(function (nodo) {
            if (nodo.dataset.lucideReady === "1") return;
            var etiqueta = nodo.getAttribute("data-lucide-label") || "";
            nodo.innerHTML = icono(nodo.getAttribute("data-lucide"), nodo.getAttribute("data-lucide-class") || "", etiqueta);
            nodo.dataset.lucideReady = "1";
        });
    }
    window.DoggerIcons = { icon: icono, hydrate: hidratar, names: nombres };
    /* Un solo catálogo semántico para toda aparición de categorías. */
    function categoria(texto) {
        var t = String(texto || "").toLowerCase(), icon = "FolderClosed", tone = "slate";
        if (/ventas|pedido/.test(t)) { icon="ShoppingCart"; tone="rose"; }
        else if (/producci|bodega/.test(t)) { icon="Package"; tone="rose"; }
        else if (/contabil|pago/.test(t)) { icon="Calculator"; tone="rose"; }
        else if (/factur/.test(t)) { icon="FileText"; tone="rose"; }
        else if (/reporte|tablero/.test(t)) { icon="ChartColumnIncreasing"; tone="rose"; }
        else if (/nomina/.test(t)) { icon="UsersRound"; tone="violet"; }
        else if (/autogesti/.test(t)) { icon="UserRoundCheck"; tone="violet"; }
        else if (/access|permiso/.test(t)) { icon="KeyRound"; tone="violet"; }
        else if (/cloud/.test(t)) { icon="Cloud"; tone="teal"; }
        else if (/cajon|monedero/.test(t)) { icon="Package"; tone="orange"; }
        else if (/impres|escan/.test(t)) { icon="Printer"; tone="orange"; }
        else if (/inventario|precio|lector|balanza/.test(t)) { icon="ScanLine"; tone="orange"; }
        else if (/sincron|dato/.test(t)) { icon="Database"; tone="orange"; }
        else if (/pos.*hard|pc|laptop/.test(t)) { icon="Laptop"; tone="orange"; }
        else if (/pos.*soft|software|aplicaci/.test(t)) { icon="Layers"; tone="teal"; }
        else if (/perifer/.test(t)) { icon="Usb"; tone="orange"; }
        else if (/red|switch|wifi|internet/.test(t)) { icon="Network"; tone="blue"; }
        else if (/firewall|watchguard|antivirus/.test(t)) { icon="ShieldAlert"; tone="blue"; }
        else if (/server|servidor|terminal/.test(t)) { icon="Server"; tone="blue"; }
        else if (/backup/.test(t)) { icon="HardDriveDownload"; tone="blue"; }
        else if (/marcacion|horario/.test(t)) { icon="Clock"; tone="blue"; }
        else if (/transfer|integracion/.test(t)) { icon="Activity"; tone="teal"; }
        else if (/web service|navegador|web/.test(t)) { icon="Globe2"; tone="teal"; }
        else if (/correo|mail/.test(t)) { icon="BellRing"; tone="teal"; }
        else if (/hardware/.test(t)) { icon="Wrench"; tone="orange"; }
        else if (/instal/.test(t)) { icon="Download"; tone="teal"; }
        else if (/actualiza|parche/.test(t)) { icon="RefreshCw"; tone="teal"; }
        else if (/creacion.*usuario|solicitud.*equipo/.test(t)) { icon="UserPlus"; tone="violet"; }
        else if (/acceso|usuario/.test(t)) { icon="ShieldCheck"; tone="violet"; }
        return { icon: icon, tone: tone };
    }
    function decorarCategorias(raiz) {
        (raiz || document).querySelectorAll("[data-category-label]").forEach(function (elemento) {
            var spec = categoria((elemento.dataset.categoryGroup || "") + " " + elemento.dataset.categoryLabel);
            var destino = elemento.querySelector("[data-category-icon]");
            if (!destino) return;
            destino.className = "category-shared-icon cat-tone-" + spec.tone;
            destino.innerHTML = icono(spec.icon);
        });
    }
    window.DoggerCategoryIcons = { resolve: categoria, decorate: decorarCategorias };
    document.addEventListener("DOMContentLoaded", function () { hidratar(document); decorarCategorias(document); });
})();
