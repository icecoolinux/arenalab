import os
from fastapi import APIRouter, Depends
from db import settings
from auth import get_current_user


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def get_settings(user = Depends(get_current_user)):
	return settings.get_global_settings()


@router.put("")
async def put_settings(payload: dict, user = Depends(get_current_user)):
	success = settings.update_global_settings(payload)
	return {"ok": success}