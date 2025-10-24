import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from auth import get_current_user
from utils.file_tools import paths

router = APIRouter(prefix="/workspace", tags=["files"])

@router.get("/{file_path:path}")
async def serve_workspace_file(file_path: str, user = Depends(get_current_user)):
	"""
	Serve files from the workspace directory.
	
	This endpoint accepts relative paths from workspace root:
	- /api/workspace/experiments/... -> ${WORKSPACE}/experiments/...
	- /api/workspace/tb_logs/... -> ${WORKSPACE}/tb_logs/...
	- etc.
	"""
	# Get workspace root from file_tools
	workspace_root = paths.WORKSPACE_ROOT
	
	# Build full path (file_path is already relative)
	full_path = os.path.join(workspace_root, file_path)
	
	# Normalize path to prevent directory traversal attacks
	full_path = os.path.normpath(full_path)
	if not full_path.startswith(workspace_root):
		raise HTTPException(status_code=403, detail="Access denied: Path outside workspace")
	
	# Check if file exists
	if not os.path.exists(full_path):
		raise HTTPException(status_code=404, detail="File not found")
	
	# Only serve files, not directories
	if not os.path.isfile(full_path):
		raise HTTPException(status_code=400, detail="Path is not a file")
	
	# Return the file
	return FileResponse(full_path)