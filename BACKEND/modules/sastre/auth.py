#!/usr/bin/env python3
import os, jwt, secrets, json
from datetime import datetime, timedelta
from dataclasses import dataclass
from passlib.hash import bcrypt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

@dataclass
class AuthConfig:
    secret_key: str
    algorithm: str = "HS256"
    token_expiry_hours: int = 24
    enabled: bool = True
    
    @classmethod
    def from_env(cls):
        secret = os.getenv("SASTRE_JWT_SECRET") or secrets.token_hex(32)
        return cls(
            secret_key=secret,
            enabled=os.getenv("SASTRE_AUTH_ENABLED", "false").lower() == "true"
        )

config = AuthConfig.from_env()
USERS_FILE = "/data/SEARCH_ENGINEER/BACKEND/modules/sastre/users.json"

def _load_users():
    try:
        with open(USERS_FILE) as f: return json.load(f)
    except: return {}

def _save_users(users):
    with open(USERS_FILE, "w") as f: json.dump(users, f, indent=2)

def create_user(username, password, role="user"):
    users = _load_users()
    if username in users: return False
    users[username] = {"password_hash": bcrypt.hash(password), "role": role}
    _save_users(users)
    return True

def verify_user(username, password):
    users = _load_users()
    user = users.get(username)
    if user and bcrypt.verify(password, user["password_hash"]):
        return {"username": username, "role": user["role"]}
    return None

def delete_user(username):
    users = _load_users()
    if username not in users: return False
    del users[username]
    _save_users(users)
    return True

def create_token(user_data, token_type="access"):
    hours = config.token_expiry_hours if token_type == "access" else 168
    payload = {**user_data, "type": token_type, "exp": datetime.utcnow() + timedelta(hours=hours)}
    return jwt.encode(payload, config.secret_key, algorithm=config.algorithm)

def verify_token(token):
    try: return jwt.decode(token, config.secret_key, algorithms=[config.algorithm])
    except: return None

def create_token_pair(user_data):
    return {
        "access_token": create_token(user_data, "access"),
        "refresh_token": create_token(user_data, "refresh"),
        "token_type": "bearer"
    }

security = HTTPBearer(auto_error=False)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not config.enabled: return {"username": "anonymous", "role": "admin"}
    if not credentials: return None
    payload = verify_token(credentials.credentials)
    if not payload or payload.get("type") != "access": return None
    return {"username": payload.get("username"), "role": payload.get("role", "user")}

async def require_auth(user=Depends(get_current_user)):
    if not config.enabled: return {"username": "anonymous", "role": "admin"}
    if not user: raise HTTPException(status_code=401, detail="Not authenticated")
    return user

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m SASTRE.auth <cmd> [args]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "create-user":
        if create_user(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "user"):
            print("Created user:", sys.argv[2])
        else: print("User exists")
    elif cmd == "list-users":
        for u, d in _load_users().items():
            print(" ", u, "role:", d.get("role", "user"))
    elif cmd == "generate-token":
        users = _load_users()
        if sys.argv[2] in users:
            tokens = create_token_pair({"username": sys.argv[2], "role": users[sys.argv[2]]["role"]})
            print("Access:", tokens["access_token"])
