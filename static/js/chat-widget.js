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
    var usuSel = document.getElementById("swUsuario");
    var ddColega = document.getElementById("ddColega");
    var ddUsuario = document.getElementById("ddUsuario");
    var ddTicket = document.getElementById("ddTicket");
    var ddColegaLabel = document.getElementById("ddColegaLabel");
    var ddUsuarioLabel = document.getElementById("ddUsuarioLabel");
    var ddTicketLabel = document.getElementById("ddTicketLabel");
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
    /* Soporte para el staff: primero la persona, luego sus tickets. */
    var hayUsuarios = Boolean(usuSel && urls.usuarios);
    var usuarioEmail = "";
    var usuariosDatos = {};
    var ticketsDatos = {};
    var colegaPk = 0;
    var colegasCargados = false;
    var colegasDatos = {};
    var novedadesCache = { sala: 0, dms: {} };
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
        /* La foto sale en ambos lados: del que escribe y del que responde. */
        return '<div class="sw-msg' + (m.propio ? " sw-msg-propio" : "") + '" data-id="' + m.id + '">' +
            avatarHtml(m) +
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
                /* Contadores por persona en el desplegable corporativo. */
                novedadesCache.sala = (d.sala && d.sala.nuevos) || 0;
                novedadesCache.dms = d.dms || {};
                pintarEtiquetasColegas();
            })
            .catch(function () { });
    }

    function pintarTicketUser(nombre) {
        if (!ticketUser) { return; }
        ticketUser.textContent = nombre ? "De: " + nombre : "";
        ticketUser.style.display = nombre ? "inline" : "none";
    }
    function primerNombre(n) { return String(n || "").trim().split(/\s+/)[0] || ""; }
    /* ---- Desplegables propios: panel compacto con filas ricas ----
       El select nativo queda oculto como fuente de datos; el panel muestra
       nombre pequeño, icono de rol y badge/contador separados a la derecha.
       Elegir una fila setea el nativo y dispara su change: toda la lógica
       existente (hilo, etiquetas, contadores) se reutiliza sin cambios. */
    var ROL_ICONO = { "Técnico": "i-wrench", "Admin": "i-shield", "Observador": "i-eye", "Usuario": "i-user" };
    function cerrarPaneles() {
        document.querySelectorAll(".sw-dd-panel").forEach(function (p) {
            if (!p.hidden) {
                p.hidden = true;
                var caja = p.closest(".sw-dd");
                if (caja) { caja.setAttribute("aria-expanded", "false"); }
            }
        });
    }
    function ubicarPanel(panel, caja) {
        panel.hidden = false;
        var r = caja.getBoundingClientRect();
        var w = Math.min(292, window.innerWidth - 16);
        panel.style.minWidth = Math.min(244, w) + "px";
        panel.style.maxWidth = w + "px";
        panel.style.left = Math.min(Math.max(8, r.left), Math.max(8, window.innerWidth - w - 8)) + "px";
        var alto = Math.min(panel.scrollHeight || 300, 302);
        var top = r.bottom + 6;
        if (top + alto > window.innerHeight - 8) { top = Math.max(8, r.top - alto - 6); }
        panel.style.top = top + "px";
    }
    function avatarMini(nombre, avatarUrl, enLinea) {
        var ini = esc(primerNombre(nombre).charAt(0).toUpperCase() || "?");
        var cara = avatarUrl
            ? '<img src="' + esc(avatarUrl) + '" alt="" loading="lazy">'
            : ini;
        return '<span class="sw-dd-ava-w"><span class="sw-dd-ava">' + cara + "</span>" +
            '<span class="sw-dd-dot' + (enLinea ? " green" : "") + '"></span></span>';
    }
    function pintarPanelUsuarios() {
        var panel = document.getElementById("ddUsuarioPanel");
        if (!panel || !usuSel) { return; }
        var html = "";
        for (var i = 0; i < usuSel.options.length; i++) {
            var op = usuSel.options[i];
            if (!op.value) { continue; }
            var u = usuariosDatos[op.value.toLowerCase()] ||
                { email: op.value, nombre: op.textContent, avatar: "", en_linea: false, n_tickets: 0 };
            var activo = op.value === usuarioEmail;
            html += '<button type="button" class="sw-dd-row' + (activo ? " is-active" : "") +
                '" role="option" aria-selected="' + activo + '" data-value="' + esc(u.email) + '">' +
                avatarMini(u.nombre, u.avatar, u.en_linea) +
                '<span class="sw-dd-name">' + esc(u.nombre) + "</span>" +
                '<span class="sw-dd-meta"><svg class="icon"><use href="#i-ticket"/></svg>' +
                esc(u.n_tickets) + "</span></button>";
        }
        panel.innerHTML = html || '<p class="sw-dd-empty">Sin usuarios para chatear.</p>';
    }
    function pintarPanelTickets() {
        var panel = document.getElementById("ddTicketPanel");
        if (!panel) { return; }
        var html = "";
        for (var i = 0; i < sel.options.length; i++) {
            var op = sel.options[i];
            if (!op.value) { continue; }
            var t = ticketsDatos[op.value] || { codigo: op.textContent, titulo: "", estado_display: "" };
            var activo = String(ticketPk) === String(op.value);
            html += '<button type="button" class="sw-dd-row' + (activo ? " is-active" : "") +
                '" role="option" aria-selected="' + activo + '" data-value="' + esc(op.value) + '">' +
                '<span class="sw-dd-meta"><svg class="icon"><use href="#i-ticket"/></svg></span>' +
                '<span class="sw-dd-name">' + esc(t.codigo) +
                (t.titulo ? " · " + esc(t.titulo) : "") + "</span>" +
                (t.estado_display ? '<span class="sw-dd-estado">' + esc(t.estado_display) + "</span>" : "") +
                "</button>";
        }
        panel.innerHTML = html || '<p class="sw-dd-empty">Sin tickets para chatear.</p>';
    }
    function pintarPanelColegas() {
        var panel = document.getElementById("ddColegaPanel");
        if (!panel || !colegaSel) { return; }
        var html = '<button type="button" class="sw-dd-row' + (!colegaPk ? " is-active" : "") +
            '" role="option" aria-selected="' + (!colegaPk) + '" data-value="0">' +
            '<span class="sw-dd-ava-w"><span class="sw-dd-ava"><svg class="icon" style="width:13px;height:13px"><use href="#i-users"/></svg></span></span>' +
            '<span class="sw-dd-name">Sala general · todos</span>' +
            (novedadesCache.sala > 0 ? '<span class="sw-dd-badge">' + novedadesCache.sala + "</span>" : "") +
            "</button>";
        for (var i = 0; i < colegaSel.options.length; i++) {
            var op = colegaSel.options[i];
            if (!op.value || op.value === "0") { continue; }
            var c = colegasDatos[op.value];
            if (!c) { continue; }
            var nuevos = (novedadesCache.dms[op.value] || {}).nuevos || 0;
            var activo = String(colegaPk) === String(op.value);
            var iconoRol = ROL_ICONO[c.insignia] || "i-user";
            html += '<button type="button" class="sw-dd-row' + (activo ? " is-active" : "") +
                '" role="option" aria-selected="' + activo + '" data-value="' + esc(op.value) + '">' +
                avatarMini(c.nombre, c.avatar, c.en_linea) +
                '<span class="sw-dd-name">' + esc(c.nombre) +
                '<small><svg class="icon"><use href="#' + iconoRol + '"/></svg>' + esc(c.insignia) + "</small></span>" +
                (nuevos > 0 ? '<span class="sw-dd-badge">' + nuevos + "</span>" : "") +
                "</button>";
        }
        panel.innerHTML = html;
    }
    function cablearDd(cajaId, panelId, natId, pintar) {
        var caja = document.getElementById(cajaId);
        var panel = document.getElementById(panelId);
        var nat = document.getElementById(natId);
        if (!caja || !panel || !nat) { return; }
        caja.setAttribute("role", "button");
        caja.setAttribute("tabindex", "0");
        caja.setAttribute("aria-expanded", "false");
        function abrir() {
            pintar();
            cerrarPaneles();
            ubicarPanel(panel, caja);
            caja.setAttribute("aria-expanded", "true");
        }
        caja.addEventListener("click", function (e) {
            e.stopPropagation();
            if (!panel.hidden) {
                panel.hidden = true;
                caja.setAttribute("aria-expanded", "false");
                return;
            }
            abrir();
        });
        caja.addEventListener("keydown", function (e) {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); abrir(); }
        });
        panel.addEventListener("click", function (e) {
            var row = e.target.closest(".sw-dd-row");
            if (!row || row.dataset.value === undefined) { return; }
            e.stopPropagation();
            nat.value = row.dataset.value;
            nat.dispatchEvent(new Event("change", { bubbles: true }));
            panel.hidden = true;
            caja.setAttribute("aria-expanded", "false");
        });
    }
    cablearDd("ddUsuario", "ddUsuarioPanel", "swUsuario", pintarPanelUsuarios);
    cablearDd("ddTicket", "ddTicketPanel", "swTicket", pintarPanelTickets);
    cablearDd("ddColega", "ddColegaPanel", "swColega", pintarPanelColegas);
    document.addEventListener("click", function (e) {
        if (!e.target.closest(".sw-dd")) { cerrarPaneles(); }
    });
    document.addEventListener("scroll", function () { cerrarPaneles(); }, true);
    window.addEventListener("resize", function () { cerrarPaneles(); });
    /* Nombre corto junto al icono: lo elegido en cada desplegable. */
    function pintarUsuarioLabel() {
        if (!ddUsuarioLabel || !usuSel) { return; }
        var u = usuariosDatos[String(usuarioEmail || "").toLowerCase()];
        if (u) {
            ddUsuarioLabel.textContent = (u.en_linea ? "🟢 " : "⚪ ") + primerNombre(u.nombre);
            return;
        }
        var op = usuSel.options[usuSel.selectedIndex];
        ddUsuarioLabel.textContent = op ? primerNombre(op.textContent.replace(/^[🟢⚪]\s*/, "")) : "Usuario";
    }
    function pintarTicketLabel() {
        if (!ddTicketLabel) { return; }
        var t = ticketsDatos[String(ticketPk || "")];
        ddTicketLabel.textContent = t ? t.codigo : "Ticket";
    }
    function pintarColegaLabel() {
        if (!ddColegaLabel) { return; }
        if (!colegaPk) {
            var ns = novedadesCache.sala || 0;
            ddColegaLabel.textContent = "Sala general" + (ns > 0 ? " (" + ns + ")" : "");
            return;
        }
        var c = colegasDatos[String(colegaPk)];
        if (!c) { return; }
        var nuevos = (novedadesCache.dms[String(colegaPk)] || {}).nuevos || 0;
        ddColegaLabel.textContent = (c.en_linea ? "🟢 " : "⚪ ") + primerNombre(c.nombre) +
            (nuevos > 0 ? " (" + nuevos + ")" : "");
    }
    /* Staff: primero la persona (con su estado en línea), luego sus tickets. */
    function listarUsuarios() {
        if (!hayUsuarios) { listarTickets(); return; }
        fetchJson(urls.usuarios, { credentials: "same-origin" })
            .then(function (res) {
                var d = res && res.datos;
                if (!d || !d.ok) { avisarUnaVez(textoFallo(res, "No se pudo cargar el chat.")); return; }
                usuSel.innerHTML = "";
                usuariosDatos = {};
                (d.usuarios || []).forEach(function (u, i) {
                    usuariosDatos[(u.email || "").toLowerCase()] = u;
                    var op = document.createElement("option");
                    op.value = u.email;
                    op.textContent = (u.en_linea ? "🟢 " : "⚪ ") + u.nombre +
                        " (" + u.n_tickets + " ticket" + (u.n_tickets === 1 ? "" : "s") + ")";
                    usuSel.appendChild(op);
                    if (i === 0) { usuarioEmail = u.email; }
                });
                if (!d.usuarios || !d.usuarios.length) {
                    var op0 = document.createElement("option");
                    op0.textContent = "Sin usuarios para chatear";
                    usuSel.appendChild(op0);
                    usuarioEmail = "";
                    if (ddUsuarioLabel) { ddUsuarioLabel.textContent = "Sin usuarios"; }
                } else {
                    usuSel.value = usuarioEmail;
                    pintarUsuarioLabel();
                }
                listarTickets(usuarioEmail);
            })
            .catch(function () { avisarUnaVez("Sin conexión con el servidor."); });
    }
    function listarTickets(email) {
        var url = urls.tickets + (email ? "?usuario=" + encodeURIComponent(email) : "");
        fetchJson(url, { credentials: "same-origin" })
            .then(function (res) {
                var d = res && res.datos;
                if (!d || !d.ok) { avisarUnaVez(textoFallo(res, "No se pudo cargar el chat.")); return; }
                sel.innerHTML = "";
                ticketsDatos = {};
                (d.tickets || []).forEach(function (t, i) {
                    ticketsDatos[String(t.pk)] = t;
                    var op = document.createElement("option");
                    op.value = t.pk;
                    op.textContent = t.codigo + " · " + t.titulo + " (" + t.estado_display + ")";
                    if (t.solicitante_nombre) { op.setAttribute("data-user", t.solicitante_nombre); }
                    sel.appendChild(op);
                    if (i === 0) {
                        ticketPk = t.pk;
                        pintarTicketUser(t.solicitante_nombre);
                        pintarTicketLabel();
                    }
                });
                if (!d.tickets || !d.tickets.length) {
                    var op0 = document.createElement("option");
                    op0.textContent = "Sin tickets para chatear";
                    sel.appendChild(op0);
                    ticketPk = 0;
                    pintarTicketUser("");
                    if (ddTicketLabel) { ddTicketLabel.textContent = "Sin tickets"; }
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
        if (esCorp()) { listarColegas(true); cargar(0); }
        else if (hayUsuarios) { listarUsuarios(); }
        else { listarTickets(); }
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
        var op = sel.options[sel.selectedIndex];
        pintarTicketUser(op ? op.getAttribute("data-user") : "");
        pintarTicketLabel();
        cargar(0);
    });
    if (usuSel) {
        usuSel.addEventListener("change", function () {
            usuarioEmail = usuSel.value || "";
            pintarUsuarioLabel();
            ultimoId = 0;
            errorMostrado = false;
            listarTickets(usuarioEmail);
        });
    }

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
        if (ddTicket) { ddTicket.hidden = enCorp; }
        if (ddUsuario) { ddUsuario.hidden = enCorp; }
        if (ddColega) { ddColega.hidden = !enCorp; }
        if (adjBtn) { adjBtn.style.display = enCorp ? "none" : ""; }
        texto.placeholder = !enCorp ? "Escríbenos…"
            : (colegaPk ? "Escríbele a " + nombreColega() + "…" : "Escríbele al equipo…");
        errorMostrado = false;
        ultimoId = 0;
        noLeidos = 0;
        pintarContador();
        if (enCorp) { listarColegas(true); cargar(0); }
        else if (hayUsuarios) { listarUsuarios(); }
        else { listarTickets(); }
        consultarNovedades();
    }
    if (modoSoporteBtn) { modoSoporteBtn.addEventListener("click", function () { ponerModo("soporte"); }); }
    if (modoCorpBtn) { modoCorpBtn.addEventListener("click", function () { ponerModo("corporativo"); }); }

    /* Etiqueta del colega: punto en línea + pendientes de esa persona. */
    function etiquetaColega(c) {
        var nuevos = (novedadesCache.dms[String(c.pk)] || {}).nuevos || 0;
        var txt = (c.en_linea ? "🟢 " : "⚪ ") + c.nombre + " · " + c.insignia;
        if (nuevos > 0) { txt += " (" + nuevos + " nuevo" + (nuevos === 1 ? "" : "s") + ")"; }
        return txt;
    }
    function pintarEtiquetasColegas() {
        if (!hayCorp || !colegaSel || !colegasCargados) { return; }
        var actual = String(colegaPk || "0");
        for (var i = 0; i < colegaSel.options.length; i++) {
            var op = colegaSel.options[i];
            if (op.value === "0") {
                var ns = novedadesCache.sala || 0;
                op.textContent = "Sala general · todos" + (ns > 0 ? " (" + ns + " nuevos)" : "");
            } else {
                var c = colegasDatos[op.value];
                if (c) { op.textContent = etiquetaColega(c); }
            }
        }
        if (colegaSel.querySelector('option[value="' + actual + '"]')) {
            colegaSel.value = actual;
        }
        pintarColegaLabel();
        var pc = document.getElementById("ddColegaPanel");
        if (pc && !pc.hidden) { pintarPanelColegas(); }
    }
    function listarColegas(forzar) {
        if (!hayCorp || (colegasCargados && !forzar)) { return; }
        colegasCargados = true;
        fetchJson(urls.colegas, { credentials: "same-origin" })
            .then(function (res) {
                var d = res && res.datos;
                if (!d || !d.ok) { colegasCargados = false; return; }
                colegasDatos = {};
                colegaSel.innerHTML = "";
                var op0 = document.createElement("option");
                op0.value = "0";
                op0.textContent = "Sala general · todos";
                colegaSel.appendChild(op0);
                (d.colegas || []).forEach(function (c) {
                    colegasDatos[String(c.pk)] = c;
                    var op = document.createElement("option");
                    op.value = c.pk;
                    op.textContent = etiquetaColega(c);
                    colegaSel.appendChild(op);
                });
                pintarEtiquetasColegas();
                /* Viene de la campana con un directo pendiente: se abre solo. */
                if (dmPendiente && colegaSel.querySelector('option[value="' + dmPendiente + '"]')) {
                    colegaSel.value = String(dmPendiente);
                    colegaPk = dmPendiente;
                    dmPendiente = 0;
                    ultimoId = 0;
                    texto.placeholder = "Escríbele a " + nombreColega() + "…";
                    cargar(0);
                } else if (colegaPk && colegaSel.querySelector('option[value="' + colegaPk + '"]')) {
                    colegaSel.value = String(colegaPk);
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
            /* Lo que se abre se descuenta del contador de esa persona. */
            if (colegaPk && novedadesCache.dms[String(colegaPk)]) {
                novedadesCache.dms[String(colegaPk)].nuevos = 0;
            } else if (!colegaPk) {
                novedadesCache.sala = 0;
            }
            pintarEtiquetasColegas();
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
        if (e.key === "Escape" && abierto) {
            var panelAbierto = document.querySelector(".sw-dd-panel:not([hidden])");
            if (panelAbierto) { cerrarPaneles(); } else { cerrarWin(); }
        }
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
