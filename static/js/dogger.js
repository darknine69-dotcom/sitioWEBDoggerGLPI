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
                item.textContent = "📎 " + f.name + " (" + Math.round(f.size / 1024) + " KB)";
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
})();
