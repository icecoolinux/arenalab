from fastapi import APIRouter, HTTPException, Depends
from db import users
from auth import create_access_token, hash_password, verify_password, get_current_user
from models import LoginBody, UserResponse


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginBody):
	user = users.find_by_email(body.email)
	if not user or not verify_password(body.password, user["password_hash"]):
		raise HTTPException(status_code=401, detail="Credenciales inválidas")
	
	# Update last login
	users.update_last_login(user["_id"])
	
	token = create_access_token(body.email)
	return {"token": token, "name": user['name']}


@router.get("/me")
async def get_me(user = Depends(get_current_user)):
	return UserResponse(
		_id=user["_id"],
		email=user["email"],
		name=user["name"],
		role=user.get("role", "user"),
		created_at=user["created_at"],
		last_login=user.get("last_login"),
		is_active=user.get("is_active", True)
	)
