"""Servidor API REST para la Interfaz de Estudio de Voz (PReal.backend.servidor_api)
================================================================================
Conecta el frontend desacoplado con los módulos de clonación, almacenamiento,
extracción de documentos (PDF, TXT, MD) y síntesis de voz en castellano.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Asegurar importaciones
DIRECTORIO_ACTUAL = os.path.dirname(os.path.abspath(__file__))
DIRECTORIO_RAIZ = os.path.abspath(os.path.join(DIRECTORIO_ACTUAL, "..", ".."))
DIRECTORIO_PREAL = os.path.abspath(os.path.join(DIRECTORIO_ACTUAL, ".."))
if DIRECTORIO_RAIZ not in sys.path:
    sys.path.insert(0, DIRECTORIO_RAIZ)
if DIRECTORIO_PREAL not in sys.path:
    sys.path.insert(0, DIRECTORIO_PREAL)

try:
    from PReal.backend.base_datos import (
        DIRECTORIO_SALIDAS_PREDETERMINADO,
        DIRECTORIO_VOCES_PREDETERMINADO,
        RUTA_BASE_DATOS_PREDETERMINADA,
        asegurar_infraestructura_almacenamiento,
    )
    from PReal.backend.almacenar_voz import (
        actualizar_perfil_voz,
        bloquear_toma_voz,
        desbloquear_toma_voz,
        eliminar_perfil_voz,
        guardar_perfil_voz,
        listar_perfiles_voz,
        obtener_perfil_voz,
        resolver_ruta_segura_voz,
    )
    from PReal.backend.clonar_voz import preparar_clon_desde_archivo
    from PReal.backend.procesar_documentos import leer_documento_transcripcion
    from PReal.backend.usar_voz import generar_audio_desde_perfil
except ImportError:
    from base_datos import (
        DIRECTORIO_SALIDAS_PREDETERMINADO,
        DIRECTORIO_VOCES_PREDETERMINADO,
        RUTA_BASE_DATOS_PREDETERMINADA,
        asegurar_infraestructura_almacenamiento,
    )
    from almacenar_voz import (
        actualizar_perfil_voz,
        bloquear_toma_voz,
        desbloquear_toma_voz,
        eliminar_perfil_voz,
        guardar_perfil_voz,
        listar_perfiles_voz,
        obtener_perfil_voz,
        resolver_ruta_segura_voz,
    )
    from clonar_voz import preparar_clon_desde_archivo
    from procesar_documentos import leer_documento_transcripcion
    from usar_voz import generar_audio_desde_perfil


@contextlib.asynccontextmanager
async def ciclo_vida_aplicacion(app_fastapi: FastAPI):
    """Inicializa automáticamente la base de datos y carpetas en la primera ejecución."""
    dir_datos, dir_voces, dir_salidas, ruta_bd = asegurar_infraestructura_almacenamiento()
    print("=" * 65)
    print("🚀 SERVIDIOR BACKEND PREAL INICIADO")
    print(f"📦 Base de datos activa: {ruta_bd}")
    print(f"📁 Directorio de voces: {dir_voces}")
    print(f"📁 Directorio de salidas: {dir_salidas}")
    print("=" * 65)
    yield


app = FastAPI(
    title="API Estudio de Voz PReal",
    description="Backend en castellano para clonar, almacenar y usar voces con soporte de PDF, TXT y MD.",
    version="1.0.0",
    lifespan=ciclo_vida_aplicacion,
)

# Permitir CORS para clientes web externos o locales
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# 0. EXTRACCIÓN DE DOCUMENTOS (PDF, TXT, MD)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/transcripcion/subir-documento")
async def extraer_texto_documento(
    documento: UploadFile = File(...),
    formato_salida: str = Form("markdown"),
):
    """Extrae y formatea el texto de un archivo PDF, TXT o MD a Markdown o texto plano."""
    contenido_bytes = await documento.read()
    if not contenido_bytes:
        raise HTTPException(status_code=400, detail="El documento subido está vacío.")

    try:
        texto_extraido = leer_documento_transcripcion(
            fuente_documento=contenido_bytes,
            nombre_archivo=documento.filename or "documento.txt",
            formato_salida=formato_salida,
        )
        return {
            "nombre_archivo": documento.filename,
            "formato_salida": formato_salida,
            "caracteres": len(texto_extraido),
            "texto": texto_extraido,
        }
    except Exception as error_extraccion:
        raise HTTPException(status_code=400, detail=f"Error procesando documento: {error_extraccion}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. CLONACIÓN DE VOZ
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/clonar/analizar")
async def analizar_audio_clon(
    archivo: UploadFile = File(...),
    texto: str = Form(""),
    documento: Optional[UploadFile] = File(None),
    formato_documento: str = Form("markdown"),
):
    """Valida el audio de referencia y genera la transcripción mediante texto, documento adjunto o ASR."""
    extension = os.path.splitext(archivo.filename or ".wav")[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as archivo_temporal:
        archivo_temporal.write(await archivo.read())
        ruta_temporal = archivo_temporal.name

    texto_final = texto.strip()
    if not texto_final and documento:
        datos_doc = await documento.read()
        if datos_doc:
            try:
                texto_final = leer_documento_transcripcion(
                    datos_doc,
                    documento.filename or "doc.txt",
                    formato_salida=formato_documento,
                )
            except Exception as error_doc:
                raise HTTPException(status_code=400, detail=f"Error en documento adjunto: {error_doc}")

    try:
        resultado = preparar_clon_desde_archivo(
            ruta_temporal,
            texto_referencia_opcional=texto_final,
        )
        return resultado
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    finally:
        if os.path.exists(ruta_temporal):
            os.remove(ruta_temporal)


# ─────────────────────────────────────────────────────────────────────────────
# 2. ALMACENAMIENTO DE VOCES (CRUD)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/voces")
def obtener_voces():
    """Devuelve la lista de todos los perfiles de voz guardados."""
    perfiles = listar_perfiles_voz()
    return [perfil.a_diccionario() for perfil in perfiles]


@app.post("/api/voces")
async def registrar_voz(
    nombre: str = Form(...),
    audio: UploadFile = File(...),
    texto_referencia: str = Form(""),
    idioma: str = Form("Auto"),
    instrucciones: str = Form(""),
    documento: Optional[UploadFile] = File(None),
    formato_documento: str = Form("markdown"),
):
    """Guarda un nuevo perfil de voz en la base de datos y disco con soporte de documentos."""
    contenido_audio = await audio.read()
    texto_final = texto_referencia.strip()

    if not texto_final and documento:
        datos_doc = await documento.read()
        if datos_doc:
            try:
                texto_final = leer_documento_transcripcion(
                    datos_doc,
                    documento.filename or "doc.txt",
                    formato_salida=formato_documento,
                )
            except Exception as error_doc:
                raise HTTPException(status_code=400, detail=f"Error leyendo documento: {error_doc}")

    perfil = guardar_perfil_voz(
        nombre=nombre,
        datos_audio=contenido_audio,
        nombre_archivo_audio=audio.filename or "voz.wav",
        texto_referencia=texto_final,
        idioma=idioma,
        instrucciones=instrucciones,
    )
    return perfil.a_diccionario()


@app.delete("/api/voces/{id_perfil}")
def borrar_voz(id_perfil: str):
    """Elimina permanentemente un perfil y sus archivos de voz."""
    if not eliminar_perfil_voz(id_perfil):
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    return {"mensaje": "Perfil eliminado con éxito", "id": id_perfil}


@app.get("/api/voces/{id_perfil}/audio")
def descargar_audio_voz(id_perfil: str):
    """Descarga el audio de referencia original de la voz."""
    perfil = obtener_perfil_voz(id_perfil)
    if not perfil or not perfil.ruta_audio_referencia:
        raise HTTPException(status_code=404, detail="Audio de referencia no encontrado")
    ruta = resolver_ruta_segura_voz(perfil.ruta_audio_referencia)
    if not ruta or not os.path.isfile(ruta):
        raise HTTPException(status_code=404, detail="Archivo físico inexistente")
    return FileResponse(ruta, media_type="audio/wav")


# ─────────────────────────────────────────────────────────────────────────────
# 3. USO Y SÍNTESIS DE VOZ
# ─────────────────────────────────────────────────────────────────────────────

class PeticionSintesis(BaseModel):
    id_perfil: str
    texto: str
    velocidad: float = 1.0
    semilla: Optional[int] = None
    idioma: Optional[str] = None


@app.post("/api/sintetizar")
def sintetizar(peticion: PeticionSintesis):
    """Ejecuta la síntesis con la voz resuelta."""
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
    """Sirve el audio generado para reproducción o descarga."""
    ruta = os.path.join(DIRECTORIO_SALIDAS_PREDETERMINADO, nombre_archivo)
    if not os.path.isfile(ruta):
        raise HTTPException(status_code=404, detail="Audio generado no encontrado")
    return FileResponse(ruta, media_type="audio/wav")


# ─────────────────────────────────────────────────────────────────────────────
# 4. SERVIDO ESTÁTICO DEL FRONTEND
# ─────────────────────────────────────────────────────────────────────────────

DIRECTORIO_FRONTEND = os.path.join(DIRECTORIO_PREAL, "frontend")
if os.path.isdir(DIRECTORIO_FRONTEND):
    app.mount("/", StaticFiles(directory=DIRECTORIO_FRONTEND, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    # Iniciar servidor en el puerto 8000
    uvicorn.run("servidor_api:app", host="127.0.0.1", port=8000, reload=True)
