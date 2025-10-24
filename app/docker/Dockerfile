ARG BASE=nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04
ARG UID=1000
ARG GID=1000

########################
# Common base
########################
FROM ${BASE} AS base
WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WORKSPACE=/workspace

# System packages and Node.js 22.x
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    curl \
    supervisor \
    vim nano \
    build-essential ca-certificates git gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && corepack enable \
    && npm -v && node -v \
    && rm -rf /var/lib/apt/lists/*

## Install Mongo
# Import GPG key
RUN curl -fsSL https://pgp.mongodb.com/server-7.0.asc | \
    gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg \
    --dearmor
# Create repository file
RUN echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] \
    https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" \
    | tee /etc/apt/sources.list.d/mongodb-org-7.0.list
RUN apt-get update
RUN apt-get install -y mongodb-org

# Non-root user (with configurable UID/GID to match the host)
ARG UID
ARG GID
RUN groupadd -g ${GID} app && useradd -m -u ${UID} -g ${GID} app

# Create base directories
RUN mkdir -p /app/{backend,frontend,config,supervisor,scripts} \
    && chown -R app:app /app

RUN mkdir -p ${WORKSPACE}/mongo \
    && chown -R app:app ${WORKSPACE}


# Install Python dependencies (cached if they don't change)
COPY --chown=app:app app/backend/requirements.txt /backend_requirements.txt
RUN pip3 install --no-cache-dir -r /backend_requirements.txt

# Clone and install ML-Agents (cached layer - won't change often)
WORKDIR /app
RUN git clone --branch release_22 --depth 1 https://github.com/Unity-Technologies/ml-agents.git ml-agents
WORKDIR /app/ml-agents
# HotFix: https://github.com/Unity-Technologies/ml-agents/pull/6251
RUN sed -i 's/torch>=2.1.1/torch>=2.1.1,<=2.8.0/g' ml-agents/setup.py 
RUN pip3 install --no-cache-dir ./ml-agents-envs
RUN pip3 install --no-cache-dir ./ml-agents

########################
# PROD image (copies code inside the image)
########################
FROM base AS prod

ENV BACKEND_MODE=prod

# Switch to app user for installations
USER app

# Copy frontend code and build
COPY --chown=app:app app/frontend /app/frontend
WORKDIR /app/frontend
RUN rm -rf node_modules .next
RUN npm ci
RUN npm run build
RUN npm prune --production

# Copy backend code
COPY --chown=app:app app/backend /app/backend

# Copy configuration and scripts
COPY --chown=app:app app/config /app/config
COPY --chown=app:app app/scripts /app/scripts
COPY --chown=app:app app/docker/startup.sh /startup.sh
RUN sed -i 's/\r$//' /app/scripts/*.sh && \
    chmod +x /app/scripts/*.sh

# Switch to root for final system configuration
USER root

# Configure supervisor
COPY app/supervisor/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
RUN chmod +x /startup.sh

# Switch back to app user for execution
USER app

WORKDIR /app
EXPOSE 3000
ENTRYPOINT ["/startup.sh"]

########################
# DEV image (doesn't copy code; expects bind-mount at /app)
########################
FROM base AS dev

ENV NODE_ENV=development \
    FRONTEND_MODE=dev \
    BACKEND_MODE=dev

# Additional development dependencies
RUN pip3 install --no-cache-dir uvicorn[standard] watchdog

# Configure supervisor for development and copy scripts
COPY app/supervisor/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY app/scripts /app/scripts
COPY app/docker/startup.sh /startup.sh
RUN chmod +x /startup.sh
RUN sed -i 's/\r$//' /app/scripts/*.sh && \
    chmod +x /app/scripts/*.sh

# Switch to app user
USER app

# In dev mode, /app will be bind-mounted, including ml-agents from host
# But ML-Agents is already installed from base stage, so it will work
WORKDIR /app

# Leave /app as "documented" mountpoint 
VOLUME ["/app"]

WORKDIR /app
EXPOSE 3000
ENTRYPOINT ["/startup.sh"]