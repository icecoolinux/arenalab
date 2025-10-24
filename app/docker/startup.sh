#!/usr/bin/env bash
set -e
mkdir -p ${WORKSPACE}/{mongo,experiments,envs,config}

if [ -f "${WORKSPACE}/config/secrets.env" ]; then
    echo "secrets.env file exists."
else
    cp "/app/config/.env.example" "${WORKSPACE}/config/secrets.env"
fi

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
