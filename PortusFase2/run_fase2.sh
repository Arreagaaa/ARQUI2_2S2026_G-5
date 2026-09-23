#!/usr/bin/env bash
# Script de inicio rapido para PORTUS Fase 2 en Raspberry Pi 3 (Linux)
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR/.."

echo "Iniciando PORTUS Fase 2..."
python3 PortusFase2/run_fase2.py "$@"
