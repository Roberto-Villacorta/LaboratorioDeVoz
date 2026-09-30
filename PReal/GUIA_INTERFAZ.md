# Guía para la Creación de la Interfaz de Estudio de Voz (PReal)

Esta guía describe paso a paso la arquitectura, los componentes y la implementación de una **interfaz gráfica moderna** conectada directamente con los módulos de **`PReal`**:
1. 🎙️ **Clonar la voz** (`clonar_voz.py`)
2. 💾 **Almacenar la voz** (`almacenar_voz.py`)
3. 🔊 **Usar la voz** (`usar_voz.py`)

---

## 1. Arquitectura de la Interfaz

Para conectar el frontend con la lógica de `PReal`, la solución más modular y escalable consta de dos capas:

```
┌────────────────────────────────────────────────────────┐
│               Frontend de Usuario                      │
│   (HTML5 + Vanilla CSS + JavaScript o Electron/React)  │
└──────────────────────────┬─────────────────────────────┘
                           │ HTTP / JSON / FormData
                           ▼
┌────────────────────────────────────────────────────────┐
│             API Backend en Castellano                  │
│       (FastAPI / endpoints REST con CORS)              │
└──────────────────────────┬─────────────────────────────┘
                           │ Llamadas a funciones
                           ▼
┌────────────────────────────────────────────────────────┐
│                   Paquete PReal                        │
│   ├── clonar_voz.py    (Extracción y recorte)          │
│   ├── almacenar_voz.py (SQLite y persistencia en disco)│
│   └── usar_voz.py      (Resolución y síntesis TTS)     │
└────────────────────────────────────────────────────────┘
```

---

## 2. Pantallas y Componentes Necesarios

La interfaz debe estructurarse en **3 secciones o pestañas principales**:

### Pestaña 1: Clonar Voz (Laboratorio de Clonación)
* **Entrada de Audio:**
  * Zona de arrastrar y soltar archivos (`.wav`, `.mp3`, `.m4a`, etc.).
  * Opción de grabación directa con el micrófono (utilizando `MediaRecorder`).
* **Visualizador de Métricas:**
  * Indicador de duración del audio (alerta visual si es menor a `5.0s` o mayor a `15.0s`).
  * Indicador de calidad y detección de canales (mono/estéreo).
* **Alineación de Texto y Subida de Documentos (PDF, TXT, MD):**
  * Campo de texto para la transcripción fonética de referencia.
  * **Botón de Carga de Documentos:** Permite subir un archivo `.pdf`, `.txt` o `.md`.
  * **Selector de Formato:** El usuario puede elegir entre convertir a `Markdown` (con títulos estructurados `#`, `##` y párrafos limpios) o `Texto plano` (`txt`).
  * Botón para invocar la transcripción acústica automática (`transcribir_audio_referencia`) si no se dispone de documento.
* **Acción:**
  * Botón para pasar a almacenar la voz como nuevo perfil.

### Pestaña 2: Biblioteca de Voces (Almacenar y Gestionar)
* **Cuadrícula de Perfiles:**
  * Tarjetas de perfil con avatar/retrato, nombre de la voz, idioma y etiquetas de estilo.
  * Botón de reproducción de la muestra original de audio.
  * Indicador de estado de fijado (`bloqueado` / `desbloqueado`).
* **Acciones de Gestión:**
  * **Crear nuevo perfil:** Modal para asignar nombre, descripción, idioma, archivo de audio y documento de transcripción opcional.
  * **Editar perfil:** Modificar nombre, personalidad o instrucciones de entonación.
  * **Fijar toma:** Botón para anclar una toma generada al perfil (`bloquear_toma_voz`).
  * **Eliminar perfil:** Confirmación y borrado seguro sin archivos huérfanos.

### Pestaña 3: Estudio de Síntesis (Usar la Voz)
* **Panel de Configuración de Voz:**
  * Selector desplegable de voces disponibles (cargadas dinámicamente desde `listar_perfiles_voz`).
  * Ajustes acústicos:
    * Control deslizante de **Velocidad** ($0.5\times$ a $2.0\times$).
    * Control deslizante de **Escala de Guía / Expresividad** ($1.0$ a $5.0$).
    * Entrada de **Semilla (Seed)** para reproducibilidad.
* **Caja de Texto a Sintetizar y Carga de Guiones:**
  * Entrada multilínea de texto con normalización automática Unicode NFC.
  * **Botón "📄 Cargar PDF / TXT / MD":** Extrae guiones o libros directamente desde archivos PDF, formateando capítulos como encabezados Markdown y rellenando el área de texto instantáneamente.
* **Reproductor y Exportación:**
  * Botón principal **"Sintetizar Audio"**.
  * Reproductor de audio HTML5 con visualizador de forma de onda.
  * Botón para **Descargar WAV** y botón **"Fijar como muestra oficial de la voz"**.

---

## 3. Implementación del Servidor Backend (`servidor_api.py`)

Crea un archivo llamado `servidor_api.py` en la carpeta `PReal/` o en la raíz para exponer la lógica de `PReal` vía HTTP:

```python
import os
import tempfile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from PReal.clonar_voz import preparar_clon_desde_archivo
from PReal.almacenar_voz import (
    guardar_perfil_voz,
    listar_perfiles_voz,
    obtener_perfil_voz,
    actualizar_perfil_voz,
    eliminar_perfil_voz,
    bloquear_toma_voz,
    desbloquear_toma_voz,
    resolver_ruta_segura_voz,
    DIRECTORIO_VOCES_PREDETERMINADO,
)
from PReal.usar_voz import generar_audio_desde_perfil

app = FastAPI(title="API Estudio de Voz PReal")

# Permitir CORS para desarrollo local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 1. RUTAS DE CLONACIÓN ──
@app.post("/api/clonar/analizar")
async def analizar_audio_clon(archivo: UploadFile = File(...), texto: str = Form("")):
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(archivo.filename or ".wav")[1]) as tmp:
        tmp.write(await archivo.read())
        ruta_temporal = tmp.name

    try:
        resultado = preparar_clon_desde_archivo(ruta_temporal, texto_referencia_opcional=texto)
        return resultado
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    finally:
        if os.path.exists(ruta_temporal):
            os.remove(ruta_temporal)

# ── 2. RUTAS DE ALMACENAMIENTO ──
@app.get("/api/voces")
def obtener_voces():
    perfiles = listar_perfiles_voz()
    return [p.a_diccionario() for p in perfiles]

@app.post("/api/voces")
async def registrar_voz(
    nombre: str = Form(...),
    audio: UploadFile = File(...),
    texto_referencia: str = Form(""),
    idioma: str = Form("Auto"),
    instrucciones: str = Form(""),
):
    contenido_audio = await audio.read()
    perfil = guardar_perfil_voz(
        nombre=nombre,
        datos_audio=contenido_audio,
        nombre_archivo_audio=audio.filename or "voz.wav",
        texto_referencia=texto_referencia,
        idioma=idioma,
        instrucciones=instrucciones,
    )
    return perfil.a_diccionario()

@app.delete("/api/voces/{id_perfil}")
def borrar_voz(id_perfil: str):
    if not eliminar_perfil_voz(id_perfil):
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    return {"mensaje": "Perfil eliminado con éxito", "id": id_perfil}

@app.get("/api/voces/{id_perfil}/audio")
def descargar_audio_voz(id_perfil: str):
    perfil = obtener_perfil_voz(id_perfil)
    if not perfil or not perfil.ruta_audio_referencia:
        raise HTTPException(status_code=404, detail="Audio no encontrado")
    ruta = resolver_ruta_segura_voz(perfil.ruta_audio_referencia)
    if not ruta or not os.path.isfile(ruta):
        raise HTTPException(status_code=404, detail="Archivo físico inexistente")
    return FileResponse(ruta, media_type="audio/wav")

# ── 3. RUTAS DE USO Y SÍNTESIS ──
class PeticionSintesis(BaseModel):
    id_perfil: str
    texto: str
    velocidad: float = 1.0
    semilla: Optional[int] = None
    idioma: Optional[str] = None

@app.post("/api/sintetizar")
def sintetizar(peticion: PeticionSintesis):
    try:
        resultado = generar_audio_desde_perfil(
            id_perfil=peticion.id_perfil,
            texto=peticion.texto,
            velocidad=peticion.velocidad,
            semilla=peticion.semilla,
            idioma=peticion.idioma,
        )
        return resultado.a_diccionario()
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

@app.get("/api/audio-salida/{nombre_archivo}")
def descargar_audio_generado(nombre_archivo: str):
    from PReal.almacenar_voz import DIRECTORIO_SALIDAS_PREDETERMINADO
    ruta = os.path.join(DIRECTORIO_SALIDAS_PREDETERMINADO, nombre_archivo)
    if not os.path.isfile(ruta):
        raise HTTPException(status_code=404, detail="Audio generado no encontrado")
    return FileResponse(ruta, media_type="audio/wav")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("servidor_api:app", host="127.0.0.1", port=8000, reload=True)
```

---

## 4. Código Completo de la Interfaz Web (`interfaz.html`)

Guarda este archivo como `interfaz.html`. Es un cliente completo en HTML5, CSS y JavaScript que se comunica con el servidor:

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Estudio de Voz PReal</title>
  <style>
    :root {
      --color-fondo: #0f172a;
      --color-panel: #1e293b;
      --color-borde: #334155;
      --color-primario: #6366f1;
      --color-primario-hover: #4f46e5;
      --color-texto: #f8fafc;
      --color-subtexto: #94a3b8;
      --color-exito: #10b981;
      --color-peligro: #ef4444;
      --radio-borde: 12px;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; font-family: system-ui, sans-serif; }
    body { background-color: var(--color-fondo); color: var(--color-texto); padding: 2rem; display: flex; justify-content: center; }
    .contenedor { width: 100%; max-width: 1000px; display: flex; flex-direction: column; gap: 1.5rem; }

    header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--color-borde); padding-bottom: 1rem; }
    h1 { font-size: 1.8rem; background: linear-gradient(135deg, #a5b4fc, #6366f1); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }

    /* Pestañas de navegación */
    .pestanas { display: flex; gap: 0.5rem; background: var(--color-panel); padding: 0.4rem; border-radius: var(--radio-borde); border: 1px solid var(--color-borde); }
    .pestana-btn { flex: 1; padding: 0.8rem; border: none; background: transparent; color: var(--color-subtexto); font-weight: 600; cursor: pointer; border-radius: 8px; transition: all 0.2s; }
    .pestana-btn.activa { background: var(--color-primario); color: #fff; }

    /* Tarjetas y secciones */
    .seccion { background: var(--color-panel); border: 1px solid var(--color-borde); border-radius: var(--radio-borde); padding: 1.5rem; display: none; flex-direction: column; gap: 1.2rem; }
    .seccion.activa { display: flex; }

    .grupo-campo { display: flex; flex-direction: column; gap: 0.4rem; }
    label { font-size: 0.9rem; color: var(--color-subtexto); font-weight: 500; }
    input, textarea, select { background: #0f172a; border: 1px solid var(--color-borde); border-radius: 8px; padding: 0.75rem; color: #fff; font-size: 1rem; }
    textarea { resize: vertical; min-height: 100px; }

    .btn-principal { background: var(--color-primario); color: white; border: none; padding: 0.9rem 1.5rem; border-radius: 8px; font-weight: 600; cursor: pointer; transition: background 0.2s; }
    .btn-principal:hover { background: var(--color-primario-hover); }

    /* Cuadrícula de voces */
    .cuadricula-voces { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }
    .tarjeta-voz { background: #0f172a; border: 1px solid var(--color-borde); border-radius: 8px; padding: 1rem; display: flex; flex-direction: column; gap: 0.6rem; position: relative; }
    .tarjeta-voz h3 { font-size: 1.1rem; }
    .tarjeta-voz p { font-size: 0.85rem; color: var(--color-subtexto); }
    .badge { display: inline-block; font-size: 0.75rem; padding: 0.2rem 0.6rem; border-radius: 999px; background: rgba(99, 102, 241, 0.2); color: #a5b4fc; }

    audio { width: 100%; margin-top: 0.5rem; }
  </style>
</head>
<body>
  <div class="contenedor">
    <header>
      <h1>🎙️ Estudio de Voz PReal</h1>
      <span class="badge" id="estado-conexion">Conectado a API local</span>
    </header>

    <nav class="pestanas">
      <button class="pestana-btn activa" onclick="mostrarPestana('sintesis')">1. Usar Voz (Síntesis)</button>
      <button class="pestana-btn" onclick="mostrarPestana('clonar')">2. Clonar Voz</button>
      <button class="pestana-btn" onclick="mostrarPestana('biblioteca')">3. Biblioteca de Voces</button>
    </nav>

    <!-- 1. PESTAÑA SÍNTESIS -->
    <section id="sec-sintesis" class="seccion activa">
      <h2>Generación de Voz</h2>
      <div class="grupo-campo">
        <label>Seleccionar Voz:</label>
        <select id="select-voz"><option value="">Cargando voces...</option></select>
      </div>
      <div class="grupo-campo">
        <label>Texto a Sintetizar:</label>
        <textarea id="texto-sintesis" placeholder="Escribe aquí el texto que deseas convertir en voz..."></textarea>
      </div>
      <div style="display: flex; gap: 1rem;">
        <div class="grupo-campo" style="flex: 1;">
          <label>Velocidad:</label>
          <input type="number" id="velocidad-sintesis" value="1.0" step="0.1" min="0.5" max="2.0">
        </div>
        <div class="grupo-campo" style="flex: 1;">
          <label>Semilla (Opcional):</label>
          <input type="number" id="semilla-sintesis" placeholder="Aleatoria">
        </div>
      </div>
      <button class="btn-principal" onclick="ejecutarSintesis()">🔊 Sintetizar Audio</button>

      <div id="resultado-sintesis" style="display: none; margin-top: 1rem; border-top: 1px solid var(--color-borde); padding-top: 1rem;">
        <h3>Resultado Generado:</h3>
        <audio id="reproductor-resultado" controls></audio>
      </div>
    </section>

    <!-- 2. PESTAÑA CLONAR -->
    <section id="sec-clonar" class="seccion">
      <h2>Clonar Nueva Voz</h2>
      <div class="grupo-campo">
        <label>Nombre de la Voz:</label>
        <input type="text" id="nombre-clon" placeholder="Ej: Narrador Español">
      </div>
      <div class="grupo-campo">
        <label>Archivo de Audio de Referencia (5 a 15 segundos recomendados):</label>
        <input type="file" id="archivo-clon" accept="audio/*">
      </div>
      <div class="grupo-campo">
        <label>Texto de la Referencia (Opcional - se transcribirá automáticamente si se omite):</label>
        <textarea id="texto-referencia-clon" placeholder="Texto exacto pronunciado en el audio..."></textarea>
      </div>
      <button class="btn-principal" onclick="guardarClon()">💾 Guardar y Crear Voz</button>
    </section>

    <!-- 3. PESTAÑA BIBLIOTECA -->
    <section id="sec-biblioteca" class="seccion">
      <h2>Voces Almacenadas</h2>
      <div class="cuadricula-voces" id="lista-voces">
        <!-- Renderizado dinámico -->
      </div>
    </section>
  </div>

  <script>
    const API_URL = "http://127.0.0.1:8000/api";

    function mostrarPestana(nombre) {
      document.querySelectorAll('.pestana-btn').forEach(b => b.classList.remove('activa'));
      document.querySelectorAll('.seccion').forEach(s => s.classList.remove('activa'));

      if (nombre === 'sintesis') {
        document.querySelector("button[onclick=\"mostrarPestana('sintesis')\"]").classList.add('activa');
        document.getElementById('sec-sintesis').classList.add('activa');
      } else if (nombre === 'clonar') {
        document.querySelector("button[onclick=\"mostrarPestana('clonar')\"]").classList.add('activa');
        document.getElementById('sec-clonar').classList.add('activa');
      } else {
        document.querySelector("button[onclick=\"mostrarPestana('biblioteca')\"]").classList.add('activa');
        document.getElementById('sec-biblioteca').classList.add('activa');
        cargarVoces();
      }
    }

    async function cargarVoces() {
      try {
        const res = await fetch(`${API_URL}/voces`);
        const voces = await res.json();

        // Actualizar selector
        const select = document.getElementById("select-voz");
        select.innerHTML = "";
        voces.forEach(v => {
          const opt = document.createElement("option");
          opt.value = v.id;
          opt.textContent = `${v.nombre} (${v.idioma || 'Auto'})`;
          select.appendChild(opt);
        });

        // Actualizar tarjetas en biblioteca
        const lista = document.getElementById("lista-voces");
        lista.innerHTML = "";
        voces.forEach(v => {
          const card = document.createElement("div");
          card.className = "tarjeta-voz";
          card.innerHTML = `
            <h3>${v.nombre}</h3>
            <p>${v.texto_referencia || 'Sin transcripción almacenada'}</p>
            <span class="badge">${v.tipo} | ${v.idioma}</span>
            <audio controls src="${API_URL}/voces/${v.id}/audio"></audio>
            <button style="background: var(--color-peligro); color: #fff; border: none; padding: 0.5rem; border-radius: 6px; cursor: pointer; margin-top: 0.5rem;" onclick="eliminarVoz('${v.id}')">Eliminar</button>
          `;
          lista.appendChild(card);
        });
      } catch (err) {
        console.error("Error al cargar voces:", err);
      }
    }

    async function guardarClon() {
      const nombre = document.getElementById("nombre-clon").value.trim();
      const archivoInput = document.getElementById("archivo-clon");
      const texto = document.getElementById("texto-referencia-clon").value.trim();

      if (!nombre || !archivoInput.files[0]) {
        alert("Por favor indica un nombre y selecciona un archivo de audio.");
        return;
      }

      const formData = new FormData();
      formData.append("nombre", nombre);
      formData.append("audio", archivoInput.files[0]);
      formData.append("texto_referencia", texto);

      const res = await fetch(`${API_URL}/voces`, { method: "POST", body: formData });
      if (res.ok) {
        alert("¡Voz guardada exitosamente!");
        document.getElementById("nombre-clon").value = "";
        archivoInput.value = "";
        mostrarPestana('sintesis');
        cargarVoces();
      } else {
        const error = await res.json();
        alert("Error al guardar: " + error.detail);
      }
    }

    async function ejecutarSintesis() {
      const idPerfil = document.getElementById("select-voz").value;
      const texto = document.getElementById("texto-sintesis").value.trim();
      const velocidad = parseFloat(document.getElementById("velocidad-sintesis").value) || 1.0;
      const semillaVal = document.getElementById("semilla-sintesis").value;
      const semilla = semillaVal ? parseInt(semillaVal) : null;

      if (!idPerfil || !texto) {
        alert("Selecciona una voz y escribe el texto a sintetizar.");
        return;
      }

      const peticion = { id_perfil: idPerfil, texto: texto, velocidad: velocidad, semilla: semilla };
      const res = await fetch(`${API_URL}/sintetizar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(peticion),
      });

      if (res.ok) {
        const datos = await res.json();
        const nombreArchivo = datos.ruta_archivo_audio.split(/[\\\\/]/).pop();
        const reproductor = document.getElementById("reproductor-resultado");
        reproductor.src = `${API_URL}/audio-salida/${nombreArchivo}`;
        document.getElementById("resultado-sintesis").style.display = "block";
        reproductor.play();
      } else {
        const error = await res.json();
        alert("Error al sintetizar: " + error.detail);
      }
    }

    async function eliminarVoz(id) {
      if (!confirm("¿Seguro que deseas eliminar esta voz?")) return;
      await fetch(`${API_URL}/voces/${id}`, { method: "DELETE" });
      cargarVoces();
    }

    window.onload = cargarVoces;
  </script>
</body>
</html>
```

---

## 5. Alternativa Rápida en Python con Gradio (`interfaz_gradio.py`)

Si deseas disponer de una interfaz gráfica inmediata sin necesidad de levantar servidor web por separado:

```python
import gradio as gr
from PReal.almacenar_voz import listar_perfiles_voz, guardar_perfil_voz
from PReal.usar_voz import generar_audio_desde_perfil

def obtener_opciones_voces():
    perfiles = listar_perfiles_voz()
    return [(f"{p.nombre} ({p.id})", p.id) for p in perfiles]

def clonar_y_guardar(nombre, audio_path, texto):
    if not audio_path:
        return "Debes subir un archivo de audio."
    with open(audio_path, "rb") as f:
        perfil = guardar_perfil_voz(nombre=nombre, datos_audio=f.read(), texto_referencia=texto or "")
    return f"Voz '{perfil.nombre}' guardada con ID: {perfil.id}"

def sintetizar(id_voz, texto, velocidad):
    resultado = generar_audio_desde_perfil(id_perfil=id_voz, texto=texto, velocidad=velocidad)
    return resultado.ruta_archivo_audio

with gr.Blocks(title="Estudio de Voz PReal") as interfaz:
    gr.Markdown("# 🎙️ Estudio de Voz PReal")
    
    with gr.Tab("1. Sintetizar con Voz"):
        selector_voz = gr.Dropdown(label="Seleccionar Voz", choices=obtener_opciones_voces())
        texto_entrada = gr.Textbox(label="Texto a Sintetizar", lines=3)
        slider_vel = gr.Slider(0.5, 2.0, value=1.0, label="Velocidad")
        btn_sintetizar = gr.Button("Sintetizar", variant="primary")
        audio_salida = gr.Audio(label="Audio Generado", type="filepath")
        btn_sintetizar.click(sintetizar, inputs=[selector_voz, texto_entrada, slider_vel], outputs=audio_salida)

    with gr.Tab("2. Clonar Nueva Voz"):
        input_nombre = gr.Textbox(label="Nombre de la Voz")
        input_audio = gr.Audio(label="Audio de Referencia", type="filepath")
        input_texto = gr.Textbox(label="Texto del Audio (Opcional)")
        btn_guardar = gr.Button("Guardar Voz")
        estado_guardado = gr.Label()
        btn_guardar.click(clonar_y_guardar, inputs=[input_nombre, input_audio, input_texto], outputs=estado_guardado)

if __name__ == "__main__":
    interfaz.launch()
```

---

## 6. Instrucciones de Ejecución

1. **Instalar Dependencias:**
   ```bash
   pip install -r PReal/requirements.txt
   ```
2. **Iniciar el Servidor Backend:**
   ```bash
   python PReal/servidor_api.py
   ```
3. **Abrir la Interfaz:**
   Abre el archivo `interfaz.html` directamente en el navegador (Google Chrome, Firefox o Edge).
