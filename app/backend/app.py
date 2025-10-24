import os
from dotenv import load_dotenv
from utils.file_tools import paths

# Load enviornment variables
# First try the main env file in workspace
env_path = os.path.join(paths.CONFIG_DIR, "secrets.env")
if os.path.exists(env_path):
	load_dotenv(env_path)
else:
	# Fallback to development env file
	load_dotenv("../config/.env.development")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter
from fastapi.responses import RedirectResponse, StreamingResponse, Response
from db import users
from auth import hash_password
from routers import auth_router, experiments_router, runs_router, settings_router, revisions_router, environments_router, files_router, plugins_router
import os
import httpx


app = FastAPI(
	title="ArenaLab API",
	description="""
	ArenaLab is a platform designed to simplify experimentation with **Unity ML-Agents**.
	
	## Features
	
	* **Experiment Management**: Organize and track ML experiments with a hierarchical structure
	* **Run Management**: Launch, monitor, and control ML-Agents training runs
	* **Plugin System**: Extensible architecture for custom algorithms
	* **Real-time Monitoring**: Live log streaming and TensorBoard integration
	* **Workspace-Centric**: Designed for persistent storage in containerized environments
	
	## Authentication
	
	All endpoints require JWT authentication. Use the `/api/auth/login` endpoint to obtain a token.
	
	## Architecture
	
	The API follows a three-tier hierarchy:
	1. **Experiments** - High-level project containers
	2. **Revisions** - Immutable versions of experiment configurations  
	3. **Runs** - Individual training executions with full snapshots
	""",
	version="1.0.0",
	contact={
		"name": "ArenaLab",
		"url": "https://github.com/your-org/arenalab",
	},
	license_info={
		"name": "MIT License",
		"url": "https://opensource.org/licenses/MIT",
	},
	openapi_tags=[
		{
			"name": "auth",
			"description": "Authentication and user management"
		},
		{
			"name": "experiments", 
			"description": "Experiment lifecycle management"
		},
		{
			"name": "runs",
			"description": "Training run execution and monitoring"
		},
		{
			"name": "revisions",
			"description": "Experiment revision management"
		},
		{
			"name": "environments",
			"description": "Unity environment management"
		},
		{
			"name": "settings",
			"description": "Application settings and configuration"
		}
	]
)
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


# Routers
api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router.router)
api_router.include_router(experiments_router.router)
api_router.include_router(runs_router.router)
api_router.include_router(settings_router.router)
api_router.include_router(revisions_router.router)
api_router.include_router(environments_router.router)
api_router.include_router(files_router.router)
api_router.include_router(plugins_router.router)
app.include_router(api_router)


# Next.js now serves frontend on port 3000, no static file serving needed

@app.get("/")
def root():
	"""Health check endpoint"""
	return {"status": "ok", "message": "ArenaLab API is running"}


@app.api_route("/tb", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def tb_root(request: Request):
	"""Proxy requests to TensorBoard root"""
	# When TensorBoard uses --path_prefix=/tb, we need to forward /tb to /tb/ (with trailing slash)
	tensorboard_url = "http://localhost:6006/tb/"

	# Forward query parameters
	if request.url.query:
		tensorboard_url += f"?{request.url.query}"

	async with httpx.AsyncClient() as client:
		response = await client.request(
			method=request.method,
			url=tensorboard_url,
			headers={key: value for key, value in request.headers.items() if key.lower() not in ['host', 'content-length']},
			content=await request.body(),
			follow_redirects=True
		)
		content = await response.aread()
		filtered_headers = {key: value for key, value in response.headers.items()
		                   if key.lower() not in ['content-encoding', 'transfer-encoding', 'connection', 'content-length']}
		return Response(
			content=content,
			status_code=response.status_code,
			headers=filtered_headers,
			media_type=response.headers.get("content-type")
		)


@app.api_route("/tb/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def tensorboard_proxy(request: Request, path: str):
	"""Proxy requests to TensorBoard running on port 6006"""
	# TensorBoard is configured with --path_prefix=/tb, so forward /tb/{path} to http://localhost:6006/tb/{path}
	tensorboard_url = f"http://localhost:6006/tb/{path}"

	# Forward query parameters
	if request.url.query:
		tensorboard_url += f"?{request.url.query}"

	async with httpx.AsyncClient() as client:
		# Forward the request to TensorBoard
		response = await client.request(
			method=request.method,
			url=tensorboard_url,
			headers={key: value for key, value in request.headers.items() if key.lower() not in ['host', 'content-length']},
			content=await request.body(),
			follow_redirects=True
		)

		# Read the full response content
		content = await response.aread()

		# Return the response with appropriate headers
		filtered_headers = {key: value for key, value in response.headers.items()
		                   if key.lower() not in ['content-encoding', 'transfer-encoding', 'connection', 'content-length']}

		return Response(
			content=content,
			status_code=response.status_code,
			headers=filtered_headers,
			media_type=response.headers.get("content-type")
		)


@app.on_event("startup")
def on_start():
	# bootstrap admin
	if users.count_documents({}) == 0:
		email = os.getenv("ADMIN_EMAIL")
		pw = os.getenv("ADMIN_PASSWORD")

		if not email or not pw:
			print("[bootstrap] ADMIN_EMAIL o ADMIN_PASSWORD no están definidos, no se creará usuario admin.")
			return

		users.create_user(
			email=email,
			name="Admin",
			password_hash=hash_password(pw),
			role="admin"
		)
		print(f"[bootstrap] Admin creado: {email}")
	
	# Initialize plugins (auto-discovery happens on import)
	try:
		from plugins import list_plugins
		registered_plugins = list_plugins()
		print(f"[bootstrap] Registered {len(registered_plugins)} plugins: {', '.join(registered_plugins)}")
	except ImportError:
		print("[bootstrap] Warning: Could not initialize plugins")