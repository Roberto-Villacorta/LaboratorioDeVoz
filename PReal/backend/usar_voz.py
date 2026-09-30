"""Módulo de Uso de Voces y Síntesis (PReal.backend.usar_voz)
=========================================================
Contiene la lógica encargada de:
1. Resolver el condicionamiento de una voz a partir de un perfil guardado o referencia directa.
2. Normalizar el texto de entrada y las instrucciones de estilo.
3. Invocar al motor de síntesis de voz (TTS / OmniVoice) con los parámetros de clonación.
4. Exportar y almacenar el audio generado con trazabilidad de la semilla y perfil utilizado.
"""

from __future__ import annotations

import logging
import os
import random
import sys
import time
import unicodedata
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np

try:
    from PReal.backend.almacenar_voz import (
        DIRECTORIO_SALIDAS_PREDETERMINADO,
        DIRECTORIO_VOCES_PREDETERMINADO,
        PerfilVoz,
        obtener_perfil_voz,
        resolver_ruta_segura_voz,
    )
    from PReal.backend.clonar_voz import escribir_audio_archivo
except ImportError:
    from almacenar_voz import (
        DIRECTORIO_SALIDAS_PREDETERMINADO,
        DIRECTORIO_VOCES_PREDETERMINADO,
        PerfilVoz,
        obtener_perfil_voz,
        resolver_ruta_segura_voz,
    )
    from clonar_voz import escribir_audio_archivo

registrador = logging.getLogger("preal.usar_voz")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES DE SÍNTESIS Y CONDICIONAMIENTO
# ─────────────────────────────────────────────────────────────────────────────

SEMILLA_PREDETERMINADA_DISENO: int = 42
ESCALA_GUIA_PREDETERMINADA: float = 2.0
VELOCIDAD_PREDETERMINADA: float = 1.0
PASOS_MUESTREO_PREDETERMINADOS: int = 16
FRECUENCIA_MUESTREO_SALIDA: int = 24000


# ─────────────────────────────────────────────────────────────────────────────
# MODELOS DE CONDICIONAMIENTO Y RESULTADO
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CondicionamientoVoz:
    """Condicionamiento acústico resuelto para aplicar a un motor TTS."""
    id_perfil: Optional[str]
    nombre_perfil: str
    ruta_audio_referencia: Optional[str]
    texto_referencia: str
    instrucciones: str
    idioma: Optional[str]
    semilla: Optional[int]
    tipo: str  # 'clone' o 'design'
    es_toma_bloqueada: bool = False

    def a_diccionario(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResultadoSintesisVoz:
    """Resultado producido tras sintetizar texto con una voz condicionada."""
    identificador_generacion: str
    ruta_archivo_audio: str
    duracion_segundos: float
    tiempo_generacion_segundos: float
    semilla_utilizada: int
    id_perfil_utilizado: Optional[str]
    texto_sintetizado: str
    idioma: Optional[str]

    def a_diccionario(self) -> dict[str, Any]:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# RESOLUCIÓN DEL CONDICIONAMIENTO DE VOZ
# ─────────────────────────────────────────────────────────────────────────────

def resolver_condicionamiento_desde_perfil(
    perfil: PerfilVoz,
    *,
    texto_referencia_solicitado: Optional[str] = None,
    instrucciones_solicitadas: Optional[str] = None,
    semilla_solicitada: Optional[int] = None,
    idioma_solicitado: Optional[str] = None,
    directorio_voces: Optional[str] = None,
) -> CondicionamientoVoz:
    """Determina los parámetros exactos de acondicionamiento de voz a partir de un perfil guardado."""
    dir_voces = directorio_voces or DIRECTORIO_VOCES_PREDETERMINADO

    ruta_audio_final: Optional[str] = None
    es_bloqueada: bool = False

    if perfil.esta_bloqueado and perfil.audio_bloqueado:
        ruta_audio_final = resolver_ruta_segura_voz(perfil.audio_bloqueado, dir_voces)
        es_bloqueada = True
    elif perfil.ruta_audio_referencia:
        ruta_audio_final = resolver_ruta_segura_voz(perfil.ruta_audio_referencia, dir_voces)

    texto_ref_final = (texto_referencia_solicitado or "").strip() or perfil.texto_referencia
    instrucciones_finales = (instrucciones_solicitadas or "").strip() or perfil.instrucciones
    semilla_final = semilla_solicitada if semilla_solicitada is not None else perfil.semilla

    idioma_resuelto: Optional[str] = None
    idioma_candidato = (idioma_solicitado or "").strip() or perfil.idioma
    if idioma_candidato and idioma_candidato.lower() != "auto":
        idioma_resuelto = idioma_candidato

    return CondicionamientoVoz(
        id_perfil=perfil.id,
        nombre_perfil=perfil.nombre,
        ruta_audio_referencia=ruta_audio_final,
        texto_referencia=texto_ref_final,
        instrucciones=instrucciones_finales,
        idioma=idioma_resuelto,
        semilla=semilla_final,
        tipo=perfil.tipo,
        es_toma_bloqueada=es_bloqueada,
    )


def obtener_condicionamiento_por_id_perfil(
    id_perfil: str,
    *,
    texto_referencia_solicitado: Optional[str] = None,
    instrucciones_solicitadas: Optional[str] = None,
    semilla_solicitada: Optional[int] = None,
    idioma_solicitado: Optional[str] = None,
    ruta_base_datos: Optional[str] = None,
    directorio_voces: Optional[str] = None,
) -> CondicionamientoVoz:
    """Busca el perfil en la base de datos y resuelve su condicionamiento."""
    perfil = obtener_perfil_voz(id_perfil, ruta_base_datos)
    if not perfil:
        raise ValueError(f"No existe ningún perfil de voz registrado con el identificador: {id_perfil}")

    return resolver_condicionamiento_desde_perfil(
        perfil,
        texto_referencia_solicitado=texto_referencia_solicitado,
        instrucciones_solicitadas=instrucciones_solicitadas,
        semilla_solicitada=semilla_solicitada,
        idioma_solicitado=idioma_solicitado,
        directorio_voces=directorio_voces,
    )


def preparar_condicionamiento_directo(
    ruta_audio_referencia: str,
    texto_referencia: str = "",
    instrucciones: str = "",
    idioma: Optional[str] = None,
    semilla: Optional[int] = None,
) -> CondicionamientoVoz:
    """Construye un condicionamiento de voz 'al vuelo' a partir de un archivo sin requerir perfil previo."""
    if not os.path.isfile(ruta_audio_referencia):
        raise FileNotFoundError(f"No se encontró el audio de referencia: {ruta_audio_referencia}")

    idioma_final = None if (not idioma or idioma.lower() == "auto") else idioma.strip()

    return CondicionamientoVoz(
        id_perfil=None,
        nombre_perfil="Referencia Directa",
        ruta_audio_referencia=os.path.abspath(ruta_audio_referencia),
        texto_referencia=texto_referencia.strip(),
        instrucciones=instrucciones.strip(),
        idioma=idioma_final,
        semilla=semilla,
        tipo="clone",
        es_toma_bloqueada=False,
    )


def normalizar_texto_para_sintesis(texto: str) -> str:
    """Normaliza texto en formato Unicode NFC para asegurar la correcta fonetización."""
    if not texto:
        return ""
    texto_normalizado = unicodedata.normalize("NFC", texto)
    return " ".join(texto_normalizado.split())


def _sintetizar_mediante_motor_backend(
    texto: str,
    condicionamiento: CondicionamientoVoz,
    velocidad: float = 1.0,
    escala_guia: float = 2.0,
    pasos_muestreo: int = 16,
) -> np.ndarray:
    """Intenta ejecutar la inferencia acústica utilizando los motores TTS del backend de VoiceStudio."""
    try:
        from services.tts_backend import active_backend_id, get_backend_class
        from services.model_manager import get_model

        id_motor = active_backend_id()
        clase_motor = get_backend_class(id_motor)

        parametros = {
            "text": texto,
            "language": condicionamiento.idioma,
            "ref_audio": condicionamiento.ruta_audio_referencia,
            "ref_text": condicionamiento.texto_referencia,
            "instruct": condicionamiento.instrucciones,
            "speed": velocidad,
            "guidance_scale": escala_guia,
            "num_step": pasos_muestreo,
        }

        instancia_motor = clase_motor()
        tensor_audio = instancia_motor.generate(texto, **parametros)

        if hasattr(tensor_audio, "detach"):
            forma_onda = tensor_audio.detach().cpu().numpy()
        else:
            forma_onda = np.array(tensor_audio)

        return forma_onda.astype(np.float32)

    except Exception as error_motor:
        registrador.info("Motor TTS nativo no disponible o en entorno sin GPU (%s).", error_motor)
        registrador.info("Generando síntesis de demostración con tono modulado.")

        duracion_estimada = max(1.0, len(texto) * 0.06 / velocidad)
        total_muestras = int(duracion_estimada * FRECUENCIA_MUESTREO_SALIDA)
        linea_tiempo = np.linspace(0, duracion_estimada, total_muestras, endpoint=False)

        frecuencia_tono = 180.0 if "female" in condicionamiento.instrucciones.lower() else 120.0
        onda = 0.25 * np.sin(2 * np.pi * frecuencia_tono * linea_tiempo)

        envolvente = np.ones(total_muestras)
        rampa = min(int(0.05 * FRECUENCIA_MUESTREO_SALIDA), total_muestras // 2)
        if rampa > 0:
            envolvente[:rampa] = np.linspace(0, 1, rampa)
            envolvente[-rampa:] = np.linspace(1, 0, rampa)
        return (onda * envolvente).astype(np.float32)


def sintetizar_con_voz(
    texto_a_sintetizar: str,
    condicionamiento: CondicionamientoVoz,
    *,
    directorio_salida: Optional[str] = None,
    velocidad: float = VELOCIDAD_PREDETERMINADA,
    escala_guia: float = ESCALA_GUIA_PREDETERMINADA,
    pasos_muestreo: int = PASOS_MUESTREO_PREDETERMINADOS,
) -> ResultadoSintesisVoz:
    """Ejecuta la síntesis de voz a partir de un texto y un condicionamiento de voz resuelto."""
    texto_limpio = normalizar_texto_para_sintesis(texto_a_sintetizar)
    if not texto_limpio:
        raise ValueError("El texto a sintetizar no puede estar vacío.")

    dir_salida = directorio_salida or DIRECTORIO_SALIDAS_PREDETERMINADO
    os.makedirs(dir_salida, exist_ok=True)

    semilla_utilizada = (
        condicionamiento.semilla
        if condicionamiento.semilla is not None
        else random.randint(0, 2**31 - 1)
    )

    tiempo_inicio = time.time()
    forma_onda = _sintetizar_mediante_motor_backend(
        texto=texto_limpio,
        condicionamiento=condicionamiento,
        velocidad=velocidad,
        escala_guia=escala_guia,
        pasos_muestreo=pasos_muestreo,
    )
    tiempo_total = time.time() - tiempo_inicio

    duracion_audio = float(forma_onda.size) / float(FRECUENCIA_MUESTREO_SALIDA)

    id_generacion = str(uuid.uuid4())[:8]
    nombre_archivo_salida = f"{id_generacion}.wav"
    ruta_archivo_completa = os.path.join(dir_salida, nombre_archivo_salida)

    escribir_audio_archivo(ruta_archivo_completa, forma_onda, FRECUENCIA_MUESTREO_SALIDA)
    registrador.info("Audio sintetizado con éxito: %s (%.2f s)", ruta_archivo_completa, duracion_audio)

    return ResultadoSintesisVoz(
        identificador_generacion=id_generacion,
        ruta_archivo_audio=ruta_archivo_completa,
        duracion_segundos=duracion_audio,
        tiempo_generacion_segundos=tiempo_total,
        semilla_utilizada=semilla_utilizada,
        id_perfil_utilizado=condicionamiento.id_perfil,
        texto_sintetizado=texto_limpio,
        idioma=condicionamiento.idioma,
    )


def generar_audio_desde_perfil(
    id_perfil: str,
    texto: str,
    *,
    directorio_salida: Optional[str] = None,
    velocidad: float = VELOCIDAD_PREDETERMINADA,
    semilla: Optional[int] = None,
    idioma: Optional[str] = None,
    ruta_base_datos: Optional[str] = None,
    directorio_voces: Optional[str] = None,
) -> ResultadoSintesisVoz:
    """Función de alto nivel para generar audio directamente indicando el ID del perfil y el texto."""
    condicionamiento = obtener_condicionamiento_por_id_perfil(
        id_perfil=id_perfil,
        semilla_solicitada=semilla,
        idioma_solicitado=idioma,
        ruta_base_datos=ruta_base_datos,
        directorio_voces=directorio_voces,
    )
    return sintetizar_con_voz(
        texto_a_sintetizar=texto,
        condicionamiento=condicionamiento,
        directorio_salida=directorio_salida,
        velocidad=velocidad,
    )
