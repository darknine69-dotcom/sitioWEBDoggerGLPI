(function () {
    "use strict";
    // Solo abre controles ya presentes; nunca envía formularios ni cambia datos.
    function openDestination() {
        var hash = location.hash, target, card, trigger;
        if (hash === "#buscar-crear-cuenta") {
            target = document.getElementById("modal-usuario");
            trigger = document.querySelector("button[data-new-user][data-open-modal='#modal-usuario']");
            if (target && trigger && !target.classList.contains("open")) trigger.click();
        } else if (hash === "#buscar-crear-categoria") {
            target = document.getElementById("formCategoriaGrupo");
            trigger = document.querySelector("button[data-inline-toggle='formCategoriaGrupo']");
            if (target && trigger && !target.classList.contains("open")) trigger.click();
            if (target && target.classList.contains("open")) target.scrollIntoView({ block: "center" });
        } else if (hash === "#crear-zona") {
            target = document.getElementById("crear-zona");
            if (target) { target.scrollIntoView({ block: "center" }); var field = target.querySelector("input[name='nombre']"); if (field) field.focus({ preventScroll: true }); }
        } else if (/^#buscar-categoria-\d+$/.test(hash)) {
            target = document.getElementById(hash.slice(1));
            if (!target) return;
            card = target.closest(".cat-group-card");
            if (card && card.classList.contains("collapsed")) { trigger = card.querySelector(".cat-group-head"); if (trigger) trigger.click(); }
            card = target.closest(".cat-grupo");
            if (card && card.classList.contains("collapsed")) { trigger = card.querySelector(".cat-grupo-head"); if (trigger) trigger.click(); }
            if (target.classList.contains("cat-item")) { trigger = target.querySelector(".cat-item-head"); if (trigger && trigger.getAttribute("aria-expanded") !== "true") trigger.click(); }
            target.scrollIntoView({ block: "center" });
        }
    }
    window.addEventListener("DOMContentLoaded", openDestination);
    window.addEventListener("hashchange", openDestination);
    document.addEventListener("click", function (event) {
        var link = event.target.closest("[data-global-search-results] a[href]");
        if (!link) return;
        var destination = new URL(link.href, location.href);
        if (destination.origin === location.origin && destination.pathname === location.pathname && destination.search === location.search && destination.hash === location.hash) openDestination();
    });
}());
