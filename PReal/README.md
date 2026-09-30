# Proyecto `PReal`: Arquitectura Modular de Estudio de Voz

Este proyecto implementa la lógica completa para **clonar una voz**, **almacenar perfiles vocales** y **sintetizar voz**, organizada en arquitectura desacoplada **Frontend / Backend**, con base de datos autogestionada en su primera ejecución y un archivo `.gitignore` optimizado.

Todos los nombres de ficheros, módulos, funciones, variables y constantes están rigurosamente definidos en **castellano**.

---

## 📁 Estructura del Proyecto

```text
PReal/
├── .gitignore                      # Reglas de exclusión de git (bases de datos, audios, temporales)
├── requirements.txt                # Dependencias Python necesarias
├── GUIA_INTERFAZ.md               # Guía exhaustiva de la interfaz y endpoints
├── README.md                       # Documentación principal del paquete
├── demostracion.py                 # Script de validación end-to-end
│
├── frontend/                       # INTERFAZ DE USUARIO (Separada e independiente)
│   ├── index.html                  # Estructura semántica HTML5 pura
│   ├── estilos.css                 # Diseño CSS Vanilla moderno (Dark theme, glassmorphism, responsive)
│   └── aplicacion.js               # Lógica cliente JS (gestión de pestañas, grabador, visor de audio, API)
│
└── backend/                        # NÚCLEO DE SERVICIOS Y PERSISTENCIA
    ├── __init__.py                 # Exportación unificada del backend
    ├── base_datos.py               # Auto-inicialización de BD SQLite y carpetas en primera ejecución
    ├── almacenar_voz.py            # Persistencia de perfiles vocales, tomas bloqueadas y limpieza
    ├── clonar_voz.py               # Extracción acústica, transcripción y selección de fragmentos
    ├── usar_voz.py                 # Motor de síntesis y condicionamiento acústico
    ├── procesar_documentos.py      # Extracción y conversión de documentos PDF (a MD/TXT), TXT y Markdown
    └── servidor_api.py             # Servidor FastAPI REST con servicio del frontend integrado
```

---

## 🗄️ Base de Datos con Creación Automática (`backend/base_datos.py`)

El backend incorpora un mecanismo de detección de primera ejecución:
- Si el directorio `datos/` o la base de datos `datos/voces.db` no existen al arrancar la API o ejecutar cualquier script, **se crean automáticamente** con:
  - Estructura de carpetas: `datos/`, `datos/voces/`, `datos/salidas/`.
  - Tablas SQLite: `voice_profiles` (perfiles de voz con metadatos y muestras) y `generation_history` (historial de síntesis).
  - Optimización de rendimiento activa: modo WAL (`PRAGMA journal_mode = WAL`) y verificación de claves foráneas.

---

## 🎨 Frontend Modular (`frontend/`)

La interfaz está desacoplada en tres ficheros según los estándares web modernos:
1. **[`index.html`](file:///d:/Users/alumno/Desktop/EstudioDeVoz/PReal/frontend/index.html)**:
   - Panel de 3 pestañas: *1. Clonar Voz*, *2. Transcribir Documento* y *3. Síntesis / Usar Voz*.
   - Drag & drop de archivos de audio (`.wav`, `.mp3`, etc.) y documentos (`.pdf`, `.txt`, `.md`).
   - Opciones para convertir PDFs a Markdown formateado o texto plano.
2. **[`estilos.css`](file:///d:/Users/alumno/Desktop/EstudioDeVoz/PReal/frontend/estilos.css)**:
   - Paleta cromática profunda, efectos de cristal translúcido (*glassmorphism*), tipografía limpia y controles interactivos con transiciones suaves.
3. **[`aplicacion.js`](file:///d:/Users/alumno/Desktop/EstudioDeVoz/PReal/frontend/aplicacion.js)**:
   - Manejo reactivo del estado sin librerías externas pesadas.
   - Peticiones asíncronas vía `fetch` al backend REST.
   - Sistema de notificaciones toast y reproductor de audio con descarga directa.

---

## 🚀 Puesta en Marcha

### 1. Instalación de dependencias
```bash
pip install -r requirements.txt
```

### 2. Ejecutar el Servidor Backend y Frontend
```bash
python backend/servidor_api.py
```
O con Uvicorn:
```bash
uvicorn backend.servidor_api:aplicacion --reload --port 8000
```
Abre en tu navegador: **`http://127.0.0.1:8000`** para interactuar con la interfaz gráfica conectada directamente a la API.

### 3. Ejecutar Pruebas Automatizadas de Demostración
```bash
python demostracion.py
```
