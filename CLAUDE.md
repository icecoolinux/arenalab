# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Local Development Setup
```bash
# Set workspace environment variable for development
export WORKSPACE=./workspace

# Load development environment variables (optional)
# Create your own .env.development based on app/config/.env.development
source app/config/.env.development

# Start MongoDB (required for backend)
docker run --name mongodb -p 27017:27017 \
  -v $(pwd)/workspace/mongo:/data/db mongo:latest

# Backend development (from project root, with conda environment)
cd app/backend
conda activate mlagents
python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload

# Frontend development  
cd app/frontend
npm run dev
```

### Build Commands
```bash
# Frontend build (dynamic Next.js mode)
cd app/frontend
npm run build

# Docker Production Build
docker build --target prod -t arenalab:prod -f app/docker/Dockerfile .

# Docker Development Build  
docker build --target dev -t arenalab:dev -f app/docker/Dockerfile .

# Run Production Container (WORKSPACE is built-in via ENV)
docker run --gpus all -p 8000:8000 -p 6006:6006 \
  -v $(pwd)/workspace:/workspace --name arenalab-prod arenalab:prod

# Run Development Container (with live code editing) 
docker run --gpus all -p 8000:8000 -p 6006:6006 \
  -v $(pwd)/workspace:/workspace \
  -v $(pwd)/app:/app \
  --name arenalab-dev arenalab:dev
```

### Development Workflow

**Prerequisites for Development Mode:**
```bash
# Clone ML-Agents in local ./app directory (required for dev container)
cd app  
git clone --branch release_22 https://github.com/Unity-Technologies/ml-agents.git
```

**Production vs Development Builds:**
- **Production (`--target prod`)**: Self-contained image with all code copied inside
- **Development (`--target dev`)**: Uses bind-mounts for live code editing
  - `/app` directory is bind-mounted from host
  - Changes to local files reflect immediately in container
  - Hot reload enabled for FastAPI backend

### Linting
```bash
cd app/frontend
npm run lint
```

## Architecture Overview

### Workspace-Centric Design
The workspace directory (configurable via `WORKSPACE` environment variable, defaults to `/workspace`) is the persistent storage heart of the application:
- `${WORKSPACE}/mongo` - MongoDB data persistence
- `${WORKSPACE}/experiments/<exp_name>_<exp_id>/revisions/<rev_name>_<rev_id>/runs/<run_id>/results/` - TensorBoard event files per run
- `${WORKSPACE}/experiments/<exp_name>_<exp_id>/revisions/<rev_name>_<rev_id>/config.yaml` - YAML configuration per revision
- `${WORKSPACE}/experiments/<exp_name>_<exp_id>/revisions/<rev_name>_<rev_id>/runs/<run_id>/{config.yaml|stdout.log}` - Run artifacts, logs, config snapshots
- `${WORKSPACE}/envs` - Unity ML-Agents environment binaries (versioned .x86_64 builds)
- `${WORKSPACE}/config/secrets.env` - Environment variables and credentials
- `${WORKSPACE}/trash` - Soft-deleted items organized by type

**Note**: Directory names combine the resource name with its ID (e.g., `my-experiment_abc123`). Names are automatically sanitized (lowercase, spaces→hyphens, special chars removed).

**Environment Configuration:**
- **Production**: `WORKSPACE=/workspace` set via Docker ENV
- **Development**: `export WORKSPACE=./workspace` before starting services
- All backend code uses `file_tools.paths` utilities to handle workspace paths dynamically

### Backend Architecture (FastAPI)

**Core Components:**
- `app.py` - FastAPI application with auto-bootstrapping admin user from environment variables
- `runner.py` - ML-Agents process orchestration with subprocess management and status tracking
- `models.py` - Pydantic schemas for Experiments, Runs, Users
- `db.py` - MongoDB connection and database operations

**API Structure:**
- `auth_router.py` - JWT authentication with Argon2 password hashing
- `experiments_router.py` - CRUD operations for ML-Agents experiments
- `runs_router.py` - Run lifecycle management with real-time log streaming
- `settings_router.py` - Application configuration endpoints

**Key Patterns:**
- Each run creates isolated directories and snapshots configurations
- Process management tracks subprocess PIDs in `RUN_PROCS` dictionary
- Authentication middleware protects all API endpoints
- MongoDB stores metadata while filesystem holds artifacts

### Frontend Architecture (Next.js)

**Dynamic Next.js Mode:**
- Next.js running in dynamic mode (NOT static export) with server-side middleware
- Server-side authentication via `middleware.js` (requires Next.js server)
- App Router structure with authentication and site layout separation
- Client-side API calls to FastAPI backend via proxy rewrites
- Dynamic routes for database-driven content (`/experiments/[id]`, `/revisions/[id]`, `/runs/[id]`)

**Route Structure:**
- `app/(auth)/` - Authentication pages and flows  
- `app/(site)/` - Main application pages requiring authentication
- `app/(site)/experiments/` - Experiment management interface
- `app/(site)/runs/` - Run monitoring and control interface

### Process Management Architecture

**ML-Agents Integration:**
- `launch_run()` in `runner.py` spawns `mlagents-learn` subprocesses
- Commands constructed dynamically from experiment config and runtime flags
- Background threads monitor process completion and update database status
- TensorBoard automatically indexes run directories for visualization

**Container Orchestration:**
- Supervisor manages MongoDB, TensorBoard, and FastAPI processes
- All services run in single GPU-enabled container
- FastAPI serves both API and static frontend
- TensorBoard proxied through FastAPI with authentication

### Data Flow Patterns

1. **Experiment Creation:** Web UI → FastAPI → MongoDB (metadata) + Filesystem (YAML templates)
2. **Run Execution:** UI trigger → `launch_run()` → subprocess spawn → status tracking → artifact collection
3. **Real-time Monitoring:** WebSocket/SSE streams from log files + TensorBoard integration
4. **Persistent Storage:** All dynamic data in `${WORKSPACE}` for container restarts

### Development Status

**Authentication Bootstrap:**
- Admin user auto-created from `ADMIN_EMAIL`/`ADMIN_PASSWORD` environment variables
- JWT tokens for session management
- All API endpoints require authentication except health checks

### Plugin System Architecture

**Configuration Utilities (`utils/yaml_tools.py`):**
- Central module for all YAML and ML-Agents configuration operations
- Handles ML-Agents config structure (behaviors, hyperparameters, network_settings, etc.)
- Preserves YAML comments during configuration merging operations
- Provides deep dictionary merging for nested configurations
- Validates configurations before creating revisions

**Key Utilities:**
- `load_yaml_with_comments()` - Load YAML preserving comments and formatting
- `save_yaml_with_comments()` - Save YAML maintaining original comments
- `deep_merge_dict()` - Recursive merge for nested dictionaries
- `merge_hyperparameters_into_config()` - Smart injection into behaviors.*.hyperparameters
- `validate_mlagents_config()` - Schema validation for ML-Agents configs
- `get_behavior_names()` - Extract behavior names from configuration

**Plugin API Helpers (`plugins/core/api.py`):**

Three methods for creating revisions with different use cases:

1. **`create_revision_with_hyperparameters()`** - Recommended for hyperparameter tuning
   - Properly merges hyperparameters into nested ML-Agents structure
   - Used by: PBT plugin, hyperparameter sweeper
   - Example: `api.create_revision_with_hyperparameters(name="PBT_Gen1", hyperparameters={"learning_rate": 0.001})`

2. **`create_revision_with_config_updates()`** - For advanced config manipulation
   - Deep merging of arbitrary configuration sections
   - Used by: Curriculum trainer, custom plugins
   - Example: `api.create_revision_with_config_updates(name="BigNetwork", config_updates={...})`

3. **`create_revision()`** - Low-level method (enhanced with deep merging)
   - Backward compatible but now uses proper nested merging
   - Preserves comments when possible

**Plugin Development Best Practices:**
- **Use `create_revision_with_hyperparameters()`** for tuning learning_rate, batch_size, etc.
- YAML comments are preserved across revision creation (using ruamel.yaml)
- Deep merging ensures nested structure integrity (no more top-level pollution)
- Configuration validation prevents invalid ML-Agents configs
- All methods automatically load from latest revision when parent not specified

**Example Plugin Pattern:**
```python
@register_plugin(name="my_tuner", scope="experiment")
def my_tuner_plugin(context, api):
    # Run training with different hyperparameters
    for lr in [0.0001, 0.0003, 0.001]:
        run = api.create_run({"learning_rate": lr}, f"Test LR={lr}")
        api.wait_for_completion([run])

        # Create revision with best config (properly nested)
        if run.get_reward() > threshold:
            api.create_revision_with_hyperparameters(
                name=f"Best_LR_{lr}",
                hyperparameters={"learning_rate": lr},
                notes=f"Achieved reward: {run.get_reward()}"
            )
```