/**
 * ==============================================================================
 * APLICACIÓN CLIENTE FRONTEND: ESTUDIO DE VOZ PREAL (PReal.frontend.aplicacion.js)
 * ==============================================================================
 * Controla la interacción del usuario, comunicación asíncrona con el backend,
 * reproducción de audio, extracción de documentos (PDF, TXT, MD) y gestión de voces.
 */

// URL base de la API backend (se adapta si se sirve desde el mismo host o en local)
const URL_BASE_API = window.location.origin.includes("http") && !window.location.origin.includes("null")
  ? `${window.location.origin}/api`
  : "http://127.0.0.1:8000/api";

// Estado de la aplicación
const estadoAplicacion = {
  vocesDisponibles: [],
  idVozSeleccionada: null,
  audioSintetizadoActual: null,
};

// ─────────────────────────────────────────────────────────────────────────────
// GESTIÓN DE PESTAÑAS
// ─────────────────────────────────────────────────────────────────────────────

function cambiarPestana(nombrePestana) {
  const pestanas = ["sintesis", "clonar", "biblioteca"];

  pestanas.forEach((pestana) => {
    const boton = document.getElementById(`btn-pestana-${pestana}`);
    const seccion = document.getElementById(`seccion-${pestana}`);

    if (pestana === nombrePestana) {
      boton?.classList.add("activa");
      seccion?.classList.add("activa");
    } else {
      boton?.classList.remove("activa");
      seccion?.classList.remove("activa");
    }
  });

  if (nombrePestana === "biblioteca" || nombrePestana === "sintesis") {
    cargarCatalogoVoces();
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// NOTIFICACIONES TOAST
// ─────────────────────────────────────────────────────────────────────────────

function mostrarMensaje(texto, tipo = "exito") {
  const toast = document.getElementById("notificacion-flotante");
  if (!toast) return;

  toast.textContent = texto;
  toast.className = `notificacion-toast ${tipo}`;
  toast.classList.remove("oculto");

  setTimeout(() => {
    toast.classList.add("oculto");
  }, 4000);
}

// ─────────────────────────────────────────────────────────────────────────────
// PROCESAMIENTO Y EXTRACCIÓN DE DOCUMENTOS (PDF, TXT, MD)
// ─────────────────────────────────────────────────────────────────────────────

async function procesarArchivoDocumento(idInputArchivo, idAreaTexto, idSelectFormato) {
  const inputArchivo = document.getElementById(idInputArchivo);
  const areaTexto = document.getElementById(idAreaTexto);
  const selectFormato = document.getElementById(idSelectFormato);
  const formatoDeseado = selectFormato ? selectFormato.value : "markdown";

  if (!inputArchivo?.files || !inputArchivo.files[0]) return;

  const archivo = inputArchivo.files[0];
  const formularioDatos = new FormData();
  formularioDatos.append("documento", archivo);
  formularioDatos.append("formato_salida", formatoDeseado);

  const textoPrevioPlaceholder = areaTexto.placeholder;
  areaTexto.placeholder = "Extrayendo y estructurando texto desde documento...";

  try {
    const respuesta = await fetch(`${URL_BASE_API}/transcripcion/subir-documento`, {
      method: "POST",
      body: formularioDatos,
    });

    if (respuesta.ok) {
      const datos = await respuesta.json();
      areaTexto.value = datos.texto;
      actualizarContadorTexto(areaTexto.id, "contador-caracteres-sintesis");
      mostrarMensaje(
        `¡Documento '${datos.nombre_archivo}' cargado (${datos.caracteres} caracteres en formato ${datos.formato_salida})!`,
        "exito"
      );
    } else {
      const error = await respuesta.json();
      mostrarMensaje(`Error en documento: ${error.detail}`, "error");
    }
  } catch (errorConexion) {
    mostrarMensaje("No se pudo conectar con el servidor para extraer el documento.", "error");
  } finally {
    areaTexto.placeholder = textoPrevioPlaceholder;
    inputArchivo.value = "";
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// CATÁLOGO Y GESTIÓN DE VOCES (BIBLIOTECA)
// ─────────────────────────────────────────────────────────────────────────────

async function cargarCatalogoVoces() {
  const selectorVoz = document.getElementById("selector-voz-sintesis");
  const contenedorBiblioteca = document.getElementById("cuadricula-voces");
  const contadorTotal = document.getElementById("contador-voces-total");
  const indicadorEstado = document.getElementById("texto-estado");
  const puntoEstado = document.querySelector(".punto-conexion");

  try {
    const respuesta = await fetch(`${URL_BASE_API}/voces`);
    if (!respuesta.ok) throw new Error("Fallo al obtener voces");

    const listaVoces = await respuesta.json();
    estadoAplicacion.vocesDisponibles = listaVoces;

    // Actualizar indicador de conexión
    indicadorEstado.textContent = "API Conectada";
    puntoEstado.classList.add("activo");

    if (contadorTotal) {
      contadorTotal.textContent = `${listaVoces.length} ${listaVoces.length === 1 ? "voz" : "voces"}`;
    }

    // 1. Llenar el selector en la pestaña de síntesis
    if (selectorVoz) {
      const valorSeleccionadoPrevio = selectorVoz.value;
      selectorVoz.innerHTML = "";

      if (listaVoces.length === 0) {
        selectorVoz.innerHTML = '<option value="">No hay voces disponibles. Clona una primero.</option>';
      } else {
        listaVoces.forEach((voz) => {
          const opcion = document.createElement("option");
          opcion.value = voz.id;
          opcion.textContent = `${voz.nombre} [${voz.tipo}] - Idioma: ${voz.idioma || "Auto"}`;
          selectorVoz.appendChild(opcion);
        });

        if (valorSeleccionadoPrevio && listaVoces.some((v) => v.id === valorSeleccionadoPrevio)) {
          selectorVoz.value = valorSeleccionadoPrevio;
        }
      }
    }

    // 2. Renderizar tarjetas en la pestaña biblioteca
    if (contenedorBiblioteca) {
      contenedorBiblioteca.innerHTML = "";

      if (listaVoces.length === 0) {
        contenedorBiblioteca.innerHTML = `
          <div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: var(--color-texto-atenuado);">
            <p>No tienes voces guardadas todavía.</p>
            <p style="margin-top: 0.5rem; font-size: 0.9rem;">Dirígete a la pestaña <strong>2. Clonar Voz</strong> para registrar tu primer perfil.</p>
          </div>
        `;
        return;
      }

      listaVoces.forEach((voz) => {
        const tarjeta = document.createElement("div");
        tarjeta.className = "tarjeta-voz";

        const textoMuestra = voz.texto_referencia ? `"${voz.texto_referencia}"` : "Sin transcripción almacenada";

        tarjeta.innerHTML = `
          <div class="cabecera-tarjeta">
            <h3>${voz.nombre}</h3>
            <span class="etiqueta-badge">${voz.idioma || "Auto"}</span>
          </div>
          <p>${textoMuestra}</p>
          <div style="font-size: 0.78rem; color: var(--color-texto-atenuado);">
            <span>Tipo: ${voz.tipo}</span> | <span>ID: ${voz.id}</span>
          </div>
          <audio controls src="${URL_BASE_API}/voces/${voz.id}/audio" class="reproductor-personalizado"></audio>
          <div class="acciones-tarjeta">
            <button class="boton-accion-secundaria" onclick="seleccionarVozParaSintesis('${voz.id}')">
              🎙️ Usar para Sintetizar
            </button>
            <button class="boton-eliminar-voz" onclick="solicitarEliminarVoz('${voz.id}', '${voz.nombre}')">
              🗑️ Eliminar
            </button>
          </div>
        `;
        contenedorBiblioteca.appendChild(tarjeta);
      });
    }
  } catch (error) {
    indicadorEstado.textContent = "Sin conexión con API";
    puntoEstado.classList.remove("activo");
  }
}

function seleccionarVozParaSintesis(idVoz) {
  cambiarPestana("sintesis");
  const selector = document.getElementById("selector-voz-sintesis");
  if (selector) {
    selector.value = idVoz;
  }
  mostrarMensaje("Voz seleccionada para síntesis.");
}

// ─────────────────────────────────────────────────────────────────────────────
// ACCIONES DE CLONACIÓN Y GUARDADO DE VOZ
// ─────────────────────────────────────────────────────────────────────────────

async function solicitarClonacionYGuardado() {
  const campoNombre = document.getElementById("campo-nombre-clon");
  const inputAudio = document.getElementById("campo-audio-clon");
  const areaTextoRef = document.getElementById("area-texto-referencia");
  const campoIdioma = document.getElementById("campo-idioma-clon");
  const campoEstilo = document.getElementById("campo-estilo-clon");
  const botonGuardar = document.getElementById("btn-guardar-clon");

  const nombre = campoNombre?.value.trim();
  const audioArchivo = inputAudio?.files ? inputAudio.files[0] : null;
  const textoRef = areaTextoRef?.value.trim() || "";
  const idioma = campoIdioma?.value.trim() || "Auto";
  const estilo = campoEstilo?.value.trim() || "";

  if (!nombre) {
    mostrarMensaje("Por favor escribe un nombre para la voz.", "error");
    campoNombre?.focus();
    return;
  }

  if (!audioArchivo) {
    mostrarMensaje("Selecciona un archivo de audio para clonar la voz.", "error");
    return;
  }

  const formulario = new FormData();
  formulario.append("nombre", nombre);
  formulario.append("audio", audioArchivo);
  formulario.append("texto_referencia", textoRef);
  formulario.append("idioma", idioma);
  formulario.append("instrucciones", estilo);

  botonGuardar.disabled = true;
  botonGuardar.innerHTML = "⏳ Procesando y guardando voz...";

  try {
    const respuesta = await fetch(`${URL_BASE_API}/voces`, {
      method: "POST",
      body: formulario,
    });

    if (respuesta.ok) {
      const vozCreada = await respuesta.json();
      mostrarMensaje(`¡Voz '${vozCreada.nombre}' guardada con éxito!`, "exito");

      // Limpiar formulario
      campoNombre.value = "";
      inputAudio.value = "";
      areaTextoRef.value = "";
      document.getElementById("texto-archivo-audio").textContent = "Haz clic o arrastra un archivo de audio aquí";

      await cargarCatalogoVoces();
      seleccionarVozParaSintesis(vozCreada.id);
    } else {
      const error = await respuesta.json();
      mostrarMensaje(`Error al guardar: ${error.detail}`, "error");
    }
  } catch (err) {
    mostrarMensaje("Error al comunicar con el servidor API.", "error");
  } finally {
    botonGuardar.disabled = false;
    botonGuardar.innerHTML = '<span class="icono-boton">💾</span> Clonar y Guardar en la Biblioteca';
  }
}

async function solicitarEliminarVoz(idVoz, nombreVoz) {
  const confirmacion = confirm(`¿Estás seguro de que deseas eliminar permanentemente la voz '${nombreVoz}'?`);
  if (!confirmacion) return;

  try {
    const respuesta = await fetch(`${URL_BASE_API}/voces/${idVoz}`, {
      method: "DELETE",
    });

    if (respuesta.ok) {
      mostrarMensaje(`Voz '${nombreVoz}' eliminada correctamente.`);
      cargarCatalogoVoces();
    } else {
      const error = await respuesta.json();
      mostrarMensaje(`Error al eliminar: ${error.detail}`, "error");
    }
  } catch (err) {
    mostrarMensaje("Error de conexión al eliminar la voz.", "error");
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ACCIONES DE SÍNTESIS DE VOZ
// ─────────────────────────────────────────────────────────────────────────────

async function solicitarSintesis() {
  const selectorVoz = document.getElementById("selector-voz-sintesis");
  const areaTexto = document.getElementById("area-texto-sintesis");
  const sliderVelocidad = document.getElementById("control-velocidad");
  const inputSemilla = document.getElementById("control-semilla");
  const botonSintetizar = document.getElementById("btn-sintetizar");

  const idPerfil = selectorVoz?.value;
  const texto = areaTexto?.value.trim();
  const velocidad = parseFloat(sliderVelocidad?.value || "1.0");
  const semilla = inputSemilla?.value ? parseInt(inputSemilla.value) : null;

  if (!idPerfil) {
    mostrarMensaje("Selecciona una voz antes de sintetizar.", "error");
    return;
  }

  if (!texto) {
    mostrarMensaje("Introduce o carga el texto a sintetizar.", "error");
    areaTexto?.focus();
    return;
  }

  botonSintetizar.disabled = true;
  botonSintetizar.innerHTML = "⏳ Sintetizando audio...";

  const peticionCuerpo = {
    id_perfil: idPerfil,
    texto: texto,
    velocidad: velocidad,
    semilla: semilla,
  };

  try {
    const respuesta = await fetch(`${URL_BASE_API}/sintetizar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(peticionCuerpo),
    });

    if (respuesta.ok) {
      const resultado = await respuesta.json();
      const nombreArchivo = resultado.ruta_archivo_audio.split(/[\\/]/).pop();
      const urlAudio = `${URL_BASE_API}/audio-salida/${nombreArchivo}`;

      // Actualizar reproductor
      const panelResultado = document.getElementById("contenedor-resultado");
      const reproductor = document.getElementById("reproductor-audio");
      const enlaceDescarga = document.getElementById("enlace-descarga-audio");
      const etiquetaDuracion = document.getElementById("etiqueta-duracion");

      reproductor.src = urlAudio;
      enlaceDescarga.href = urlAudio;
      etiquetaDuracion.textContent = `${resultado.duracion_segundos.toFixed(2)} s`;
      panelResultado.classList.remove("oculto");

      reproductor.play();
      mostrarMensaje("¡Audio sintetizado con éxito!", "exito");
    } else {
      const error = await respuesta.json();
      mostrarMensaje(`Error de síntesis: ${error.detail}`, "error");
    }
  } catch (err) {
    mostrarMensaje("Error de conexión con el motor de síntesis.", "error");
  } finally {
    botonSintetizar.disabled = false;
    botonSintetizar.innerHTML = '<span class="icono-boton">▶</span> Sintetizar Voz';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// INICIALIZACIÓN Y EVENTOS
// ─────────────────────────────────────────────────────────────────────────────

function actualizarContadorTexto(idAreaTexto, idContador) {
  const area = document.getElementById(idAreaTexto);
  const contador = document.getElementById(idContador);
  if (area && contador) {
    contador.textContent = `${area.value.length} caracteres`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // Cargar catálogo inicial
  cargarCatalogoVoces();

  // Control deslizante de velocidad
  const sliderVelocidad = document.getElementById("control-velocidad");
  const etiquetaVelocidad = document.getElementById("valor-velocidad");
  sliderVelocidad?.addEventListener("input", (e) => {
    if (etiquetaVelocidad) etiquetaVelocidad.textContent = parseFloat(e.target.value).toFixed(2);
  });

  // Contador de caracteres en síntesis
  const areaSintesis = document.getElementById("area-texto-sintesis");
  areaSintesis?.addEventListener("input", () => {
    actualizarContadorTexto("area-texto-sintesis", "contador-caracteres-sintesis");
  });

  // Subida de documento en pestaña síntesis
  const entradaDocSintesis = document.getElementById("entrada-documento-sintesis");
  entradaDocSintesis?.addEventListener("change", () => {
    procesarArchivoDocumento("entrada-documento-sintesis", "area-texto-sintesis", "formato-documento-sintesis");
  });

  // Subida de documento en pestaña clonación
  const entradaDocClon = document.getElementById("entrada-documento-clon");
  entradaDocClon?.addEventListener("change", () => {
    procesarArchivoDocumento("entrada-documento-clon", "area-texto-referencia", "formato-documento-clon");
  });

  // Zona de arrastre de audio
  const zonaArrastre = document.getElementById("zona-arrastre-audio");
  const inputAudio = document.getElementById("campo-audio-clon");
  const textoArchivo = document.getElementById("texto-archivo-audio");

  inputAudio?.addEventListener("change", () => {
    if (inputAudio.files && inputAudio.files[0]) {
      textoArchivo.textContent = `Archivo seleccionado: ${inputAudio.files[0].name} (${(inputAudio.files[0].size / 1024).toFixed(1)} KB)`;
    }
  });

  zonaArrastre?.addEventListener("dragover", (e) => {
    e.preventDefault();
    zonaArrastre.classList.add("arrastrando");
  });

  zonaArrastre?.addEventListener("dragleave", () => {
    zonaArrastre.classList.remove("arrastrando");
  });

  zonaArrastre?.addEventListener("drop", (e) => {
    e.preventDefault();
    zonaArrastre.classList.remove("arrastrando");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      inputAudio.files = e.dataTransfer.files;
      textoArchivo.textContent = `Archivo seleccionado: ${e.dataTransfer.files[0].name}`;
    }
  });
});
