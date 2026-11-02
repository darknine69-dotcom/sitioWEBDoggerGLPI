(function () {
    "use strict";
    var root = document.querySelector("[data-global-search]");
    if (!root) return;
    var input = root.querySelector("[data-global-search-input]"), results = root.querySelector("[data-global-search-results]");
    var clear = root.querySelector("[data-global-search-clear]"), timer, controller, sequence = 0, active = -1;
    function close() { results.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); active = -1; }
    function mark(node, text, query) {
        text = String(text || ""); var at = text.toLocaleLowerCase().indexOf(query.toLocaleLowerCase());
        if (at < 0) { node.textContent = text; return; }
        node.append(document.createTextNode(text.slice(0, at))); var m = document.createElement("mark"); m.textContent = text.slice(at, at + query.length); node.append(m, document.createTextNode(text.slice(at + query.length)));
    }
    function heading(label) { var h = document.createElement("p"); h.className = "global-search-heading"; h.textContent = label; results.appendChild(h); }
    function item(label, detail, url, query, ticket, avatar, icon) {
        var link = document.createElement("a"); link.href = url; link.setAttribute("role", "option"); link.setAttribute("aria-selected", "false"); link.id = "global-result-" + results.querySelectorAll("a").length;
        if (ticket) link.dataset.ticketFicha = ticket;
        if (avatar) { var img = document.createElement("img"); img.src = avatar; img.alt = ""; img.className = "global-search-avatar"; link.appendChild(img); }
        else if (icon) { var glyph = icon.cloneNode(true); glyph.removeAttribute("id"); glyph.setAttribute("aria-hidden", "true"); link.appendChild(glyph); }
        var content = document.createElement("span"), title = document.createElement("strong"), caption = document.createElement("small");
        mark(title, label, query); caption.textContent = detail || ""; content.append(title, caption); link.appendChild(content); results.appendChild(link);
    }
    function search() {
        var query = input.value.trim(), current = ++sequence;
        if (controller) controller.abort();
        if (query.length < 2) { close(); return; }
        controller = new AbortController(); active = -1; input.removeAttribute("aria-activedescendant");
        var nav = Array.from(document.querySelectorAll(".sidebar a.sidebar-link[href]"))
            .filter(function (a) { return a.getClientRects().length && a.textContent.trim().toLocaleLowerCase().includes(query.toLocaleLowerCase()); }).slice(0, 6);
        results.replaceChildren();
        var status = document.createElement("p"); status.className = "global-search-status"; status.textContent = "Buscando…"; results.appendChild(status);
        results.hidden = false; input.setAttribute("aria-expanded", "true");
        var url = new URL(root.dataset.url, location.origin); url.searchParams.set("q", query); url.searchParams.set("global", "1"); url.searchParams.set("contexto", location.pathname);
        fetch(url, { signal: controller.signal, headers: { Accept: "application/json" } })
            .then(function (response) { if (!response.ok) throw new Error("search failed"); return response.json(); })
            .then(function (data) {
                if (current !== sequence) return;
                results.replaceChildren();
                var tickets = Array.isArray(data.tickets) ? data.tickets.slice(0, 6) : [];
                if (tickets.length) { heading("Tickets"); tickets.forEach(function (t) { item(t.codigo + " · " + t.titulo, [t.estado_display, t.prioridad_display, t.ans_vencido ? "ANS vencido" : ""].filter(Boolean).join(" · "), t.url, query, t.pk); }); }
                if (Array.isArray(data.funciones) || Array.isArray(data.registros)) {
                    var groups = new Map();
                    (data.funciones || []).concat(data.registros || []).forEach(function (entry) { if (!groups.has(entry.categoria)) groups.set(entry.categoria, []); groups.get(entry.categoria).push(entry); });
                    groups.forEach(function (entries, name) {
                        heading(name);
                        entries.forEach(function (entry) {
                            var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg"), use = document.createElementNS("http://www.w3.org/2000/svg", "use");
                            svg.classList.add("icon"); use.setAttribute("href", "#" + entry.icono); svg.appendChild(use);
                            item(entry.nombre, entry.descripcion, entry.url, query, null, null, svg);
                        });
                    });
                }
                [["Técnicos", data.tecnicos], ["Puntos de venta", data.puntos], ["Categorías", data.categorias]].forEach(function (group) {
                    if (!Array.isArray(group[1]) || !group[1].length) return;
                    heading(group[0]); group[1].forEach(function (entry) { item(entry.nombre, "Ver ticket relacionado", entry.url, query, entry.ticket_pk, entry.avatar); });
                });
                if (nav.length) { heading("Secciones"); nav.forEach(function (a) { var path = new URL(a.href, location.href).pathname; item(a.textContent.trim(), path, a.href, query, null, null, a.querySelector("svg")); }); }
                if (!results.querySelector("a")) { status.textContent = "No se encontraron resultados."; results.appendChild(status); }
            })
            .catch(function (error) { if (error.name !== "AbortError" && current === sequence) { status.textContent = "No se pudieron consultar los resultados."; } });
    }
    input.addEventListener("input", function () { clearTimeout(timer); if (controller) controller.abort(); ++sequence; clear.hidden = !input.value; if (input.value.trim().length < 2) close(); else timer = setTimeout(search, 300); });
    input.addEventListener("focus", function () { if (input.value.trim().length >= 2) search(); });
    input.addEventListener("keydown", function (event) {
        if (event.key === "Escape") { close(); return; }
        var items = Array.from(results.querySelectorAll("a"));
        if ((event.key === "ArrowDown" || event.key === "ArrowUp") && items.length && !results.hidden) {
            event.preventDefault(); active = (active + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
            items.forEach(function (link, index) { link.classList.toggle("is-selected", index === active); link.setAttribute("aria-selected", index === active ? "true" : "false"); });
            input.setAttribute("aria-activedescendant", items[active].id); items[active].scrollIntoView({ block: "nearest" });
        } else if (event.key === "Enter" && active >= 0 && !results.hidden && items[active]) { event.preventDefault(); items[active].click(); }
    });
    clear.addEventListener("click", function () { clearTimeout(timer); if (controller) controller.abort(); ++sequence; input.value = ""; clear.hidden = true; close(); input.focus(); });
    document.addEventListener("keydown", function (event) { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); input.focus(); if (input.value.trim().length < 2) { results.replaceChildren(); var p = document.createElement("p"); p.className = "global-search-status"; p.textContent = "Escribe al menos dos caracteres para buscar."; results.appendChild(p); results.hidden = false; input.setAttribute("aria-expanded", "true"); } } });
    document.addEventListener("click", function (event) { if (!root.contains(event.target)) close(); });
}());
