"""Módulo de Almacenamiento de Voces (PReal.backend.almacenar_voz)
==============================================================
Contiene la lógica encargada de:
1. Persistir archivos de audio de referencia y retratos en el sistema de archivos.
2. Guardar, actualizar, listar, consultar y eliminar registros de perfiles de voz.
3. Bloquear y fijar tomas de audio específicas a un perfil de voz.
4. Limpiar de forma segura los archivos huérfanos al borrar o reemplazar una voz.
"""

from __future__ import annotations

import contextlib
from contextlib import closing, suppress
from dataclasses import asdict, dataclass
import logging
import os
import re
import shutil
import sqlite3
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

# Importar infraestructura de base de datos
try:
    from PReal.backend.base_datos import (
        DIRECTORIO_SALIDAS_PREDETERMINADO,
        DIRECTORIO_VOCES_PREDETERMINADO,
        RUTA_BASE_DATOS_PREDETERMINADA,
        asegurar_infraestructura_almacenamiento,
        obtener_conexion_base_datos,
    )
except ImportError:
    from base_datos import (
        DIRECTORIO_SALIDAS_PREDETERMINADO,
        DIRECTORIO_VOCES_PREDETERMINADO,
        RUTA_BASE_DATOS_PREDETERMINADA,
        asegurar_infraestructura_almacenamiento,
        obtener_conexion_base_datos,
    )

asegurar_directorios_almacenamiento = asegurar_infraestructura_almacenamiento
registrador = logging.getLogger("preal.almacenar_voz")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES DE ALMACENAMIENTO Y RESTRICCIONES
# ─────────────────────────────────────────────────────────────────────────────

TAMANO_MAXIMO_AUDIO_REFERENCIA_BYTES: int = 128 * 1024 * 1024  # 128 MB
TAMANO_MINIMO_AUDIO_REFERENCIA_BYTES: int = 1000  # 1 KB mínimo para evitar archivos vacíos
TAMANO_MAXIMO_IMAGEN_BYTES: int = 10 * 1024 * 1024  # 10 MB

PATRON_IDENTIFICADOR_PERFIL = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

EXTENSIONES_AUDIO_PERMITIDAS = frozenset({
    ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".oga", ".opus", ".aac", ".webm"
})


# ─────────────────────────────────────────────────────────────────────────────
# MODELO DE DATOS DE PERFIL DE VOZ
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PerfilVoz:
    """Estructura representativa de un perfil de voz almacenado."""
    id: str
    nombre: str
    ruta_audio_referencia: Optional[str] = None
    texto_referencia: str = ""
    instrucciones: str = ""
    idioma: str = "Auto"
    audio_bloqueado: str = ""
    semilla: Optional[int] = None
    esta_bloqueado: bool = False
    personalidad: str = ""
    descripcion: str = ""
    es_demostracion: bool = False
    tipo: str = "clone"  # 'clone' o 'design'
    estados_diseno: Optional[str] = None
    creado_en: float = 0.0

    def a_diccionario(self) -> dict[str, Any]:
        """Convierte la entidad a un diccionario serializable."""
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# SEGURIDAD DE RUTAS Y ARCHIVOS EN DISCO
# ─────────────────────────────────────────────────────────────────────────────

def resolver_ruta_segura_voz(
    nombre_archivo: str,
    directorio_voces: Optional[str] = None,
) -> Optional[str]:
    """Valida y resuelve una ruta dentro del directorio de voces.

    Aplica barrera contra desbordamiento de directorio (Path Traversal / CWE-22).
    """
    if not nombre_archivo or os.path.basename(nombre_archivo) != nombre_archivo:
        return None

    dir_voces = directorio_voces or DIRECTORIO_VOCES_PREDETERMINADO
    raiz_absoluta = os.path.realpath(dir_voces)
    ruta_candidata = os.path.realpath(os.path.join(raiz_absoluta, nombre_archivo))

    if not ruta_candidata.startswith(raiz_absoluta + os.sep) and ruta_candidata != raiz_absoluta:
        return None

    return ruta_candidata


def sanitizar_instruccion_estilo(texto_instruccion: Optional[str]) -> str:
    """Elimina etiquetas corruptas o inyecciones de texto libre tipo '[object Object]'."""
    if not texto_instruccion:
        return ""
    texto = str(texto_instruccion).strip()
    if texto == "[object Object]":
        return ""
    return texto


# ─────────────────────────────────────────────────────────────────────────────
# OPERACIONES DE ALMACENAMIENTO (CRUD)
# ─────────────────────────────────────────────────────────────────────────────

def guardar_perfil_voz(
    nombre: str,
    *,
    datos_audio: Optional[bytes] = None,
    nombre_archivo_audio: Optional[str] = None,
    texto_referencia: str = "",
    instrucciones: str = "",
    idioma: str = "Auto",
    semilla: Optional[int] = None,
    personalidad: str = "",
    tipo: str = "clone",
    estados_diseno: Optional[str] = None,
    datos_imagen: Optional[bytes] = None,
    directorio_voces: Optional[str] = None,
    ruta_base_datos: Optional[str] = None,
) -> PerfilVoz:
    """Almacena un nuevo perfil de voz en la base de datos y en el sistema de archivos."""
    nombre_limpio = nombre.strip()
    if not nombre_limpio:
        raise ValueError("El perfil de voz debe tener un nombre válido.")

    if tipo not in ("clone", "design"):
        raise ValueError("El tipo de perfil debe ser 'clone' o 'design'.")

    if tipo == "clone" and not datos_audio:
        raise ValueError("Los perfiles de clonación requieren el contenido de audio de referencia.")

    # Asegurar que existan directorios y base de datos en la primera ejecución
    dir_voces = directorio_voces or DIRECTORIO_VOCES_PREDETERMINADO
    ruta_bd = ruta_base_datos or RUTA_BASE_DATOS_PREDETERMINADA
    asegurar_infraestructura_almacenamiento(directorio_voces=dir_voces, ruta_base_datos=ruta_bd)

    id_perfil = str(uuid.uuid4())[:8]
    nombre_archivo_final: Optional[str] = None
    ruta_audio_disco: Optional[str] = None

    if datos_audio:
        if len(datos_audio) > TAMANO_MAXIMO_AUDIO_REFERENCIA_BYTES:
            raise ValueError("El archivo de audio supera el tamaño máximo permitido.")

        extension = os.path.splitext(nombre_archivo_audio or ".wav")[1].lower()
        if extension not in EXTENSIONES_AUDIO_PERMITIDAS:
            extension = ".wav"

        nombre_archivo_final = f"{id_perfil}{extension}"
        ruta_audio_disco = os.path.join(dir_voces, nombre_archivo_final)

        with open(ruta_audio_disco, "wb") as archivo_salida:
            archivo_salida.write(datos_audio)

    ruta_imagen_disco: Optional[str] = None
    if datos_imagen and len(datos_imagen) <= TAMANO_MAXIMO_IMAGEN_BYTES:
        nombre_imagen = f"{id_perfil}.portrait.jpg"
        ruta_imagen_disco = os.path.join(dir_voces, nombre_imagen)
        with open(ruta_imagen_disco, "wb") as archivo_imagen:
            archivo_imagen.write(datos_imagen)

    instruccion_saneada = sanitizar_instruccion_estilo(instrucciones)
    tiempo_creacion = time.time()

    try:
        with closing(obtener_conexion_base_datos(ruta_bd)) as conexion:
            conexion.execute(
                """
                INSERT INTO voice_profiles (
                    id, name, ref_audio_path, ref_text, instruct,
                    language, seed, personality, kind, vd_states, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    id_perfil,
                    nombre_limpio,
                    nombre_archivo_final,
                    texto_referencia.strip(),
                    instruccion_saneada,
                    idioma.strip() or "Auto",
                    semilla,
                    personalidad.strip(),
                    tipo,
                    estados_diseno,
                    tiempo_creacion,
                ),
            )
            conexion.commit()
    except Exception as error_db:
        if ruta_audio_disco and os.path.exists(ruta_audio_disco):
            with suppress(OSError):
                os.remove(ruta_audio_disco)
        if ruta_imagen_disco and os.path.exists(ruta_imagen_disco):
            with suppress(OSError):
                os.remove(ruta_imagen_disco)
        raise RuntimeError(f"Error al registrar perfil en la base de datos: {error_db}") from error_db

    registrador.info("Perfil de voz almacenado con éxito: %s (%s)", nombre_limpio, id_perfil)
    perfil = obtener_perfil_voz(id_perfil, ruta_bd)
    if not perfil:
        raise RuntimeError(f"No se pudo recuperar el perfil recién creado: {id_perfil}")
    return perfil


def obtener_perfil_voz(
    id_perfil: str,
    ruta_base_datos: Optional[str] = None,
) -> Optional[PerfilVoz]:
    """Recupera un perfil de voz por su identificador único."""
    if not PATRON_IDENTIFICADOR_PERFIL.match(id_perfil or ""):
        return None

    ruta_bd = ruta_base_datos or RUTA_BASE_DATOS_PREDETERMINADA
    asegurar_infraestructura_almacenamiento(ruta_base_datos=ruta_bd)

    with closing(obtener_conexion_base_datos(ruta_bd)) as conexion:
        fila = conexion.execute(
            "SELECT * FROM voice_profiles WHERE id = ?", (id_perfil,)
        ).fetchone()

    if not fila:
        return None

    return PerfilVoz(
        id=fila["id"],
        nombre=fila["name"],
        ruta_audio_referencia=fila["ref_audio_path"],
        texto_referencia=fila["ref_text"] or "",
        instrucciones=fila["instruct"] or "",
        idioma=fila["language"] or "Auto",
        audio_bloqueado=fila["locked_audio_path"] or "",
        semilla=fila["seed"],
        esta_bloqueado=bool(fila["is_locked"]),
        personalidad=fila["personality"] or "",
        descripcion=fila["description"] or "",
        es_demostracion=bool(fila["is_demo"]),
        tipo=fila["kind"] or "clone",
        estados_diseno=fila["vd_states"],
        creado_en=float(fila["created_at"] or 0.0),
    )


def listar_perfiles_voz(ruta_base_datos: Optional[str] = None) -> list[PerfilVoz]:
    """Devuelve la lista completa de todos los perfiles de voz guardados."""
    ruta_bd = ruta_base_datos or RUTA_BASE_DATOS_PREDETERMINADA
    asegurar_infraestructura_almacenamiento(ruta_base_datos=ruta_bd)

    with closing(obtener_conexion_base_datos(ruta_bd)) as conexion:
        filas = conexion.execute(
            "SELECT * FROM voice_profiles ORDER BY created_at DESC"
        ).fetchall()

    perfiles: list[PerfilVoz] = []
    for fila in filas:
        perfiles.append(
            PerfilVoz(
                id=fila["id"],
                nombre=fila["name"],
                ruta_audio_referencia=fila["ref_audio_path"],
                texto_referencia=fila["ref_text"] or "",
                instrucciones=fila["instruct"] or "",
                idioma=fila["language"] or "Auto",
                audio_bloqueado=fila["locked_audio_path"] or "",
                semilla=fila["seed"],
                esta_bloqueado=bool(fila["is_locked"]),
                personalidad=fila["personality"] or "",
                descripcion=fila["description"] or "",
                es_demostracion=bool(fila["is_demo"]),
                tipo=fila["kind"] or "clone",
                estados_diseno=fila["vd_states"],
                creado_en=float(fila["created_at"] or 0.0),
            )
        )
    return perfiles


def actualizar_perfil_voz(
    id_perfil: str,
    *,
    nombre: Optional[str] = None,
    texto_referencia: Optional[str] = None,
    instrucciones: Optional[str] = None,
    idioma: Optional[str] = None,
    personalidad: Optional[str] = None,
    ruta_base_datos: Optional[str] = None,
) -> Optional[PerfilVoz]:
    """Actualiza campos específicos de un perfil de voz existente."""
    if not PATRON_IDENTIFICADOR_PERFIL.match(id_perfil or ""):
        return None

    campos_modificar: list[str] = []
    valores_parametros: list[Any] = []

    if nombre is not None:
        nombre_valido = nombre.strip()
        if not nombre_valido:
            raise ValueError("El nombre no puede estar vacío.")
        campos_modificar.append("name = ?")
        valores_parametros.append(nombre_valido)

    if texto_referencia is not None:
        campos_modificar.append("ref_text = ?")
        valores_parametros.append(texto_referencia.strip())

    if instrucciones is not None:
        campos_modificar.append("instruct = ?")
        valores_parametros.append(sanitizar_instruccion_estilo(instrucciones))

    if idioma is not None:
        campos_modificar.append("language = ?")
        valores_parametros.append(idioma.strip() or "Auto")

    if personalidad is not None:
        campos_modificar.append("personality = ?")
        valores_parametros.append(personalidad.strip())

    ruta_bd = ruta_base_datos or RUTA_BASE_DATOS_PREDETERMINADA
    if not campos_modificar:
        return obtener_perfil_voz(id_perfil, ruta_bd)

    valores_parametros.append(id_perfil)
    clausula_sql = f"UPDATE voice_profiles SET {', '.join(campos_modificar)} WHERE id = ?"

    with closing(obtener_conexion_base_datos(ruta_bd)) as conexion:
        cursor = conexion.execute(clausula_sql, valores_parametros)
        if cursor.rowcount == 0:
            return None
        conexion.commit()

    return obtener_perfil_voz(id_perfil, ruta_bd)


def bloquear_toma_voz(
    id_perfil: str,
    ruta_audio_toma: str,
    texto_toma: str = "",
    semilla: Optional[int] = None,
    directorio_voces: Optional[str] = None,
    ruta_base_datos: Optional[str] = None,
) -> bool:
    """Bloquea o fija una toma de audio generada a un perfil para mantener una identidad idéntica en futuras generaciones."""
    ruta_bd = ruta_base_datos or RUTA_BASE_DATOS_PREDETERMINADA
    perfil = obtener_perfil_voz(id_perfil, ruta_bd)
    if not perfil:
        return False

    if not os.path.isfile(ruta_audio_toma):
        raise FileNotFoundError(f"La toma de audio especificada no existe en disco: {ruta_audio_toma}")

    dir_voces = directorio_voces or DIRECTORIO_VOCES_PREDETERMINADO
    asegurar_infraestructura_almacenamiento(directorio_voces=dir_voces, ruta_base_datos=ruta_bd)

    nombre_archivo_bloqueado = f"{id_perfil}_locked.wav"
    ruta_destino = os.path.join(dir_voces, nombre_archivo_bloqueado)

    shutil.copy2(ruta_audio_toma, ruta_destino)

    with closing(obtener_conexion_base_datos(ruta_bd)) as conexion:
        conexion.execute(
            """
            UPDATE voice_profiles
            SET locked_audio_path = ?, seed = ?, is_locked = 1, ref_text = ?
            WHERE id = ?
            """,
            (nombre_archivo_bloqueado, semilla, texto_toma[:150], id_perfil),
        )
        conexion.commit()

    registrador.info("Toma de voz bloqueada con éxito para el perfil %s", id_perfil)
    return True


def desbloquear_toma_voz(
    id_perfil: str,
    directorio_voces: Optional[str] = None,
    ruta_base_datos: Optional[str] = None,
) -> bool:
    """Desbloquea una toma fija de un perfil y elimina el archivo fijado."""
    ruta_bd = ruta_base_datos or RUTA_BASE_DATOS_PREDETERMINADA
    perfil = obtener_perfil_voz(id_perfil, ruta_bd)
    if not perfil:
        return False

    dir_voces = directorio_voces or DIRECTORIO_VOCES_PREDETERMINADO
    if perfil.audio_bloqueado:
        ruta_archivo = resolver_ruta_segura_voz(perfil.audio_bloqueado, dir_voces)
        if ruta_archivo and os.path.exists(ruta_archivo):
            with suppress(OSError):
                os.remove(ruta_archivo)

    with closing(obtener_conexion_base_datos(ruta_bd)) as conexion:
        conexion.execute(
            """
            UPDATE voice_profiles
            SET locked_audio_path = '', is_locked = 0
            WHERE id = ?
            """,
            (id_perfil,),
        )
        conexion.commit()

    return True


def eliminar_perfil_voz(
    id_perfil: str,
    directorio_voces: Optional[str] = None,
    ruta_base_datos: Optional[str] = None,
) -> bool:
    """Elimina permanentemente un perfil de voz y todos los archivos físicos asociados."""
    ruta_bd = ruta_base_datos or RUTA_BASE_DATOS_PREDETERMINADA
    perfil = obtener_perfil_voz(id_perfil, ruta_bd)
    if not perfil:
        return False

    dir_voces = directorio_voces or DIRECTORIO_VOCES_PREDETERMINADO

    archivos_a_eliminar = [
        perfil.ruta_audio_referencia,
        perfil.audio_bloqueado,
        f"{id_perfil}.portrait.jpg",
    ]

    for archivo in archivos_a_eliminar:
        if archivo:
            ruta_disco = resolver_ruta_segura_voz(archivo, dir_voces)
            if ruta_disco and os.path.exists(ruta_disco):
                with suppress(OSError):
                    os.remove(ruta_disco)

    with closing(obtener_conexion_base_datos(ruta_bd)) as conexion:
        with suppress(sqlite3.OperationalError):
            conexion.execute(
                "UPDATE generation_history SET profile_id = NULL WHERE profile_id = ?",
                (id_perfil,),
            )
        conexion.execute("DELETE FROM voice_profiles WHERE id = ?", (id_perfil,))
        conexion.commit()

    registrador.info("Perfil de voz %s eliminado por completo.", id_perfil)
    return True
