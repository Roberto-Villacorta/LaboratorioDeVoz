"""Backend del Paquete PReal: Clonación, Almacenamiento y Síntesis de Voces
========================================================================
"""

from PReal.backend.base_datos import (
    DIRECTORIO_DATOS_PREDETERMINADO,
    DIRECTORIO_SALIDAS_PREDETERMINADO,
    DIRECTORIO_VOCES_PREDETERMINADO,
    RUTA_BASE_DATOS_PREDETERMINADA,
    asegurar_infraestructura_almacenamiento,
    inicializar_tablas_base_datos,
    obtener_conexion_base_datos,
)
from PReal.backend.clonar_voz import (
    DURACION_IDEAL_REFERENCIA_SEGUNDOS,
    DURACION_MAXIMA_REFERENCIA_SEGUNDOS,
    DURACION_MINIMA_REFERENCIA_SEGUNDOS,
    calcular_duracion_audio,
    concatenar_fragmentos_audio,
    extraer_clones_hablantes,
    extraer_referencias_por_segmento,
    preparar_clon_desde_archivo,
    sanitizar_nombre_hablante,
    seleccionar_fragmentos_referencia,
    transcribir_audio_referencia,
    validar_archivo_audio_para_clonacion,
)
from PReal.backend.almacenar_voz import (
    PerfilVoz,
    actualizar_perfil_voz,
    bloquear_toma_voz,
    desbloquear_toma_voz,
    eliminar_perfil_voz,
    guardar_perfil_voz,
    listar_perfiles_voz,
    obtener_perfil_voz,
    resolver_ruta_segura_voz,
)
from PReal.backend.usar_voz import (
    CondicionamientoVoz,
    ResultadoSintesisVoz,
    generar_audio_desde_perfil,
    normalizar_texto_para_sintesis,
    obtener_condicionamiento_por_id_perfil,
    preparar_condicionamiento_directo,
    resolver_condicionamiento_desde_perfil,
    sintetizar_con_voz,
)
from PReal.backend.procesar_documentos import (
    convertir_texto_a_markdown,
    convertir_texto_a_plano,
    extraer_texto_de_pdf,
    leer_documento_transcripcion,
)

__all__ = [
    # Base de datos e infraestructura
    "asegurar_infraestructura_almacenamiento",
    "obtener_conexion_base_datos",
    "inicializar_tablas_base_datos",
    "DIRECTORIO_DATOS_PREDETERMINADO",
    "DIRECTORIO_VOCES_PREDETERMINADO",
    "DIRECTORIO_SALIDAS_PREDETERMINADO",
    "RUTA_BASE_DATOS_PREDETERMINADA",
    # Clonación
    "extraer_clones_hablantes",
    "extraer_referencias_por_segmento",
    "seleccionar_fragmentos_referencia",
    "concatenar_fragmentos_audio",
    "validar_archivo_audio_para_clonacion",
    "transcribir_audio_referencia",
    "preparar_clon_desde_archivo",
    "sanitizar_nombre_hablante",
    "calcular_duracion_audio",
    "DURACION_MINIMA_REFERENCIA_SEGUNDOS",
    "DURACION_MAXIMA_REFERENCIA_SEGUNDOS",
    "DURACION_IDEAL_REFERENCIA_SEGUNDOS",
    # Almacenamiento
    "PerfilVoz",
    "guardar_perfil_voz",
    "obtener_perfil_voz",
    "listar_perfiles_voz",
    "actualizar_perfil_voz",
    "bloquear_toma_voz",
    "desbloquear_toma_voz",
    "eliminar_perfil_voz",
    "resolver_ruta_segura_voz",
    # Uso y Síntesis
    "CondicionamientoVoz",
    "ResultadoSintesisVoz",
    "resolver_condicionamiento_desde_perfil",
    "obtener_condicionamiento_por_id_perfil",
    "preparar_condicionamiento_directo",
    "sintetizar_con_voz",
    "generar_audio_desde_perfil",
    "normalizar_texto_para_sintesis",
    # Procesamiento de documentos
    "convertir_texto_a_markdown",
    "convertir_texto_a_plano",
    "extraer_texto_de_pdf",
    "leer_documento_transcripcion",
]
