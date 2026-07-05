import os
import jwt
import secrets
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel, EmailStr

from database import db, serialize_doc
from auth_utils import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    set_auth_cookies, clear_auth_cookies, get_current_user, require_admin,
    check_brute_force, record_failed_attempt, clear_attempts, log_audit,
    generate_totp_secret, totp_uri, verify_totp, get_jwt_secret, JWT_ALGORITHM,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TwoFALoginRequest(BaseModel):
    temp_token: str
    code: str


class TwoFAVerifyRequest(BaseModel):
    code: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    email = payload.email.lower()
    await check_brute_force(email)

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        await record_failed_attempt(email)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is deactivated")

    await clear_attempts(email)
    uid = str(user["_id"])

    if user.get("two_fa_enabled"):
        temp_token = jwt.encode(
            {"sub": uid, "type": "twofa", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
            get_jwt_secret(), algorithm=JWT_ALGORITHM,
        )
        return {"requires_2fa": True, "temp_token": temp_token}

    access_token = create_access_token(uid, email, user["role"])
    refresh_token = create_refresh_token(uid)
    set_auth_cookies(response, access_token, refresh_token)
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login": datetime.now(timezone.utc).isoformat()}})
    await log_audit(uid, "login", request=request)
    u = serialize_doc(user)
    u.pop("password_hash", None)
    u.pop("two_fa_secret", None)
    return u


@router.post("/2fa/login")
async def two_fa_login(payload: TwoFALoginRequest, request: Request, response: Response):
    try:
        decoded = jwt.decode(payload.temp_token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if decoded.get("type") != "twofa":
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await db.users.find_one({"_id": ObjectId(decoded["sub"])})
    if not user or not verify_totp(user.get("two_fa_secret", ""), payload.code):
        raise HTTPException(status_code=401, detail="Invalid authentication code")

    uid = str(user["_id"])
    access_token = create_access_token(uid, user["email"], user["role"])
    refresh_token = create_refresh_token(uid)
    set_auth_cookies(response, access_token, refresh_token)
    await log_audit(uid, "login_2fa", request=request)
    u = serialize_doc(user)
    u.pop("password_hash", None)
    u.pop("two_fa_secret", None)
    return u


@router.post("/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    await log_audit(user["id"], "logout")
    return {"message": "Logged out"}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    new_access = create_access_token(str(user["_id"]), user["email"], user["role"])
    response.set_cookie(key="access_token", value=new_access, httponly=True, secure=True, samesite="lax", max_age=900, path="/")
    return {"message": "Refreshed"}


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest):
    user = await db.users.find_one({"email": payload.email.lower()})
    if user:
        token = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({
            "token": token,
            "user_id": str(user["_id"]),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "used": False,
        })
        print(f"[PASSWORD RESET LINK] /reset-password?token={token} (for {payload.email})")
    return {"message": "If an account exists, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    rec = await db.password_reset_tokens.find_one({"token": payload.token, "used": False})
    if not rec or datetime.fromisoformat(rec["expires_at"]) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    await db.users.update_one({"_id": ObjectId(rec["user_id"])}, {"$set": {"password_hash": hash_password(payload.password)}})
    await db.password_reset_tokens.update_one({"_id": rec["_id"]}, {"$set": {"used": True}})
    return {"message": "Password reset successful"}


@router.post("/2fa/setup")
async def setup_2fa(user: dict = Depends(get_current_user)):
    secret = generate_totp_secret()
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"two_fa_secret": secret}})
    return {"secret": secret, "uri": totp_uri(secret, user["email"])}


@router.post("/2fa/enable")
async def enable_2fa(payload: TwoFAVerifyRequest, user: dict = Depends(get_current_user)):
    u = await db.users.find_one({"_id": ObjectId(user["id"])})
    if not u.get("two_fa_secret") or not verify_totp(u["two_fa_secret"], payload.code):
        raise HTTPException(status_code=400, detail="Invalid code")
    await db.users.update_one({"_id": u["_id"]}, {"$set": {"two_fa_enabled": True}})
    await log_audit(user["id"], "2fa_enabled")
    return {"message": "2FA enabled"}


@router.post("/2fa/disable")
async def disable_2fa(user: dict = Depends(get_current_user)):
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"two_fa_enabled": False, "two_fa_secret": None}})
    await log_audit(user["id"], "2fa_disabled")
    return {"message": "2FA disabled"}
