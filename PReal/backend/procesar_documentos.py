"""Módulo de Procesamiento y Extracción de Documentos (PReal.procesar_documentos)
=============================================================================
Contiene la lógica encargada de:
1. Extraer texto desde archivos PDF, TXT y Markdown (MD).
2. Convertir y estructurar el texto extraído a formato Markdown o texto plano limpio.
3. Detectar títulos, capítulos y formatear párrafos para su uso como guión de síntesis
   o como texto fonético de referencia en la clonación de voz.
"""

from __future__ import annotations

import io
import logging
import os
import re
import zlib
from typing import Optional, Union

# Intentar importar pypdf si está instalado
try:
    import pypdf
    from pypdf import PdfReader
    TIENE_PYPDF = True
except ImportError:
    pypdf = None
    PdfReader = None
    TIENE_PYPDF = False

registrador = logging.getLogger("preal.procesar_documentos")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES DE PROCESAMIENTO DE DOCUMENTOS
# ─────────────────────────────────────────────────────────────────────────────

EXTENSIONES_DOCUMENTOS_PERMITIDAS = frozenset({".pdf", ".txt", ".md", ".markdown"})
MAXIMO_PAGINAS_PDF_PREDETERMINADO: int = 200

# Expresiones regulares para detectar encabezados comunes (capítulos, actos, secciones)
PATRON_ENCABEZADOS = re.compile(
    r"^(?:cap[ií]tulo|cap\.|secci[oó]n|parte|acto|escena|pr[oó]logo|ep[ií]logo|introducci[oó]n)\b",
    re.IGNORECASE,
)
PATRON_NUMERAL_ROMANO = re.compile(r"^(?:[IVXLCDM]+|[0-9]+)[\.\:\-\s]+", re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSIÓN DE TEXTO A FORMATO MARKDOWN
# ─────────────────────────────────────────────────────────────────────────────

def convertir_texto_a_markdown(texto_crudo: str) -> str:
    """Convierte texto plano extraído de un documento a un Markdown estructurado y limpio.

    - Detecta títulos y capítulos, asignándoles encabezados Markdown ('# ' o '## ').
    - Une saltos de línea involuntarios dentro de un mismo párrafo (reflow).
    - Preserva la separación de párrafos dobles.
    - Limpia guiones de corte de palabra al final de línea ('pa- <salto> labra' -> 'palabra').
    """
    if not texto_crudo:
        return ""

    # Normalizar retornos de carro Windows/Mac a Unix (\n)
    texto = texto_crudo.replace("\r\n", "\n").replace("\r", "\n")

    # Unir palabras cortadas por salto de línea con guion (ejemplo: "infor-\nmación" -> "información")
    texto = re.sub(r"(\w+)-\n(\w+)", r"\1\2", texto)

    lineas = texto.split("\n")
    bloques_procesados: list[str] = []
    lineas_parrafo_actual: list[str] = []

    def vaciar_parrafo_acumulado():
        if lineas_parrafo_actual:
            parrafo = " ".join(lineas_parrafo_actual)
            # Limpiar espacios múltiples
            parrafo = re.sub(r"[ \t]+", " ", parrafo).strip()
            if parrafo:
                bloques_procesados.append(parrafo)
            lineas_parrafo_actual.clear()

    for linea in lineas:
        linea_limpia = linea.strip()

        # Línea en blanco -> delimitador de párrafo
        if not linea_limpia:
            vaciar_parrafo_acumulado()
            continue

        # Si ya tiene formato de encabezado Markdown (# Encabezado)
        if linea_limpia.startswith("#"):
            vaciar_parrafo_acumulado()
            bloques_procesados.append(linea_limpia)
            continue

        # Detección de títulos por palabras clave o mayúsculas
        es_encabezado_capitulo = bool(PATRON_ENCABEZADOS.match(linea_limpia))
        es_linea_corta_mayusculas = (
            linea_limpia.isupper()
            and len(linea_limpia) < 60
            and not linea_limpia.endswith((".", ",", ";", ":"))
        )

        if es_encabezado_capitulo:
            vaciar_parrafo_acumulado()
            bloques_procesados.append(f"## {linea_limpia}")
        elif es_linea_corta_mayusculas:
            vaciar_parrafo_acumulado()
            # Convertir a mayúscula inicial para lectura agradable
            titulo_capitalizado = linea_limpia.title()
            bloques_procesados.append(f"# {titulo_capitalizado}")
        else:
            # Línea normal de párrafo
            lineas_parrafo_actual.append(linea_limpia)

    vaciar_parrafo_acumulado()
    return "\n\n".join(bloques_procesados)


def convertir_texto_a_plano(texto_crudo: str) -> str:
    """Limpia el texto eliminando marcas Markdown y normalizando párrafos para transcripción pura."""
    if not texto_crudo:
        return ""
    # Quitar marcas de encabezados '#', '**', '*', '__'
    texto = re.sub(r"^#+\s*", "", texto_crudo, flags=re.MULTILINE)
    texto = re.sub(r"[\*_]{1,3}(.*?)[\\*_]{1,3}", r"\1", texto)
    # Reflow de párrafos
    return convertir_texto_a_markdown(texto)


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACCIÓN DE TEXTO DESDE ARCHIVOS PDF
# ─────────────────────────────────────────────────────────────────────────────

def _extraer_texto_pdf_mediante_flujos_nativos(datos_bytes: bytes) -> str:
    """Extractor nativo de respaldo sin librerías externas para archivos PDF.

    Descomprime flujos FlateDecode (zlib) y extrae las cadenas de operadores de texto 'BT ... ET'.
    """
    fragmentos_texto: list[str] = []
    bloques_flujo = re.findall(b"stream[\r\n]+(.*?)[\r\n]+endstream", datos_bytes, re.DOTALL)

    for flujo in bloques_flujo:
        datos_descomprimidos: Optional[bytes] = None
        try:
            datos_descomprimidos = zlib.decompress(flujo)
        except Exception:
            datos_descomprimidos = flujo

        if not datos_descomprimidos:
            continue

        # Buscar bloques de texto PDF delimitados por BT (Begin Text) y ET (End Text)
        bloques_texto = re.findall(b"BT(.*?)ET", datos_descomprimidos, re.DOTALL)
        for bloque in bloques_texto:
            # Extraer cadenas de texto entre paréntesis (texto) Tj o [(texto)] TJ
            cadenas = re.findall(rb"\((.*?)\)\s*(?:Tj|'|\")", bloque)
            for cadena in cadenas:
                try:
                    texto_decodificado = cadena.decode("utf-8", errors="ignore")
                    if texto_decodificado.strip():
                        fragmentos_texto.append(texto_decodificado)
                except Exception:
                    continue

    return " ".join(fragmentos_texto)


def extraer_texto_de_pdf(
    fuente_pdf: Union[str, bytes],
    *,
    max_paginas: int = MAXIMO_PAGINAS_PDF_PREDETERMINADO,
    formato_salida: str = "markdown",
) -> str:
    """Extrae el contenido textual de un archivo PDF y lo formatea como Markdown o texto plano.

    Parámetros:
        fuente_pdf: Ruta en disco al archivo PDF o bytes en memoria del archivo.
        max_paginas: Límite máximo de páginas a procesar para prevenir bloqueos por documentos gigantes.
        formato_salida: 'markdown' para texto estructurado o 'txt' para texto plano.
    """
    if isinstance(fuente_pdf, str):
        if not os.path.isfile(fuente_pdf):
            raise FileNotFoundError(f"El archivo PDF especificado no existe: {fuente_pdf}")
        with open(fuente_pdf, "rb") as archivo:
            datos_bytes = archivo.read()
    else:
        datos_bytes = fuente_pdf

    if not datos_bytes:
        raise ValueError("El archivo PDF proporcionado está vacío.")

    paginas_extraidas: list[str] = []

    # 1. Intentar con pypdf si está disponible
    if TIENE_PYPDF and PdfReader is not None:
        try:
            lector = PdfReader(io.BytesIO(datos_bytes))
            total_paginas = len(lector.pages)

            if total_paginas > max_paginas:
                registrador.warning("El PDF supera el límite de páginas (%d > %d). Se limitará la extracción.", total_paginas, max_paginas)

            for num_pagina, pagina in enumerate(lector.pages[:max_paginas]):
                try:
                    texto_pagina = pagina.extract_text() or ""
                    if texto_pagina.strip():
                        paginas_extraidas.append(texto_pagina.strip())
                except Exception as error_pagina:
                    registrador.debug("Fallo en extracción de página %d: %s", num_pagina + 1, error_pagina)
        except Exception as error_pypdf:
            registrador.info("pypdf no pudo leer el documento (%s), intentando extractor nativo.", error_pypdf)

    # 2. Si no hay pypdf o no extrajo texto, usar el extractor nativo de respaldo
    if not paginas_extraidas:
        texto_nativo = _extraer_texto_pdf_mediante_flujos_nativos(datos_bytes)
        if texto_nativo.strip():
            paginas_extraidas.append(texto_nativo.strip())

    if not paginas_extraidas:
        raise ValueError("No se pudo extraer texto del PDF. Podría ser un documento escaneado (solo imágenes) o protegido.")

    texto_completo = "\n\n".join(paginas_extraidas)

    if formato_salida.lower() == "txt":
        return convertir_texto_a_plano(texto_completo)
    return convertir_texto_a_markdown(texto_completo)


# ─────────────────────────────────────────────────────────────────────────────
# LECTURA UNIVERSAL DE DOCUMENTOS (PDF, TXT, MD)
# ─────────────────────────────────────────────────────────────────────────────

def leer_documento_transcripcion(
    fuente_documento: Union[str, bytes],
    nombre_archivo: str,
    *,
    formato_salida: str = "markdown",
    max_paginas: int = MAXIMO_PAGINAS_PDF_PREDETERMINADO,
) -> str:
    """Función de alto nivel que lee cualquier archivo admitido (.pdf, .txt, .md, .markdown)

    y devuelve su contenido listo para ser usado como transcripción o guión de voz.
    """
    extension = os.path.splitext(nombre_archivo)[1].lower()
    if extension not in EXTENSIONES_DOCUMENTOS_PERMITIDAS:
        raise ValueError(
            f"Extensión no admitida ({extension}). Formatos válidos: {', '.join(sorted(EXTENSIONES_DOCUMENTOS_PERMITIDAS))}"
        )

    # Caso PDF
    if extension == ".pdf":
        return extraer_texto_de_pdf(
            fuente_documento,
            max_paginas=max_paginas,
            formato_salida=formato_salida,
        )

    # Caso TXT o Markdown (MD)
    if isinstance(fuente_documento, str):
        with open(fuente_documento, "rb") as archivo:
            datos_bytes = archivo.read()
    else:
        datos_bytes = fuente_documento

    # Intentar decodificación con UTF-8, Latin-1 y CP1252
    texto_decodificado = ""
    for codificacion in ("utf-8", "latin-1", "cp1252"):
        try:
            texto_decodificado = datos_bytes.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue

    if not texto_decodificado:
        raise ValueError("No se pudo decodificar el texto del archivo con codificaciones estándar.")

    if formato_salida.lower() == "txt":
        return convertir_texto_a_plano(texto_decodificado)
    return convertir_texto_a_markdown(texto_decodificado)
