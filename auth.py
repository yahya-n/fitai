"""
FitAI — Authentication System
==============================
- Email/Password registration + login with bcrypt
- Google OAuth 2.0 (OIDC id_token verification)
- JWT access tokens (1h) + refresh tokens (7d) in HTTP-only cookies
- Rate limiting: 5 login attempts per 15 minutes per IP
- Middleware decorator for protecting routes
"""

import os
import jwt
import bcrypt
import logging
import functools
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, redirect, make_response, g
from models import db, User

logger = logging.getLogger("fitai.auth")

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# ═══════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════
JWT_SECRET = os.environ.get("JWT_SECRET", "fitai-jwt-secret-change-in-production-2026")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_HOURS = 1
REFRESH_TOKEN_DAYS = 7
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

# In-memory rate limiter store (per-IP)
_login_attempts = {}  # ip -> [(timestamp), ...]
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_MINUTES = 15


# ═══════════════════════════════════════
#  RATE LIMITER
# ═══════════════════════════════════════
def _check_rate_limit(ip):
    """Returns True if rate limit exceeded."""
    now = datetime.now(timezone.utc)
    window = timedelta(minutes=LOGIN_WINDOW_MINUTES)
    if ip not in _login_attempts:
        _login_attempts[ip] = []
    # Prune old entries
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < window]
    return len(_login_attempts[ip]) >= LOGIN_MAX_ATTEMPTS


def _record_attempt(ip):
    """Record a login attempt."""
    now = datetime.now(timezone.utc)
    if ip not in _login_attempts:
        _login_attempts[ip] = []
    _login_attempts[ip].append(now)


# ═══════════════════════════════════════
#  JWT HELPERS
# ═══════════════════════════════════════
def _create_access_token(user_id):
    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _create_refresh_token(user_id):
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token):
    """Decode and validate a JWT. Returns payload or None."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def _set_auth_cookies(response, user_id):
    """Set HTTP-only, Secure, SameSite=Strict JWT cookies on a response."""
    access = _create_access_token(user_id)
    refresh = _create_refresh_token(user_id)

    # Determine if we're on HTTPS
    is_secure = request.is_secure or request.headers.get("X-Forwarded-Proto") == "https"

    response.set_cookie(
        "fitai_access",
        access,
        httponly=True,
        secure=is_secure,
        samesite="Strict" if is_secure else "Lax",
        max_age=ACCESS_TOKEN_HOURS * 3600,
        path="/",
    )
    response.set_cookie(
        "fitai_refresh",
        refresh,
        httponly=True,
        secure=is_secure,
        samesite="Strict" if is_secure else "Lax",
        max_age=REFRESH_TOKEN_DAYS * 86400,
        path="/",
    )
    return response


# ═══════════════════════════════════════
#  AUTH MIDDLEWARE
# ═══════════════════════════════════════
def login_required(f):
    """Decorator: Require valid JWT to access endpoint."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            # Check if it's an API call or page request
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect("/login")
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    """Get the current user from JWT cookie, with automatic token refresh."""
    # Try access token first
    access_token = request.cookies.get("fitai_access")
    if access_token:
        payload = _decode_token(access_token)
        if payload and payload.get("type") == "access":
            try:
                user = db.session.get(User, int(payload["sub"]))
            except (ValueError, TypeError):
                user = None
            if user:
                return user

    # Try refresh token for auto-renewal
    refresh_token = request.cookies.get("fitai_refresh")
    if refresh_token:
        payload = _decode_token(refresh_token)
        if payload and payload.get("type") == "refresh":
            try:
                user = db.session.get(User, int(payload["sub"]))
            except (ValueError, TypeError):
                user = None
            if user:
                # Mark for cookie refresh in after_request
                g._refresh_user_id = user.id
                return user

    return None


def refresh_cookies_if_needed(response):
    """After-request hook to refresh cookies if access token was expired but refresh was valid."""
    user_id = getattr(g, "_refresh_user_id", None)
    if user_id:
        response = _set_auth_cookies(response, user_id)
    return response


# ═══════════════════════════════════════
#  PASSWORD HASHING (Bcrypt)
# ═══════════════════════════════════════
def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password, password_hash):
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# ═══════════════════════════════════════
#  ROUTES
# ═══════════════════════════════════════

@auth_bp.route("/register", methods=["POST"])
def register():
    """Register a new user with email/password."""
    ip = request.remote_addr
    if _check_rate_limit(ip):
        return jsonify({"error": "Too many attempts. Try again later."}), 429

    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()

    # Validation
    if not email or "@" not in email:
        return jsonify({"error": "Valid email is required."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    if not name:
        name = email.split("@")[0].title()

    # Check existing
    existing = User.query.filter_by(email=email).first()
    if existing:
        _record_attempt(ip)
        return jsonify({"error": "An account with this email already exists."}), 409

    # Create user
    user = User(
        email=email,
        password_hash=hash_password(password),
        name=name,
    )
    db.session.add(user)
    db.session.commit()

    logger.info(f"User registered: {email}")

    resp = make_response(jsonify({"success": True, "user": user.to_dict()}))
    return _set_auth_cookies(resp, user.id)


@auth_bp.route("/login", methods=["POST"])
def login():
    """Login with email/password."""
    ip = request.remote_addr
    if _check_rate_limit(ip):
        return jsonify({"error": "Too many login attempts. Try again in 15 minutes."}), 429

    _record_attempt(ip)

    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.password_hash:
        return jsonify({"error": "Invalid email or password."}), 401
    if not verify_password(password, user.password_hash):
        return jsonify({"error": "Invalid email or password."}), 401

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    logger.info(f"User logged in: {email}")

    resp = make_response(jsonify({"success": True, "user": user.to_dict()}))
    return _set_auth_cookies(resp, user.id)


@auth_bp.route("/google", methods=["POST"])
def google_login():
    """Login/register with Google OAuth 2.0 (id_token verification)."""
    data = request.json or {}
    id_token_str = data.get("credential") or data.get("id_token") or ""

    if not id_token_str:
        return jsonify({"error": "Google credential is required."}), 400

    if not GOOGLE_CLIENT_ID:
        return jsonify({"error": "Google OAuth is not configured on this server."}), 503

    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests

        idinfo = id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )

        google_id = idinfo.get("sub")
        email = idinfo.get("email", "").lower()
        name = idinfo.get("name", email.split("@")[0].title())
        avatar = idinfo.get("picture", "")

        if not email:
            return jsonify({"error": "Could not retrieve email from Google."}), 400

    except ValueError as e:
        logger.warning(f"Google token verification failed: {e}")
        return jsonify({"error": "Invalid Google token."}), 401

    # Find or create user
    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            # Link Google to existing email account
            user.google_id = google_id
            if avatar:
                user.avatar_url = avatar
        else:
            # New user via Google
            user = User(
                email=email,
                name=name,
                google_id=google_id,
                avatar_url=avatar,
            )
            db.session.add(user)

    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    logger.info(f"Google login: {email}")

    resp = make_response(jsonify({"success": True, "user": user.to_dict()}))
    return _set_auth_cookies(resp, user.id)


@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    """Clear auth cookies."""
    resp = make_response(jsonify({"success": True}))
    resp.delete_cookie("fitai_access", path="/")
    resp.delete_cookie("fitai_refresh", path="/")

    if request.method == "GET":
        resp = make_response(redirect("/login"))
        resp.delete_cookie("fitai_access", path="/")
        resp.delete_cookie("fitai_refresh", path="/")

    return resp


@auth_bp.route("/me", methods=["GET"])
def me():
    """Return current user info."""
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False}), 401
    return jsonify({"authenticated": True, "user": user.to_dict()})


@auth_bp.route("/google-config", methods=["GET"])
def google_config():
    """Return Google client ID for frontend initialization."""
    return jsonify({"client_id": GOOGLE_CLIENT_ID if GOOGLE_CLIENT_ID else None})
