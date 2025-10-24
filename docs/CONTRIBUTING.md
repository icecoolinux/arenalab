# Contributing to ArenaLab

Thank you for your interest in contributing to ArenaLab! This document provides guidelines and information for contributors.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Development Setup](#development-setup)  
3. [Project Architecture](#project-architecture)
4. [Contributing Guidelines](#contributing-guidelines)
5. [Adding New Algorithms](#adding-new-algorithms)
6. [Testing](#testing)
7. [Code Style](#code-style)
8. [Pull Request Process](#pull-request-process)

## Getting Started

ArenaLab is a platform for Unity ML-Agents experimentation with a focus on:
- **Simplicity**: Clean, understandable code
- **Extensibility**: Plugin architecture for custom algorithms
- **Community**: Welcoming to contributors of all levels

## Development Setup

For local development with live code editing.

### Docker Development Setup

1. Clone this repository

2. Clone ML-Agents in your local directory (required for development)
```bash
cd app
git clone --branch release_22 --depth 1 https://github.com/Unity-Technologies/ml-agents.git ml-agents
```

3. Build development image
```bash
cd ..
docker build --target dev -t arenalab:dev -f app/docker/Dockerfile .
```

4. Run container with bind-mount for development
```bash
# Run container (first time)
docker run --gpus all \
  -p 3000:3000 \
  -v $(pwd)/workspace:/workspace \
  -v $(pwd)/app:/app \
  --name arenalab-dev arenalab:dev
```

5. Edit the configuration file `workspace/config/secrets.env`, you must uncomment and define admin credentials:
```bash
JWT_SECRET=put_something_random_and_long
#ADMIN_EMAIL=**admin@example.com**
#ADMIN_PASSWORD=**changeme**
MONGODB_URI=mongodb://localhost:27017
MONGO_DB=mlagents_lab
#OPENAI_API_KEY=...
```
6. Re-start container
```bash
# Stop the running container using Ctrl+C

# Start the container (use this command next time you want to start it)
docker start -ai arenalab-dev
```

7. Open in browser `http://localhost:3000`

**Development mode advantages:**
- Live editing: changes in `./app` are reflected immediately
- Hot reload enabled for FastAPI and frontend
- Direct access to logs and debugging


### Local development

1. Clone the Repository

```bash
git clone https://github.com/icecoolinux/arenalab.git
cd arenalab
```

2. Start mongo
```bash
# Make local data directory
mkdir workspace/mongo

# Build
docker build -t mongolocaldev -f app/docker/Dockerfile_mongolocaldev .

# Run the container (first time)
docker run \
  --name mongodb \
  -p 27017:27017 \
  -v <arenalab_path>/workspace/mongo:/data/db \
  mongolocaldev

# Start the container (next times)
docker start -ai mongodb
```

3. Build backend (first time)
```bash
conda create --name mlagents python=3.10.12
conda activate mlagents
cd app
git clone --branch release_22 --depth 1 https://github.com/Unity-Technologies/ml-agents.git ml-agents
python3 -m pip install --user ./ml-agents/ml-agents-envs
python3 -m pip install --user ./ml-agents/ml-agents
cd backend
pip install -r requirements.txt
```

4. Start backend
```bash
cd app/backend
conda activate mlagents
export WORKSPACE=../../workspace && python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

5. Tensorboard
```bash
# On arenalab root directory
conda activate mlagents
tensorboard --logdir=./workspace/experiments --host=0.0.0.0 --port=6006
```

6. Start frontend
```bash
cd app/frontend
npm run dev
```

7. Open in browser `http://localhost:3000`


Visit http://localhost:8000/docs for API documentation.

## Project Architecture

[ARCHITECTURE.md](ARCHITECTURE.md)

## Adding New Algorithms

> **Note:** The plugin system for adding custom algorithms will be available in the next version of ArenaLab. The infrastructure is fully implemented and documented, and will be included in the upcoming release.

One of the best ways to contribute is by implementing new algorithms! ArenaLab's plugin system makes this straightforward.

For detailed instructions on creating plugins, see the comprehensive **[Plugin Development Guide](PLUGINS_DEVELOPMENT.md)**. The guide covers:
- Function-based plugin architecture (ultra-simple: just write a function!)
- Plugin API reference with examples
- Creating runs and revisions
- Configuration management
- Best practices and testing
