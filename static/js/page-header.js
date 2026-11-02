(function () {
    "use strict";
    document.querySelectorAll("[data-page-clock]").forEach(function (contenedor) {
        var zona = contenedor.dataset.timeZone, fecha = contenedor.querySelector("[data-page-date]"), hora = contenedor.querySelector("[data-page-time]");
        function actualizar() {
            var ahora = new Date();
            try {
                fecha.textContent = new Intl.DateTimeFormat("es-CO", { timeZone:zona, weekday:"long", day:"numeric", month:"long", year:"numeric" }).format(ahora);
                hora.textContent = new Intl.DateTimeFormat("es-CO", { timeZone:zona, hour:"2-digit", minute:"2-digit", second:"2-digit", hour12:false }).format(ahora);
                fecha.dateTime = hora.dateTime = ahora.toISOString();
            } catch (_) { fecha.textContent = ahora.toLocaleDateString("es-CO"); hora.textContent = ahora.toLocaleTimeString("es-CO", {hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false}); }
        }
        actualizar(); setInterval(actualizar, 1000);
    });
    var nav = document.querySelector("[data-profile-breadcrumb]");
    if (!nav) return;
    var secciones = { perfil:"Mi perfil", password:"Contraseña", ayuda:"Ayuda y tour", notificaciones:"Notificaciones", atajos:"Atajos", glpi:"GLPI", pagina:"Página" };
    function perfil() {
        nav.querySelectorAll("[data-profile-extra]").forEach(function (el) { el.remove(); });
        var key = location.hash.slice(1), texto = secciones[key];
        if (!texto || key === "perfil" || !document.querySelector('[data-settings-panel="' + key + '"]')) { nav.querySelector("[data-current-crumb]").textContent = "Mi perfil"; return; }
        var actual = nav.querySelector("[data-current-crumb]"), enlace = document.createElement("a"), separador = document.createElement("span");
        enlace.href = nav.dataset.profileUrl + "#perfil"; enlace.textContent = "Mi perfil"; enlace.dataset.profileExtra = "1";
        separador.textContent = "›"; separador.setAttribute("aria-hidden", "true"); separador.dataset.profileExtra = "1";
        nav.insertBefore(enlace, actual); nav.insertBefore(separador, actual); actual.textContent = texto;
    }
    perfil(); window.addEventListener("hashchange", perfil);
})();
