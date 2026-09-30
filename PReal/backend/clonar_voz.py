"""Módulo de Clonación de Voz (PReal.clonar_voz)
==============================================
Contiene la lógica encargada de:
1. Extraer y seleccionar los fragmentos de audio más limpios de un hablante.
2. Concatenar los fragmentos con silencios de transición para preservar la prosodia.
3. Validar y procesar archivos de audio de referencia para clonación sin requerir entrenamiento.
4. Transcribir el audio de referencia mediante reconocimiento de voz (ASR) para alinear
   fonéticamente el texto y el audio de referencia.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import sys
import wave
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Intentar importar soundfile de forma opcional; si no está, se usa el módulo nativo wave
try:
    import soundfile as sf
    TIENE_SOUNDFILE = True
except ImportError:
    sf = None
    TIENE_SOUNDFILE = False

# Configuración del registro de eventos en castellano
registrador = logging.getLogger("preal.clonar_voz")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES DE CLONACIÓN DE VOZ (en segundos y parámetros acústicos)
# ─────────────────────────────────────────────────────────────────────────────

# Duración mínima recomendada del audio de referencia (menos de esto genera clones inestables)
DURACION_MINIMA_REFERENCIA_SEGUNDOS: float = 5.0

# Duración máxima recomendada (por encima se desperdicia contexto computacional)
DURACION_MAXIMA_REFERENCIA_SEGUNDOS: float = 15.0

# Duración ideal para capturar prosodia y timbre óptimos
DURACION_IDEAL_REFERENCIA_SEGUNDOS: float = 8.0

# Duración mínima de un segmento individual para referencias por subtítulo
DURACION_MINIMA_SEGMENTO_SEGUNDOS: float = 3.0

# Duración mínima por fragmento para evitar ruidos de frontera en la diarización
DURACION_MINIMA_FRAGMENTO_SEGUNDOS: float = 1.5

# Margen de seguridad con respecto al turno de otro hablante (en segundos)
MARGEN_SEGURIDAD_TURNO_ADYACENTE_SEGUNDOS: float = 0.3

# Silencio de relleno entre fragmentos concatenados (20 milisegundos)
DURACION_SILENCIO_ENTRE_CORTES_SEGUNDOS: float = 0.02

# Extensiones de audio válidas para clonación de voz
EXTENSIONES_AUDIO_SOPORTADAS = frozenset({
    ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".oga", ".opus", ".aac", ".webm"
})


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES DE ENTRADA Y SALIDA DE AUDIO
# ─────────────────────────────────────────────────────────────────────────────

def leer_audio_archivo(ruta_audio: str) -> tuple[np.ndarray, int]:
    """Carga un archivo de audio como un arreglo NumPy en coma flotante (float32)

    y devuelve una tupla con (forma_onda, frecuencia_muestreo).
    Soporta soundfile si está disponible y wave estándar de Python como alternativa.
    """
    if TIENE_SOUNDFILE and sf is not None:
        try:
            datos, frecuencia = sf.read(ruta_audio, dtype="float32", always_2d=False)
            if datos.ndim > 1:
                datos = datos.mean(axis=1)
            return datos, int(frecuencia)
        except Exception as error_sf:
            registrador.debug("Fallo lectura soundfile (%s), probando con módulo wave", error_sf)

    # Lectura alternativa mediante el módulo wave estándar de Python
    with wave.open(ruta_audio, "rb") as archivo_wav:
        canales = archivo_wav.getnchannels()
        ancho_muestra = archivo_wav.getsampwidth()
        frecuencia = archivo_wav.getframerate()
        total_cuadros = archivo_wav.getnframes()
        datos_crudos = archivo_wav.readframes(total_cuadros)

        if ancho_muestra == 2:
            datos_enteros = np.frombuffer(datos_crudos, dtype=np.int16)
            datos_flotantes = datos_enteros.astype(np.float32) / 32768.0
        elif ancho_muestra == 4:
            datos_enteros = np.frombuffer(datos_crudos, dtype=np.int32)
            datos_flotantes = datos_enteros.astype(np.float32) / 2147483648.0
        elif ancho_muestra == 1:
            datos_enteros = np.frombuffer(datos_crudos, dtype=np.uint8)
            datos_flotantes = (datos_enteros.astype(np.float32) - 128.0) / 128.0
        else:
            raise ValueError(f"Ancho de muestra WAV no soportado: {ancho_muestra} bytes")

        if canales > 1:
            datos_flotantes = datos_flotantes.reshape(-1, canales).mean(axis=1)

        return datos_flotantes, int(frecuencia)


def escribir_audio_archivo(ruta_audio: str, datos_audio: np.ndarray, frecuencia_muestreo: int) -> None:
    """Escribe un arreglo NumPy en un archivo de audio WAV de 16 bits.

    Utiliza soundfile si está disponible o el módulo wave integrado de Python.
    """
    os.makedirs(os.path.dirname(os.path.abspath(ruta_audio)), exist_ok=True)

    if TIENE_SOUNDFILE and sf is not None:
        try:
            sf.write(ruta_audio, datos_audio, frecuencia_muestreo)
            return
        except Exception as error_sf:
            registrador.debug("Fallo escritura soundfile (%s), probando con wave", error_sf)

    # Escritura alternativa con módulo wave nativo
    muestras_ajustadas = np.clip(datos_audio, -1.0, 1.0)
    muestras_enteras = (muestras_ajustadas * 32767.0).astype(np.int16)

    with wave.open(ruta_audio, "wb") as archivo_wav:
        archivo_wav.setnchannels(1)
        archivo_wav.setsampwidth(2)
        archivo_wav.setframerate(frecuencia_muestreo)
        archivo_wav.writeframes(muestras_enteras.tobytes())


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES DE UTILIDAD Y SANITIZACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def sanitizar_nombre_hablante(identificador_hablante: str) -> str:
    """Convierte un identificador como 'Hablante 1' en 'hablante_1'.

    Mantiene nombres de archivo portables entre sistemas operativos (Windows, Linux, macOS).
    """
    caracteres_limpios: list[str] = []
    for caracter in identificador_hablante.lower():
        if caracter.isalnum():
            caracteres_limpios.append(caracter)
        elif caracter in (" ", "-"):
            caracteres_limpios.append("_")
    resultado = "".join(caracteres_limpios)
    return resultado or "hablante"


def calcular_duracion_audio(ruta_audio: str) -> float:
    """Obtiene la duración en segundos de un archivo de audio legible."""
    if not os.path.isfile(ruta_audio):
        return 0.0

    if TIENE_SOUNDFILE and sf is not None:
        try:
            info_archivo = sf.info(ruta_audio)
            return float(info_archivo.duration)
        except Exception:
            pass

    # Fallback con wave
    try:
        with wave.open(ruta_audio, "rb") as wav:
            cuadros = wav.getnframes()
            frecuencia = wav.getframerate()
            return float(cuadros) / float(frecuencia) if frecuencia > 0 else 0.0
    except Exception as error_lectura:
        registrador.debug("No se pudo leer duración: %s", error_lectura)
        return 0.0


def validar_archivo_audio_para_clonacion(ruta_audio: str) -> bool:
    """Verifica que el archivo de audio exista, tenga una extensión admitida

    y contenga muestras de audio decodificables reales.
    """
    if not ruta_audio or not os.path.exists(ruta_audio):
        registrador.warning("El archivo de audio no existe: %s", ruta_audio)
        return False

    extension = os.path.splitext(ruta_audio)[1].lower()
    if extension not in EXTENSIONES_AUDIO_SOPORTADAS:
        registrador.warning("Extensión de archivo no soportada (%s): %s", extension, ruta_audio)
        return False

    try:
        audio, frecuencia = leer_audio_archivo(ruta_audio)
        return frecuencia > 0 and audio.size > 0
    except Exception as excepcion_sonido:
        registrador.warning("Error decodificando audio para clonación: %s", excepcion_sonido)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# DETECCIÓN DE CONTAMINACIÓN ENTRE HABLANTES
# ─────────────────────────────────────────────────────────────────────────────

def es_adyacente_a_otro_hablante(
    segmento_actual: dict[str, Any],
    identificador_hablante: str,
    todos_los_segmentos: Optional[list[dict[str, Any]]] = None,
) -> bool:
    """Comprueba si un segmento está demasiado cerca o se solapa temporalmente con

    el turno de otro hablante, para evitar mezclar voces distintas en la referencia.
    """
    if not todos_los_segmentos:
        return False

    inicio_actual = float(segmento_actual.get("start", 0.0))
    fin_actual = float(segmento_actual.get("end", 0.0))

    for otro_segmento in todos_los_segmentos:
        if otro_segmento is segmento_actual:
            continue
        otro_hablante = otro_segmento.get("speaker_id") or "Hablante 1"
        if otro_hablante == identificador_hablante:
            continue

        inicio_otro = float(otro_segmento.get("start", 0.0))
        fin_otro = float(otro_segmento.get("end", 0.0))

        distancia = max(inicio_otro - fin_actual, inicio_actual - fin_otro)
        if distancia < MARGEN_SEGURIDAD_TURNO_ADYACENTE_SEGUNDOS:
            return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# SELECCIÓN Y CONCATENACIÓN DE MUESTRAS ACÚSTICAS
# ─────────────────────────────────────────────────────────────────────────────

def seleccionar_fragmentos_referencia(
    elementos_segmentos: list[tuple[int, dict[str, Any]]],
    *,
    identificador_hablante: Optional[str] = None,
    todos_los_segmentos: Optional[list[dict[str, Any]]] = None,
    fuente_etiquetas: Optional[str] = None,
) -> list[tuple[int, dict[str, Any]]]:
    """Selecciona los fragmentos de audio más convenientes de un hablante.

    Estrategia de priorización:
    1. Fragmentos limpios (no adyacentes a otro hablante).
    2. Fragmentos más largos primero.
    3. Acumulación progresiva hasta alcanzar la duración ideal (8 segundos).
    4. Descarte de fragmentos menores al umbral mínimo (1.5 segundos).
    """
    if not elementos_segmentos:
        return []
    if fuente_etiquetas == "heuristic":
        registrador.info("Etiquetas heurísticas: se omite clonación por riesgo de mezcla.")
        return []

    if identificador_hablante is None:
        identificador_hablante = (
            elementos_segmentos[0][1].get("speaker_id") or "Hablante 1"
        )

    def obtener_duracion(par: tuple[int, dict[str, Any]]) -> float:
        seg = par[1]
        return max(0.0, float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)))

    fragmentos_ordenados = sorted(
        elementos_segmentos,
        key=lambda par: (
            es_adyacente_a_otro_hablante(par[1], identificador_hablante, todos_los_segmentos),
            -obtener_duracion(par),
        ),
    )

    seleccionados: list[tuple[int, dict[str, Any]]] = []
    duracion_acumulada: float = 0.0

    for indice, segmento in fragmentos_ordenados:
        duracion = obtener_duracion((indice, segmento))
        if duracion < DURACION_MINIMA_FRAGMENTO_SEGUNDOS:
            continue
        if duracion_acumulada + duracion > DURACION_MAXIMA_REFERENCIA_SEGUNDOS and seleccionados:
            continue

        seleccionados.append((indice, segmento))
        duracion_acumulada += duracion
        if duracion_acumulada >= DURACION_IDEAL_REFERENCIA_SEGUNDOS:
            break

    if duracion_acumulada < DURACION_MINIMA_REFERENCIA_SEGUNDOS:
        registrador.info(
            "Duración acumulada insuficiente (%.2fs < %.2fs) para hablante: %s",
            duracion_acumulada, DURACION_MINIMA_REFERENCIA_SEGUNDOS, identificador_hablante
        )
        return []

    seleccionados.sort(key=lambda par: par[0])
    return seleccionados


def concatenar_fragmentos_audio(
    forma_onda_audio: np.ndarray,
    frecuencia_muestreo: int,
    fragmentos_seleccionados: list[tuple[int, dict[str, Any]]],
) -> np.ndarray:
    """Concatena los intervalos de audio seleccionados agregando una pequeña pausa

    de silencio de 20 ms entre ellos para un anclaje fonético estable.
    """
    cortes: list[np.ndarray] = []
    tamano_total_audio = forma_onda_audio.size

    for _, segmento in fragmentos_seleccionados:
        muestra_inicio = int(float(segmento.get("start", 0.0)) * frecuencia_muestreo)
        muestra_fin = int(float(segmento.get("end", 0.0)) * frecuencia_muestreo)

        muestra_inicio = max(0, muestra_inicio)
        muestra_fin = min(tamano_total_audio, muestra_fin)

        if muestra_fin <= muestra_inicio:
            continue

        corte_actual = forma_onda_audio[muestra_inicio:muestra_fin]
        cortes.append(corte_actual)

    if not cortes:
        return np.zeros(0, dtype=np.float32)

    tamano_silencio = int(DURACION_SILENCIO_ENTRE_CORTES_SEGUNDOS * frecuencia_muestreo)
    silencio_intermedio = np.zeros(tamano_silencio, dtype=np.float32)

    resultado_final: list[np.ndarray] = []
    for posicion, corte in enumerate(cortes):
        if posicion > 0:
            resultado_final.append(silencio_intermedio)
        resultado_final.append(corte.astype(np.float32, copy=False))

    return np.concatenate(resultado_final)


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACCIÓN DE CLONES POR HABLANTE Y POR SEGMENTO
# ─────────────────────────────────────────────────────────────────────────────

def extraer_clones_hablantes(
    ruta_pista_voz: str,
    segmentos_transcripcion: list[dict[str, Any]],
    directorio_destino: str,
    *,
    fuente_etiquetas: Optional[str] = None,
) -> dict[str, dict[str, Any]]:
    """Construye muestras de audio de referencia por cada hablante detectado.

    Retorna un diccionario con la estructura:
    {
        "Hablante 1": {
            "ruta_audio_referencia": ".../voz_hablante_1.wav",
            "texto_referencia": "texto transcrito concatenado...",
            "duracion_segundos": 8.45,
            "cantidad_fragmentos": 2
        }
    }
    """
    if not ruta_pista_voz or not os.path.exists(ruta_pista_voz) or not segmentos_transcripcion:
        return {}

    try:
        audio, frecuencia = leer_audio_archivo(ruta_pista_voz)
    except Exception as error_lectura:
        registrador.error("Error al leer el audio de voces %s: %s", ruta_pista_voz, error_lectura)
        return {}

    segmentos_por_hablante: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for indice, seg in enumerate(segmentos_transcripcion):
        hablante = seg.get("speaker_id") or "Hablante 1"
        segmentos_por_hablante.setdefault(hablante, []).append((indice, seg))

    os.makedirs(directorio_destino, exist_ok=True)
    clones_generados: dict[str, dict[str, Any]] = {}

    for id_hablante, lista_segmentos in segmentos_por_hablante.items():
        seleccionados = seleccionar_fragmentos_referencia(
            lista_segmentos,
            identificador_hablante=id_hablante,
            todos_los_segmentos=segmentos_transcripcion,
            fuente_etiquetas=fuente_etiquetas,
        )
        if not seleccionados:
            registrador.info("Hablante %s no cuenta con suficiente audio limpio para clonación.", id_hablante)
            continue

        audio_referencia = concatenar_fragmentos_audio(audio, frecuencia, seleccionados)
        if audio_referencia.size == 0:
            continue

        nombre_seguro = sanitizar_nombre_hablante(id_hablante)
        ruta_archivo_referencia = os.path.join(directorio_destino, f"voz_{nombre_seguro}.wav")

        try:
            escribir_audio_archivo(ruta_archivo_referencia, audio_referencia, frecuencia)
        except Exception as error_escritura:
            registrador.error("Error guardando referencia de clon %s: %s", ruta_archivo_referencia, error_escritura)
            continue

        texto_referencia = " ".join(
            (seg.get("text") or "").strip() for _, seg in seleccionados
        ).strip()

        duracion_segundos = float(audio_referencia.size) / float(frecuencia)
        clones_generados[id_hablante] = {
            "ruta_audio_referencia": ruta_archivo_referencia,
            "texto_referencia": texto_referencia,
            "duracion_segundos": duracion_segundos,
            "cantidad_fragmentos": len(seleccionados),
        }
        registrador.info("Clon generado para %s: %s (%.2f s)", id_hablante, ruta_archivo_referencia, duracion_segundos)

    return clones_generados


def extraer_referencias_por_segmento(
    ruta_pista_voz: str,
    segmentos: list[dict[str, Any]],
    directorio_destino: str,
    *,
    identificadores_segmento: Optional[list[str]] = None,
) -> dict[str, dict[str, Any]]:
    """Extrae una referencia de audio individual por cada segmento o subtítulo

    para transferir la emoción y prosodia exacta línea por línea.
    """
    if not ruta_pista_voz or not os.path.exists(ruta_pista_voz) or not segmentos:
        return {}

    try:
        audio, frecuencia = leer_audio_archivo(ruta_pista_voz)
    except Exception as error_lectura:
        registrador.error("Error leyendo archivo de pista de voz: %s", error_lectura)
        return {}

    os.makedirs(directorio_destino, exist_ok=True)
    referencias_segmentos: dict[str, dict[str, Any]] = {}

    for indice, seg in enumerate(segmentos):
        id_seg = (
            str(identificadores_segmento[indice])
            if (identificadores_segmento and indice < len(identificadores_segmento))
            else f"seg_{indice}"
        )
        inicio = float(seg.get("start", 0.0))
        fin = float(seg.get("end", 0.0))

        if fin - inicio < DURACION_MINIMA_SEGMENTO_SEGUNDOS:
            continue

        muestra_inicio = max(0, int(inicio * frecuencia))
        muestra_fin = min(audio.size, int(fin * frecuencia))

        if muestra_fin <= muestra_inicio:
            continue

        corte = audio[muestra_inicio:muestra_fin].astype(np.float32, copy=False)
        nombre_archivo = f"ref_segmento_{sanitizar_nombre_hablante(id_seg)}.wav"
        ruta_salida = os.path.join(directorio_destino, nombre_archivo)

        try:
            escribir_audio_archivo(ruta_salida, corte, frecuencia)
        except Exception as error_guardado:
            registrador.warning("No se pudo escribir el archivo de segmento %s: %s", ruta_salida, error_guardado)
            continue

        texto_original = (seg.get("text_original") or seg.get("text") or "").strip()
        referencias_segmentos[id_seg] = {
            "ruta_audio_referencia": ruta_salida,
            "texto_referencia": texto_original,
            "duracion_segundos": float(corte.size) / float(frecuencia),
        }

    return referencias_segmentos


# ─────────────────────────────────────────────────────────────────────────────
# TRANSCRIPCIÓN Y PREPARACIÓN DE CLON DESDE ARCHIVO DIRECTO
# ─────────────────────────────────────────────────────────────────────────────

def transcribir_audio_referencia(ruta_audio: str) -> str:
    """Realiza la transcripción automática del audio de referencia con el motor ASR local.

    Garantiza que la referencia cuente con texto alineado para el modelo TTS.
    """
    if not ruta_audio or not os.path.exists(ruta_audio):
        return ""
    try:
        from services.asr_backend import transcribe_reference
        texto_transcrito = transcribe_reference(ruta_audio)
        return (texto_transcrito or "").strip()
    except Exception as error_transcripcion:
        registrador.info("Transcripción automática ASR no disponible o fallida: %s", error_transcripcion)
        return ""


def preparar_clon_desde_archivo(
    ruta_archivo_entrada: str,
    texto_referencia_opcional: str = "",
    directorio_salida_opcional: Optional[str] = None,
    *,
    ruta_documento_transcripcion: Optional[str] = None,
    formato_documento: str = "markdown",
) -> dict[str, Any]:
    """Valida un archivo de audio proporcionado por el usuario, obtiene su duración,

    comprueba decodificación y genera el texto de referencia mediante un documento (PDF/TXT/MD),
    mediante el texto explícito o mediante ASR automático si no se proporcionó ninguno.
    """
    if not validar_archivo_audio_para_clonacion(ruta_archivo_entrada):
        raise ValueError(f"El archivo de audio de referencia no es válido o está corrupto: {ruta_archivo_entrada}")

    duracion = calcular_duracion_audio(ruta_archivo_entrada)
    if duracion < DURACION_MINIMA_REFERENCIA_SEGUNDOS:
        registrador.warning(
            "El audio tiene una duración de %.2fs, inferior a los %.2fs ideales.",
            duracion, DURACION_MINIMA_REFERENCIA_SEGUNDOS
        )

    texto_final = texto_referencia_opcional.strip()

    # Si se proporciona un documento (PDF, TXT, MD), extraer el texto de él
    if not texto_final and ruta_documento_transcripcion and os.path.isfile(ruta_documento_transcripcion):
        try:
            from PReal.procesar_documentos import leer_documento_transcripcion
            registrador.info("Extrayendo texto de transcripción desde documento: %s", ruta_documento_transcripcion)
            texto_final = leer_documento_transcripcion(
                ruta_documento_transcripcion,
                os.path.basename(ruta_documento_transcripcion),
                formato_salida=formato_documento,
            )
        except Exception as error_doc:
            registrador.warning("No se pudo extraer texto del documento (%s). Se intentará con ASR.", error_doc)

    if not texto_final:
        registrador.info("Texto de referencia no proporcionado. Iniciando transcripción automática...")
        texto_final = transcribir_audio_referencia(ruta_archivo_entrada)

    return {
        "ruta_audio": os.path.abspath(ruta_archivo_entrada),
        "duracion_segundos": duracion,
        "texto_referencia": texto_final,
        "es_valido": True,
    }
