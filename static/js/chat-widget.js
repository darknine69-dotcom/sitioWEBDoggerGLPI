/* Chat corporativo de soporte: FAB arrastrable + ventana con hilo por ticket.
   Sin dependencias: usa las APIs JSON del backend y el csrftoken. */
(function () {
    var urls = window.__SW_URLS__;
    var fab = document.getElementById("swFab");
    var win = document.getElementById("swWin");
    if (!urls || !fab || !win) { return; }

    var sel = document.getElementById("swTicket");
    var hilo = document.getElementById("swThread");
    var texto = document.getElementById("swTexto");
    var enviar = document.getElementById("swEnviar");
    var adjBtn = document.getElementById("swAdjuntar");
    var archivo = document.getElementById("swArchivo");
    var emojiBtn = document.getElementById("swEmojiBtn");
    var cerrar = document.getElementById("swCerrar");
    var count = document.getElementById("swCount");

    var ticketPk = 0;
    var ultimoId = 0;
    var noLeidos = 0;
    var abierto = false;
    var timer = null;

    var EMOJIS = ["😀", "😄", "😉", "😍", "🤝", "👍", "👏", "🙏", "✅", "❌",
                  "⚠️", "❓", "❗", "🎉", "🔧", "🖨️", "💻", "🌐", "📎",
                  "📄", "🕐", "✔️", "🚀", "👋", "🙂", "😅", "🤔", "💡",
                  "📞", "✉️"];

    function csrf() {
        var m = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
        return m;
    }
    function esc(s) {
        return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
        });
    }
    function urlBase(tpl) { return tpl.replace("/0/", "/" + ticketPk + "/"); }

    function avatarHtml(m) {
        var ini = esc((m.autor || "?").trim().charAt(0).toUpperCase() || "?");
        if (m.avatar) {
            return '<span class="sw-avatar"><img src="' + esc(m.avatar) + '" alt=""></span>';
        }
        return '<span class="sw-avatar">' + ini + "</span>";
    }
    function adjuntoHtml(a) {
        if (a.es_imagen && a.url) {
            return '<a class="sw-adj" href="' + esc(a.url) + '" target="_blank" rel="noopener">' +
                '<img src="' + esc(a.url) + '" alt="' + esc(a.nombre) + '" loading="lazy"></a>';
        }
        return '<a class="sw-adj-file" href="' + esc(a.url || "#") + '" target="_blank" rel="noopener">📄 ' +
            esc(a.nombre) + "</a>";
    }
    function mensajeHtml(m) {
        return '<div class="sw-msg' + (m.propio ? " sw-msg-propio" : "") + '" data-id="' + m.id + '">' +
            (m.propio ? "" : avatarHtml(m)) +
            '<div class="sw-bubble"><span class="sw-bubble-n">' + esc(m.autor) +
            (m.insignia ? " · " + esc(m.insignia) : "") + "</span>" +
            '<span class="sw-bubble-t">' + esc(m.texto) + "</span>" +
            '<span class="sw-bubble-f">' + esc(m.fecha) + "</span></div></div>";
    }
    function bajar() { hilo.scrollTop = hilo.scrollHeight; }

    function pintarAdjuntos(lista) {
        if (!lista || !lista.length) { return; }
        var caja = document.createElement("div");
        caja.className = "sw-msg";
        caja.innerHTML = '<div class="sw-bubble">' +
            lista.map(adjuntoHtml).join("") + "</div>";
        hilo.appendChild(caja);
    }

    function cargar(desde) {
        if (!ticketPk) { return; }
        fetch(urlBase(urls.hilo) + "?desde=" + (desde || 0), { credentials: "same-origin" })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (!d.ok) { return; }
                if (!desde) {
                    hilo.innerHTML = "";
                    ultimoId = 0;
                    if (!d.mensajes.length && !d.adjuntos.length) {
                        hilo.innerHTML = '<p class="sw-empty">Cuéntanos en qué te ayudamos.</p>';
                    }
                    (d.mensajes || []).forEach(function (m) {
                        hilo.insertAdjacentHTML("beforeend", mensajeHtml(m));
                        ultimoId = Math.max(ultimoId, m.id);
                    });
                    pintarAdjuntos(d.adjuntos);
                    bajar();
                } else if ((d.mensajes || []).length) {
                    d.mensajes.forEach(function (m) {
                        hilo.insertAdjacentHTML("beforeend", mensajeHtml(m));
                        ultimoId = Math.max(ultimoId, m.id);
                    });
                    if (abierto) { bajar(); }
                    else {
                        noLeidos += d.mensajes.length;
                        pintarContador();
                    }
                }
            })
            .catch(function () { });
    }

    function pintarContador() {
        if (!count) { return; }
        if (noLeidos > 0) {
            count.hidden = false;
            count.textContent = noLeidos > 9 ? "9+" : String(noLeidos);
        } else { count.hidden = true; }
    }

    function listarTickets() {
        fetch(urls.tickets, { credentials: "same-origin" })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                sel.innerHTML = "";
                (d.tickets || []).forEach(function (t, i) {
                    var op = document.createElement("option");
                    op.value = t.pk;
                    op.textContent = t.codigo + " · " + t.titulo + " (" + t.estado_display + ")";
                    sel.appendChild(op);
                    if (i === 0) { ticketPk = t.pk; }
                });
                if (!d.tickets || !d.tickets.length) {
                    var op0 = document.createElement("option");
                    op0.textContent = "Sin tickets para chatear";
                    sel.appendChild(op0);
                }
                cargar(0);
            })
            .catch(function () { });
    }

    function abrir() {
        abierto = true;
        noLeidos = 0;
        pintarContador();
        win.setAttribute("data-open", "");
        fab.setAttribute("aria-expanded", "true");
        cargar(0);
        clearInterval(timer);
        timer = setInterval(function () { cargar(ultimoId); }, 8000);
    }
    function cerrarWin() {
        abierto = false;
        win.removeAttribute("data-open");
        fab.setAttribute("aria-expanded", "false");
        clearInterval(timer);
    }

    /* FAB arrastrable: clic abre, arrastrar reposiciona y se guarda. */
    var moviendo = false, movido = false, ox = 0, oy = 0, fx = 0, fy = 0;
    try {
        var pos = JSON.parse(localStorage.getItem("dogger:chat:pos") || "null");
        if (pos && typeof pos.left === "number" && typeof pos.top === "number") {
            fab.style.left = pos.left + "px";
            fab.style.top = pos.top + "px";
            fab.style.right = "auto";
            fab.style.bottom = "auto";
        } else if (document.querySelector(".corp-fab")) {
            fab.style.bottom = "92px";
        }
    } catch (e) { }
    fab.addEventListener("pointerdown", function (e) {
        moviendo = true; movido = false;
        ox = e.clientX; oy = e.clientY;
        var r = fab.getBoundingClientRect();
        fx = r.left; fy = r.top;
        fab.setPointerCapture(e.pointerId);
    });
    fab.addEventListener("pointermove", function (e) {
        if (!moviendo) { return; }
        var dx = e.clientX - ox, dy = e.clientY - oy;
        if (Math.abs(dx) + Math.abs(dy) > 6) { movido = true; }
        if (movido) {
            fab.style.left = Math.min(Math.max(8, fx + dx), window.innerWidth - 66) + "px";
            fab.style.top = Math.min(Math.max(8, fy + dy), window.innerHeight - 66) + "px";
            fab.style.right = "auto";
            fab.style.bottom = "auto";
        }
    });
    fab.addEventListener("pointerup", function (e) {
        moviendo = false;
        if (!movido) {
            if (abierto) { cerrarWin(); } else { abrir(); }
            return;
        }
        try {
            var r = fab.getBoundingClientRect();
            localStorage.setItem("dogger:chat:pos", JSON.stringify({ left: r.left, top: r.top }));
        } catch (err) { }
    });
    fab.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (abierto) { cerrarWin(); } else { abrir(); } }
    });
    cerrar.addEventListener("click", cerrarWin);

    sel.addEventListener("change", function () {
        ticketPk = parseInt(sel.value, 10) || 0;
        ultimoId = 0;
        cargar(0);
    });

    function enviarTexto() {
        var v = (texto.value || "").trim();
        if (!v || !ticketPk) { return; }
        var datos = new FormData();
        datos.append("mensaje", v);
        fetch(urlBase(urls.responder), {
            method: "POST", credentials: "same-origin",
            headers: { "X-CSRFToken": csrf() }, body: datos
        })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (!d.ok) { return; }
                texto.value = "";
                hilo.insertAdjacentHTML("beforeend", mensajeHtml(d.mensaje));
                ultimoId = Math.max(ultimoId, d.mensaje.id);
                bajar();
            })
            .catch(function () { });
    }
    enviar.addEventListener("click", enviarTexto);
    texto.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviarTexto(); }
    });

    adjBtn.addEventListener("click", function () { if (ticketPk) { archivo.click(); } });
    archivo.addEventListener("change", function () {
        if (!archivo.files.length || !ticketPk) { return; }
        var datos = new FormData();
        datos.append("archivo", archivo.files[0]);
        fetch(urlBase(urls.adjuntar), {
            method: "POST", credentials: "same-origin",
            headers: { "X-CSRFToken": csrf() }, body: datos
        })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                archivo.value = "";
                if (!d.ok) { return; }
                var caja = document.createElement("div");
                caja.className = "sw-msg sw-msg-propio";
                caja.innerHTML = '<div class="sw-bubble">' + adjuntoHtml(d.adjunto) + "</div>";
                hilo.appendChild(caja);
                bajar();
            })
            .catch(function () { archivo.value = ""; });
    });

    var pop = null;
    emojiBtn.addEventListener("click", function () {
        if (pop) { pop.remove(); pop = null; emojiBtn.setAttribute("aria-expanded", "false"); return; }
        pop = document.createElement("div");
        pop.className = "sw-emoji";
        EMOJIS.forEach(function (em) {
            var b = document.createElement("button");
            b.type = "button";
            b.textContent = em;
            b.addEventListener("click", function () {
                var s = texto.selectionStart || texto.value.length;
                texto.value = texto.value.slice(0, s) + em + texto.value.slice(texto.selectionEnd || s);
                texto.focus();
                pop.remove(); pop = null;
            });
            pop.appendChild(b);
        });
        emojiBtn.parentElement.style.position = "relative";
        emojiBtn.parentElement.appendChild(pop);
        emojiBtn.setAttribute("aria-expanded", "true");
    });

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && abierto) { cerrarWin(); }
        if (e.key === "Escape" && pop) { pop.remove(); pop = null; }
    });

    listarTickets();
})();
