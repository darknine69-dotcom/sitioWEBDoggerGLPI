(function () {
    "use strict";
    var pagina = document.querySelector(".perfil-page");
    if (!pagina) return;
    var form = pagina.querySelector('#perfil form');
    var foto = document.getElementById("id_avatar");
    var errorFoto = document.getElementById("perfil-avatar-error");
    var fotoInvalida = false;
    if (foto && !foto.hasAttribute("data-avatar-editor")) {
        foto.addEventListener("change", function () {
            var archivo = foto.files && foto.files[0];
            var error = archivo && !/^image\/(jpeg|png|gif|webp)$/i.test(archivo.type) ? "Selecciona una imagen JPG, PNG, GIF o WebP." : archivo && archivo.size > 2 * 1024 * 1024 ? "La foto no debe pesar más de 2 MB." : "";
            fotoInvalida = Boolean(error);
            if (errorFoto) { errorFoto.textContent = error; errorFoto.hidden = !error; }
            if (error) { foto.value = ""; }
        }, true);
        if (form) form.addEventListener("reset", function () { fotoInvalida = false; if (errorFoto) { errorFoto.hidden = true; errorFoto.textContent = ""; } });
    }
    if (foto && foto.hasAttribute("data-avatar-editor")) {
        var dialogo = document.getElementById("perfil-photo-dialog"), lienzo = document.getElementById("perfil-photo-canvas");
        var zoom = document.getElementById("perfil-photo-zoom"), posX = document.getElementById("perfil-photo-x"), posY = document.getElementById("perfil-photo-y");
        var borrar = document.getElementById("perfil-avatar-clear"), quitar = document.getElementById("perfil-avatar-remove");
        var estado = document.getElementById("perfil-avatar-status"), errorDialogo = document.getElementById("perfil-photo-dialog-error");
        var aplicar = document.getElementById("perfil-photo-apply"), imagen = new Image(), confirmado = null, lectura = 0;
        var original = document.getElementById("avatar-preview").cloneNode(true);
        function mostrarError(mensaje) { fotoInvalida = Boolean(mensaje); errorFoto.textContent = mensaje; errorFoto.hidden = !mensaje; }
        function asignarArchivo(archivo) {
            var transferencia = new DataTransfer();
            if (archivo) transferencia.items.add(archivo);
            foto.files = transferencia.files;
        }
        function restaurarArchivo() { try { asignarArchivo(confirmado); } catch (_) { foto.value = ""; } }
        function vista(src) {
            var anterior = document.getElementById("avatar-preview"), nuevo;
            if (src) { nuevo = document.createElement("img"); nuevo.src = src; nuevo.alt = ""; nuevo.className = "settings-avatar-img"; }
            else { nuevo = document.createElement("div"); nuevo.className = "settings-avatar-placeholder lg"; nuevo.textContent = foto.dataset.iniciales; }
            nuevo.id = "avatar-preview"; anterior.replaceWith(nuevo);
        }
        function dibujar() {
            if (!imagen.naturalWidth) return;
            var lado = lienzo.width, escala = Math.max(lado / imagen.naturalWidth, lado / imagen.naturalHeight) * Number(zoom.value) / 100;
            var ancho = imagen.naturalWidth * escala, alto = imagen.naturalHeight * escala;
            var x = (lado - ancho) / 2 + (ancho - lado) / 2 * Number(posX.value) / 100;
            var y = (lado - alto) / 2 + (alto - lado) / 2 * Number(posY.value) / 100;
            var ctx = lienzo.getContext("2d"); ctx.clearRect(0, 0, lado, lado); ctx.drawImage(imagen, x, y, ancho, alto);
            document.getElementById("perfil-photo-zoom-value").textContent = zoom.value + "%";
        }
        [zoom, posX, posY].forEach(function (control) { control.addEventListener("input", dibujar); });
        foto.addEventListener("change", function () {
            var archivo = foto.files && foto.files[0]; if (!archivo) return;
            var error = !/^image\/(jpeg|png|gif|webp)$/i.test(archivo.type) ? "Selecciona una imagen JPG, PNG, GIF o WebP." : archivo.size > 2 * 1024 * 1024 ? "La foto no debe pesar más de 2 MB." : "";
            if (error) { restaurarArchivo(); mostrarError(error); return; }
            mostrarError(""); var actual = ++lectura, lector = new FileReader();
            lector.onload = function () {
                if (actual !== lectura) return;
                imagen.onload = function () { if (actual !== lectura) return; zoom.value = 100; posX.value = posY.value = 0; errorDialogo.hidden = true; dibujar(); dialogo.showModal(); };
                imagen.onerror = function () { restaurarArchivo(); mostrarError("No se pudo abrir la imagen seleccionada."); };
                imagen.src = lector.result;
            };
            lector.onerror = function () { restaurarArchivo(); mostrarError("No se pudo leer la imagen seleccionada."); };
            lector.readAsDataURL(archivo);
        });
        dialogo.addEventListener("close", function () { restaurarArchivo(); });
        dialogo.querySelectorAll("[data-photo-cancel]").forEach(function (boton) { boton.addEventListener("click", function () { dialogo.close(); }); });
        aplicar.addEventListener("click", function () {
            aplicar.disabled = true;
            lienzo.toBlob(function (blob) {
                aplicar.disabled = false; if (!dialogo.open) return;
                if (!blob) { errorDialogo.textContent = "No se pudo preparar la imagen. Inténtalo de nuevo."; errorDialogo.hidden = false; return; }
                try { var archivo = new File([blob], "foto-perfil.png", { type: "image/png" }); asignarArchivo(archivo); confirmado = archivo; }
                catch (_) { errorDialogo.textContent = "Tu navegador no permite preparar la foto. Prueba con otro navegador."; errorDialogo.hidden = false; return; }
                borrar.checked = false; quitar.hidden = false; vista(lienzo.toDataURL("image/png")); estado.textContent = "Foto lista. Guarda los cambios para aplicarla."; mostrarError(""); dialogo.close();
            }, "image/png");
        });
        quitar.addEventListener("click", function () { lectura++; confirmado = null; foto.value = ""; borrar.checked = true; quitar.hidden = true; vista(""); estado.textContent = "La foto se eliminará al guardar los cambios."; mostrarError(""); });
        if (form) form.addEventListener("reset", function () { lectura++; confirmado = null; mostrarError(""); estado.textContent = ""; quitar.hidden = foto.dataset.tieneAvatar !== "1"; var actual = document.getElementById("avatar-preview"); actual.replaceWith(original.cloneNode(true)); });
    }
    pagina.querySelectorAll("[data-toggle-password]").forEach(function (boton) {
        boton.addEventListener("click", function () {
            var campo = document.getElementById(boton.dataset.togglePassword);
            if (!campo) return;
            var visible = campo.type === "password";
            campo.type = visible ? "text" : "password";
            boton.setAttribute("aria-pressed", String(visible));
            boton.setAttribute("aria-label", (visible ? "Ocultar" : "Mostrar") + " contraseña");
        });
    });
    if (!form) return;
    function firma() {
        var datos = new FormData(form);
        return Array.from(datos.entries()).map(function (entrada) {
            var valor = entrada[1];
            return entrada[0] + "=" + (valor instanceof File ? valor.name + ":" + valor.size : valor);
        }).join("&");
    }
    var inicial = firma();
    form.addEventListener("reset", function () { setTimeout(function () { inicial = firma(); }, 0); });
    form.addEventListener("submit", function (evento) { if (fotoInvalida) { evento.preventDefault(); if (errorFoto) errorFoto.hidden = false; return; } inicial = firma(); });
    pagina.addEventListener("click", function (evento) {
        var enlace = evento.target.closest("a[href]");
        if (!enlace || firma() === inicial || enlace.hasAttribute("download") || enlace.target === "_blank") return;
        var panel = pagina.querySelector('[data-settings-panel="perfil"]');
        if (!panel || !panel.classList.contains("active")) return;
        var destino = enlace.getAttribute("href");
        if (!destino || destino === "#perfil") return;
        evento.preventDefault(); evento.stopImmediatePropagation();
        if (!window.DoggerConfirma) return;
        window.DoggerConfirma("Tienes cambios sin guardar en tu perfil. Si continúas, se perderán.", function () {
            form.reset();
            if (destino.charAt(0) === "#") location.hash = destino;
            else location.href = enlace.href;
        }, "Descartar cambios", { titulo:"¿Descartar cambios?", icono:"#i-alert" });
    }, true);
})();
