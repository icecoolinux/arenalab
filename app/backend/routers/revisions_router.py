from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from auth import get_current_user
from models import RevisionBody
from services.revisions_service import RevisionsService, RevisionError

router = APIRouter(prefix="/revisions", tags=["revisions"])

# Service instance
revision_service = RevisionsService()

@router.get("")
async def list_revisions(experiment_id: Optional[str] = Query(None), user = Depends(get_current_user)):
	return revision_service.list_revisions(experiment_id)


@router.post("")
async def create_revision(body: RevisionBody, user = Depends(get_current_user)):
	try:
		return revision_service.create_revision(body)
	except RevisionError as e:
		raise HTTPException(status_code=e.status_code, detail=e.detail)

@router.get("/{id}")
async def get_revision(id: str, user = Depends(get_current_user)):
	rev = revision_service.get_revision(id)
	if not rev:
		raise HTTPException(404, "Revision not found")
	return rev

@router.put("/{id}/results")
async def update_revision_results(id: str, results_text: str, user = Depends(get_current_user)):
	"""Update the results text for a revision."""
	try:
		return revision_service.update_results(id, results_text)
	except RevisionError as e:
		raise HTTPException(status_code=e.status_code, detail=e.detail)

@router.put("/{id}/favorite")
async def toggle_revision_favorite(id: str, user = Depends(get_current_user)):
	"""Toggle the favorite status of a revision."""
	try:
		return revision_service.toggle_favorite(id)
	except RevisionError as e:
		raise HTTPException(status_code=e.status_code, detail=e.detail)

@router.get("/{id}/dependencies")
async def check_revision_dependencies_endpoint(id: str, user = Depends(get_current_user)):
	"""Check dependencies for a revision before deletion."""
	try:
		return revision_service.check_dependencies(id)
	except RevisionError as e:
		raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.delete("/{id}")
async def delete_revision(id: str, confirmed: bool = Query(False), user = Depends(get_current_user)):
	"""
	Delete a revision by moving it to trash.

	First call without confirmed=true will check for dependencies and return warnings.
	If warnings exist, client must call again with confirmed=true to proceed.
	"""
	try:
		return revision_service.delete_revision(id, confirmed)
	except RevisionError as e:
		raise HTTPException(status_code=e.status_code, detail=e.detail)