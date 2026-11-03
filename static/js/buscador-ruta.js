(function () {
    "use strict";
    var key = "dogger:search-navigation";

    function read() {
        try { return JSON.parse(sessionStorage.getItem(key) || "null"); } catch (_) { return null; }
    }
    function store(value) {
        try { sessionStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* Navegación normal sin almacenamiento. */ }
    }
    function render() {
        var nav = document.querySelector(".dogger-page-breadcrumb"), data = read();
        if (!nav) return;
        nav.querySelectorAll("[data-search-origin]").forEach(function (node) { node.remove(); });
        var current = nav.querySelector("[data-current-crumb]");
        if (current) current.setAttribute("aria-current", "page");
        if (!data || Date.now() - data.created > 1800000) return;
        var actual = location.pathname + location.search + location.hash;
        if (data.destination !== actual) return;
        var source;
        try { source = new URL(data.origin, location.origin); } catch (_) { return; }
        if (source.origin !== location.origin || source.href === location.href || !data.label) return;
        var icon = nav.querySelector(".dogger-crumb-icon"), link = document.createElement("a"), separator = document.createElement("span");
        link.href = source.pathname + source.search + source.hash;
        link.textContent = String(data.label).slice(0, 100);
        link.dataset.searchOrigin = "1";
        separator.textContent = "›"; separator.setAttribute("aria-hidden", "true"); separator.dataset.searchOrigin = "1";
        var next = icon ? icon.nextSibling : nav.firstChild;
        nav.insertBefore(link, next); nav.insertBefore(separator, next);
        if (current && data.result && current.textContent.trim().toLocaleLowerCase() !== String(data.result).trim().toLocaleLowerCase()) {
            var endSeparator = document.createElement("span"), result = document.createElement("span");
            endSeparator.textContent = "›"; endSeparator.setAttribute("aria-hidden", "true"); endSeparator.dataset.searchOrigin = "1";
            result.textContent = String(data.result).slice(0, 120); result.setAttribute("aria-current", "page"); result.dataset.searchOrigin = "1";
            current.removeAttribute("aria-current"); nav.append(endSeparator, result);
        }
    }

    document.addEventListener("click", function (event) {
        var link = event.target.closest("[data-global-search-results] a[href]");
        if (!link || link.dataset.ticketFicha || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.target === "_blank") return;
        var destination = new URL(link.href, location.href);
        if (destination.origin !== location.origin) return;
        var nav = document.querySelector(".dogger-page-breadcrumb [data-current-crumb]");
        var title = document.querySelector(".topbar-titles h1");
        var label = (nav && nav.textContent.trim()) || (title && title.textContent.trim()) || "Inicio";
        var result = link.querySelector("strong");
        store({ origin: location.pathname + location.search + location.hash, label: label, result: result ? result.textContent.trim() : "", destination: destination.pathname + destination.search + destination.hash, created: Date.now() });
        if (destination.href === location.href) setTimeout(render, 0);
    }, true);
    document.addEventListener("DOMContentLoaded", render);
    window.addEventListener("hashchange", render);
}());
