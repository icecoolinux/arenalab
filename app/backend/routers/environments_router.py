from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from auth import get_current_user
from models import EnvironmentBody
from services.environments_service import EnvironmentsService, EnvironmentError
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/environments", tags=["environments"])

# Service instance
environment_service = EnvironmentsService()

@router.get("")
async def list_environments(user = Depends(get_current_user)):
	return environment_service.list_environments()

@router.post("/upload")
async def upload_environment(
	file: UploadFile = File(...),
	name: str = Form(...),
	description: str = Form(default=""),
	git_commit_url: str = Form(default=""),
	user = Depends(get_current_user)
):
	"""Upload and extract a compressed environment file"""
	try:
		return environment_service.upload_environment(
			file=file,
			name=name,
			description=description,
			git_commit_url=git_commit_url
		)
	except EnvironmentError as e:
		# Use 413 for file too large, otherwise use the exception's status_code
		if "too large" in str(e).lower():
			raise HTTPException(status_code=413, detail=e.detail)
		raise HTTPException(status_code=e.status_code, detail=e.detail)

if False:  # Keep old endpoint as fallback but disable it
	@router.post("")
	async def create_environment(body: EnvironmentBody, user = Depends(get_current_user)):
		"""Legacy endpoint - disabled in favor of upload endpoint"""
		raise HTTPException(
			status_code=400, 
			detail="This endpoint is deprecated. Use POST /environments/upload instead."
		)

@router.get("/{id}")
async def get_environment(id: str, user = Depends(get_current_user)):
	env = environment_service.get_environment(id)
	if not env:
		raise HTTPException(404, "Environment not found")
	return env

@router.get("/{id}/info")
async def get_environment_info_endpoint(id: str, user = Depends(get_current_user)):
	"""Get detailed information about an environment including filesystem status"""
	try:
		return environment_service.get_environment_info(id)
	except EnvironmentError as e:
		raise HTTPException(status_code=e.status_code, detail=e.detail)

@router.get("/{id}/dependencies")
async def check_environment_dependencies_endpoint(id: str, user = Depends(get_current_user)):
	"""Check dependencies for an environment before deletion."""
	try:
		return environment_service.check_dependencies(id)
	except EnvironmentError as e:
		raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.delete("/{id}")
async def delete_environment(id: str, confirmed: bool = Query(False), user = Depends(get_current_user)):
	"""
	Delete an environment by moving it to trash.

	First call without confirmed=true will check for dependencies and return warnings.
	If warnings exist, client must call again with confirmed=true to proceed.
	"""
	try:
		return environment_service.delete_environment(id, confirmed)
	except EnvironmentError as e:
		raise HTTPException(status_code=e.status_code, detail=e.detail)