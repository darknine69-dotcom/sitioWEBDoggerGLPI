/* Dogger HelpDesk — interacciones globales (sin dependencias) */
(function () {
    "use strict";

    /* ---- Toast de notificación: auto-cierre con pausa al hover ---- */
    document.querySelectorAll(".toast-stack .toast").forEach(function (el) {
        var close = el.querySelector(".toast-close");
        var delay = el.classList.contains("toast-error") ? 12000 : 6500;
        el.style.setProperty("--toast-delay", delay + "ms");
        var timer = null;
        function dismiss() {
            if (!el.isConnected) return;
            el.classList.add("toast-out");
            setTimeout(function () { el.remove(); }, 340);
        }
        if (close) close.addEventListener("click", dismiss);
        /* El CSS pausa la barra de progreso en hover; aquí retomamos el cierre
           contando el tiempo transcurrido para no disparar inmediatamente. */
        var started = Date.now();
        var remaining = delay;
        function schedule() {
            if (timer) { clearTimeout(timer); timer = null; }
            timer = setTimeout(function () {
                el.classList.add("toast-out");
                setTimeout(function () { el.remove(); }, 340);
            }, remaining);
        }
        el.addEventListener("mouseenter", function () {
            remaining -= Date.now() - started;
            if (timer) { clearTimeout(timer); timer = null; }
        });
        el.addEventListener("mouseleave", function () {
            if (remaining <= 0) return;
            started = Date.now();
            schedule();
        });
        schedule();
    });

    /* ---- Modal de confirmación personalizado (reemplaza confirm nativo) ---- */
    var confirmOverlay = document.getElementById("confirm-overlay");
    var confirmMsgEl = document.getElementById("confirm-msg");
    var confirmOkBtn = document.getElementById("confirm-ok");
    var confirmCancelBtn = document.getElementById("confirm-cancel");
    var confirmCallback = null;

    function cerrarConfirm() {
        if (!confirmOverlay) return;
        confirmOverlay.classList.remove("open");
        confirmCallback = null;
    }
    function confirmarAction(mensaje, onOk, textoOk) {
        if (!confirmOverlay || !confirmMsgEl) { if (onOk) onOk(); return; }
        confirmMsgEl.textContent = mensaje;
        confirmCallback = onOk;
        if (confirmOkBtn) {
            var peligro = /eliminar|borra|quedar/iu.test(mensaje || "");
            var textoBtn = textoOk ||
                (peligro ? "Sí, eliminar" : "Sí, continuar");
            confirmOkBtn.textContent = textoBtn;
            confirmOkBtn.classList.toggle("btn-danger", peligro);
        }
        confirmOverlay.classList.add("open");
        if (confirmOkBtn) confirmOkBtn.focus();
    }
    if (confirmOkBtn) confirmOkBtn.addEventListener("click", function () {
        var cb = confirmCallback;
        cerrarConfirm();
        if (cb) cb();
    });
    if (confirmCancelBtn) confirmCancelBtn.addEventListener("click", cerrarConfirm);
    if (confirmOverlay) confirmOverlay.addEventListener("click", function (e) {
        if (e.target === confirmOverlay) cerrarConfirm();
    });
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && confirmOverlay && confirmOverlay.classList.contains("open")) cerrarConfirm();
    });
    window.DoggerConfirma = confirmarAction;

    /* Intercepta <form onsubmit="return confirm('...')"> (fase captura) */
    document.addEventListener("submit", function (e) {
        var f = e.target;
        if (!f || f.tagName !== "FORM") return;
        var os = f.getAttribute("onsubmit") || "";
        var mm = os.match(/confirm\(\s*'([^']*)'\s*\)|confirm\(\s*"([^"]*)"\s*\)/);
        if (!mm) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        confirmarAction(mm[1] || mm[2], function () {
            f.removeAttribute("onsubmit");
            try { f.submit(); } catch (err) { location.reload(); }
        });
    }, true);

    /* ---- Modales ---- */
    function openModal(sel) {
        var m = document.querySelector(sel);
        if (m) { m.classList.add("open"); document.body.style.overflow = "hidden"; }
    }
    function closeModal(m) {
        m.classList.remove("open");
        if (!document.querySelector(".modal-overlay.open")) document.body.style.overflow = "";
    }
    document.querySelectorAll("[data-open-modal]").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
            e.preventDefault();
            openModal(btn.getAttribute("data-open-modal"));
        });
    });
    document.querySelectorAll(".modal-overlay").forEach(function (m) {
        m.addEventListener("click", function (e) {
            if (e.target === m || e.target.closest(".modal-close")) closeModal(m);
        });
    });
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
            document.querySelectorAll(".modal-overlay.open").forEach(closeModal);
        }
    });

    /* ---- Grupos de categorías: colapsar/expandir (cerrados por defecto) ---- */
    document.querySelectorAll(".cat-group-head").forEach(function (head) {
        head.addEventListener("click", function () {
            var card = head.closest(".cat-group-card");
            var isCollapsed = card.classList.toggle("collapsed");
            head.querySelectorAll(".cat-toggle").forEach(function (b) {
                b.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
            });
        });
    });

    /* ---- Edición en línea ---- */
    document.querySelectorAll("[data-inline-toggle]").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            var target = document.getElementById(btn.getAttribute("data-inline-toggle"));
            if (target) {
                target.classList.toggle("open");
                var first = target.querySelector("input, select");
                if (first && target.classList.contains("open")) first.focus();
            }
        });
    });

    /* ---- Filtro rápido de tabla (client-side) ---- */
    document.querySelectorAll("[data-table-filter]").forEach(function (input) {
        var table = document.getElementById(input.getAttribute("data-table-filter"));
        if (!table) return;
        input.addEventListener("input", function () {
            var q = input.value.trim().toLowerCase();
            table.querySelectorAll("tbody tr").forEach(function (row) {
                row.style.display = row.textContent.toLowerCase().indexOf(q) !== -1 ? "" : "none";
            });
        });
    });

    /* ---- Selects que envían su formulario al cambiar ---- */
    document.querySelectorAll("select[data-autosubmit]").forEach(function (sel) {
        sel.addEventListener("change", function () { sel.form.submit(); });
    });

    /* ---- Selector "Filas por página": recarga con el nuevo tamaño ---- */
    var PAGE_PARAMS = ["page", "page_sol", "page_recientes", "page_glpi"];
    document.querySelectorAll("select[data-per-page-param]").forEach(function (sel) {
        sel.addEventListener("change", function () {
            var url = new URL(window.location.href);
            url.searchParams.set(sel.getAttribute("data-per-page-param"), sel.value);
            PAGE_PARAMS.forEach(function (p) { url.searchParams.delete(p); });
            window.location.href = url.toString();
        });
    });

    /* ---- Mapa del footer: cambiar punto ---- */
    document.querySelectorAll("[data-maps-src]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var frame = document.getElementById("doggerMap");
            if (!frame) return;
            frame.src = btn.getAttribute("data-maps-src");
            document.querySelectorAll(".maps-tab.active").forEach(function (t) {
                t.classList.remove("active");
            });
            btn.classList.add("active");
        });
    });

    /* ---- Símbolo del título: el texto que la vista tenía debajo ---- */
    (function () {
        var hint = document.querySelector(".title-hint");
        if (!hint) return;
        var bubble = hint.querySelector(".title-hint-bubble");
        var txt = bubble ? (bubble.textContent || "").replace(/\s+/g, " ").trim() : "";
        /* Sin texto que explicar, el símbolo no se muestra. */
        if (!txt) { hint.remove(); return; }
    })();

    /* ---- Sidebar lateral: plegar a iconos y cajón en móvil ---- */
    (function () {
        var side = document.getElementById("sidebar");
        if (!side) return;
        var burger = document.getElementById("sidebarBurger");
        var backdrop = document.getElementById("sidebarBackdrop");
        var plegar = document.getElementById("sidebarCollapse");

        /* Plegado: se guarda igual que la preferencia de "navegación compacta"
           de Ajustes, así que los dos sitios controlan lo mismo. */
        function plegarA(mini) {
            document.documentElement.setAttribute("data-navcompact", mini ? "1" : "0");
            try { localStorage.setItem("dogger:pv:navcompact", mini ? "1" : "0"); } catch (e) {}
            if (plegar) {
                plegar.setAttribute("aria-label", mini ? "Expandir el menú" : "Contraer el menú");
                plegar.title = mini ? "Expandir el menú" : "Contraer el menú";
            }
        }
        if (plegar) {
            plegar.addEventListener("click", function () {
                plegarA(document.documentElement.getAttribute("data-navcompact") !== "1");
            });
        }

        function abrir(abrir) {
            side.classList.toggle("is-open", abrir);
            if (burger) {
                burger.classList.toggle("is-active", abrir);
                burger.setAttribute("aria-expanded", String(abrir));
            }
            if (backdrop) backdrop.hidden = !abrir;
            document.body.classList.toggle("sidebar-abierto", abrir);
        }
        if (burger) {
            burger.addEventListener("click", function () {
                abrir(!side.classList.contains("is-open"));
            });
        }
        if (backdrop) backdrop.addEventListener("click", function () { abrir(false); });
        document.addEventListener("keydown", function (ev) {
            if (ev.key === "Escape") abrir(false);
        });
        // Al navegar dentro del cajón se cierra, para no tapar la página nueva.
        side.querySelectorAll(".sidebar-link").forEach(function (link) {
            link.addEventListener("click", function () { abrir(false); });
        });
        // Si la ventana crece y deja de ser móvil, el cajón se olvida.
        window.addEventListener("resize", function () {
            if (window.innerWidth > 1080) abrir(false);
        });

        /* Aviso con el nombre del enlace al pasar el ratón por un icono.
           Va pegado al body y posicionado con fixed porque el menú es la
           zona desplazable: dentro de él el rótulo se recortaba. */
        var tip = document.createElement("div");
        tip.className = "sidebar-tip";
        tip.setAttribute("role", "tooltip");
        tip.hidden = true;
        document.body.appendChild(tip);

        function plegado() {
            return document.documentElement.getAttribute("data-navcompact") === "1"
                && window.innerWidth > 1080;
        }
        function mostrarTip(link) {
            var texto = link.getAttribute("data-title");
            if (!texto) return;
            tip.textContent = texto;
            tip.hidden = false;
            var r = link.getBoundingClientRect();
            var alto = tip.offsetHeight;
            var arriba = r.top + (r.height / 2) - (alto / 2);
            tip.style.left = (r.right + 10) + "px";
            tip.style.top = Math.max(8, Math.min(arriba, window.innerHeight - alto - 8)) + "px";
        }
        function ocultarTip() { tip.hidden = true; }

        side.querySelectorAll(".sidebar-link").forEach(function (link) {
            link.addEventListener("mouseenter", function () { if (plegado()) mostrarTip(link); });
            link.addEventListener("focus", function () { if (plegado()) mostrarTip(link); });
            link.addEventListener("mouseleave", ocultarTip);
            link.addEventListener("blur", ocultarTip);
        });
        side.addEventListener("scroll", ocultarTip, { passive: true });
        if (plegar) plegar.addEventListener("click", ocultarTip);
        window.addEventListener("resize", ocultarTip);
        document.addEventListener("keydown", function (ev) {
            if (ev.key === "Escape") ocultarTip();
        });
    })();

    /* ---- Nombre de archivos seleccionados + preview de imagen ---- */
    document.querySelectorAll('input[type="file"][multiple], input[type="file"]').forEach(function (input) {
        input.addEventListener("change", function () {
            var box = document.getElementById(input.id + "-preview") ||
                      input.closest(".form-group")?.querySelector(".file-preview");
            if (!box) return;
            box.innerHTML = "";
            Array.from(input.files).slice(0, 6).forEach(function (f) {
                var item = document.createElement("span");
                item.className = "file-chip";
                item.textContent = f.name + " (" + Math.round(f.size / 1024) + " KB)";
                box.appendChild(item);
            });
            if (input.files.length > 6) {
                var more = document.createElement("span");
                more.className = "file-chip";
                more.textContent = "+" + (input.files.length - 6) + " más…";
                box.appendChild(more);
            }
        });
    });

    /* ---- Donut de reportes: conic-gradient desde la leyenda ---- */
    document.querySelectorAll(".donut-ring[data-donut]").forEach(function (ring) {
        var wrap = ring.closest(".donut-chart-wrap");
        var total = parseInt(ring.getAttribute("data-total") || "0", 10);
        if (!wrap || !total) return;
        var grad = [];
        var acc = 0;
        wrap.querySelectorAll(".donut-legend li").forEach(function (li) {
            var dot = li.querySelector(".donut-dot");
            var countEl = li.querySelector(".donut-legend-count");
            var count = parseInt((countEl ? countEl.textContent : "") || "0", 10);
            var pct = count ? Math.round(count / total * 100) : 0;
            var color = dot ? getComputedStyle(dot).backgroundColor : "#eee";
            grad.push(color + " " + acc + "% " + (acc + pct) + "%");
            acc += pct;
        });
        if (acc < 100) grad.push("#eee " + acc + "% 100%");
        ring.style.background = "conic-gradient(" + grad.join(", ") + ")";
    });

    /* ---- Modal de usuario (usuarios.html): rellenar formulario ---- */
    document.querySelectorAll("[data-fill-pk]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            [
                ["pk", "value", "data-fill-pk", ""],
                ["nombre", "value", "data-fill-nombre", ""],
                ["email", "value", "data-fill-email", ""],
                ["rol", "value", "data-fill-rol", "usuario"],
                ["glpi", "value", "data-fill-glpi", ""],
                ["activo", "checked", "data-fill-activo", null],
                ["telefono", "value", "data-fill-telefono", ""],
                ["ubicacion", "value", "data-fill-ubicacion", ""],
                ["pass", "value", "", ""]
            ].forEach(function (spec) {
                var el = document.getElementById("u-" + spec[0]);
                if (!el) return;
                if (spec[2]) {
                    if (spec[1] === "checked") el.checked = btn.getAttribute(spec[2]) === "1";
                    else el.value = btn.getAttribute(spec[2]) || spec[3];
                } else {
                    el.value = spec[3];
                }
            });
            var pass = document.getElementById("u-pass");
            if (pass) pass.placeholder = "Dejar vacía = sin cambios";
        });
    });
    document.querySelectorAll("[data-new-user]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            ["pk", "nombre", "email", "glpi"].forEach(function (f) {
                var el = document.getElementById("u-" + f);
                if (el) el.value = "";
            });
            var rol = document.getElementById("u-rol");
            if (rol) rol.value = btn.getAttribute("data-default-rol") === "tecnico" ? "tecnico" : "usuario";
            var activo = document.getElementById("u-activo");
            if (activo) activo.checked = true;
            var pass = document.getElementById("u-pass");
            if (pass) { pass.value = ""; pass.placeholder = "Obligatoria para cuentas nuevas"; }
        });
    });

    /* ---- Ajustes de cuenta: tabs + preview de avatar ---- */
    document.querySelectorAll("[data-settings-tab]").forEach(function (tab) {
        tab.addEventListener("click", function (e) {
            e.preventDefault();
            document.querySelectorAll("[data-settings-tab]").forEach(function (t) { t.classList.remove("active"); });
            document.querySelectorAll("[data-settings-panel]").forEach(function (p) { p.classList.remove("active"); });
            tab.classList.add("active");
            var target = document.querySelector('[data-settings-panel="' + tab.getAttribute("data-settings-tab") + '"]');
            if (target) target.classList.add("active");
        });
    });
    function openSettingsPanel(name) {
        var tab = document.querySelector('[data-settings-tab="' + name + '"]');
        var panel = document.querySelector('[data-settings-panel="' + name + '"]');
        if (!tab || !panel) return;
        document.querySelectorAll("[data-settings-tab]").forEach(function (t) { t.classList.remove("active"); });
        document.querySelectorAll("[data-settings-panel]").forEach(function (p) { p.classList.remove("active"); });
        tab.classList.add("active");
        panel.classList.add("active");
        setTimeout(function () {
            if (panel.getBoundingClientRect().top < 0) panel.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 50);
    }
    if (location.hash && location.hash.length > 1) {
        openSettingsPanel(location.hash.slice(1));
    }
    window.addEventListener("hashchange", function () {
        if (location.hash && location.hash.length > 1) openSettingsPanel(location.hash.slice(1));
    });
    var avatarInput = document.getElementById("id_avatar");
    var avatarPreview = document.getElementById("avatar-preview");
    if (avatarInput && avatarPreview) {
        avatarInput.addEventListener("change", function () {
            var file = avatarInput.files[0];
            if (!file) return;
            var reader = new FileReader();
            reader.onload = function (e) {
                if (avatarPreview.tagName === "IMG") {
                    avatarPreview.src = e.target.result;
                } else {
                    var img = document.createElement("img");
                    img.src = e.target.result;
                    img.alt = "";
                    img.className = "settings-avatar-img";
                    img.id = "avatar-preview";
                    avatarPreview.parentNode.replaceChild(img, avatarPreview);
                }
            };
            reader.readAsDataURL(file);
        });
    }

    /* ---- Categoría inteligente: auto-selección por título/descripción ---- */
    var catKeywordsEl = document.getElementById("dogger-cat-keywords");
    var tituloEl = document.getElementById("id_titulo");
    var descEl = document.getElementById("id_descripcion");
    var catSelEl = document.getElementById("id_categoria");
    var suggestChip = document.getElementById("cat-suggest");
    var autoHintEl = document.getElementById("cat-auto-hint");
    if (catKeywordsEl && tituloEl && catSelEl && suggestChip) {
        var CATS = JSON.parse(catKeywordsEl.textContent);
        var MED_THRESHOLD = 2;   // ofrecer el chip para confirmar
        var AUTO_THRESHOLD = 4;  // selección automática confiable
        var suggestName = document.getElementById("cat-suggest-name");
        var autoName = document.getElementById("cat-auto-name");
        var suggestionsEnabled = true;
        var applyingAuto = false;

        function normText(s) {
            return (s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        }
        function escapeRx(s) {
            return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        }
        function hideAll() {
            suggestChip.hidden = true;
            if (autoHintEl) autoHintEl.hidden = true;
        }
        function applyToSelect(pk) {
            applyingAuto = true;
            catSelEl.value = pk;
            catSelEl.classList.remove("suggest-applied");
            void catSelEl.offsetWidth;
            catSelEl.classList.add("suggest-applied");
            catSelEl.dispatchEvent(new Event("change", { bubbles: true }));
            applyingAuto = false;
        }
        function evalSuggestion() {
            if (!suggestionsEnabled) return;
            var text = (normText(tituloEl.value) + " " + normText(descEl ? descEl.value : "")).trim();
            if (text.length < 12) { hideAll(); return; }
            var best = null, bestScore = 0, i, j;
            for (i = 0; i < CATS.length; i++) {
                var c = CATS[i], score = 0, claves = c.claves || [];
                for (j = 0; j < claves.length; j++) {
                    var k = normText(claves[j]);
                    if (!k) continue;
                    if (k.indexOf(" ") > -1) {
                        if (text.indexOf(k) > -1) score += 4;
                    } else {
                        var re = new RegExp("\\b" + escapeRx(k) + "\\b");
                        if (re.test(text)) score += 2;
                        else if (text.indexOf(k) > -1) score += 1;
                    }
                }
                if (normText(c.nombre) && text.indexOf(normText(c.nombre)) > -1) score += 2;
                if (normText(c.grupo) && text.indexOf(normText(c.grupo)) > -1) score += 1;
                if (score > bestScore) { best = c; bestScore = score; }
            }
            if (!best || bestScore < MED_THRESHOLD) { hideAll(); return; }

            if (bestScore >= AUTO_THRESHOLD) {
                // Coincidencia clara: se auto-selecciona y se avisa al usuario.
                if (!catSelEl.value || String(catSelEl.value) !== String(best.id)) {
                    applyToSelect(best.id);
                }
                if (autoHintEl) {
                    autoName.textContent = best.nombre + " (" + best.grupo + ")";
                    autoHintEl.hidden = false;
                }
                suggestChip.hidden = true;
                return;
            }

            // Coincidencia media: se ofrece el chip para confirmar.
            if (catSelEl.value && String(catSelEl.value) === String(best.id)) {
                hideAll();
                return;
            }
            suggestName.textContent = best.nombre + " (" + best.grupo + ")";
            suggestChip.setAttribute("data-best", best.id);
            if (autoHintEl) autoHintEl.hidden = true;
            suggestChip.hidden = false;
        }
        var suggestTimer = null;
        function suggestOnInput() {
            clearTimeout(suggestTimer);
            suggestTimer = setTimeout(evalSuggestion, 220);
        }
        tituloEl.addEventListener("input", suggestOnInput);
        if (descEl) descEl.addEventListener("input", suggestOnInput);
        document.addEventListener("click", function (e) {
            var apply = e.target.closest ? e.target.closest("[data-suggest-apply]") : null;
            if (apply && suggestChip) {
                e.preventDefault();
                var pk = suggestChip.getAttribute("data-best");
                if (pk) applyToSelect(pk);
                suggestionsEnabled = false;
                hideAll();
                return;
            }
            var dismiss = e.target.closest ? e.target.closest("[data-suggest-dismiss]") : null;
            if (dismiss) {
                e.preventDefault();
                suggestionsEnabled = false;
                catSelEl.classList.remove("suggest-applied");
                hideAll();
                return;
            }
        });
        catSelEl.addEventListener("change", function () {
            if (applyingAuto) return;
            // El usuario eligió manualmente: detener la auto-selección.
            suggestionsEnabled = false;
            catSelEl.classList.remove("suggest-applied");
            hideAll();
        });

        /* ---- Resaltado ANS según la categoría seleccionada ---- */
        var ansCatsEl = document.getElementById("dogger-ans-cats");
        var ansScaleEl = document.getElementById("ans-scale");
        var ansActiveEl = document.getElementById("ans-por-categoria");
        if (ansCatsEl && ansScaleEl) {
            var ANS_CATS = JSON.parse(ansCatsEl.textContent);
            var ansItems = Array.prototype.slice.call(ansScaleEl.children);
            var ansPrioridadEl = document.getElementById("ans-active-prioridad");
            var ansHorasEl = document.getElementById("ans-active-horas");
            function prioridadTexto(p) {
                return { urgente: "Urgente", alta: "Alta", media: "Media", baja: "Baja" }[p] || "";
            }
            function marcarAns(pk) {
                var match = null;
                for (var i = 0; i < ANS_CATS.length; i++) {
                    if (String(ANS_CATS[i].id) === String(pk)) { match = ANS_CATS[i]; break; }
                }
                for (var j = 0; j < ansItems.length; j++) {
                    ansItems[j].classList.toggle("is-active", !!(match && ansItems[j].getAttribute("data-prioridad") === match.prioridad));
                    ansItems[j].classList.toggle("not-active", !!(match && ansItems[j].getAttribute("data-prioridad") !== match.prioridad));
                }
                if (!match) {
                    if (ansActiveEl) ansActiveEl.hidden = true;
                    return;
                }
                if (ansActiveEl && ansPrioridadEl && ansHorasEl) {
                    ansPrioridadEl.textContent = prioridadTexto(match.prioridad);
                    ansHorasEl.textContent = (match.ans || "—") + " horas";
                    ansActiveEl.hidden = false;
                }
            }
            catSelEl.addEventListener("change", function () { marcarAns(catSelEl.value); });
            if (catSelEl.value) marcarAns(catSelEl.value);
        }
    }

    /* ---- Menú de la portada (móvil): el nav de la landing se pliega ---- */
    (function () {
        var toggle = document.getElementById("ln-toggle");
        var links = document.getElementById("ln-links");
        if (!toggle || !links) return;

        function abrir(abrir) {
            links.classList.toggle("is-open", abrir);
            toggle.setAttribute("aria-expanded", abrir ? "true" : "false");
            toggle.setAttribute("aria-label", abrir ? "Ocultar el menú de la página" : "Ver el menú de la página");
        }
        function estaAbierto() { return links.classList.contains("is-open"); }
        abrir(window.matchMedia("(min-width: 981px)").matches);

        toggle.addEventListener("click", function () {
            abrir(!estaAbierto());
        });
        links.addEventListener("click", function (ev) {
            if (ev.target.closest("a")) abrir(false);
        });
        document.addEventListener("keydown", function (ev) {
            if (ev.key === "Escape" && estaAbierto()) { abrir(false); toggle.focus(); }
        });
        document.addEventListener("click", function (ev) {
            if (!estaAbierto()) return;
            if (!ev.target.closest(".landing-nav")) abrir(false);
        });
    })();

    /* ---- Preguntas frecuentes: "ver todas" despliega en la misma página ---- */
    var faqBoton = document.getElementById("faq-ver-mas");
    var faqExtra = document.getElementById("faq-extra");
    var faqTexto = document.getElementById("faq-ver-mas-txt");
    if (faqBoton && faqExtra) {
        faqBoton.addEventListener("click", function () {
            var abierto = faqExtra.hasAttribute("hidden");
            if (abierto) {
                faqExtra.removeAttribute("hidden");
            } else {
                faqExtra.setAttribute("hidden", "");
            }
            faqBoton.setAttribute("aria-expanded", abierto ? "true" : "false");
            if (faqTexto) faqTexto.textContent = abierto ? "Ocultar las demás preguntas" : "Ver todas las preguntas frecuentes";
            if (abierto) {
                faqExtra.scrollIntoView({ behavior: "smooth", block: "nearest" });
            }
        });
    }

    /* ---- Espacio para escribir una pregunta: se envía por correo ---- */
    var formPregunta = document.getElementById("lp-pregunta-form");
    if (formPregunta) {
        var aviso = document.getElementById("lp-pregunta-aviso");
        formPregunta.addEventListener("submit", function (ev) {
            ev.preventDefault();
            var nombre = document.getElementById("pq-nombre");
            var correo = document.getElementById("pq-correo");
            var texto = document.getElementById("pq-texto");
            if (!texto.value.trim() || !nombre.value.trim()) {
                if (aviso) aviso.textContent = "Escribe tu nombre y tu pregunta para poder enviar el mensaje.";
                (!texto.value.trim() ? texto : nombre).focus();
                return;
            }
            if (aviso) aviso.textContent = "";
            var cuerpo = "Pregunta enviada desde el portal\n\n" +
                "Nombre: " + nombre.value.trim() + "\n" +
                "Correo: " + (correo && correo.value.trim() ? correo.value.trim() : "no informado") + "\n\n" +
                texto.value.trim();
            var correoSoporte = formPregunta.getAttribute("data-correo") || "";
            window.location.href = "mailto:" + correoSoporte +
                "?subject=" + encodeURIComponent("Pregunta desde el portal - " + nombre.value.trim()) +
                "&body=" + encodeURIComponent(cuerpo);
            texto.value = "";
            if (aviso) aviso.textContent = "Abrimos tu programa de correo con la pregunta lista para enviar.";
        });
    }
})();

/* =====================================================================
   Campana de notificaciones: abrir la lista, marcar leídas, quitar con la
   "x", refresco automático y ventanas emergentes encadenadas.
   ===================================================================== */
(function () {
    var wrap = document.getElementById("notifWrap");
    var bell = document.getElementById("notifBell");
    var panel = document.getElementById("notifPanel");
    var URL_API = (wrap && wrap.getAttribute("data-url-api")) || "";

    function csrf() {
        var input = document.querySelector("[name=csrfmiddlewaretoken]");
        if (input) { return input.value; }
        var m = document.cookie.match(/(^|;\s*)csrftoken=([^;]+)/);
        return m ? m[2] : "";
    }

    function pedir(destino) {
        if (!destino) { return; }
        try {
            fetch(destino, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrf(),
                    "X-Requested-With": "XMLHttpRequest"
                },
                credentials: "same-origin"
            }).then(function (r) {
                return r.ok ? r.json() : null;
            }).then(function (data) {
                if (data && typeof data.pendientes === "number") {
                    pintarContador(data.pendientes);
                }
            }).catch(function () { });
        } catch (e) { }
    }

    function pintarContador(pendientes) {
        var badge = document.getElementById("notifBadge");
        if (!badge || typeof pendientes !== "number") { return; }
        badge.textContent = pendientes > 99 ? "99+" : pendientes;
        badge.classList.toggle("is-empty", pendientes === 0);
        if (bell) {
            var oculto = document.querySelector(".visually-hidden", bell);
            if (oculto) {
                oculto.textContent = pendientes
                    ? "Notificaciones: " + pendientes + " sin leer"
                    : "Notificaciones";
            }
        }
    }

    /* ---- Aviso breve en la esquina inferior izquierda ----
       Sale cuando llega algo nuevo, sin bloquear y se va solo. Es el mismo
       sitio donde aparecen los mensajes del sistema. */
    function toastAviso(n) {
        var pila = document.querySelector(".toast-stack");
        if (!pila) { return; }
        var url = n.url || "#";
        var el = document.createElement("div");
        el.className = "toast toast-notif";
        el.innerHTML =
            '<span class="notif-icon notif-icon-' + esc(n.tipo) + '" aria-hidden="true">' +
            '<svg class="icon icon-sm"><use href="#' + esc(n.icono || "i-bell") + '"/></svg></span>' +
            '<div class="toast-body">' +
            '<strong>' + esc(n.titulo) + '</strong>' +
            '<span>' + esc(n.mensaje || "") + '</span>' +
            '<a href="' + esc(url) + '">Ver</a>' +
            '</div>' +
            '<button type="button" class="toast-close" aria-label="Cerrar">&times;</button>';
        pila.appendChild(el);

        // Al hacer clic en "Ver" se marca como mostrada, como la emergente.
        el.querySelector("a").addEventListener("click", function () {
            pedir(baseDe("data-url-mostrada", n.id));
        });
        // Mismo auto-cierre con pausa al pasar el mouse que los toasts del servidor.
        var delay = 7000;
        el.style.setProperty("--toast-delay", delay + "ms");
        var timer = null, started = Date.now(), remaining = delay;
        function dismiss() {
            if (!el.isConnected) { return; }
            el.classList.add("toast-out");
            setTimeout(function () { el.remove(); }, 340);
        }
        function schedule() {
            if (timer) { clearTimeout(timer); timer = null; }
            timer = setTimeout(dismiss, remaining);
        }
        var btn = el.querySelector(".toast-close");
        if (btn) { btn.addEventListener("click", dismiss); }
        el.addEventListener("mouseenter", function () {
            remaining -= Date.now() - started;
            if (timer) { clearTimeout(timer); timer = null; }
        });
        el.addEventListener("mouseleave", function () {
            if (remaining <= 0) { return; }
            started = Date.now();
            schedule();
        });
        schedule();
    }

    function vacioHTML() {
        return '<li class="notif-empty">' +
            '<span class="notif-empty-icon"><svg class="icon"><use href="#i-check-circle"/></svg></span>' +
            '<strong>No tienes avisos</strong>' +
            '<span>Aquí verás tus tickets activos, tareas y recordatorios.</span>' +
            '</li>';
    }

    function baseDe(atributo, id) {
        var base = wrap.getAttribute(atributo) || "";
        return id ? base.replace("/0/", "/" + id + "/") : base;
    }

    function esc(t) {
        return String(t == null ? "" : t)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    /* ---- Ventanas emergentes: se acumulan y salen de una en una ---- */
    var colaEmergente = [];
    var emergenteViva = false;

    function filaHTML(n) {
        return '<li class="notif-row' + (n.nueva ? " is-new" : "") + '" data-id="' + esc(n.id) + '">' +
            '<span class="notif-icon notif-icon-' + esc(n.tipo) + '" aria-hidden="true">' +
            '<svg class="icon icon-sm"><use href="#' + esc(n.icono || "i-bell") + '"/></svg>' +
            '</span>' +
            '<span class="notif-text">' +
            '<a class="notif-link" href="' + esc(n.url || "#") + '">' + esc(n.titulo) + '</a>' +
            '<span class="notif-msg">' + esc(n.mensaje) + '</span>' +
            '<small class="notif-time">ahora mismo</small>' +
            '</span>' +
            '<button type="button" class="notif-x" data-notif-quitar="' + esc(n.id) + '" ' +
            'aria-label="Quitar notificación" title="Quitar">&times;</button>' +
            '</li>';
    }

    function mostrarEmergenteSiguiente() {
        if (emergenteViva || !colaEmergente.length) { return; }
        var n = colaEmergente.shift();
        emergenteViva = true;
        var overlay = document.createElement("div");
        overlay.className = "notif-popup-overlay notif-popup-viva notif-popup-" + esc(n.tipo);
        overlay.setAttribute("data-id", n.id);
        overlay.setAttribute("role", "dialog");
        overlay.setAttribute("aria-modal", "true");
        overlay.setAttribute("aria-labelledby", "notifPopVivaTitulo");
        overlay.innerHTML =
            '<div class="notif-popup">' +
            '<button type="button" class="notif-popup-x" data-notif-cerrar aria-label="Cerrar">&times;</button>' +
            '<span class="notif-popup-head">' +
            '<span class="notif-popup-icon" aria-hidden="true">' +
            '<svg class="icon"><use href="#' + esc(n.icono || "i-bell") + '"/></svg></span>' +
            '<h3 class="notif-popup-title" id="notifPopVivaTitulo">' + esc(n.titulo) + '</h3>' +
            '</span>' +
            '<p class="notif-popup-text">' + esc(n.mensaje) + '</p>' +
            '<div class="notif-popup-actions">' +
            '<a class="btn btn-accent btn-sm notif-popup-ver" href="' + esc(n.url || "#") + '">Ver</a>' +
            '<button type="button" class="btn btn-ghost btn-sm" data-notif-cerrar>Ahora no</button>' +
            '</div>' +
            (colaEmergente.length
                ? '<small class="notif-popup-foot notif-popup-faltan">Quedan ' +
                  colaEmergente.length + ' aviso' + (colaEmergente.length === 1 ? "" : "s") +
                  ' más.</small>'
                : '<small class="notif-popup-foot">También lo verás en la campana de notificaciones.</small>') +
            '</div>';
        document.body.appendChild(overlay);
        overlay.addEventListener("click", function (ev) {
            if (ev.target.closest("[data-notif-cerrar]") || ev.target === overlay) {
                ev.preventDefault();
                cerrarEmergenteViva(overlay);
            }
        });
        overlay.querySelectorAll("a").forEach(function (a) {
            a.addEventListener("click", function () { pedir(baseDe("data-url-mostrada", n.id)); });
        });
    }

    function cerrarEmergenteViva(overlay) {
        var id = overlay.getAttribute("data-id");
        overlay.remove();
        emergenteViva = false;
        if (wrap) { pedir(baseDe("data-url-mostrada", id)); }
        // La siguiente emerge enseguida: así no se encadenan encima.
        setTimeout(mostrarEmergenteSiguiente, 450);
    }

    /* ---- Refresco automático: el estado se consulta solo ---- */
    function refrescar() {
        if (!URL_API || document.hidden) { return; }
        fetch(URL_API, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin",
            cache: "no-store"
        }).then(function (r) { return r.ok ? r.json() : null; }).then(function (data) {
            if (!data || !data.ok) { return; }
            pintarContador(data.no_leidas);

            // 1) Los avisos nuevos se apilan en la lista de la campana.
            if (panel && Array.isArray(data.avisos)) {
                var lista = panel.querySelector(".notif-list");
                if (lista) {
                    var actuales = {};
                    lista.querySelectorAll(".notif-row[data-id]").forEach(function (f) {
                        actuales[f.getAttribute("data-id")] = true;
                    });
                    var frescos = data.avisos.filter(function (n) { return !actuales[n.id]; });
                    if (frescos.length) {
                        var vacia = lista.querySelector(".notif-empty");
                        if (vacia) { vacia.remove(); }
                        lista.insertAdjacentHTML("afterbegin", frescos.reverse().map(function (n) {
                            return filaHTML(n);
                        }).join(""));
                    }
                    // Refresca el texto "hace x" de los que ya estaban.
                    lista.querySelectorAll(".notif-row[data-id]").forEach(function (f) {
                        var t = f.querySelector(".notif-time");
                        if (t) { t.textContent = "ahora mismo"; }
                    });
                }
            }

            // 2) Las emergentes se acumulan y salen una detrás de otra.
            if (Array.isArray(data.emergentes) && data.emergentes.length) {
                var yaEnCola = {};
                colaEmergente.forEach(function (n) { yaEnCola[n.id] = true; });
                var actual = document.querySelector(".notif-popup-viva");
                if (actual) { yaEnCola[actual.getAttribute("data-id")] = true; }
                // La emergente inicial viene ya pintada por el servidor: si
                // sigue en pantalla no se vuelve a encolar la misma.
                var inicial = document.getElementById("notifPopup");
                if (inicial && inicial.getAttribute("data-id")) {
                    yaEnCola[inicial.getAttribute("data-id")] = true;
                }
                data.emergentes.forEach(function (n) {
                    if (!yaEnCola[n.id]) {
                        colaEmergente.push(n);
                        // Aviso breve en la esquina inferior izquierda.
                        toastAviso(n);
                    }
                });
                mostrarEmergenteSiguiente();
            }
        }).catch(function () { });
    }

    /* ---- Latido: avisa que esta pestaña sigue viva ---- */
    function latido() {
        var url = document.body.getAttribute("data-url-latido");
        if (!url || document.hidden) { return; }
        fetch(url, {
            method: "POST",
            headers: { "X-CSRFToken": csrf(), "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin",
            cache: "no-store"
        }).catch(function () { });
    }

    if (wrap && bell && panel) {
        function abrir() {
            panel.classList.add("open");
            bell.setAttribute("aria-expanded", "true");
            var nuevas = panel.querySelectorAll(".notif-row.is-new");
            if (nuevas.length) {
                Array.prototype.forEach.call(nuevas, function (fila) {
                    fila.classList.remove("is-new");
                });
                pedir(baseDe("data-url-todas"));
            }
            refrescar();
        }

        function cerrar() {
            panel.classList.remove("open");
            bell.setAttribute("aria-expanded", "false");
        }

        bell.addEventListener("click", function (ev) {
            ev.stopPropagation();
            if (panel.classList.contains("open")) { cerrar(); } else { abrir(); }
        });
        document.addEventListener("click", function (ev) {
            if (!wrap.contains(ev.target)) { cerrar(); }
        });
        document.addEventListener("keydown", function (ev) {
            if (ev.key === "Escape") { cerrar(); }
        });

        panel.addEventListener("click", function (ev) {
            var quitar = ev.target.closest("[data-notif-quitar]");
            if (quitar) {
                ev.preventDefault();
                ev.stopPropagation();
                var fila = quitar.closest(".notif-row");
                var id = quitar.getAttribute("data-notif-quitar");
                if (fila) { fila.remove(); }
                pedir(baseDe("data-url-descartar", id));
                if (!panel.querySelector(".notif-row")) {
                    var lista = panel.querySelector(".notif-list");
                    if (lista && !lista.querySelector(".notif-empty")) {
                        lista.innerHTML = vacioHTML();
                    }
                }
                refrescar();
                return;
            }
            var accion = ev.target.closest("[data-notif]");
            if (!accion) { return; }
            ev.stopPropagation();
            var tipo = accion.getAttribute("data-notif");
            if (tipo === "leer-todas") {
                pedir(baseDe("data-url-todas"));
                Array.prototype.forEach.call(
                    panel.querySelectorAll(".notif-row"), function (f) { f.classList.remove("is-new"); }
                );
            } else if (tipo === "limpiar") {
                pedir(baseDe("data-url-limpiar"));
                var lista2 = panel.querySelector(".notif-list");
                if (lista2) { lista2.innerHTML = vacioHTML(); }
                var botones = panel.querySelectorAll(".notif-head-btn");
                Array.prototype.forEach.call(botones, function (b) { b.remove(); });
            }
        });
    }

    /* ---- Ventana emergente inicial (la que trae la página) ---- */
    var popup = document.getElementById("notifPopup");
    if (popup) {
        function cerrarPopup() {
            var id = popup.getAttribute("data-id");
            popup.remove();
            if (wrap) { pedir(baseDe("data-url-mostrada", id)); }
        }
        popup.addEventListener("click", function (ev) {
            if (ev.target.closest("[data-notif-cerrar]")) {
                ev.stopPropagation();
                cerrarPopup();
            }
        });
        document.addEventListener("keydown", function (ev) {
            if (ev.key === "Escape" && document.getElementById("notifPopup")) { cerrarPopup(); }
        });
    }


    /* ---- Tablas con scroll: exactamente N filas a la vista ----
       Cada tabla se ve densa, asi que una altura fija deja 4 filas en una y
       8 en otra. Se mide la fila real y se limita el alto a la del encabezado
       mas N filas: siempre se ven las mismas N, ni mas ni menos. */
    function ajustarFilas(wrap) {
        var tabla = wrap.querySelector("table");
        if (!tabla) return;
        var thead = wrap.querySelector("thead");
        var filas = wrap.querySelectorAll("tbody tr");
        if (!filas.length) { wrap.style.removeProperty("--alto-filas"); return; }
        var n = parseInt(wrap.getAttribute("data-filas"), 10) || 6;
        // Se promedian las primeras n filas para que una fila alta
        // no empuje la altura de toda la tabla.
        var muestra = Array.prototype.slice.call(filas, 0, n);
        var suma = 0;
        muestra.forEach(function (f) { suma += f.offsetHeight; });
        var alto = (suma / muestra.length) * n + (thead ? thead.offsetHeight : 0);
        wrap.style.setProperty("--alto-filas", Math.ceil(alto) + "px");
    }

    function ajustarTablas() {
        var wraps = document.querySelectorAll("[data-filas]");
        wraps.forEach(ajustarFilas);
        // Se vuelve a medir cuando cambian las filas: al abrir la ficha de un
        // usuario se inserta una fila y el alto volveria a quedar corto.
        wraps.forEach(function (wrap) {
            var cuerpo = wrap.querySelector("tbody");
            if (!cuerpo || cuerpo.dataset.observado) return;
            cuerpo.dataset.observado = "1";
            new MutationObserver(function () {
                clearTimeout(cuerpo._t);
                cuerpo._t = setTimeout(ajustarFilas, 80);
            }).observe(cuerpo, { childList: true });
        });
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", ajustarTablas);
    } else {
        ajustarTablas();
    }
    window.addEventListener("load", ajustarTablas);
    var pending;
    window.addEventListener("resize", function () {
        clearTimeout(pending);
        pending = setTimeout(ajustarTablas, 150);
    });

    /* ---- Arranque del refresco automático ---- */
    if (URL_API) {
        // Al entrar, lo que ya se está viendo pasa a leído: el contador se
        // queda en 0 en vez de quedar activo hasta que alguien abra la campana.
        // Los avisos siguen en la lista, solo dejan de contar como pendientes.
        pedir(baseDe("data-url-todas"));
        // El intervalo es corto para que el contador no se sienta viejo.
        setInterval(refrescar, 12000);
        // Al volver a la pestaña se consulta de inmediato.
        document.addEventListener("visibilitychange", function () {
            if (!document.hidden) { refrescar(); }
        });
    }
    if (document.body.getAttribute("data-url-latido")) {
        // Un latido al entrar para que el punto quede verde de inmediato, y
        // otro cada 2 minutos mientras la pestaña siga abierta.
        latido();
        setInterval(latido, 120000);
        document.addEventListener("visibilitychange", function () {
            if (!document.hidden) { latido(); }
        });
    }
})();

