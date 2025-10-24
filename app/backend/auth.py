import os
from datetime import datetime, timedelta
from typing import Optional
from jose import jwt, JWTError
from passlib.hash import argon2
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from db import users


ALGO = "HS256"
SCHEME = HTTPBearer()


def hash_password(pw: str) -> str:
	return argon2.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
	return argon2.verify(pw, hashed)


def create_access_token(sub: str, expires_minutes: int = 1440) -> str:
	secret = os.getenv("JWT_SECRET", "devsecret")
	exp = datetime.utcnow() + timedelta(minutes=expires_minutes)
	return jwt.encode({"sub": sub, "exp": exp}, secret, algorithm=ALGO)


async def get_current_user(token: HTTPAuthorizationCredentials = Depends(SCHEME)):
	secret = os.getenv("JWT_SECRET", "devsecret")
	try:
		payload = jwt.decode(token.credentials, secret, algorithms=[ALGO])
		email = payload.get("sub")
	except JWTError:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
	
	user = users.find_by_email(email)
	if not user:
		raise HTTPException(status_code=401, detail="Usuario no encontrado")
	return user