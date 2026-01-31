import os
from fastapi import APIRouter, Depends
from db import settings
from auth import get_current_user


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def get_settings(user = Depends(get_current_user)):
	data = settings.get_global_settings()
	# Mask API keys for security
	response = data.copy()
	if "openai_api_key" in response and response["openai_api_key"]:
		response["openai_api_key"] = "***" + response["openai_api_key"][-4:] if len(response["openai_api_key"]) > 4 else "***"
	if "anthropic_api_key" in response and response["anthropic_api_key"]:
		response["anthropic_api_key"] = "***" + response["anthropic_api_key"][-4:] if len(response["anthropic_api_key"]) > 4 else "***"

	# Provide defaults for model fields if not set
	if "openai_model" not in response or not response["openai_model"]:
		response["openai_model"] = "gpt-4o-mini"
	if "anthropic_model" not in response or not response["anthropic_model"]:
		response["anthropic_model"] = "claude-3-5-sonnet-20241022"
	if "llm_provider" not in response or not response["llm_provider"]:
		response["llm_provider"] = "openai"

	return response


@router.put("")
async def put_settings(payload: dict, user = Depends(get_current_user)):
	# Filter out masked API keys to prevent overwriting real keys
	filtered_payload = payload.copy()
	if "openai_api_key" in filtered_payload and filtered_payload["openai_api_key"].startswith("***"):
		del filtered_payload["openai_api_key"]
	if "anthropic_api_key" in filtered_payload and filtered_payload["anthropic_api_key"].startswith("***"):
		del filtered_payload["anthropic_api_key"]

	success = settings.update_global_settings(filtered_payload)
	return {"ok": success}