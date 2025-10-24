# ArenaLab Architecture Documentation

This document provides a comprehensive overview of ArenaLab's architecture, design decisions, and implementation patterns.

## Table of Contents

1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [Backend Architecture](#backend-architecture)
4. [Frontend Architecture](#frontend-architecture)
5. [Data Models](#data-models)
6. [Plugin System](#plugin-system)
7. [Configuration Management](#configuration-management)
8. [Process Management](#process-management)
9. [Security Model](#security-model)
10. [Deployment Architecture](#deployment-architecture)

## Overview

ArenaLab is designed as a **workspace-centric** ML experimentation platform with a focus on:

- **Simplicity**: Clean, understandable codebase
- **Extensibility**: Plugin architecture for custom algorithms
- **Reliability**: Robust error handling and process management
- **Community**: Easy for contributors to understand and extend

### Key Design Principles

1. **Service Layer Pattern**: Business logic separated from HTTP concerns
2. **Plugin Architecture**: Easy to add new algorithms via plugin system
3. **Workspace-Centric**: Persistent storage in configurable workspace directory
4. **Clean Dependencies**: Each layer has clear responsibilities
5. **Comprehensive Testing**: Unit and integration tests with fixtures
6. **API-First**: Well-documented REST API with FastAPI

## Project Structure

ArenaLab follows a modern, modular architecture with clear separation of concerns:

```
app/
├── backend/
│   ├── app.py                    # FastAPI application entry point
│   ├── runner.py                 # ML-Agents process orchestration
│   ├── auth.py                   # JWT authentication logic
│   ├── models.py                 # Pydantic schemas
│   ├── db.py                     # MongoDB operations
│   ├── services/                 # Business logic layer
│   │   ├── experiments_service.py
│   │   ├── runs_service.py
│   │   ├── environments_service.py
│   │   └── revisions_service.py
│   ├── routers/                  # API endpoints (thin layer)
│   │   ├── auth_router.py
│   │   ├── environments_router.py
│   │   ├── experiments_router.py
│   │   ├── files_router.py
│   │   ├── plugins_router.py
│   │   ├── revisions_router.py
│   │   ├── runs_router.py
│   │   └── settings_router.py
│   ├── plugins/                  # Algorithm plugin system
│   │   ├── core/                 # Plugin infrastructure
│   │   │   ├── __init__.py       # Core exports
│   │   │   ├── registry.py       # Plugin registration & discovery
│   │   │   ├── runner.py         # Plugin execution engine
│   │   │   ├── api.py            # Plugin API for experiments/runs
│   │   │   └── database.py       # Plugin data collections
│   │   ├── pbt_plugin.py         # Population Based Training
│   │   ├── hyperparameter_sweeper_plugin.py
│   │   ├── auto_analyzer_plugin.py
│   │   └── performance_monitor_plugin.py
│   ├── utils/                    # Shared utilities
│   │   ├── yaml_tools.py         # YAML with comment preservation
│   │   ├── file_tools.py         # Workspace path utilities
│   │   ├── env_tools.py          # Environment variable handling
│   │   ├── dependency_checks.py  # Dependency validation
│   │   └── trash.py              # Soft-delete operations
│   ├── tests/                    # Comprehensive test suite
│   │   ├── fixtures/             # Test data and fixtures
│   │   ├── unit/                 # Unit tests
│   │   │   ├── test_plugins.py
│   │   │   ├── test_yaml_tools.py
│   │   │   ├── test_experiments_service.py
│   │   │   ├── test_runs_service.py
│   │   │   ├── test_environments_service.py
│   │   │   └── test_revisions_service.py
│   │   └── integration/          # API integration tests
│   │       └── test_api_experiments.py
│   └── run_tests.py              # Test runner
├── frontend/                     # Next.js React application
│   ├── src/app/
│   │   ├── (auth)/               # Authentication pages
│   │   │   ├── login/
│   │   │   └── logout/
│   │   └── (site)/               # Main application pages
│   │       ├── experiments/      # Experiment management UI
│   │       ├── revisions/        # Revision management UI
│   │       ├── runs/             # Run monitoring UI
│   │       ├── plugins/          # Plugin management UI
│   │       ├── environments/     # Environment setup UI
│   │       └── tb/               # TensorBoard integration
│   ├── src/components/           # Reusable UI components
│   │   ├── CLIFlagsEditor.js
│   │   ├── YamlEditor.js
│   │   ├── PluginCard.js
│   │   ├── DeleteConfirmationDialog.js
│   │   └── themes/               # Theme configurations
│   └── src/hooks/                # Custom React hooks
│       └── useDeleteWithConfirmation.js
├── config/                       # Environment configuration
├── docker/                       # Container configuration
│   ├── Dockerfile                # Multi-stage build (dev/prod)
│   └── Dockerfile_mongolocaldev  # MongoDB for local dev
└── supervisor/                   # Process management
    └── supervisord.conf          # MongoDB, TensorBoard, FastAPI
```

## Backend Architecture

### Layered Architecture

The backend follows a **layered architecture** pattern:

```
┌─────────────────────────────────────┐
│             Routers Layer           │
│        (HTTP Endpoints)             │
├─────────────────────────────────────┤
│            Services Layer           │
│         (Business Logic)            │
├─────────────────────────────────────┤
│            Plugins Layer            │
│       (Algorithm Implementations)   │
├─────────────────────────────────────┤
│             Data Layer              │
│        (Database & Files)           │
└─────────────────────────────────────┘
```

### 1. Routers Layer (`routers/`)

**Responsibility**: HTTP request/response handling, authentication, validation

Thin wrappers around service calls with Pydantic validation and consistent error handling.

**Available Routers**:
- `auth_router.py` - JWT authentication
- `experiments_router.py` - Experiment CRUD
- `revisions_router.py` - Revision management
- `runs_router.py` - Run lifecycle and monitoring
- `plugins_router.py` - Plugin management
- `environments_router.py` - Unity environment management
- `files_router.py` - File operations
- `settings_router.py` - Application settings

### 2. Services Layer (`services/`)

**Responsibility**: Business logic, orchestration, transaction management

Encapsulates business rules, domain-specific error handling, and coordinates between database and filesystem operations.

**Available Services**:
- `ExperimentService` - Experiment CRUD and statistics
- `RunService` - Run lifecycle and process orchestration
- `EnvironmentsService` - Environment management
- `RevisionsService` - Revision creation and YAML management

Services use custom exceptions that routers translate to HTTP responses.

### 3. Plugins Layer (`plugins/`)

**Responsibility**: Algorithm implementations, extensibility

The plugin system has evolved into a **function-based architecture** with modular core components:

#### Core Plugin Infrastructure (`plugins/core/`)

- **registry.py** - Plugin registration and discovery via decorators
- **runner.py** - Plugin execution lifecycle and status tracking
- **api.py** - Plugin API for creating runs, revisions, and accessing data
- **database.py** - Plugin execution tracking and settings storage

**Key Features**:
- Function-based plugins (no complex inheritance)
- Three scopes: `experiment`, `run`, `revision`
- Settings schema validation and automatic registration

#### Implemented Plugins

> **Note:** The plugin system will be available in the next version of ArenaLab. The following plugins are implemented but not included in the initial release:

1. **pbt_plugin.py** - Population Based Training
2. **hyperparameter_sweeper_plugin.py** - Grid/random search
3. **auto_analyzer_plugin.py** - Automatic analysis
4. **performance_monitor_plugin.py** - Performance tracking

### 4. Data Layer (`db.py`, `models.py`)

**Responsibility**: Data persistence, schema definition

```python
# Collection classes with domain-specific methods
class ExperimentsCollection(BaseCollection):
    def create_experiment(self, name: str, description: str, tags: List[str]) -> str:
        # Domain-specific database operations
```

**Collections**:
- `users` - User accounts and authentication
- `experiments` - Experiment metadata
- `revisions` - Configuration versions
- `runs` - Training execution records
- `environments` - Unity environment metadata

**Plugin Collections** (in `plugins/core/database.py`):
- `plugin_executions` - Plugin execution tracking
- `plugin_settings` - Plugin configuration

## Frontend Architecture

### Next.js Application

The frontend is a **Next.js React application** with:
- **App Router**: Modern Next.js routing structure
- **Client-Side Rendering**: Dynamic React components with `'use client'` directives
- **API Proxy**: Next.js rewrites proxy requests to FastAPI backend
- **Development Server**: Hot reload with Turbopack during development
- **No Static Export**: Standard Next.js mode with API rewrites

```
┌─────────────────────────────────────┐
│         Next.js App Router          │
│      (Client-Side Rendering)        │
├─────────────────────────────────────┤
│         API Proxy Layer             │
│   (/api/* → localhost:8000/api/*)   │
│   (/tb/* → localhost:8000/tb/*)     │
├─────────────────────────────────────┤
│            React Pages              │
│       (Dynamic Routing)             │
├─────────────────────────────────────┤
│       API Client + Auth             │
│  (JWT + localStorage + Cookies)     │
├─────────────────────────────────────┤
│          State Management           │
│  (Component-level useState/useRef)  │
└─────────────────────────────────────┘
```

### Route Structure

```
app/
├── (auth)/                # Authentication layout (light background)
│   ├── login/            # Login page
│   └── logout/           # Logout handling
├── (site)/               # Main application layout (dark theme)
│   ├── experiments/      # Experiment management
│   │   └── [id]/        # Experiment detail
│   ├── runs/             # Run monitoring
│   │   ├── [id]/        # Run detail with logs/TensorBoard
│   │   └── new/         # Create new run
│   ├── revisions/        # Revision management
│   │   ├── [id]/        # Revision detail
│   │   └── new/         # Create new revision
│   ├── plugins/          # Plugin management UI
│   ├── environments/     # Environment setup
│   └── tb/               # TensorBoard integration (proxied, empty directory)
```

**Note on TensorBoard**: The `tb/` directory exists but is empty. TensorBoard is accessed via Next.js rewrites in `next.config.mjs` that proxy to the FastAPI backend at `/tb/*`. The frontend does not have TensorBoard pages—it's entirely backend-proxied.

### Authentication & Middleware

**Dual-Storage Strategy**: JWT token stored in both `localStorage` (for API calls) and cookies (for middleware).

**Flow**: Login → token storage → middleware checks on navigation → API calls with Authorization header

### API Integration

**API Client** (`api/api-client.js`): Centralized fetch wrapper with domain-specific functions for experiments, runs, revisions, plugins, and environments.

**Configuration** (`next.config.mjs`): API and TensorBoard proxying to FastAPI backend, 1GB upload limit.

### UI Components

**Reusable Components** (`components/`):
- `YamlEditor.js` - ML-Agents configuration editor (Ace Editor with dynamic import)
- `CLIFlagsEditor.js` - Runtime flags editor
- `PluginCard.js` - Plugin display card
- `DeleteConfirmationDialog.js` - Deletion confirmation
- `StarButton.js`, `ContextTag.js` - UI utilities

**Custom Hooks**: `useDeleteWithConfirmation.js` for deletion patterns with dependency checking.

### State Management

Component-level state only (no Redux/Zustand). Each component manages state with `useState`/`useEffect`/`useRef`. Polling for real-time updates.

### Styling Approach

Minimal custom CSS with global utility classes (`.btn`, `.card`, `.input`, `.table`) and inline styles. Dark theme, no TypeScript.

### Technical Stack

- **Next.js** 15.5.2, **React** 19.1.0
- **Ace Editor** for YAML editing
- Tailwind v4 (minimal usage)

### Key Patterns

- Separation of concerns with API client abstraction
- Custom hooks for reusable logic
- Server-side middleware for auth
- Dynamic imports for performance

## Data Models

### Hierarchical Experiment Structure

ArenaLab uses a **three-tier hierarchy** for organizing ML experiments:

```
                    ┌─────────────────────────┐
                    │      EXPERIMENT         │
                    │  (High-level project)   │
                    └────────────┬────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            │                    │                    │
            ▼                    ▼                    ▼
    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
    │  Revision v1 │    │  Revision v2 │    │  Revision v3 │
    │ (Config v1)  │    │ (Config v2)  │    │ (Config v3)  │
    └──────┬───────┘    └──────┬───────┘    └──────┬───────┘
           │                   │                   │
       ┌───┴───┐           ┌───┴───┐              │
       │       │           │       │              │
       ▼       ▼           ▼       ▼              ▼
    ┌────┐  ┌────┐      ┌────┐  ┌────┐        ┌────┐
    │Run │  │Run │      │Run │  │Run │        │Run │
    │1.1 │  │1.2 │      │2.1 │  │2.2 │        │3.1 │
    └────┘  └────┘      └────┘  └────┘        └────┘
   (Training executions with full snapshots)
```

### 1. Experiments

**Purpose**: High-level project containers

```python
class ExperimentModel(BaseModel):
    id: str
    name: str                    # Human-readable identifier
    description: str
    tags: List[str]             # Categorization
    plugins: List[Dict]         # Enabled plugins
    created_at: datetime
    updated_at: datetime
```

**Use Cases**:
- Organizing related research
- Grouping different approaches to the same problem
- Long-term project tracking
- Plugin attachment point

### 2. Revisions

**Purpose**: Immutable configuration snapshots

```python
class RevisionModel(BaseModel):
    id: str
    version: int                 # Auto-incrementing within experiment
    experiment_id: str
    name: str
    description: str
    yaml_path: str              # ML-Agents configuration
    cli_flags: Dict[str, Any]   # Default runtime parameters
    environment_id: str         # Unity environment reference
    created_by_plugin: bool     # Track plugin-created revisions
    created_at: datetime
```

**Immutability Rules**:
- Once created, revisions cannot be modified
- Changes require creating a new revision
- Enables reproducible research
- Clear version history

### 3. Runs

**Purpose**: Individual training executions

```python
class RunModel(BaseModel):
    id: str
    revision_id: str
    experiment_id: str          # Denormalized for queries
    yaml_snapshot: str          # Full config snapshot
    cli_flags_snapshot: Dict    # Runtime parameters
    status: str                 # running, completed, failed, etc.
    created_at: datetime
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    tb_logdir: str             # TensorBoard logs
    stdout_log_path: str       # Console output
    artifacts_dir: str         # Model checkpoints, etc.
    plugins: List[str]         # Attached plugins
```

**Key Features**:
- Complete configuration snapshots for reproducibility
- Process lifecycle tracking
- Artifact management
- Performance metrics storage
- Plugin execution tracking

## Plugin System

> **Note:** The plugin system is fully designed and implemented, but will be released in the next version of ArenaLab.

### Architecture Overview

The plugin system enables **easy extensibility** without modifying core code:

```
┌──────────────────────────────────────────────────────────────────┐
│                      CORE PLUGIN SYSTEM                          │
│  ┌────────────────┐  ┌────────────────┐  ┌─────────────────┐   │
│  │    Plugin      │  │     Plugin     │  │    Plugin       │   │
│  │   Registry     │  │     Runner     │  │      API        │   │
│  │  (Discovery)   │  │  (Execution)   │  │  (Operations)   │   │
│  └────────┬───────┘  └────────┬───────┘  └────────┬────────┘   │
│           │                   │                   │             │
│           └───────────────────┼───────────────────┘             │
│                               │                                 │
│  ┌────────────────────────────┴──────────────────────────────┐ │
│  │              Plugin Database (Executions & Settings)      │ │
│  └───────────────────────────────────────────────────────────┘ │
└────────────────────────────┬─────────────────────────────────────┘
                             │
        ┌────────────────────┴────────────────────┐
        │                                         │
        ▼                                         ▼
┌───────────────────────────┐  ┌──────────────────┐
│      BUILT-IN PLUGINS     │  │   COMMUNITY      │
│                           │  │    PLUGINS       │
├───────────────────────────┤  ├──────────────────┤
│ • PBT Plugin              │  │ • Custom Plugin  │
│ • HP Sweeper              │  │ • Future Plugins │
│ • Auto Analyzer           │  │                  │
│ • Perf Monitor            │  │                  │
└───────────────────────────┘  └──────────────────┘

        All plugins implement: (context, api) → execution
```

### Function-Based Plugin System

Simple function-based approach with decorator registration:

```python
@plugin(name="my_tuner", scope="experiment", description="...",
        settings_schema={...})
def my_tuner(context: PluginContext, api: PluginAPI):
    # Access settings, create runs, wait for completion
    # Find best run and create revision with best config
```

### Plugin Scopes

Plugins are manually triggered via the `/api/plugins/execute` endpoint. The scope determines what context and data the plugin receives:

1. **Experiment Scope**: Operates on an experiment, receives `experiment_id`, can create/manage multiple runs and revisions
2. **Run Scope**: Operates on a specific run, receives `run_id`, can analyze results and create new revisions
3. **Revision Scope**: Operates on a specific revision, receives `revision_id`, can create runs or new revisions

### Plugin API

Methods for run management (`create_run`, `wait_for_completion`), revision management (`create_revision_with_hyperparameters`), data access (`get_best_run`), and logging.

### Benefits

- Simple function-based creation
- Automatic registration and validation
- Three execution scopes (experiment/run/revision)
- Built-in tracking and community-friendly

## Configuration Management

### YAML Tools (`utils/yaml_tools.py`)

Provides YAML handling with **comment preservation** using ruamel.yaml, deep dictionary merging, and ML-Agents configuration validation.

## Process Management

### Hybrid Approach

Global in-memory dictionaries track active processes, status, and monitoring threads. Simple, fast, and container-lifecycle compatible.

### Process Lifecycle

States: Created → Starting → Running → (Completed/Failed/Stopped)

Background threads monitor process health with frequent startup checks and robust cleanup.

## Security Model

### Authentication

- **JWT tokens** with Argon2 password hashing
- CORS configuration and Pydantic input validation
- Role-based access: `admin` (full access) and `user` (standard access)
- Process isolation per run

## Deployment Architecture

### Container Strategy

**Single-Container Design**: CUDA-enabled container with MongoDB, FastAPI, TensorBoard, and Next.js frontend managed by Supervisor.

**Services**:
- MongoDB (port 27017)
- FastAPI backend (port 8000)
- TensorBoard (port 6006)
- Next.js frontend (port 3000)

**Frontend Deployment**:
- Next.js runs as a separate service on port 3000 in both development and production
- **Development**: `npm run dev` with hot reload
- **Production**: `npm run build` then `npm run start` serving the optimized build
- Next.js proxies API requests to FastAPI backend via rewrites in `next.config.mjs`

### Persistent Storage

**Workspace-centric design**:

```
/workspace/                              # Persistent volume mount
├── mongo/                               # MongoDB data
├── experiments/<exp_name>_<exp_id>/     # Named experiment directories
│   └── revisions/<rev_name>_<rev_id>/   # Named revision directories
│       ├── config.yaml                  # Revision configuration
│       └── runs/<run_id>/               # Run directories (by ID)
│           ├── config.yaml              # Run configuration snapshot
│           ├── stdout.log               # Run output logs
│           └── results/                 # TensorBoard event files
├── envs/                                # Unity environment binaries (.x86_64)
├── config/secrets.env                   # Environment variables
└── trash/                               # Soft-deleted items
```

**Environment Configuration**:
- **Production**: `WORKSPACE=/workspace` set via Docker ENV
- **Development**: `export WORKSPACE=./workspace` before starting services
- All backend code uses `file_tools.paths` utilities for dynamic workspace paths

### Benefits

- Single container deployment with GPU support
- All data persisted in `/workspace` volume
- Stateless design for horizontal scaling

## Future Considerations

- Microservices migration as complexity grows
- Message queues for async job processing
- Plugin marketplace and version management
- Multi-tenancy and resource quotas
