/* Voto de técnicos con pulgar arriba / abajo.

Lo usan dos vistas con el mismo diseño de tarjeta:
  - Mi panel: el voto al técnico en general.
  - Detalle de un ticket ya resuelto: el voto atado a ese ticket, que es lo
    que mueve la barra de aprobación por tickets resueltos.

El HTML pone en la lista la ruta con un 0 de relleno (data-calificar) y, si
viene del detalle, el pk del ticket (data-ticket).
*/
(function () {
    "use strict";

    var lista = document.getElementById("tec-lista");
    if (!lista) return;

    var base = lista.getAttribute("data-calificar") || "";
    var ticket = lista.getAttribute("data-ticket") || "";
    /* El token del POST. Va en un meta del <head> (base.html) y, si una
       pagina no lo trae, se busca en cualquier formulario de la pagina. Sin
       esto Django responde 403 y el voto parece que no hace nada. */
    var metaCsrf = document.querySelector('meta[name="csrfmiddlewaretoken"]');
    var inputCsrf = document.querySelector('input[name="csrfmiddlewaretoken"]');
    var csrf = (metaCsrf && metaCsrf.content) || (inputCsrf && inputCsrf.value) || "";

    function post(url, datos) {
        var fd = new URLSearchParams();
        Object.keys(datos).forEach(function (k) { fd.append(k, datos[k]); });
        return fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-CSRFToken": csrf
            },
            body: fd.toString()
        }).then(function (r) {
            if (r.status === 403) {
                return { ok: false, detalle: "La página quedó vieja: recarga con Ctrl+F5 y vota de nuevo." };
            }
            return r.json().catch(function () { return { ok: false, error: "Respuesta no válida." }; });
        });
    }

    /* Si algo falla, se dice. Antes el fallo se comía en silencio y parecía
       que los botones no hicieran nada. */
    function aviso(card, texto) {
        var caja = card.querySelector(".tec-voto");
        if (!caja) return;
        var el = caja.querySelector("[data-voto-error]");
        if (!el) {
            el = document.createElement("small");
            el.className = "tec-voto-aviso";
            el.setAttribute("data-voto-error", "");
            caja.appendChild(el);
        }
        clearTimeout(el._t);
        el.textContent = texto;
        el.hidden = false;
        el._t = setTimeout(function () { el.hidden = true; }, 5000);
    }

    function pintarBarra(card, barra) {
        if (!barra) return;
        var fill = card.querySelector("[data-barra-fill]");
        if (fill) fill.style.width = barra.porcentaje + "%";
        var pct = card.querySelector("[data-barra-pct]");
        if (pct) {
            pct.textContent = barra.total
                ? barra.porcentaje + "% de aprobación · " + barra.me_gusta + " de " +
                  barra.total + " ticket" + (barra.total === 1 ? " resuelto" : " resueltos")
                : "Todavía sin votos en tickets resueltos.";
        }
        var barraEl = card.querySelector(".tec-barra");
        if (barraEl) barraEl.classList.toggle("is-vacia", !barra.total);
        var track = card.querySelector(".tec-barra");
        if (track) track.setAttribute("title", barra.porcentaje + "% de aprobación en " +
            barra.total + " ticket" + (barra.total === 1 ? " resuelto" : " resueltos"));
    }

    document.querySelectorAll(".tec-pulgar").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var pk = btn.getAttribute("data-tec");
            var valor = btn.getAttribute("data-valor");
            var card = btn.closest(".tec-card");
            if (!base || !card) return;

            /* La ruta trae un 0 de relleno y hay que cambiarlo por el pk del
               técnico. Ojo: se cambia ese trozo exacto; antes se cambiaba un
               "0" del final y, como la ruta acaba en "/calificar/", el 0 se
               quedaba y todos los votos iban al técnico 0, que no existe. */
            var url = base.replace("/tecnicos/0/", "/tecnicos/" + pk + "/");
            if (url === base) {
                aviso(card, "No se pudo localizar la ruta de calificación.");
                return;
            }

            var datos = { valor: valor, csrfmiddlewaretoken: csrf };
            if (ticket) datos.ticket = ticket;

            btn.disabled = true;
            post(url, datos).then(function (r) {
                btn.disabled = false;
                if (!r || !r.ok) {
                    aviso(card, (r && (r.detalle || r.error)) || "No se pudo registrar el voto.");
                    return;
                }
                var up = card.querySelector('[data-rol="up"]');
                var down = card.querySelector('[data-rol="down"]');
                if (up) up.textContent = r.me_gusta;
                if (down) down.textContent = r.no_me_gusta;
                card.querySelectorAll(".tec-pulgar").forEach(function (b) {
                    var mio = parseInt(b.getAttribute("data-valor"), 10) === r.mi_voto;
                    b.classList.toggle("is-on", mio);
                });
                pintarBarra(card, r.barra);
            }).catch(function () {
                btn.disabled = false;
                aviso(card, "Error de conexión.");
            });
        });
    });
})();
