/* Dogger HelpDesk — interacciones globales (sin dependencias) */
(function () {
    "use strict";

    /* ---- Mensajes flash: cerrar y auto-ocultar ---- */
    document.querySelectorAll(".flash").forEach(function (el) {
        var close = el.querySelector(".flash-close");
        if (close) {
            close.addEventListener("click", function () {
                el.style.opacity = "0";
                setTimeout(function () { el.remove(); }, 180);
            });
        }
        var delay = el.classList.contains("flash-error") ? 12000 : 6500;
        setTimeout(function () {
            if (!el.isConnected) return;
            el.style.transition = "opacity .4s ease";
            el.style.opacity = "0";
            setTimeout(function () { el.remove(); }, 420);
        }, delay);
    });

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

    /* ---- Grupos de categorías: colapsar/expandir ---- */
    document.querySelectorAll(".cat-group-head").forEach(function (head) {
        head.addEventListener("click", function () {
            head.closest(".cat-group-card").classList.toggle("collapsed");
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

    /* ---- Botón volver ---- */
    document.querySelectorAll(".back-btn[data-back]").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
            e.preventDefault();
            if (window.history.length > 1) { window.history.back(); }
            else { window.location.href = btn.getAttribute("href") || "/"; }
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

    /* ---- Hamburger menu toggle (mobile) ---- */
    var navToggle = document.getElementById("navToggle");
    var navList = document.getElementById("navList");
    if (navToggle && navList) {
        navToggle.addEventListener("click", function () {
            var expanded = navToggle.getAttribute("aria-expanded") === "true";
            navToggle.setAttribute("aria-expanded", String(!expanded));
            navList.classList.toggle("nav-open");
            navToggle.classList.toggle("is-active");
        });
        navList.querySelectorAll(".nav-link").forEach(function (link) {
            link.addEventListener("click", function () {
                navToggle.setAttribute("aria-expanded", "false");
                navList.classList.remove("nav-open");
                navToggle.classList.remove("is-active");
            });
        });
    }

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

    /* ---- Sugerencia de categoría por título/descripción (crear ticket) ---- */
    var catKeywordsEl = document.getElementById("dogger-cat-keywords");
    var tituloEl = document.getElementById("id_titulo");
    var descEl = document.getElementById("id_descripcion");
    var catSelEl = document.getElementById("id_categoria");
    var suggestChip = document.getElementById("cat-suggest");
    if (catKeywordsEl && tituloEl && catSelEl && suggestChip) {
        var CATS = JSON.parse(catKeywordsEl.textContent);
        var suggestName = document.getElementById("cat-suggest-name");
        var suggestionsEnabled = true;

        function normText(s) {
            return (s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        }
        function escapeRx(s) {
            return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        }
        function suggestHide() {
            suggestChip.hidden = true;
        }
        function suggestShow() {
            suggestChip.hidden = false;
        }
        function evalSuggestion() {
            if (!suggestionsEnabled) return;
            var text = (normText(tituloEl.value) + " " + normText(descEl ? descEl.value : "")).trim();
            if (text.length < 12) {
                suggestHide();
                return;
            }
            var best = null, bestScore = 0, i, j;
            for (i = 0; i < CATS.length; i++) {
                var c = CATS[i], score = 0, claves = c.claves || [];
                for (j = 0; j < claves.length; j++) {
                    var k = normText(claves[j]);
                    if (!k) continue;
                    if (k.indexOf(" ") > -1) {
                        if (text.indexOf(k) > -1) score += 3;
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
            if (!best || bestScore < 2) {
                suggestHide();
                return;
            }
            if (catSelEl.value && String(catSelEl.value) === String(best.id)) {
                suggestHide();
                return;
            }
            suggestName.textContent = best.nombre + " (" + best.grupo + ")";
            suggestChip.setAttribute("data-best", best.id);
            suggestShow();
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
                if (pk) {
                    catSelEl.value = pk;
                    catSelEl.classList.remove("suggest-applied");
                    void catSelEl.offsetWidth;
                    catSelEl.classList.add("suggest-applied");
                    catSelEl.dispatchEvent(new Event("change", { bubbles: true }));
                }
                suggestionsEnabled = false;
                suggestHide();
                return;
            }
            var dismiss = e.target.closest ? e.target.closest("[data-suggest-dismiss]") : null;
            if (dismiss && suggestChip) {
                e.preventDefault();
                suggestionsEnabled = false;
                suggestHide();
            }
        });
        catSelEl.addEventListener("change", function () {
            suggestionsEnabled = false;
            suggestHide();
        });
    }
})();
