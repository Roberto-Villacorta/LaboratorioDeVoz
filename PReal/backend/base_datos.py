"""Módulo de Inicialización y Gestión de la Base de Datos (PReal.backend.base_datos)
=============================================================================
Se encarga de crear y preparar automáticamente en la primera ejecución:
1. El directorio de datos, la carpeta de voces y la carpeta de salidas.
2. La base de datos SQLite con las tablas de perfiles de voz e historial de síntesis.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from contextlib import closing

registrador = logging.getLogger("preal.base_datos")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE RUTAS DE ALMACENAMIENTO Y BASE DE DATOS
# ─────────────────────────────────────────────────────────────────────────────

DIRECTORIO_BACKEND = os.path.dirname(os.path.abspath(__file__))
DIRECTORIO_PREAL = os.path.dirname(DIRECTORIO_BACKEND)

# La base de datos y los datos se almacenan por defecto en la carpeta 'datos' de PReal
DIRECTORIO_DATOS_PREDETERMINADO = os.path.join(DIRECTORIO_PREAL, "datos")
DIRECTORIO_VOCES_PREDETERMINADO = os.path.join(DIRECTORIO_DATOS_PREDETERMINADO, "voces")
DIRECTORIO_SALIDAS_PREDETERMINADO = os.path.join(DIRECTORIO_DATOS_PREDETERMINADO, "salidas")
RUTA_BASE_DATOS_PREDETERMINADA = os.path.join(DIRECTORIO_DATOS_PREDETERMINADO, "voces.db")


def asegurar_infraestructura_almacenamiento(
    directorio_datos: str | None = None,
    directorio_voces: str | None = None,
    directorio_salidas: str | None = None,
    ruta_base_datos: str | None = None,
) -> tuple[str, str, str, str]:
    """Crea los directorios físicos y la base de datos si no existen aún en el sistema."""
    dir_datos = directorio_datos or DIRECTORIO_DATOS_PREDETERMINADO
    dir_voces = directorio_voces or DIRECTORIO_VOCES_PREDETERMINADO
    dir_salidas = directorio_salidas or DIRECTORIO_SALIDAS_PREDETERMINADO
    ruta_bd = ruta_base_datos or RUTA_BASE_DATOS_PREDETERMINADA

    # Crear carpetas si no existen
    os.makedirs(dir_datos, exist_ok=True)
    os.makedirs(dir_voces, exist_ok=True)
    os.makedirs(dir_salidas, exist_ok=True)

    # Verificar si la base de datos ya existía
    es_primera_ejecucion = not os.path.exists(ruta_bd) or os.path.getsize(ruta_bd) == 0

    if es_primera_ejecucion:
        registrador.info("Primera ejecución detectada. Inicializando base de datos en: %s", ruta_bd)

    inicializar_tablas_base_datos(ruta_bd)

    return dir_datos, dir_voces, dir_salidas, ruta_bd


def obtener_conexion_base_datos(ruta_base_datos: str | None = None) -> sqlite3.Connection:
    """Abre y devuelve una conexión configurada con WAL y claves foráneas."""
    ruta_final = ruta_base_datos or RUTA_BASE_DATOS_PREDETERMINADA
    directorio_padre = os.path.dirname(ruta_final)
    if directorio_padre:
        os.makedirs(directorio_padre, exist_ok=True)

    conexion = sqlite3.connect(ruta_final, timeout=30.0)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA journal_mode = WAL;")
    conexion.execute("PRAGMA synchronous = NORMAL;")
    conexion.execute("PRAGMA foreign_keys = ON;")
    return conexion


def inicializar_tablas_base_datos(ruta_base_datos: str | None = None) -> None:
    """Crea las tablas 'voice_profiles' y 'generation_history' si no existen."""
    ruta_final = ruta_base_datos or RUTA_BASE_DATOS_PREDETERMINADA
    with closing(obtener_conexion_base_datos(ruta_final)) as conexion:
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS voice_profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                ref_audio_path TEXT,
                ref_text TEXT DEFAULT '',
                instruct TEXT DEFAULT '',
                language TEXT DEFAULT 'Auto',
                locked_audio_path TEXT DEFAULT '',
                seed INTEGER DEFAULT NULL,
                is_locked INTEGER DEFAULT 0,
                personality TEXT DEFAULT '',
                description TEXT DEFAULT '',
                is_demo INTEGER DEFAULT 0,
                verified_own_voice INTEGER DEFAULT 0,
                consent_text TEXT DEFAULT '',
                consent_audio_path TEXT DEFAULT '',
                consent_recorded_at REAL DEFAULT NULL,
                kind TEXT DEFAULT 'clone',
                vd_states TEXT DEFAULT NULL,
                created_at REAL
            );
        """)
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS generation_history (
                id TEXT PRIMARY KEY,
                text TEXT,
                mode TEXT,
                language TEXT,
                instruct TEXT,
                profile_id TEXT,
                audio_path TEXT,
                duration_seconds REAL,
                generation_time REAL,
                seed INTEGER DEFAULT NULL,
                starred INTEGER DEFAULT 0,
                created_at REAL,
                FOREIGN KEY (profile_id) REFERENCES voice_profiles(id)
            );
        """)
        conexion.commit()


# Alias compatibles para retrocompatibilidad
inicializar_esquema_almacenamiento = inicializar_tablas_base_datos
asegurar_directorios_almacenamiento = asegurar_infraestructura_almacenamiento


def cerrar_conexion_base_datos(conexion: sqlite3.Connection | None) -> None:
    """Cierra de forma segura una conexión abierta a la base de datos."""
    if conexion is not None:
        try:
            conexion.close()
        except Exception as error:
            registrador.warning("Error al cerrar conexión a base de datos: %s", error)
