/* Chat corporativo de soporte: FAB arrastrable + ventana con hilo por ticket.
   Sin dependencias: usa las APIs JSON del backend y el csrftoken. */
(function () {
    var urls = window.__SW_URLS__;
    var fab = document.getElementById("swFab");
    var win = document.getElementById("swWin");
    if (!urls || !fab || !win) { return; }

    var sel = document.getElementById("swTicket");
    var ticketUser = document.getElementById("swTicketUser");
    var hilo = document.getElementById("swThread");
    var texto = document.getElementById("swTexto");
    var enviar = document.getElementById("swEnviar");
    var adjBtn = document.getElementById("swAdjuntar");
    var archivo = document.getElementById("swArchivo");
    var emojiBtn = document.getElementById("swEmojiBtn");
    var cerrar = document.getElementById("swCerrar");
    var count = document.getElementById("swCount");
    var modoSoporteBtn = document.getElementById("swModoSoporte");
    var modoCorpBtn = document.getElementById("swModoCorp");
    var colegaSel = document.getElementById("swColega");
    var headTitulo = document.getElementById("swHeadTitulo");
    var headSub = document.getElementById("swHeadSub");

    var ticketPk = 0;
    var ultimoId = 0;
    var noLeidos = 0;
    var abierto = false;
    var timer = null;
    /* Modo del chat: soporte (hilo por ticket) o corporativo (sala staff).
       El usuario final no tiene selector: siempre va en soporte. */
    var hayCorp = Boolean(modoCorpBtn && colegaSel && urls.corpHilo && urls.corpEnviar && urls.colegas && urls.novedades);
    var colegaPk = 0;
    var colegasCargados = false;
    var dmPendiente = 0;
    /* Lo ya visto del corporativo (sala + cada directo): con esto el
       servidor cuenta lo pendiente para la burbuja, esté o no abierto. */
    var visto = { sala: 0, dm: {} };
    try {
        var gv = JSON.parse(localStorage.getItem("dogger:chat:vistoCorp") || "null");
        if (gv && typeof gv.sala === "number") { visto.sala = gv.sala; }
        if (gv && gv.dm && typeof gv.dm === "object") { visto.dm = gv.dm; }
    } catch (e) { }
    function guardarVisto() {
        try { localStorage.setItem("dogger:chat:vistoCorp", JSON.stringify(visto)); } catch (e) { }
    }
    /* Al pintar mensajes corporativos, esa conversación queda vista. */
    function marcarVisto(lista) {
        if (!hayCorp || !lista || !lista.length) { return; }
        var max = 0;
        lista.forEach(function (m) { if (m.id > max) { max = m.id; } });
        if (!max) { return; }
        if (colegaPk) {
            if ((visto.dm[colegaPk] || 0) < max) { visto.dm[colegaPk] = max; guardarVisto(); }
        } else if (visto.sala < max) {
            visto.sala = max; guardarVisto();
        }
    }
    var corpPendientes = 0;
    var modo = "soporte";
    try {
        if (hayCorp && localStorage.getItem("dogger:chat:modo") === "corporativo") {
            modo = "corporativo";
        }
    } catch (e) { }
    function esCorp() { return hayCorp && modo === "corporativo"; }

    var EMOJIS = ["😀", "😄", "😉", "😍", "🤝", "👍", "👏", "🙏", "✅", "❌",
                  "⚠️", "❓", "❗", "🎉", "🔧", "🖨️", "💻", "🌐", "📎",
                  "📄", "🕐", "✔️", "🚀", "👋", "🙂", "😅", "🤔", "💡",
                  "📞", "✉️"];

    function csrf() {
        var m = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
        if (!m) {
            var inp = document.querySelector('input[name="csrfmiddlewaretoken"]');
            m = (inp && inp.value) || "";
        }
        return m;
    }
    function esc(s) {
        return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
        });
    }
    /* Enlaces directos: las URLs del mensaje se vuelven clicables.
       Va sobre el texto ya escapado para no abrir huecos XSS. */
    function enlaceify(s) {
        return String(s).replace(/(https?:\/\/[^\s<>"']+)/g, function (u) {
            return '<a href="' + u + '" target="_blank" rel="noopener">' + u + "</a>";
        });
    }
    /* Respuestas que no son JSON (404, 500, sesión vencida) dicen el
       código exacto en vez de un genérico, para saber dónde mirar. */
    function fetchJson(url, opciones) {
        return fetch(url, opciones).then(function (r) {
            var ct = (r.headers.get("content-type") || "").toLowerCase();
            if (r.redirected && /login/.test(r.url || "")) {
                return { sesion: true };
            }
            if (ct.indexOf("application/json") === -1) {
                return { http: r.status || 0 };
            }
            return r.json().catch(function () { return null; }).then(function (d) {
                return { http: r.status, datos: d };
            });
        });
    }
    function textoFallo(res, defecto) {
        if (!res) { return "Sin conexión con el servidor."; }
        if (res.sesion) { return "Tu sesión venció. Recarga la página e inténtalo de nuevo."; }
        if (res.datos && res.datos.error) { return res.datos.error; }
        if (res.http === 404) { return "Servicio no encontrado (404): reconstruye con docker compose up -d --build."; }
        if (res.http === 403) { return "Sin permiso (403): revisa tu sesión o el permiso de chateo."; }
        if (res.http >= 500) { return "Error del servidor (" + res.http + "): revisa docker compose logs web."; }
        if (res.http) { return (defecto || "No se pudo completar") + " (" + res.http + ")."; }
        return defecto || "No se pudo completar.";
    }
    /* Aviso dentro del hilo: ningún fallo vuelve a ser silencioso,
       pero sale una sola vez (el sondeo reintenta en silencio). */
    var errorMostrado = false;
    function aviso(texto) {
        var caja = document.createElement("div");
        caja.className = "sw-msg";
        caja.innerHTML = '<div class="sw-bubble sw-bubble-error">' + esc(texto) + "</div>";
        hilo.appendChild(caja);
        bajar();
    }
    function avisarUnaVez(texto) {
        if (errorMostrado) { return; }
        errorMostrado = true;
        aviso(texto);
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
            '<span class="sw-bubble-t">' + enlaceify(esc(m.texto)) + "</span>" +
            '<span class="sw-bubble-f">' + esc(m.fecha) + "</span></div></div>";
    }
    /* Pinta sin duplicar: los sondeos solapados traen lo mismo dos veces. */
    function pintarMensaje(m) {
        if (!m || hilo.querySelector('.sw-msg[data-id="' + m.id + '"]')) { return false; }
        hilo.insertAdjacentHTML("beforeend", mensajeHtml(m));
        ultimoId = Math.max(ultimoId, m.id);
        return true;
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

    function nombreColega() {
        if (!colegaSel || !colegaPk) { return ""; }
        var op = colegaSel.querySelector('option[value="' + colegaPk + '"]');
        return op ? op.textContent : "";
    }
    function cargar(desde) {
        var enCorp = esCorp();
        var url = enCorp
            ? urls.corpHilo + "?desde=" + (desde || 0) + (colegaPk ? "&para=" + colegaPk : "")
            : (ticketPk ? urlBase(urls.hilo) + "?desde=" + (desde || 0) : null);
        if (!url) { return; }
        var esInicial = !desde;
        fetchJson(url, { credentials: "same-origin" })
            .then(function (res) {
                var d = res && res.datos;
                if (!d || !d.ok) {
                    if (!desde) { avisarUnaVez(textoFallo(res, "No se pudo cargar la conversación.")); }
                    return;
                }
                if (!desde) {
                    hilo.innerHTML = "";
                    ultimoId = 0;
                    errorMostrado = false;
                    if (!d.mensajes.length && !(d.adjuntos || []).length) {
                        hilo.innerHTML = !enCorp
                            ? '<p class="sw-empty">Cuéntanos en qué te ayudamos.</p>'
                            : (colegaPk
                                ? '<p class="sw-empty">Directo con ' + esc(nombreColega()) + ": solo ustedes dos lo ven.</p>"
                                : '<p class="sw-empty">Sala corporativa: coordínate con técnicos, admins y observadores.</p>');
                        // El saludo va en la caja del técnico como mensaje
                        // inicial para enviar; al usuario le sale solo cuando
                        // el técnico realmente le escribe.
                        if (!enCorp && (urls.rol === "tecnico" || urls.rol === "admin") && !texto.value) {
                            texto.value = "¡Hola! Gracias por escribirnos. Cuéntanos tu caso y un técnico te atiende enseguida.";
                        }
                    }
                    (d.mensajes || []).forEach(function (m) { pintarMensaje(m); });
                    if (enCorp) { marcarVisto(d.mensajes); }
                    else { pintarAdjuntos(d.adjuntos); }
                    bajar();
                } else if ((d.mensajes || []).length) {
                    d.mensajes.forEach(function (m) { pintarMensaje(m); });
                    if (enCorp) { marcarVisto(d.mensajes); }
                    if (abierto) { bajar(); }
                    else {
                        noLeidos += d.mensajes.length;
                        pintarContador();
                    }
                }
            })
            .catch(function () { if (esInicial) { avisarUnaVez("Sin conexión con el servidor."); } });
    }

    function pintarContador() {
        if (!count) { return; }
        var total = noLeidos + corpPendientes;
        if (total > 0) {
            count.hidden = false;
            count.textContent = total > 9 ? "9+" : String(total);
        } else { count.hidden = true; }
    }
    /* Sondeo de pendientes del corporativo: corre siempre (abierto o no)
       para que la burbuja avise con el número aunque se escriba en otro
       hilo o con el chat cerrado. */
    function consultarNovedades() {
        if (!hayCorp) { return; }
        var pares = Object.keys(visto.dm).map(function (k) { return k + ":" + visto.dm[k]; }).join(",");
        var url = urls.novedades + "?sala=" + visto.sala + (pares ? "&dm=" + encodeURIComponent(pares) : "");
        fetchJson(url, { credentials: "same-origin" })
            .then(function (res) {
                var d = res && res.datos;
                if (!d || !d.ok) { return; }
                /* Lo que está en pantalla se descuenta: ya se ve o está
                   por pintarse en el sondeo del hilo abierto. */
                var enPantalla = 0;
                if (abierto && esCorp()) {
                    if (colegaPk && d.dms && d.dms[colegaPk]) { enPantalla = d.dms[colegaPk].nuevos || 0; }
                    else if (!colegaPk && d.sala) { enPantalla = d.sala.nuevos || 0; }
                }
                corpPendientes = Math.max(0, (d.total || 0) - enPantalla);
                pintarContador();
            })
            .catch(function () { });
    }

    function listarTickets() {
        fetchJson(urls.tickets, { credentials: "same-origin" })
            .then(function (res) {
                var d = res && res.datos;
                if (!d || !d.ok) { avisarUnaVez(textoFallo(res, "No se pudo cargar el chat.")); return; }
                sel.innerHTML = "";
                (d.tickets || []).forEach(function (t, i) {
                    var op = document.createElement("option");
                    op.value = t.pk;
                    op.textContent = t.codigo + " · " + t.titulo + " (" + t.estado_display + ")";
                    sel.appendChild(op);
                    if (i === 0) {
                        ticketPk = t.pk;
                        if (ticketUser) {
                            ticketUser.textContent = t.solicitante_nombre ? "De: " + t.solicitante_nombre : "";
                            ticketUser.style.display = t.solicitante_nombre ? "inline" : "none";
                        }
                    }
                });
                if (!d.tickets || !d.tickets.length) {
                    var op0 = document.createElement("option");
                    op0.textContent = "Sin tickets para chatear";
                    sel.appendChild(op0);
                    if (ticketUser) ticketUser.style.display = "none";
                }
                cargar(0);
            })
            .catch(function () { avisarUnaVez("Sin conexión con el servidor."); });
    }

    /* La ventana se abre junto a la burbuja: arriba de ella y alineada
       a su derecha. En móvil manda el CSS de pantalla completa. */
    function ubicarVentana() {
        if (window.innerWidth <= 520) {
            win.style.left = ""; win.style.top = "";
            win.style.right = ""; win.style.bottom = "";
            return;
        }
        var r = fab.getBoundingClientRect();
        var w = Math.min(374, window.innerWidth - 16);
        var h = Math.min(540, window.innerHeight - 100);
        win.style.left = Math.min(Math.max(8, r.right - w), window.innerWidth - w - 8) + "px";
        win.style.top = Math.max(8, r.top - h - 12) + "px";
        win.style.right = "auto";
        win.style.bottom = "auto";
    }
    function abrir() {
        abierto = true;
        noLeidos = 0;
        errorMostrado = false;
        pintarContador();
        ubicarVentana();
        win.setAttribute("data-open", "");
        fab.setAttribute("aria-expanded", "true");
        cargar(0);
        consultarNovedades();
        clearInterval(timer);
        timer = setInterval(function () { cargar(ultimoId); }, 6000);
    }
    /* En vivo: al volver a la pestaña se trae lo nuevo sin esperar el turno. */
    document.addEventListener("visibilitychange", function () {
        if (!document.hidden && abierto) {
            cargar(ultimoId);
            consultarNovedades();
        }
    });
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
            /* La ventana pudo cambiar de tamaño o de monitor desde que se
               guardo la posicion: se limita a lo visible para que el boton
               nunca quede fuera de la pantalla. */
            var maxL = Math.max(8, window.innerWidth - 66);
            var maxT = Math.max(8, window.innerHeight - 66);
            fab.style.left = Math.min(Math.max(8, pos.left), maxL) + "px";
            fab.style.top = Math.min(Math.max(8, pos.top), maxT) + "px";
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
        errorMostrado = false;
        cargar(0);
    });

    function ponerModo(nuevo) {
        if (!hayCorp || (nuevo !== "soporte" && nuevo !== "corporativo")) { return; }
        modo = nuevo;
        try { localStorage.setItem("dogger:chat:modo", modo); } catch (e) { }
        var enCorp = esCorp();
        if (modoSoporteBtn) {
            modoSoporteBtn.classList.toggle("is-active", !enCorp);
            modoSoporteBtn.setAttribute("aria-selected", String(!enCorp));
        }
        if (modoCorpBtn) {
            modoCorpBtn.classList.toggle("is-active", enCorp);
            modoCorpBtn.setAttribute("aria-selected", String(enCorp));
        }
        win.setAttribute("data-modo", enCorp ? "corporativo" : "soporte");
        if (headTitulo) { headTitulo.textContent = enCorp ? "Sala corporativa" : "Mesa de ayuda"; }
        if (headSub) { headSub.textContent = enCorp ? "Solo staff en línea" : "Estamos en línea"; }
        if (sel) { sel.hidden = enCorp; }
        if (colegaSel) { colegaSel.hidden = !enCorp; }
        if (adjBtn) { adjBtn.style.display = enCorp ? "none" : ""; }
        texto.placeholder = !enCorp ? "Escríbenos…"
            : (colegaPk ? "Escríbele a " + nombreColega() + "…" : "Escríbele al equipo…");
        errorMostrado = false;
        ultimoId = 0;
        noLeidos = 0;
        pintarContador();
        if (enCorp) { listarColegas(); cargar(0); }
        else { listarTickets(); }
        consultarNovedades();
    }
    if (modoSoporteBtn) { modoSoporteBtn.addEventListener("click", function () { ponerModo("soporte"); }); }
    if (modoCorpBtn) { modoCorpBtn.addEventListener("click", function () { ponerModo("corporativo"); }); }

    function listarColegas() {
        if (!hayCorp || colegasCargados) { return; }
        colegasCargados = true;
        fetchJson(urls.colegas, { credentials: "same-origin" })
            .then(function (res) {
                var d = res && res.datos;
                if (!d || !d.ok) { colegasCargados = false; return; }
                colegaSel.innerHTML = "";
                var op0 = document.createElement("option");
                op0.value = "0";
                op0.textContent = "Sala general · todos";
                colegaSel.appendChild(op0);
                (d.colegas || []).forEach(function (c) {
                    var op = document.createElement("option");
                    op.value = c.pk;
                    op.textContent = c.nombre + " · " + c.insignia + (c.en_linea ? " (en línea)" : "");
                    colegaSel.appendChild(op);
                });
                /* Viene de la campana con un directo pendiente: se abre solo. */
                if (dmPendiente && colegaSel.querySelector('option[value="' + dmPendiente + '"]')) {
                    colegaSel.value = String(dmPendiente);
                    colegaPk = dmPendiente;
                    dmPendiente = 0;
                    ultimoId = 0;
                    texto.placeholder = "Escríbele a " + nombreColega() + "…";
                    cargar(0);
                }
            })
            .catch(function () { colegasCargados = false; });
    }
    if (colegaSel) {
        colegaSel.addEventListener("change", function () {
            colegaPk = parseInt(colegaSel.value, 10) || 0;
            ultimoId = 0;
            errorMostrado = false;
            noLeidos = 0;
            pintarContador();
            texto.placeholder = colegaPk ? "Escríbele a " + nombreColega() + "…" : "Escríbele al equipo…";
            cargar(0);
        });
    }

    var enviando = false;
    function enviarTexto() {
        var v = (texto.value || "").trim();
        var enCorp = esCorp();
        if (enviando || !v || (!enCorp && !ticketPk)) { return; }
        enviando = true;
        enviar.disabled = true;
        var datos = new FormData();
        datos.append("mensaje", v);
        if (enCorp && colegaPk) { datos.append("para", colegaPk); }
        fetchJson(enCorp ? urls.corpEnviar : urlBase(urls.responder), {
            method: "POST", credentials: "same-origin",
            headers: { "X-CSRFToken": csrf() }, body: datos
        })
            .then(function (res) {
                var d = res && res.datos;
                if (!d || !d.ok) {
                    aviso(textoFallo(res, "No se pudo enviar."));
                    return;
                }
                texto.value = "";
                pintarMensaje(d.mensaje);
                if (enCorp) { marcarVisto([d.mensaje]); consultarNovedades(); }
                else { cargar(ultimoId); }
                bajar();
            })
            .catch(function () { aviso("Sin conexión con el servidor."); })
            .then(function () { enviando = false; enviar.disabled = false; texto.focus(); });
    }
    enviar.addEventListener("click", enviarTexto);
    texto.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviarTexto(); }
    });

    adjBtn.addEventListener("click", function () { if (!esCorp() && ticketPk) { archivo.click(); } });
    archivo.addEventListener("change", function () {
        if (!archivo.files.length || !ticketPk) { return; }
        var datos = new FormData();
        datos.append("archivo", archivo.files[0]);
        fetchJson(urlBase(urls.adjuntar), {
            method: "POST", credentials: "same-origin",
            headers: { "X-CSRFToken": csrf() }, body: datos
        })
            .then(function (res) {
                var d = res && res.datos;
                archivo.value = "";
                if (!d || !d.ok) { aviso(textoFallo(res, "No se pudo adjuntar el archivo.")); return; }
                var caja = document.createElement("div");
                caja.className = "sw-msg sw-msg-propio";
                caja.innerHTML = '<div class="sw-bubble">' + adjuntoHtml(d.adjunto) + "</div>";
                hilo.appendChild(caja);
                bajar();
            })
            .catch(function () { archivo.value = ""; aviso("Sin conexión con el servidor."); });
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

    if (hayCorp) {
        ponerModo(modo);
        consultarNovedades();
        setInterval(consultarNovedades, 15000);
        /* Desde la campana se abre directo el corporativo (y su directo). */
        var hm = (location.hash || "").match(/^#chat-corp(?:-dm-(\d+))?$/);
        if (hm) {
            dmPendiente = hm[1] ? parseInt(hm[1], 10) : 0;
            try { history.replaceState(null, "", location.pathname + location.search); } catch (e) { }
            ponerModo("corporativo");
            abrir();
        }
    } else { listarTickets(); }
})();
