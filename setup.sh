#!/usr/bin/env bash

set -e

# Nombre del entorno virtual
VENV_DIR=".venv"

echo "=== Configurando Entorno Virtual Python ==="

# 1. Detectar comando de Python disponible
if command -v python3 &>/dev/null; then
    PYTHON_CMD=python3
elif command -v python &>/dev/null; then
    PYTHON_CMD=python
else
    echo "Error: Python no está instalado o no se encuentra en el PATH."
    exit 1
fi

echo "Usando: $($PYTHON_CMD --version)"

# 2. Crear entorno virtual si no existe
if [ ! -d "$VENV_DIR" ]; then
    echo "Creando entorno virtual en '$VENV_DIR'..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
else
    echo "El entorno virtual '$VENV_DIR' ya existe."
fi

# 3. Activar el entorno virtual (compatible con Linux, macOS y Windows Git Bash)
if [ -f "$VENV_DIR/Scripts/activate" ]; then
    # Windows (Git Bash / MSYS2)
    source "$VENV_DIR/Scripts/activate"
elif [ -f "$VENV_DIR/bin/activate" ]; then
    # Linux / macOS / WSL
    source "$VENV_DIR/bin/activate"
else
    echo "Error: No se encontró el script de activación del entorno virtual."
    exit 1
fi

echo "Entorno virtual activado: $(python --version)"

# 4. Actualizar pip
echo "Actualizando pip..."
python -m pip install --upgrade pip

# 5. Localizar requirements.txt e instalar dependencias
REQ_FILE=""
if [ -f "requirements.txt" ]; then
    REQ_FILE="requirements.txt"
elif [ -f "PReal/requirements.txt" ]; then
    REQ_FILE="PReal/requirements.txt"
fi

if [ -n "$REQ_FILE" ]; then
    echo "Instalando dependencias desde '$REQ_FILE'..."
    python -m pip install -r "$REQ_FILE"
    echo "=== Instalación completada con éxito ==="
else
    echo "Aviso: No se encontró archivo 'requirements.txt'."
fi
