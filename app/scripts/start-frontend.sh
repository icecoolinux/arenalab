#!/bin/bash
set -e

cd /app/frontend

# 1) Asegurar dependencias en dev: si el bind-mount tapó node_modules, instalarlas acá
if [ ! -d "node_modules" ]; then
    echo "[frontend] node_modules no encontrado, instalando dependencias..."
    if [ -f "package-lock.json" ]; then
        npm ci
    else
        npm install
    fi
fi

# 2) Modo: dev forzado por env, y fallback a detección por .next/BUILD_ID
MODE="${FRONTEND_MODE:-auto}"

if [ "$MODE" = "dev" ]; then
    echo "[frontend] FRONTEND_MODE=dev -> arrancando Next en modo desarrollo"
    npm run dev -- -H 0.0.0.0 -p "${PORT:-3000}"
    exit $?
fi

if [ -f ".next/BUILD_ID" ]; then
    echo "[frontend] Build detectado (.next/BUILD_ID) -> modo producción"
    npm run start -- -p "${PORT:-3000}"
else
    echo "[frontend] Sin build detectado -> modo desarrollo"
    npm run dev -- -H 0.0.0.0 -p "${PORT:-3000}"
fi
