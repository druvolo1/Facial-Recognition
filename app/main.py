"""
Facial Recognition App with FastAPI and User Authentication
Based on plant_logs_server authentication system
"""
import os
import sys
from datetime import datetime, timedelta
from typing import Optional, AsyncGenerator, List
import secrets
import base64
from io import BytesIO
import json

from fastapi import FastAPI, Depends, HTTPException, Request, Form, status, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import Boolean, Integer, String, Text, Column, ForeignKey, select, DateTime, func, Numeric
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.exc import IntegrityError

from fastapi_users import FastAPIUsers, BaseUserManager, IntegerIDMixin, models, schemas, exceptions
from fastapi_users.authentication import AuthenticationBackend, CookieTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase, SQLAlchemyBaseUserTable
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase, SQLAlchemyBaseAccessTokenTable

from pydantic import EmailStr, BaseModel
from dotenv import load_dotenv
import requests
from PIL import Image

# Load environment variables
load_dotenv()

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "mariadb+aiomysql://app_user:testpass123@172.16.1.150:3306/facial_recognition")
SECRET = os.getenv("SECRET_KEY", "changeme")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123!")

# CodeProject.AI configuration
CODEPROJECT_HOST = os.getenv("CODEPROJECT_HOST", "172.16.1.150")
CODEPROJECT_PORT = int(os.getenv("CODEPROJECT_PORT", "32168"))
CODEPROJECT_BASE_URL = f"http://{CODEPROJECT_HOST}:{CODEPROJECT_PORT}/v1"

# Device security configuration
DEVICE_TOKEN_ROTATION_DAYS = int(os.getenv("DEVICE_TOKEN_ROTATION_DAYS", "30"))
REGISTRATION_CODE_EXPIRATION_MINUTES = int(os.getenv("REGISTRATION_CODE_EXPIRATION_MINUTES", "15"))

# Detection/Scan configuration
SCAN_RETENTION_MINUTES = int(os.getenv("SCAN_RETENTION_MINUTES", "60"))
DEFAULT_CONFIDENCE_THRESHOLD = float(os.getenv("DEFAULT_CONFIDENCE_THRESHOLD", "0.6"))
DEFAULT_PRESENCE_TIMEOUT_MINUTES = int(os.getenv("DEFAULT_PRESENCE_TIMEOUT_MINUTES", "2"))
DEFAULT_DETECTION_COOLDOWN_SECONDS = int(os.getenv("DEFAULT_DETECTION_COOLDOWN_SECONDS", "10"))

# Get the application directory
APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(APP_DIR)

# Create necessary directories
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
AUDIO_FOLDER = os.path.join(BASE_DIR, "audio")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)

print(f"[CONFIG] Database URL: {DATABASE_URL}")
print(f"[CONFIG] Base directory: {BASE_DIR}")
print(f"[CONFIG] Upload folder: {UPLOAD_FOLDER}")
print(f"[CONFIG] CodeProject.AI: {CODEPROJECT_BASE_URL}")

# ============================================================================
# DATABASE MODELS
# ============================================================================

class Base(DeclarativeBase):
    pass


class User(SQLAlchemyBaseUserTable[int], Base):
    """User table with custom fields"""
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # Standard FastAPI-Users fields
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Pending approval by default
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Custom fields
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dashboard_preferences: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    password_change_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AccessToken(SQLAlchemyBaseAccessTokenTable[int], Base):
    """Access token table for JWT tokens"""
    pass


class RegisteredFace(Base):
    """Track registered faces and their associated files"""
    __tablename__ = "registered_face"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The person's name - used as the user_id in CodeProject.AI
    person_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # The CodeProject.AI user_id (same as person_name but stored for clarity)
    codeproject_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Path to the image file
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    # CodeProject.AI endpoint URL where this face was registered
    codeproject_endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    # Location where this face was registered
    location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("location.id"), nullable=True)
    # When it was registered
    registered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    # User who registered this face
    registered_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("user.id"), nullable=True)
    # Profile photo (base64 encoded image for dashboard thumbnails)
    profile_photo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Location(Base):
    """Physical locations where devices will be deployed"""
    __tablename__ = "location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    address: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default='UTC')
    contact_info: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False)


class UserLocationRole(Base):
    """Many-to-many relationship between users and locations with roles"""
    __tablename__ = "user_location_role"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(Integer, ForeignKey("location.id"), nullable=False)
    # Role can be: 'location_admin' or 'location_user'
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    assigned_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("user.id"), nullable=True)


class ServerSettings(Base):
    """Global server settings"""
    __tablename__ = "server_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    setting_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    setting_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("user.id"), nullable=True)


class CodeProjectServer(Base):
    """CodeProject.AI servers available for facial recognition"""
    __tablename__ = "codeproject_server"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    friendly_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    endpoint_url: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False)


class Device(Base):
    """Devices registered for facial recognition (kiosks and scanners)"""
    __tablename__ = "device"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)  # UUID
    registration_code: Mapped[str] = mapped_column(String(6), unique=True, nullable=False)  # 6-digit code
    device_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("location.id"), nullable=True)
    # Device type: 'registration_kiosk' or 'people_scanner'
    device_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    codeproject_endpoint: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approved_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("user.id"), nullable=True)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Device authentication token
    device_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    token_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    token_rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Device-specific detection settings (if NULL, use .env defaults)
    confidence_threshold: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    presence_timeout_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    detection_cooldown_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class Detection(Base):
    """Tracks face detection events for dashboard display"""
    __tablename__ = "detection"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("device.device_id", ondelete="CASCADE"), nullable=False, index=True)
    person_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    location_id: Mapped[int] = mapped_column(Integer, ForeignKey("location.id", ondelete="CASCADE"), nullable=False, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)


# Database engine and session
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def create_db_and_tables():
    """Create database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


def generate_device_token() -> str:
    """Generate a cryptographically secure random token for device authentication"""
    return secrets.token_urlsafe(48)  # Returns ~64 characters


async def rotate_device_token_if_needed(device: Device, session: AsyncSession) -> Optional[str]:
    """
    Check if device token needs rotation and rotate if necessary.
    Returns new token if rotated, None otherwise.
    """
    if not device.device_token or not device.token_created_at:
        # Device has no token yet
        return None

    # Check if token is older than rotation period
    token_age = datetime.utcnow() - device.token_created_at
    if token_age > timedelta(days=DEVICE_TOKEN_ROTATION_DAYS):
        # Token expired - generate new one
        new_token = generate_device_token()
        device.device_token = new_token
        device.token_rotated_at = datetime.utcnow()
        await session.commit()

        print(f"[TOKEN] Rotated token for device {device.device_name or device.device_id[:8]}")
        return new_token

    return None


# Device authentication dependency
async def get_current_device(
    request: Request,
    session: AsyncSession = Depends(get_async_session)
) -> Device:
    """Authenticate device by device_id and token from request headers"""
    # Get device_id from header first
    device_id = request.headers.get("X-Device-ID")

    # If not in header, try to get from body
    if not device_id:
        try:
            body = await request.json()
            device_id = body.get("device_id")
        except:
            pass

    if not device_id:
        raise HTTPException(
            status_code=401,
            detail="Device ID required"
        )

    # Get device token from header
    device_token = request.headers.get("X-Device-Token")

    # Get device from database
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=401,
            detail="Device not found"
        )

    if not device.is_approved:
        raise HTTPException(
            status_code=403,
            detail="Device not approved"
        )

    # Validate device token
    if not device.device_token:
        raise HTTPException(
            status_code=401,
            detail="Device has no token. Please re-register."
        )

    if not device_token or device_token != device.device_token:
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing device token"
        )

    # Check if token needs rotation
    new_token = await rotate_device_token_if_needed(device, session)
    if new_token:
        # Token was rotated - include in response header for client to update
        request.state.new_device_token = new_token

    # Update last_seen
    device.last_seen = datetime.utcnow()
    await session.commit()

    return device


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)


async def get_access_token_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyAccessTokenDatabase(session, AccessToken)


# ============================================================================
# PYDANTIC REQUEST MODELS
# ============================================================================

class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: bool = True
    is_superuser: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class RegisterRequest(BaseModel):
    name: str
    photos: List[str]


class RecognizeRequest(BaseModel):
    image: str


# Device-specific request models
class DeviceRegisterRequest(BaseModel):
    device_id: str
    name: str
    photos: List[str]
    profile_photo: Optional[str] = None  # Base64 encoded profile photo for dashboard


class DeviceRecognizeRequest(BaseModel):
    device_id: str
    image: str


class UpdateSettingRequest(BaseModel):
    setting_key: str
    setting_value: Optional[str] = None


class RegisterDeviceRequest(BaseModel):
    device_id: str  # UUID from client


class ApproveDeviceRequest(BaseModel):
    device_name: str
    location_id: int
    device_type: str  # 'registration_kiosk', 'people_scanner', or 'location_dashboard'
    codeproject_endpoint: Optional[str] = None  # Not required for location_dashboard


class UpdateDeviceRequest(BaseModel):
    device_name: Optional[str] = None
    location_id: Optional[int] = None
    device_type: Optional[str] = None
    codeproject_endpoint: Optional[str] = None
    # Scanner detection settings
    confidence_threshold: Optional[float] = None
    presence_timeout_minutes: Optional[int] = None
    detection_cooldown_seconds: Optional[int] = None


class CreateLocationRequest(BaseModel):
    name: str
    address: Optional[str] = None
    description: Optional[str] = None
    timezone: Optional[str] = 'UTC'
    contact_info: Optional[str] = None


class UpdateLocationRequest(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None
    timezone: Optional[str] = None
    contact_info: Optional[str] = None


class AssignUserToLocationRequest(BaseModel):
    user_id: int
    role: str  # 'location_admin' or 'location_user'


class CreateCodeProjectServerRequest(BaseModel):
    friendly_name: str
    endpoint_url: str
    description: Optional[str] = None


class UpdateCodeProjectServerRequest(BaseModel):
    friendly_name: Optional[str] = None
    endpoint_url: Optional[str] = None
    description: Optional[str] = None


# ============================================================================
# USER SCHEMAS
# ============================================================================

class UserRead(schemas.BaseUser[int]):
    """Schema for reading user data"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_suspended: bool = False
    dashboard_preferences: Optional[str] = None


class UserCreate(schemas.BaseUserCreate):
    """Schema for creating users"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: bool = False
    is_verified: bool = False
    is_suspended: bool = False


class UserUpdate(schemas.BaseUserUpdate):
    """Schema for updating users"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_suspended: Optional[bool] = None
    dashboard_preferences: Optional[str] = None


# ============================================================================
# USER MANAGER
# ============================================================================

class CustomUserManager(IntegerIDMixin, BaseUserManager[User, int]):
    """Custom user manager with approval workflow and suspension support"""

    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        print(f"[AUTH] User {user.email} registered (pending approval)")

    async def on_after_forgot_password(self, user: User, token: str, request: Optional[Request] = None):
        print(f"[AUTH] User {user.email} forgot password. Token: {token}")

    async def on_after_request_verify(self, user: User, token: str, request: Optional[Request] = None):
        print(f"[AUTH] Verification requested for user {user.email}. Token: {token}")



async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield CustomUserManager(user_db)


# ============================================================================
# AUTHENTICATION SETUP
# ============================================================================

cookie_transport = CookieTransport(
    cookie_name="auth_cookie",
    cookie_max_age=3600,
    cookie_path="/",
    cookie_secure=False,
    cookie_httponly=True,
    cookie_samesite="lax"
)


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, int](
    get_user_manager,
    [auth_backend],
)

current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)


# ============================================================================
# WEBSOCKET CONNECTION MANAGER
# ============================================================================

class ConnectionManager:
    """Manages WebSocket connections for dashboard updates"""

    def __init__(self):
        # Dictionary mapping location_id to list of active WebSocket connections
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, location_id: int):
        """Accept and register a WebSocket connection for a location"""
        await websocket.accept()
        if location_id not in self.active_connections:
            self.active_connections[location_id] = []
        self.active_connections[location_id].append(websocket)
        print(f"[WEBSOCKET] New connection for location {location_id}. Total: {len(self.active_connections[location_id])}")

    def disconnect(self, websocket: WebSocket, location_id: int):
        """Remove a WebSocket connection"""
        if location_id in self.active_connections:
            self.active_connections[location_id].remove(websocket)
            print(f"[WEBSOCKET] Connection closed for location {location_id}. Remaining: {len(self.active_connections[location_id])}")
            if not self.active_connections[location_id]:
                del self.active_connections[location_id]

    async def broadcast_to_location(self, location_id: int, message: dict):
        """Send a message to all WebSocket connections for a specific location"""
        if location_id not in self.active_connections:
            return

        disconnected = []
        for connection in self.active_connections[location_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"[WEBSOCKET] Error sending to connection: {e}")
                disconnected.append(connection)

        # Clean up disconnected connections
        for connection in disconnected:
            self.disconnect(connection, location_id)

manager = ConnectionManager()


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(title="Facial Recognition App")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Mount static files
app.mount("/uploads", StaticFiles(directory=UPLOAD_FOLDER), name="uploads")
app.mount("/audio", StaticFiles(directory=AUDIO_FOLDER), name="audio")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


# ============================================================================
# STARTUP / SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def on_startup():
    """Initialize database and create admin user"""
    print(f"\n{'='*60}")
    print(f"[STARTUP] Facial Recognition App starting...")

    # Import database initialization
    from init_database import create_database as init_db

    # Try to create database if it doesn't exist
    try:
        db_created = await init_db()
        if not db_created:
            print(f"[STARTUP] ⚠ Database creation failed - see instructions above")
            print(f"[STARTUP] Application will attempt to continue...")
    except Exception as e:
        print(f"[STARTUP] ⚠ Database initialization warning: {e}")
        print(f"[STARTUP] Application will attempt to continue...")

    # Create tables
    try:
        await create_db_and_tables()
        print(f"[STARTUP] ✓ Database tables created/verified")
    except Exception as e:
        print(f"[STARTUP] ✗ Error creating tables: {e}")
        print(f"[STARTUP] Please ensure database exists and user has permissions")
        raise

    # Create admin user if doesn't exist
    try:
        async for session in get_async_session():
            async for user_db in get_user_db(session):
                async for user_manager in get_user_manager(user_db):
                    try:
                        # Try to get existing admin user
                        try:
                            existing_admin = await user_manager.get_by_email(ADMIN_EMAIL)
                            print(f"[STARTUP] ✓ Admin user already exists: {ADMIN_EMAIL}")
                        except exceptions.UserNotExists:
                            # User doesn't exist, create it
                            admin_user = UserCreate(
                                email=ADMIN_EMAIL,
                                password=ADMIN_PASSWORD,
                                is_active=True,
                                is_superuser=True,
                                is_verified=True,
                                first_name="Admin",
                                last_name="User"
                            )
                            await user_manager.create(admin_user)
                            print(f"[STARTUP] ✓ Admin user created: {ADMIN_EMAIL}")
                    except Exception as e:
                        print(f"[STARTUP] ⚠ Could not create admin user: {e}")
                        import traceback
                        traceback.print_exc()
                    break
                break
            break
    except Exception as e:
        print(f"[STARTUP] ⚠ Error during admin user creation: {e}")
        import traceback
        traceback.print_exc()

    print(f"[STARTUP] ✓ Startup complete")
    print(f"{'='*60}\n")


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register-account", response_class=HTMLResponse)
async def register_account_page(request: Request):
    """User registration page"""
    return templates.TemplateResponse("register_account.html", {"request": request})


@app.post("/auth/register")
async def register_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    manager: CustomUserManager = Depends(get_user_manager)
):
    """Register a new user (pending approval)"""
    try:
        user_create = UserCreate(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=False,  # Pending approval
            is_verified=False,
            is_suspended=False
        )

        user = await manager.create(user_create)

        print(f"[AUTH] New user registered: {email} (pending approval)")

        return templates.TemplateResponse("registration_pending.html", {"request": request})

    except IntegrityError:
        raise HTTPException(status_code=400, detail="User already exists")
    except Exception as e:
        print(f"[AUTH] Registration error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request, user: User = Depends(current_active_user)):
    """Password change page"""
    return templates.TemplateResponse("change_password.html", {
        "request": request,
        "user": user,
        "required": user.password_change_required
    })


@app.post("/api/change-password")
async def change_password(
    password_data: ChangePasswordRequest,
    user: User = Depends(current_active_user),
    user_manager: CustomUserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session)
):
    """User changes their own password"""
    try:
        # Verify current password
        is_valid = user_manager.password_helper.verify_and_update(
            password_data.current_password,
            user.hashed_password
        )[0]

        if not is_valid:
            raise HTTPException(status_code=400, detail="Current password is incorrect")

        # Update to new password
        user.hashed_password = user_manager.password_helper.hash(password_data.new_password)
        user.password_change_required = False
        await session.commit()

        print(f"[AUTH] Password changed for user: {user.email}")

        return {
            "success": True,
            "message": "Password changed successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[AUTH] Password change error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page - redirects to login if not authenticated"""
    try:
        # Try to get current user from cookie
        # If no cookie or invalid, redirect to login
        return RedirectResponse(url="/login", status_code=302)
    except:
        return RedirectResponse(url="/login", status_code=302)


@app.get("/no-location", response_class=HTMLResponse)
async def no_location_page(request: Request, user: User = Depends(current_active_user)):
    """Page shown to users who are not assigned to any locations"""
    return templates.TemplateResponse("no_location.html", {
        "request": request,
        "user": user
    })


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Main dashboard (requires authentication and location assignment)"""
    is_location_admin = False

    # Superadmins have access to all locations, so they bypass the check
    if not user.is_superuser:
        # Check if user has any location assignments
        result = await session.execute(
            select(UserLocationRole).where(UserLocationRole.user_id == user.id)
        )
        user_locations = result.scalars().all()

        # If no locations assigned, redirect to no-location page
        if not user_locations:
            return RedirectResponse(url="/no-location", status_code=302)

        # Check if user is admin of any location
        is_location_admin = any(loc.role == 'location_admin' for loc in user_locations)

        # Auto-select first location if none selected
        if user_locations:
            prefs = {}
            if user.dashboard_preferences:
                try:
                    prefs = json.loads(user.dashboard_preferences)
                except:
                    pass

            if not prefs.get('selected_location_id'):
                # Auto-select first location
                first_location_id = user_locations[0].location_id
                prefs['selected_location_id'] = first_location_id
                user.dashboard_preferences = json.dumps(prefs)
                await session.commit()
                print(f"[DASHBOARD] Auto-selected location {first_location_id} for user {user.email}")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "is_location_admin": is_location_admin
    })


@app.post("/auth/jwt/login")
async def custom_login(
    request: Request,
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager: CustomUserManager = Depends(get_user_manager),
    strategy: JWTStrategy = Depends(get_jwt_strategy),
):
    """Custom login endpoint that properly sets the auth cookie"""
    try:
        # Authenticate user
        user = await user_manager.authenticate(credentials)

        if user is None:
            raise HTTPException(status_code=400, detail="LOGIN_BAD_CREDENTIALS")

        # Check if user is suspended
        if user.is_suspended:
            raise HTTPException(status_code=403, detail="User account is suspended")

        # Check if user is active (approved)
        if not user.is_active:
            raise HTTPException(status_code=403, detail="User account is pending approval")

        # Generate token
        token = await strategy.write_token(user)

        # Check if password change is required
        password_change_required = user.password_change_required

        # Return success response
        response = JSONResponse(content={
            "detail": "Login successful",
            "password_change_required": password_change_required
        })

        # Set the auth cookie
        response.set_cookie(
            key="auth_cookie",
            value=token,
            httponly=True,
            max_age=3600,
            path="/",
            samesite="lax",
            secure=False  # Set to True if using HTTPS
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        print(f"[LOGIN] Error: {e}")
        raise HTTPException(status_code=400, detail="LOGIN_BAD_CREDENTIALS")


@app.post("/auth/logout")
async def logout(response: HTMLResponse):
    """Logout user"""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("auth_cookie")
    return response


# ============================================================================
# ADMIN ROUTES
# ============================================================================

# Helper dependency to check if user has admin privileges (superadmin or location admin)
async def require_any_admin_access(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Require user to be either a superadmin or location admin"""
    if user.is_superuser:
        return user

    # Check if user is admin of any location
    result = await session.execute(
        select(UserLocationRole).where(
            UserLocationRole.user_id == user.id,
            UserLocationRole.role == 'location_admin'
        )
    )
    admin_locations = result.scalars().all()
    if admin_locations:
        return user

    raise HTTPException(status_code=403, detail="Admin access required")


@app.get("/admin/manage", response_class=HTMLResponse)
async def admin_manage_page(request: Request, user: User = Depends(require_any_admin_access)):
    """Combined admin management page - for superadmins and location admins"""
    return templates.TemplateResponse("admin_manage.html", {"request": request, "user": user})


@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, user: User = Depends(current_superuser)):
    """Admin user management page - redirects to new combined page"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin/manage")


@app.get("/admin/locations", response_class=HTMLResponse)
async def admin_locations_page(request: Request, user: User = Depends(current_superuser)):
    """Admin location management page - redirects to new combined page"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin/manage")


@app.get("/api/admin/overview")
async def get_admin_overview(
    location_id: Optional[int] = None,
    user: User = Depends(require_any_admin_access),
    session: AsyncSession = Depends(get_async_session)
):
    """Get overview stats for the management dashboard"""
    stats = {
        "is_superuser": user.is_superuser,
        "total_users": 0,
        "total_locations": 0,
        "total_devices": 0,
        "pending_devices": 0,
        "total_registered_faces": 0,
        "managed_locations": []
    }

    # Verify location access if filtering by specific location
    if location_id and not user.is_superuser:
        # Check if user has access to this location
        result = await session.execute(
            select(UserLocationRole).where(
                UserLocationRole.user_id == user.id,
                UserLocationRole.location_id == location_id
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Access denied to this location")

    if user.is_superuser:
        # Superadmin sees everything (or filtered by location_id)

        if location_id:
            # Filtering by specific location
            # Count users assigned to this location
            user_count = await session.execute(
                select(func.count(func.distinct(UserLocationRole.user_id))).where(
                    UserLocationRole.location_id == location_id
                )
            )
            stats["total_users"] = user_count.scalar()

            # Location count is always 1 when filtering
            stats["total_locations"] = 1

            # Count devices in this location
            device_count = await session.execute(
                select(func.count(Device.id)).where(
                    Device.is_approved == True,
                    Device.location_id == location_id
                )
            )
            stats["total_devices"] = device_count.scalar()

            # Count ALL pending devices (not filtered - pending devices have no location yet)
            pending_count = await session.execute(
                select(func.count(Device.id)).where(Device.is_approved == False)
            )
            stats["pending_devices"] = pending_count.scalar()

            # Count unique registered people in this location
            face_count = await session.execute(
                select(func.count(func.distinct(RegisteredFace.person_name))).where(
                    RegisteredFace.location_id == location_id
                )
            )
            stats["total_registered_faces"] = face_count.scalar()
        else:
            # Show all locations (no filter)
            # Count users
            user_count = await session.execute(select(func.count(User.id)))
            stats["total_users"] = user_count.scalar()

            # Count locations
            location_count = await session.execute(select(func.count(Location.id)))
            stats["total_locations"] = location_count.scalar()

            # Count all devices
            device_count = await session.execute(
                select(func.count(Device.id)).where(Device.is_approved == True)
            )
            stats["total_devices"] = device_count.scalar()

            # Count pending devices
            pending_count = await session.execute(
                select(func.count(Device.id)).where(Device.is_approved == False)
            )
            stats["pending_devices"] = pending_count.scalar()

            # Count unique registered people (not total photos)
            face_count = await session.execute(select(func.count(func.distinct(RegisteredFace.person_name))))
            stats["total_registered_faces"] = face_count.scalar()

        # Get all locations for managed_locations dropdown (always show all for superadmin)
        locations_result = await session.execute(select(Location))
        all_locations = locations_result.scalars().all()
        stats["managed_locations"] = [
            {"id": loc.id, "name": loc.name} for loc in all_locations
        ]

    else:
        # Location admin sees only their locations
        # Get ALL user's locations (both admin and user roles)
        all_user_locations = await session.execute(
            select(UserLocationRole, Location)
            .join(Location)
            .where(UserLocationRole.user_id == user.id)
        )
        all_locs = all_user_locations.all()
        all_location_ids = [loc.id for _, loc in all_locs]
        stats["managed_locations"] = [
            {"id": loc.id, "name": loc.name} for _, loc in all_locs
        ]

        # Get locations where user is admin (for permission filtering)
        admin_locations = await session.execute(
            select(UserLocationRole, Location)
            .join(Location)
            .where(
                UserLocationRole.user_id == user.id,
                UserLocationRole.role == 'location_admin'
            )
        )
        admin_locs = admin_locations.all()
        admin_location_ids = [loc.id for _, loc in admin_locs]
        stats["admin_location_ids"] = admin_location_ids

        # Determine which location IDs to use for counts
        if location_id:
            # Filtering by specific location - use only that one
            location_ids = [location_id]
            stats["total_locations"] = 1
        else:
            # Show all managed locations
            location_ids = all_location_ids
            stats["total_locations"] = len(location_ids)

        if location_ids:
            # Count devices in managed/filtered locations
            device_count = await session.execute(
                select(func.count(Device.id)).where(
                    Device.is_approved == True,
                    Device.location_id.in_(location_ids)
                )
            )
            stats["total_devices"] = device_count.scalar()

            # Count ALL pending devices (not filtered - pending devices have no location yet)
            pending_count = await session.execute(
                select(func.count(Device.id)).where(Device.is_approved == False)
            )
            stats["pending_devices"] = pending_count.scalar()

            # Count unique registered people in managed/filtered locations
            face_count = await session.execute(
                select(func.count(func.distinct(RegisteredFace.person_name))).where(
                    RegisteredFace.location_id.in_(location_ids)
                )
            )
            stats["total_registered_faces"] = face_count.scalar()

            # Count users assigned to these locations
            user_count = await session.execute(
                select(func.count(func.distinct(UserLocationRole.user_id))).where(
                    UserLocationRole.location_id.in_(location_ids)
                )
            )
            stats["total_users"] = user_count.scalar()

    return stats


@app.get("/api/admin/users")
async def list_all_users(
    location_id: Optional[int] = None,
    user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """List all users (admin only), optionally filtered by location"""

    if location_id:
        # Get user IDs assigned to this location
        location_assignments = await session.execute(
            select(UserLocationRole.user_id).where(
                UserLocationRole.location_id == location_id
            ).distinct()
        )
        location_user_ids = {user_id for (user_id,) in location_assignments.all()}

        # Get all users
        all_users_result = await session.execute(select(User))
        all_users = all_users_result.scalars().all()

        users = []
        for u in all_users:
            # Check if user has any location assignments
            has_locations_result = await session.execute(
                select(func.count(UserLocationRole.id)).where(
                    UserLocationRole.user_id == u.id
                )
            )
            location_count = has_locations_result.scalar()

            # Include if user is at selected location OR has no locations (pending)
            if u.id in location_user_ids or location_count == 0:
                users.append(u)
    else:
        # No filter - show all users
        result = await session.execute(select(User))
        users = result.scalars().all()

    # Get location assignments for all users
    user_locations = {}
    for u in users:
        loc_result = await session.execute(
            select(UserLocationRole, Location).join(Location).where(
                UserLocationRole.user_id == u.id
            )
        )
        assignments = loc_result.all()
        user_locations[u.id] = [
            {
                "location_id": loc.id,
                "location_name": loc.name,
                "role": assignment.role
            }
            for assignment, loc in assignments
        ]

    return {
        "current_user_id": user.id,
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "is_active": u.is_active,
                "is_superuser": u.is_superuser,
                "is_suspended": u.is_suspended,
                "is_verified": u.is_verified,
                "locations": user_locations.get(u.id, [])
            }
            for u in users
        ]
    }


@app.get("/api/users/{user_id}/locations")
async def get_user_locations(
    user_id: int,
    admin: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Get location assignments for a specific user (superadmin only)"""
    # Verify user exists
    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get user's location assignments
    result = await session.execute(
        select(UserLocationRole, Location).join(Location).where(
            UserLocationRole.user_id == user_id
        )
    )
    assignments = result.all()

    return {
        "user_id": user_id,
        "locations": [
            {
                "location_id": loc.id,
                "location_name": loc.name,
                "role": assignment.role,
                "assigned_at": assignment.assigned_at.isoformat()
            }
            for assignment, loc in assignments
        ]
    }


@app.get("/api/test-auth")
async def test_auth(
    request: Request,
    user: User = Depends(current_active_user)
):
    """Test endpoint to verify authentication is working"""
    cookies = request.cookies
    return {
        "authenticated": True,
        "user_id": user.id,
        "user_email": user.email,
        "cookies_present": list(cookies.keys())
    }


@app.get("/api/my-locations")
async def get_my_locations(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get current user's location assignments"""
    try:
        print(f"[GET-LOCATIONS] User: {user.email} (ID: {user.id}, Superuser: {user.is_superuser})")

        # Superadmins have access to all locations
        if user.is_superuser:
            result = await session.execute(select(Location))
            all_locations = result.scalars().all()
            print(f"[GET-LOCATIONS] Superuser - returning {len(all_locations)} locations")
            return {
                "user_id": user.id,
                "is_superuser": True,
                "locations": [
                    {
                        "location_id": loc.id,
                        "location_name": loc.name,
                        "role": "superadmin"
                    }
                    for loc in all_locations
                ]
            }

        # Get user's location assignments
        print(f"[GET-LOCATIONS] Regular user - querying UserLocationRole")
        result = await session.execute(
            select(UserLocationRole, Location).join(Location).where(
                UserLocationRole.user_id == user.id
            )
        )
        assignments = result.all()
        print(f"[GET-LOCATIONS] Found {len(assignments)} location assignments")

        locations_data = {
            "user_id": user.id,
            "is_superuser": False,
            "locations": [
                {
                    "location_id": loc.id,
                    "location_name": loc.name,
                    "role": assignment.role
                }
                for assignment, loc in assignments
            ]
        }
        print(f"[GET-LOCATIONS] Returning: {locations_data}")
        return locations_data

    except Exception as e:
        print(f"[GET-LOCATIONS] ERROR: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


@app.get("/api/users/me/selected-location")
async def get_selected_location(
    user: User = Depends(current_active_user)
):
    """Get the user's currently selected location"""
    if user.dashboard_preferences:
        try:
            prefs = json.loads(user.dashboard_preferences)
            return {
                "selected_location_id": prefs.get("selected_location_id")
            }
        except:
            pass

    return {"selected_location_id": None}


async def get_user_selected_location_and_role(user: User, session: AsyncSession):
    """Helper function to get user's selected location and their role for it"""
    # Superusers can access all locations
    if user.is_superuser:
        # Get selected location if set, otherwise return None
        selected_location_id = None
        if user.dashboard_preferences:
            try:
                prefs = json.loads(user.dashboard_preferences)
                selected_location_id = prefs.get("selected_location_id")
            except:
                pass

        return {
            "location_id": selected_location_id,
            "role": "superadmin",
            "is_superuser": True
        }

    # Get user's selected location from preferences
    selected_location_id = None
    if user.dashboard_preferences:
        try:
            prefs = json.loads(user.dashboard_preferences)
            selected_location_id = prefs.get("selected_location_id")
        except:
            pass

    # If no location selected, return None
    if not selected_location_id:
        return None

    # Check user's role for this location
    result = await session.execute(
        select(UserLocationRole).where(
            UserLocationRole.user_id == user.id,
            UserLocationRole.location_id == selected_location_id
        )
    )
    role_assignment = result.scalar_one_or_none()

    if not role_assignment:
        # User doesn't have access to this location
        return None

    return {
        "location_id": selected_location_id,
        "role": role_assignment.role,  # 'location_admin' or 'location_user'
        "is_superuser": False
    }


class SetLocationRequest(BaseModel):
    location_id: int


@app.post("/api/users/me/selected-location")
async def set_selected_location(
    request: SetLocationRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Set the user's currently selected location"""
    location_id = request.location_id

    # Verify the location exists
    loc_result = await session.execute(select(Location).where(Location.id == location_id))
    location = loc_result.scalar_one_or_none()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Verify user has access to this location (unless superuser)
    if not user.is_superuser:
        access_result = await session.execute(
            select(UserLocationRole).where(
                UserLocationRole.user_id == user.id,
                UserLocationRole.location_id == location_id
            )
        )
        access = access_result.scalar_one_or_none()

        if not access:
            raise HTTPException(status_code=403, detail="You don't have access to this location")

    # Update user preferences
    prefs = {}
    if user.dashboard_preferences:
        try:
            prefs = json.loads(user.dashboard_preferences)
        except:
            prefs = {}

    prefs["selected_location_id"] = location_id
    user.dashboard_preferences = json.dumps(prefs)

    await session.commit()

    return {
        "success": True,
        "selected_location_id": location_id,
        "location_name": location.name
    }


@app.post("/api/admin/users/{user_id}/approve")
async def approve_user(
    user_id: int,
    admin: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Approve a pending user (superadmin or location admin)"""
    # Check if user is superadmin or location admin
    is_location_admin = False
    admin_locations = []

    if not admin.is_superuser:
        # Check if they're a location admin
        result = await session.execute(
            select(UserLocationRole).where(
                UserLocationRole.user_id == admin.id,
                UserLocationRole.role == 'location_admin'
            )
        )
        admin_locations = result.scalars().all()

        if not admin_locations:
            raise HTTPException(status_code=403, detail="Only superadmins and location admins can approve users")

        is_location_admin = True

    # Get the user to approve
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Approve the user
    user.is_active = True
    await session.commit()

    # If approved by location admin, auto-assign to their location(s) as location_user
    if is_location_admin:
        for admin_loc in admin_locations:
            # Check if assignment already exists
            existing = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user_id,
                    UserLocationRole.location_id == admin_loc.location_id
                )
            )
            if not existing.scalar_one_or_none():
                # Create new assignment
                new_assignment = UserLocationRole(
                    user_id=user_id,
                    location_id=admin_loc.location_id,
                    role='location_user',
                    assigned_by_user_id=admin.id
                )
                session.add(new_assignment)

        await session.commit()
        print(f"[ADMIN] User {user.email} approved by location admin {admin.email} and assigned to {len(admin_locations)} location(s)")
    else:
        print(f"[ADMIN] User {user.email} approved by superadmin {admin.email}")

    return {"success": True, "message": f"User {user.email} approved"}


@app.get("/api/pending-users")
async def list_pending_users(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """List pending users (for superadmins and location admins)"""
    # Check if user is superadmin or location admin
    if not user.is_superuser:
        # Check if they're a location admin
        result = await session.execute(
            select(UserLocationRole).where(
                UserLocationRole.user_id == user.id,
                UserLocationRole.role == 'location_admin'
            )
        )
        admin_locations = result.scalars().all()

        if not admin_locations:
            raise HTTPException(status_code=403, detail="Access denied")

    # Get all pending users
    result = await session.execute(
        select(User).where(User.is_active == False, User.is_suspended == False)
    )
    pending_users = result.scalars().all()

    return {
        "success": True,
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "is_verified": u.is_verified
            }
            for u in pending_users
        ]
    }


@app.post("/api/admin/users/{user_id}/suspend")
async def suspend_user(
    user_id: int,
    admin: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Suspend a user"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_suspended = True
    await session.commit()

    print(f"[ADMIN] User suspended: {user.email}")

    return {"success": True, "message": f"User {user.email} suspended"}


@app.post("/api/admin/users/{user_id}/unsuspend")
async def unsuspend_user(
    user_id: int,
    admin: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Unsuspend a user"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_suspended = False
    await session.commit()

    print(f"[ADMIN] User unsuspended: {user.email}")

    return {"success": True, "message": f"User {user.email} unsuspended"}


@app.post("/api/admin/users/{user_id}/make-admin")
async def make_admin(
    user_id: int,
    admin: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Make a user an admin (superuser)"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Don't allow removing your own admin status accidentally
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own admin status")

    user.is_superuser = True
    await session.commit()

    print(f"[ADMIN] User promoted to admin: {user.email}")

    return {"success": True, "message": f"User {user.email} is now an admin"}


@app.post("/api/admin/users/{user_id}/remove-admin")
async def remove_admin(
    user_id: int,
    admin: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Remove admin status from a user"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Don't allow removing your own admin status
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot remove your own admin status")

    user.is_superuser = False
    await session.commit()

    print(f"[ADMIN] Admin status removed from user: {user.email}")

    return {"success": True, "message": f"Admin status removed from {user.email}"}


@app.post("/api/admin/users/create")
async def create_user_by_admin(
    user_data: CreateUserRequest,
    admin: User = Depends(current_superuser),
    user_manager: CustomUserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session)
):
    """Admin creates a new user with temporary password"""
    try:
        # Create user with fastapi-users
        user_create = UserCreate(
            email=user_data.email,
            password=user_data.password,
            is_active=user_data.is_active,
            is_superuser=user_data.is_superuser,
            is_verified=True,  # Admin-created users are verified
            first_name=user_data.first_name,
            last_name=user_data.last_name
        )

        new_user = await user_manager.create(user_create)

        # Query the user again in our session to update the password_change_required flag
        result = await session.execute(select(User).where(User.id == new_user.id))
        user_to_update = result.scalar_one_or_none()

        if user_to_update:
            user_to_update.password_change_required = True
            await session.commit()

        print(f"[ADMIN] User created by admin {admin.email}: {new_user.email}")

        return {
            "success": True,
            "message": f"User {new_user.email} created successfully",
            "user_id": new_user.id,
            "email": new_user.email
        }

    except exceptions.UserAlreadyExists:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    except Exception as e:
        print(f"[ADMIN] Error creating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    admin: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
    user_manager: CustomUserManager = Depends(get_user_manager)
):
    """Admin resets a user's password to a temporary one"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate temporary password (12 characters: letters, numbers, special chars)
    import string
    temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits + '!@#$%') for _ in range(12))

    # Update user's password
    user.hashed_password = user_manager.password_helper.hash(temp_password)
    user.password_change_required = True
    await session.commit()

    print(f"[ADMIN] Password reset by {admin.email} for user: {user.email}")

    return {
        "success": True,
        "message": f"Password reset for {user.email}",
        "temporary_password": temp_password,
        "user_email": user.email
    }


@app.post("/api/admin/users/{user_id}/activate")
async def activate_user(
    user_id: int,
    admin: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Activate a pending user account"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_active:
        raise HTTPException(status_code=400, detail="User is already active")

    # Activate the user
    user.is_active = True
    user.is_verified = True
    await session.commit()

    return {"success": True, "message": f"User {user.email} has been activated"}


@app.delete("/api/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Admin deletes a user account"""
    # Don't allow deleting yourself
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_email = user.email

    # Delete user's location assignments first
    await session.execute(
        select(UserLocationRole).where(UserLocationRole.user_id == user_id)
    )
    location_roles = await session.execute(
        select(UserLocationRole).where(UserLocationRole.user_id == user_id)
    )
    for role in location_roles.scalars():
        await session.delete(role)

    # Delete the user
    await session.delete(user)
    await session.commit()

    print(f"[ADMIN] User deleted by {admin.email}: {user_email}")

    return {
        "success": True,
        "message": f"User {user_email} deleted successfully"
    }


# ============================================================================
# LOCATION MANAGEMENT API ROUTES
# ============================================================================

@app.post("/api/locations")
async def create_location(
    location_data: CreateLocationRequest,
    admin: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Create a new location (superadmin only)"""
    try:
        # Check if location name already exists
        result = await session.execute(
            select(Location).where(Location.name == location_data.name)
        )
        existing_location = result.scalar_one_or_none()

        if existing_location:
            raise HTTPException(status_code=400, detail="Location with this name already exists")

        # Create new location
        new_location = Location(
            name=location_data.name,
            address=location_data.address,
            description=location_data.description,
            timezone=location_data.timezone,
            contact_info=location_data.contact_info,
            created_by_user_id=admin.id
        )

        session.add(new_location)
        await session.commit()
        await session.refresh(new_location)

        print(f"[LOCATION] Location created by {admin.email}: {new_location.name}")

        return {
            "success": True,
            "message": f"Location '{new_location.name}' created successfully",
            "location_id": new_location.id,
            "location": {
                "id": new_location.id,
                "name": new_location.name,
                "address": new_location.address,
                "description": new_location.description,
                "timezone": new_location.timezone,
                "contact_info": new_location.contact_info,
                "created_at": new_location.created_at.isoformat()
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[LOCATION] Error creating location: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/locations")
async def list_locations(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """List locations accessible to the user"""
    try:
        # Superadmins see all locations
        if user.is_superuser:
            result = await session.execute(select(Location))
            locations = result.scalars().all()
        else:
            # Regular users see only their assigned locations
            result = await session.execute(
                select(Location).join(UserLocationRole).where(
                    UserLocationRole.user_id == user.id
                )
            )
            locations = result.scalars().all()

        # Get approved devices for each location
        location_list = []
        for loc in locations:
            devices_result = await session.execute(
                select(Device).where(
                    Device.location_id == loc.id,
                    Device.is_approved == True
                )
            )
            devices = devices_result.scalars().all()

            location_list.append({
                "id": loc.id,
                "name": loc.name,
                "address": loc.address,
                "description": loc.description,
                "timezone": loc.timezone,
                "contact_info": loc.contact_info,
                "created_at": loc.created_at.isoformat(),
                "approved_devices": [
                    {
                        "device_id": d.device_id,
                        "device_name": d.device_name,
                        "device_type": d.device_type,
                        "codeproject_endpoint": d.codeproject_endpoint,
                        "location_id": d.location_id,
                        "last_seen": d.last_seen.isoformat() if d.last_seen else None
                    }
                    for d in devices
                ]
            })

        return {
            "success": True,
            "locations": location_list,
            "total": len(location_list)
        }

    except Exception as e:
        print(f"[LOCATION] Error listing locations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/locations/{location_id}")
async def get_location(
    location_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get location details"""
    result = await session.execute(select(Location).where(Location.id == location_id))
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Check permissions
    if not user.is_superuser:
        # Check if user has access to this location
        access_check = await session.execute(
            select(UserLocationRole).where(
                UserLocationRole.user_id == user.id,
                UserLocationRole.location_id == location_id
            )
        )
        user_role = access_check.scalar_one_or_none()

        if not user_role:
            raise HTTPException(status_code=403, detail="Access denied to this location")

    # Get approved devices for this location
    devices_result = await session.execute(
        select(Device).where(
            Device.location_id == location_id,
            Device.is_approved == True
        )
    )
    devices = devices_result.scalars().all()

    return {
        "success": True,
        "location": {
            "id": location.id,
            "name": location.name,
            "address": location.address,
            "description": location.description,
            "timezone": location.timezone,
            "contact_info": location.contact_info,
            "created_at": location.created_at.isoformat(),
            "approved_devices": [
                {
                    "device_id": d.device_id,
                    "device_name": d.device_name,
                    "device_type": d.device_type,
                    "codeproject_endpoint": d.codeproject_endpoint,
                    "location_id": d.location_id,
                    "last_seen": d.last_seen.isoformat() if d.last_seen else None
                }
                for d in devices
            ]
        }
    }


@app.put("/api/locations/{location_id}")
async def update_location(
    location_id: int,
    location_data: UpdateLocationRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Update location (superadmin or location admin)"""
    result = await session.execute(select(Location).where(Location.id == location_id))
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Check permissions
    if not user.is_superuser:
        # Check if user is location admin
        role_check = await session.execute(
            select(UserLocationRole).where(
                UserLocationRole.user_id == user.id,
                UserLocationRole.location_id == location_id,
                UserLocationRole.role == 'location_admin'
            )
        )
        user_role = role_check.scalar_one_or_none()

        if not user_role:
            raise HTTPException(status_code=403, detail="Only location admins can update this location")

    # Update fields
    if location_data.name is not None:
        location.name = location_data.name
    if location_data.address is not None:
        location.address = location_data.address
    if location_data.description is not None:
        location.description = location_data.description
    if location_data.timezone is not None:
        location.timezone = location_data.timezone
    if location_data.contact_info is not None:
        location.contact_info = location_data.contact_info

    await session.commit()

    print(f"[LOCATION] Location updated by {user.email}: {location.name}")

    return {
        "success": True,
        "message": f"Location '{location.name}' updated successfully"
    }


@app.delete("/api/locations/{location_id}")
async def delete_location(
    location_id: int,
    admin: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Delete a location (superadmin only)"""
    result = await session.execute(select(Location).where(Location.id == location_id))
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    location_name = location.name

    # Check if any devices are assigned to this location
    devices_result = await session.execute(
        select(Device).where(Device.location_id == location_id)
    )
    devices = devices_result.scalars().all()

    if devices:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete location: {len(devices)} device(s) are assigned to it. Please remove or reassign devices first."
        )

    # Delete associated user-location roles
    roles_result = await session.execute(
        select(UserLocationRole).where(UserLocationRole.location_id == location_id)
    )
    roles = roles_result.scalars().all()
    for role in roles:
        await session.delete(role)

    await session.delete(location)
    await session.commit()

    print(f"[LOCATION] Location deleted by {admin.email}: {location_name}")

    return {
        "success": True,
        "message": f"Location '{location_name}' deleted successfully"
    }


@app.post("/api/locations/{location_id}/users")
async def assign_user_to_location(
    location_id: int,
    assignment_data: AssignUserToLocationRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Assign a user to a location with a role (superadmin or location admin)"""
    # Check location exists
    location_result = await session.execute(select(Location).where(Location.id == location_id))
    location = location_result.scalar_one_or_none()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Check user exists
    user_result = await session.execute(select(User).where(User.id == assignment_data.user_id))
    target_user = user_result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check permissions
    if not user.is_superuser:
        # Check if user is location admin for this location
        role_check = await session.execute(
            select(UserLocationRole).where(
                UserLocationRole.user_id == user.id,
                UserLocationRole.location_id == location_id,
                UserLocationRole.role == 'location_admin'
            )
        )
        user_role = role_check.scalar_one_or_none()

        if not user_role:
            raise HTTPException(status_code=403, detail="Only location admins can assign users")

    # Validate role
    if assignment_data.role not in ['location_admin', 'location_user']:
        raise HTTPException(status_code=400, detail="Role must be 'location_admin' or 'location_user'")

    # Check if already assigned
    existing_assignment = await session.execute(
        select(UserLocationRole).where(
            UserLocationRole.user_id == assignment_data.user_id,
            UserLocationRole.location_id == location_id
        )
    )
    existing = existing_assignment.scalar_one_or_none()

    if existing:
        # Update role if different
        if existing.role != assignment_data.role:
            existing.role = assignment_data.role
            await session.commit()
            print(f"[LOCATION] User role updated by {user.email}: {target_user.email} -> {assignment_data.role} at {location.name}")
            return {
                "success": True,
                "message": f"User role updated to {assignment_data.role}"
            }
        else:
            return {
                "success": True,
                "message": "User already assigned with this role"
            }

    # Create new assignment
    new_assignment = UserLocationRole(
        user_id=assignment_data.user_id,
        location_id=location_id,
        role=assignment_data.role,
        assigned_by_user_id=user.id
    )

    session.add(new_assignment)
    await session.commit()

    print(f"[LOCATION] User assigned by {user.email}: {target_user.email} -> {assignment_data.role} at {location.name}")

    return {
        "success": True,
        "message": f"User assigned as {assignment_data.role}"
    }


@app.delete("/api/locations/{location_id}/users/{user_id}")
async def remove_user_from_location(
    location_id: int,
    user_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Remove a user from a location (superadmin or location admin)"""
    # Check location exists
    location_result = await session.execute(select(Location).where(Location.id == location_id))
    location = location_result.scalar_one_or_none()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Check permissions
    if not user.is_superuser:
        # Check if user is location admin for this location
        role_check = await session.execute(
            select(UserLocationRole).where(
                UserLocationRole.user_id == user.id,
                UserLocationRole.location_id == location_id,
                UserLocationRole.role == 'location_admin'
            )
        )
        user_role = role_check.scalar_one_or_none()

        if not user_role:
            raise HTTPException(status_code=403, detail="Only location admins can remove users")

    # Find and delete assignment
    assignment_result = await session.execute(
        select(UserLocationRole).where(
            UserLocationRole.user_id == user_id,
            UserLocationRole.location_id == location_id
        )
    )
    assignment = assignment_result.scalar_one_or_none()

    if not assignment:
        raise HTTPException(status_code=404, detail="User assignment not found")

    await session.delete(assignment)
    await session.commit()

    print(f"[LOCATION] User removed from location by {user.email}: user_id={user_id} from {location.name}")

    return {
        "success": True,
        "message": "User removed from location"
    }


@app.get("/api/locations/{location_id}/users")
async def list_location_users(
    location_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """List users assigned to a location"""
    # Check location exists
    location_result = await session.execute(select(Location).where(Location.id == location_id))
    location = location_result.scalar_one_or_none()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Check permissions
    if not user.is_superuser:
        # Check if user has access to this location
        access_check = await session.execute(
            select(UserLocationRole).where(
                UserLocationRole.user_id == user.id,
                UserLocationRole.location_id == location_id
            )
        )
        user_access = access_check.scalar_one_or_none()

        if not user_access:
            raise HTTPException(status_code=403, detail="Access denied to this location")

    # Get all user assignments for this location
    result = await session.execute(
        select(UserLocationRole, User).join(
            User, UserLocationRole.user_id == User.id
        ).where(
            UserLocationRole.location_id == location_id
        )
    )
    assignments = result.all()

    return {
        "success": True,
        "location_id": location_id,
        "location_name": location.name,
        "users": [
            {
                "user_id": user_obj.id,
                "email": user_obj.email,
                "first_name": user_obj.first_name,
                "last_name": user_obj.last_name,
                "role": assignment.role,
                "assigned_at": assignment.assigned_at.isoformat()
            }
            for assignment, user_obj in assignments
        ],
        "total": len(assignments)
    }


# ============================================================================
# SERVER SETTINGS API ROUTES
# ============================================================================

@app.get("/api/settings")
async def get_all_settings(
    user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Get all server settings (superadmin only)"""
    result = await session.execute(select(ServerSettings))
    settings = result.scalars().all()

    return {
        "settings": {
            setting.setting_key: setting.setting_value
            for setting in settings
        }
    }


@app.get("/api/settings/{setting_key}")
async def get_setting(
    setting_key: str,
    user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Get a specific setting (superadmin only)"""
    result = await session.execute(
        select(ServerSettings).where(ServerSettings.setting_key == setting_key)
    )
    setting = result.scalar_one_or_none()

    return {
        "setting_key": setting_key,
        "setting_value": setting.setting_value if setting else None
    }


@app.post("/api/settings")
async def update_setting(
    data: UpdateSettingRequest,
    user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Update or create a server setting (superadmin only)"""
    # Check if setting exists
    result = await session.execute(
        select(ServerSettings).where(ServerSettings.setting_key == data.setting_key)
    )
    setting = result.scalar_one_or_none()

    if setting:
        setting.setting_value = data.setting_value
        setting.updated_by_user_id = user.id
        setting.updated_at = datetime.utcnow()
    else:
        setting = ServerSettings(
            setting_key=data.setting_key,
            setting_value=data.setting_value,
            updated_by_user_id=user.id
        )
        session.add(setting)

    await session.commit()

    print(f"[SETTINGS] Setting updated by {user.email}: {data.setting_key} = {data.setting_value}")

    return {
        "success": True,
        "setting_key": data.setting_key,
        "setting_value": data.setting_value
    }


# ============================================================================
# CODEPROJECT SERVER MANAGEMENT API ROUTES
# ============================================================================

@app.get("/api/codeproject-servers")
async def get_codeproject_servers(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get all CodeProject.AI servers"""
    result = await session.execute(select(CodeProjectServer))
    servers = result.scalars().all()

    return [
        {
            "id": server.id,
            "friendly_name": server.friendly_name,
            "endpoint_url": server.endpoint_url,
            "description": server.description,
            "created_at": server.created_at.isoformat()
        }
        for server in servers
    ]


@app.post("/api/codeproject-servers")
async def create_codeproject_server(
    data: CreateCodeProjectServerRequest,
    user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Create a new CodeProject.AI server (superadmin only)"""
    # Check if friendly name already exists
    result = await session.execute(
        select(CodeProjectServer).where(CodeProjectServer.friendly_name == data.friendly_name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Server with this name already exists")

    server = CodeProjectServer(
        friendly_name=data.friendly_name,
        endpoint_url=data.endpoint_url.rstrip('/'),  # Remove trailing slash
        description=data.description,
        created_by_user_id=user.id
    )
    session.add(server)
    await session.commit()

    print(f"[CODEPROJECT-SERVER] Created by {user.email}: {data.friendly_name} -> {data.endpoint_url}")

    return {
        "success": True,
        "id": server.id,
        "friendly_name": server.friendly_name,
        "endpoint_url": server.endpoint_url
    }


@app.put("/api/codeproject-servers/{server_id}")
async def update_codeproject_server(
    server_id: int,
    data: UpdateCodeProjectServerRequest,
    user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Update a CodeProject.AI server (superadmin only)"""
    result = await session.execute(
        select(CodeProjectServer).where(CodeProjectServer.id == server_id)
    )
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if data.friendly_name is not None:
        # Check if new name already exists
        result = await session.execute(
            select(CodeProjectServer).where(
                CodeProjectServer.friendly_name == data.friendly_name,
                CodeProjectServer.id != server_id
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Server with this name already exists")
        server.friendly_name = data.friendly_name

    if data.endpoint_url is not None:
        server.endpoint_url = data.endpoint_url.rstrip('/')

    if data.description is not None:
        server.description = data.description

    await session.commit()

    print(f"[CODEPROJECT-SERVER] Updated by {user.email}: {server.friendly_name}")

    return {
        "success": True,
        "id": server.id,
        "friendly_name": server.friendly_name,
        "endpoint_url": server.endpoint_url
    }


@app.delete("/api/codeproject-servers/{server_id}")
async def delete_codeproject_server(
    server_id: int,
    user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Delete a CodeProject.AI server (superadmin only)"""
    result = await session.execute(
        select(CodeProjectServer).where(CodeProjectServer.id == server_id)
    )
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    # Check if any devices are using this server
    devices_result = await session.execute(
        select(Device).where(Device.codeproject_endpoint == server.endpoint_url)
    )
    devices = devices_result.scalars().all()

    if devices:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete server: {len(devices)} device(s) are using it"
        )

    friendly_name = server.friendly_name
    await session.delete(server)
    await session.commit()

    print(f"[CODEPROJECT-SERVER] Deleted by {user.email}: {friendly_name}")

    return {"success": True, "message": f"Deleted server: {friendly_name}"}


@app.get("/api/codeproject-servers/{server_id}/test")
async def test_codeproject_server(
    server_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Test connection to a CodeProject.AI server"""
    result = await session.execute(
        select(CodeProjectServer).where(CodeProjectServer.id == server_id)
    )
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    try:
        # Try to ping the server with a simple status check
        response = requests.post(
            f"{server.endpoint_url}/vision/face/list",
            timeout=5
        )

        if response.status_code == 200:
            return {
                "success": True,
                "online": True,
                "status_code": response.status_code,
                "message": "Server is online and responding"
            }
        else:
            return {
                "success": True,
                "online": False,
                "status_code": response.status_code,
                "message": f"Server responded with status {response.status_code}"
            }

    except requests.Timeout:
        return {
            "success": True,
            "online": False,
            "status_code": None,
            "message": "Connection timeout (server not responding)"
        }
    except requests.ConnectionError:
        return {
            "success": True,
            "online": False,
            "status_code": None,
            "message": "Connection error (server unreachable)"
        }
    except Exception as e:
        return {
            "success": True,
            "online": False,
            "status_code": None,
            "message": f"Error: {str(e)}"
        }


@app.get("/api/codeproject-servers/{server_id}/faces")
async def get_server_faces(
    server_id: int,
    user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Get list of faces registered on a CodeProject.AI server"""
    result = await session.execute(
        select(CodeProjectServer).where(CodeProjectServer.id == server_id)
    )
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    try:
        # Get list from CodeProject.AI
        response = requests.post(
            f"{server.endpoint_url}/vision/face/list",
            timeout=30
        )

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"CodeProject.AI returned status {response.status_code}")

        result_data = response.json()

        if not result_data.get('success'):
            raise HTTPException(status_code=500, detail="Failed to get face list from CodeProject.AI")

        # Get the list of user IDs from CodeProject
        codeproject_faces = result_data.get('faces', [])

        # Match with our database records
        faces_with_info = []
        for cp_face in codeproject_faces:
            userid = cp_face if isinstance(cp_face, str) else cp_face.get('userid')

            # Look up in our database
            db_result = await session.execute(
                select(RegisteredFace).where(
                    RegisteredFace.codeproject_user_id == userid,
                    RegisteredFace.codeproject_endpoint == server.endpoint_url
                )
            )
            db_records = db_result.scalars().all()

            faces_with_info.append({
                "userid": userid,
                "photo_count": len(db_records),
                "in_database": len(db_records) > 0,
                "registered_at": db_records[0].registered_at.isoformat() if db_records else None
            })

        return {
            "success": True,
            "server_name": server.friendly_name,
            "endpoint_url": server.endpoint_url,
            "faces": faces_with_info
        }

    except requests.RequestException as e:
        print(f"[CODEPROJECT-SERVER] Error fetching faces from {server.friendly_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Error connecting to CodeProject.AI: {str(e)}")


@app.delete("/api/codeproject-servers/{server_id}/faces/{userid}")
async def delete_server_face(
    server_id: int,
    userid: str,
    user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Delete a face from CodeProject.AI server and database"""
    result = await session.execute(
        select(CodeProjectServer).where(CodeProjectServer.id == server_id)
    )
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    print(f"\n{'='*60}")
    print(f"[DELETE-FACE] Deleting {userid} from {server.friendly_name}")

    # Delete from CodeProject.AI
    try:
        response = requests.post(
            f"{server.endpoint_url}/vision/face/delete",
            data={'userid': userid},
            timeout=30
        )

        if response.status_code == 200:
            result_data = response.json()
            if result_data.get('success'):
                print(f"[DELETE-FACE]   ✓ Removed from CodeProject.AI")
            else:
                print(f"[DELETE-FACE]   ⚠ CodeProject.AI: {result_data.get('error', 'Unknown error')}")
        else:
            print(f"[DELETE-FACE]   ⚠ CodeProject.AI returned status {response.status_code}")
    except Exception as e:
        print(f"[DELETE-FACE]   ⚠ Error removing from CodeProject.AI: {e}")
        # Continue with database deletion

    # Delete from database
    db_result = await session.execute(
        select(RegisteredFace).where(
            RegisteredFace.codeproject_user_id == userid,
            RegisteredFace.codeproject_endpoint == server.endpoint_url
        )
    )
    face_records = db_result.scalars().all()

    deleted_files = 0
    for face_record in face_records:
        try:
            if os.path.exists(face_record.file_path):
                os.remove(face_record.file_path)
                deleted_files += 1
                print(f"[DELETE-FACE]   ✓ Deleted file: {os.path.basename(face_record.file_path)}")
            else:
                print(f"[DELETE-FACE]   ⚠ File not found: {face_record.file_path}")
        except Exception as e:
            print(f"[DELETE-FACE]   ⚠ Error deleting file {face_record.file_path}: {e}")

    for face_record in face_records:
        await session.delete(face_record)
    await session.commit()

    if face_records:
        print(f"[DELETE-FACE]   ✓ Removed {len(face_records)} record(s) from database")
    else:
        print(f"[DELETE-FACE]   ⚠ No database records found for {userid}")

    print(f"[DELETE-FACE] Deletion complete")
    print(f"{'='*60}\n")

    return {
        "success": True,
        "message": f"Deleted {userid} from {server.friendly_name}",
        "files_deleted": deleted_files,
        "records_deleted": len(face_records)
    }


# ============================================================================
# DEVICE MANAGEMENT API ROUTES
# ============================================================================

@app.post("/api/devices/register")
async def register_device(
    data: RegisterDeviceRequest,
    session: AsyncSession = Depends(get_async_session)
):
    """Register a new device (called by Facial_Display client)"""
    import random
    import string

    # Check if device already exists
    result = await session.execute(
        select(Device).where(Device.device_id == data.device_id)
    )
    existing_device = result.scalar_one_or_none()

    if existing_device:
        # Device already registered, return existing registration code
        return {
            "success": True,
            "device_id": existing_device.device_id,
            "registration_code": existing_device.registration_code,
            "is_approved": existing_device.is_approved,
            "device_name": existing_device.device_name,
            "device_type": existing_device.device_type,
            "location_id": existing_device.location_id,
            "codeproject_endpoint": existing_device.codeproject_endpoint
        }

    # Generate unique 6-digit registration code
    while True:
        registration_code = ''.join(random.choices(string.digits, k=6))
        # Check if code is unique
        check_result = await session.execute(
            select(Device).where(Device.registration_code == registration_code)
        )
        if not check_result.scalar_one_or_none():
            break

    # Create new device
    new_device = Device(
        device_id=data.device_id,
        registration_code=registration_code,
        is_approved=False
    )

    session.add(new_device)
    await session.commit()

    print(f"[DEVICE] New device registered: {data.device_id} with code {registration_code}")

    return {
        "success": True,
        "device_id": data.device_id,
        "registration_code": registration_code,
        "is_approved": False
    }


@app.get("/api/devices/status/{device_id}")
async def get_device_status(
    device_id: str,
    session: AsyncSession = Depends(get_async_session)
):
    """Check device status (called by Facial_Display client for polling)"""
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Update last_seen
    device.last_seen = datetime.utcnow()
    await session.commit()

    response_data = {
        "device_id": device.device_id,
        "registration_code": device.registration_code,
        "is_approved": device.is_approved,
        "device_name": device.device_name,
        "device_type": device.device_type,
        "location_id": device.location_id,
        "codeproject_endpoint": device.codeproject_endpoint
    }

    # Add token if device is approved (only sent once during first status check after approval)
    if device.is_approved and device.device_token:
        response_data["device_token"] = device.device_token

    # Add registration expiration info for pending devices
    if not device.is_approved:
        registration_age_seconds = (datetime.utcnow() - device.registered_at).total_seconds()
        expires_in_seconds = (REGISTRATION_CODE_EXPIRATION_MINUTES * 60) - registration_age_seconds
        response_data["registration_expires_in_seconds"] = max(0, int(expires_in_seconds))

    return response_data



@app.post("/api/devices/heartbeat")
async def device_heartbeat(
    request: Request,
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Device heartbeat endpoint - validates token and returns current configuration.

    Devices should call this every 10-15 seconds to:
    - Validate their token is still active
    - Update last_seen timestamp
    - Detect configuration changes (device_type, device_name, etc.)
    - Get notified if they need to reload/change modes
    """
    # Device is already authenticated by get_current_device dependency
    # last_seen is already updated by get_current_device

    # Check if a new token was rotated (set by get_current_device)
    new_token = getattr(request.state, 'new_device_token', None)

    # Return current device configuration
    response_data = {
        "status": "ok",
        "device_id": device.device_id,
        "device_name": device.device_name,
        "device_type": device.device_type,
        "location_id": device.location_id,
        "codeproject_endpoint": device.codeproject_endpoint,
        "is_approved": device.is_approved,
        # Detection settings (use device-specific or fall back to .env defaults)
        "confidence_threshold": float(device.confidence_threshold) if device.confidence_threshold is not None else DEFAULT_CONFIDENCE_THRESHOLD,
        "presence_timeout_minutes": device.presence_timeout_minutes if device.presence_timeout_minutes is not None else DEFAULT_PRESENCE_TIMEOUT_MINUTES,
        "detection_cooldown_seconds": device.detection_cooldown_seconds if device.detection_cooldown_seconds is not None else DEFAULT_DETECTION_COOLDOWN_SECONDS
    }

    # If token was rotated, send the new token
    if new_token:
        response_data["new_token"] = new_token
        print(f"[HEARTBEAT] Sending rotated token to device {device.device_name or device.device_id[:8]}")

    return response_data


@app.post("/api/devices/log-scan")
async def log_scan(
    request: Request,
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Log face detection events from scanner devices.

    Expects a JSON body with a 'detections' array:
    {
        "detections": [
            {"person_name": "John Doe", "confidence": 0.95},
            {"person_name": "Jane Smith", "confidence": 0.87}
        ]
    }
    """
    try:
        data = await request.json()
        detections = data.get("detections", [])

        if not detections:
            raise HTTPException(status_code=400, detail="No detections provided")

        if not device.location_id:
            raise HTTPException(status_code=400, detail="Device must have a location assigned")

        # Create detection records
        detection_records = []
        for det in detections:
            person_name = det.get("person_name")
            confidence = det.get("confidence")

            if not person_name or confidence is None:
                continue

            detection = Detection(
                device_id=device.device_id,
                person_name=person_name,
                confidence=float(confidence),
                location_id=device.location_id,
                detected_at=datetime.utcnow()
            )
            session.add(detection)
            detection_records.append({
                "person_name": person_name,
                "confidence": confidence,
                "device_name": device.device_name or device.device_id[:8],
                "detected_at": detection.detected_at.isoformat()
            })

        await session.commit()

        # Get profile photos for detected people
        if detection_records:
            person_names = [det["person_name"] for det in detection_records]
            face_result = await session.execute(
                select(RegisteredFace.person_name, RegisteredFace.profile_photo)
                .where(RegisteredFace.location_id == device.location_id)
                .where(RegisteredFace.person_name.in_(person_names))
                .distinct(RegisteredFace.person_name)
            )
            profile_photos = {row.person_name: row.profile_photo for row in face_result.all()}

            # Add profile photos to detection records
            for det in detection_records:
                det["profile_photo"] = profile_photos.get(det["person_name"])
                det["device_id"] = device.device_id

            # Broadcast to dashboards for this location via WebSocket
            await manager.broadcast_to_location(device.location_id, {
                "type": "new_detections",
                "detections": detection_records
            })

        print(f"[LOG-SCAN] Logged {len(detection_records)} detections from {device.device_name or device.device_id[:8]}")

        return {"status": "ok", "logged": len(detection_records)}

    except Exception as e:
        print(f"[LOG-SCAN] Error: {e}")
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/test")
async def websocket_test(websocket: WebSocket):
    """Simple test WebSocket endpoint"""
    print("[WEBSOCKET-TEST] Connection attempt")
    await websocket.accept()
    print("[WEBSOCKET-TEST] Connection accepted")
    await websocket.send_json({"message": "Test connection successful"})
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        print("[WEBSOCKET-TEST] Client disconnected")


@app.websocket("/ws/dashboard/{location_id}")
async def websocket_dashboard(
    websocket: WebSocket,
    location_id: int
):
    """
    WebSocket endpoint for dashboard real-time updates.

    Dashboards connect to this endpoint to receive live detection updates
    for their assigned location.
    """
    print(f"[WEBSOCKET] Connection attempt for location {location_id}")
    print(f"[WEBSOCKET] Headers: {websocket.headers}")

    await manager.connect(websocket, location_id)
    print(f"[WEBSOCKET] Connected successfully for location {location_id}")

    try:
        # Create a database session manually for WebSocket
        async with async_session_maker() as session:
            # Send initial data: recent detections for this location
            presence_threshold = datetime.utcnow() - timedelta(minutes=DEFAULT_PRESENCE_TIMEOUT_MINUTES)

            # Query recent detections (within presence timeout)
            result = await session.execute(
                select(Detection)
                .where(Detection.location_id == location_id)
                .where(Detection.detected_at >= presence_threshold)
                .order_by(Detection.detected_at.desc())
            )
            recent_detections = result.scalars().all()

            # Group by person_name and get most recent detection for each
            person_latest = {}
            for det in recent_detections:
                if det.person_name not in person_latest:
                    person_latest[det.person_name] = {
                        "person_name": det.person_name,
                        "confidence": float(det.confidence),
                        "device_id": det.device_id,
                        "detected_at": det.detected_at.isoformat()
                    }

            # Get device names
            device_result = await session.execute(
                select(Device).where(Device.location_id == location_id)
            )
            devices = {d.device_id: d.device_name for d in device_result.scalars().all()}

            # Get profile photos from registered_face table
            # Group by person_name to get one photo per person
            face_result = await session.execute(
                select(RegisteredFace.person_name, RegisteredFace.profile_photo)
                .where(RegisteredFace.location_id == location_id)
                .where(RegisteredFace.profile_photo.isnot(None))
            )
            profile_photos = {}
            for row in face_result.all():
                if row.person_name not in profile_photos:
                    profile_photos[row.person_name] = row.profile_photo

            # Add device names and profile photos to detections
            for detection in person_latest.values():
                detection["device_name"] = devices.get(detection["device_id"], detection["device_id"][:8])
                detection["profile_photo"] = profile_photos.get(detection["person_name"])

            await websocket.send_json({
                "type": "initial_data",
                "detections": list(person_latest.values())
            })

        # Keep connection alive and wait for disconnect
        while True:
            # Wait for any message from client (ping/pong)
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WEBSOCKET] Error: {e}")
    finally:
        manager.disconnect(websocket, location_id)


@app.get("/api/devices/pending")
async def list_pending_devices(
    location_id: Optional[int] = None,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """List pending device approvals (for superadmins and location admins)

    Note: Pending devices don't have a location_id yet (assigned during approval),
    so location filtering is not applied to pending devices - they're always shown.
    """
    # Only superadmins and location admins can see pending devices
    if not user.is_superuser:
        # Check if they're a location admin
        result = await session.execute(
            select(UserLocationRole).where(
                UserLocationRole.user_id == user.id,
                UserLocationRole.role == 'location_admin'
            )
        )
        admin_locations = result.scalars().all()

        if not admin_locations:
            raise HTTPException(status_code=403, detail="Access denied")

    # Pending devices always shown regardless of location filter
    # (they haven't been assigned to a location yet - that happens during approval)
    query = select(Device).where(Device.is_approved == False)

    result = await session.execute(query)
    pending_devices = result.scalars().all()

    return {
        "success": True,
        "devices": [
            {
                "id": d.id,
                "device_id": d.device_id,
                "registration_code": d.registration_code,
                "registered_at": d.registered_at.isoformat(),
                "last_seen": d.last_seen.isoformat() if d.last_seen else None
            }
            for d in pending_devices
        ]
    }


@app.post("/api/devices/{device_id}/approve")
async def approve_device(
    device_id: str,
    data: ApproveDeviceRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Approve a device and configure it (superadmin or location admin)"""
    # Get the device
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Check if registration code has expired
    registration_age = datetime.utcnow() - device.registered_at
    if registration_age > timedelta(minutes=REGISTRATION_CODE_EXPIRATION_MINUTES):
        # Delete expired device
        await session.delete(device)
        await session.commit()
        raise HTTPException(
            status_code=410,  # Gone
            detail=f"Registration code expired ({REGISTRATION_CODE_EXPIRATION_MINUTES} minutes). Device must re-register."
        )

    # Check permissions - must be superadmin or admin of the target location
    if not user.is_superuser:
        location_check = await session.execute(
            select(UserLocationRole).where(
                UserLocationRole.user_id == user.id,
                UserLocationRole.location_id == data.location_id,
                UserLocationRole.role == 'location_admin'
            )
        )
        if not location_check.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="You must be an admin of the target location")

    # Verify location exists
    location_result = await session.execute(
        select(Location).where(Location.id == data.location_id)
    )
    if not location_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Location not found")

    # Validate device type and codeproject_endpoint requirements
    if data.device_type in ['registration_kiosk', 'people_scanner']:
        if not data.codeproject_endpoint:
            raise HTTPException(
                status_code=400,
                detail=f"CodeProject endpoint is required for {data.device_type}"
            )
    elif data.device_type == 'location_dashboard':
        # Dashboard doesn't need CodeProject endpoint
        data.codeproject_endpoint = None
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid device_type: {data.device_type}. Must be 'registration_kiosk', 'people_scanner', or 'location_dashboard'"
        )

    # Generate device token
    device_token = generate_device_token()

    # Approve and configure device
    device.is_approved = True
    device.device_name = data.device_name
    device.location_id = data.location_id
    device.device_type = data.device_type
    device.codeproject_endpoint = data.codeproject_endpoint
    device.approved_at = datetime.utcnow()
    device.approved_by_user_id = user.id
    device.device_token = device_token
    device.token_created_at = datetime.utcnow()

    await session.commit()

    print(f"[DEVICE] Device approved by {user.email}: {device_id} -> {data.device_name} at location {data.location_id}")
    print(f"[TOKEN] Generated token for device {data.device_name}")

    return {
        "success": True,
        "message": f"Device {data.device_name} approved",
        "device_token": device_token  # Return token to device
    }


@app.get("/api/my-devices")
async def get_my_location_devices(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get devices for the user's currently selected location"""
    # Get user's selected location and role
    location_context = await get_user_selected_location_and_role(user, session)

    if not location_context:
        return {"success": True, "devices": [], "message": "No location selected"}

    location_id = location_context.get("location_id")
    role = location_context.get("role")
    is_superuser = location_context.get("is_superuser", False)

    # Get devices for the selected location
    if is_superuser and not location_id:
        # Superuser with no location selected - show all devices
        result = await session.execute(select(Device).where(Device.is_approved == True))
    else:
        # Show devices for selected location
        result = await session.execute(
            select(Device).where(
                Device.location_id == location_id,
                Device.is_approved == True
            )
        )

    devices = result.scalars().all()

    return {
        "success": True,
        "devices": [
            {
                "id": device.id,
                "device_id": device.device_id,
                "device_name": device.device_name,
                "device_type": device.device_type,
                "location_id": device.location_id,
                "registration_code": device.registration_code,
                "created_at": device.created_at.isoformat() if device.created_at else None
            }
            for device in devices
        ],
        "role": role,
        "can_manage_users": role in ["superadmin", "location_admin"]
    }


@app.get("/api/devices")
async def list_devices(
    location_id: int = None,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """List all approved devices (filtered by user permissions and optionally by location)"""
    if user.is_superuser:
        # Superadmins see all devices
        query = select(Device).where(Device.is_approved == True)
        if location_id:
            query = query.where(Device.location_id == location_id)
        result = await session.execute(query)
        devices = result.scalars().all()
    else:
        # Location admins see devices in their locations
        # Get user's admin locations
        loc_result = await session.execute(
            select(UserLocationRole).where(
                UserLocationRole.user_id == user.id,
                UserLocationRole.role == 'location_admin'
            )
        )
        admin_locations = [ulr.location_id for ulr in loc_result.scalars().all()]

        if not admin_locations:
            return {"success": True, "devices": []}

        # Build query with location filter
        query = select(Device).where(
            Device.is_approved == True,
            Device.location_id.in_(admin_locations)
        )
        if location_id:
            # Ensure user has access to the requested location
            if location_id not in admin_locations:
                raise HTTPException(status_code=403, detail="You don't have access to this location")
            query = query.where(Device.location_id == location_id)

        result = await session.execute(query)
        devices = result.scalars().all()

    # Get location names
    device_list = []
    for device in devices:
        location_name = None
        if device.location_id:
            loc_result = await session.execute(
                select(Location).where(Location.id == device.location_id)
            )
            location = loc_result.scalar_one_or_none()
            if location:
                location_name = location.name

        # Calculate token status
        has_token = device.device_token is not None
        token_status = "active" if has_token else "missing"
        token_age_days = None
        if has_token and device.token_created_at:
            token_age = datetime.utcnow() - device.token_created_at
            token_age_days = token_age.days

        device_list.append({
            "id": device.id,
            "device_id": device.device_id,
            "device_name": device.device_name,
            "device_type": device.device_type,
            "location_id": device.location_id,
            "location_name": location_name,
            "codeproject_endpoint": device.codeproject_endpoint,
            "registered_at": device.registered_at.isoformat(),
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "token_status": token_status,
            "token_age_days": token_age_days,
            "token_created_at": device.token_created_at.isoformat() if device.token_created_at else None
        })

    return {
        "success": True,
        "devices": device_list
    }


@app.put("/api/devices/{device_id}")
async def update_device(
    device_id: str,
    data: UpdateDeviceRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Update device configuration (superadmin or location admin)"""
    # Get the device
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Check permissions
    if not user.is_superuser:
        # Must be admin of the device's current location or target location
        locations_to_check = [device.location_id]
        if data.location_id and data.location_id != device.location_id:
            locations_to_check.append(data.location_id)

        has_permission = False
        for loc_id in locations_to_check:
            if loc_id:
                loc_check = await session.execute(
                    select(UserLocationRole).where(
                        UserLocationRole.user_id == user.id,
                        UserLocationRole.location_id == loc_id,
                        UserLocationRole.role == 'location_admin'
                    )
                )
                if loc_check.scalar_one_or_none():
                    has_permission = True
                    break

        if not has_permission:
            raise HTTPException(status_code=403, detail="Access denied")

    # Validate device type and codeproject_endpoint compatibility
    target_device_type = data.device_type if data.device_type is not None else device.device_type

    if target_device_type in ['registration_kiosk', 'people_scanner']:
        # These types require a CodeProject endpoint
        target_endpoint = data.codeproject_endpoint if data.codeproject_endpoint is not None else device.codeproject_endpoint
        if not target_endpoint:
            raise HTTPException(
                status_code=400,
                detail=f"CodeProject endpoint is required for {target_device_type}"
            )
    elif target_device_type == 'location_dashboard':
        # Dashboard doesn't use CodeProject, clear it if changing to this type
        if data.device_type == 'location_dashboard':
            data.codeproject_endpoint = None

    # Update device
    if data.device_name is not None:
        device.device_name = data.device_name
    if data.location_id is not None:
        device.location_id = data.location_id
    if data.device_type is not None:
        device.device_type = data.device_type
    if data.codeproject_endpoint is not None:
        device.codeproject_endpoint = data.codeproject_endpoint
    elif data.device_type == 'location_dashboard':
        # Explicitly clear codeproject_endpoint when switching to dashboard
        device.codeproject_endpoint = None

    # Update scanner detection settings
    if data.confidence_threshold is not None:
        device.confidence_threshold = data.confidence_threshold
    if data.presence_timeout_minutes is not None:
        device.presence_timeout_minutes = data.presence_timeout_minutes
    if data.detection_cooldown_seconds is not None:
        device.detection_cooldown_seconds = data.detection_cooldown_seconds

    await session.commit()

    print(f"[DEVICE] Device updated by {user.email}: {device_id}")

    return {
        "success": True,
        "message": "Device updated successfully"
    }


@app.post("/api/devices/{device_id}/revoke-token")
async def revoke_device_token(
    device_id: str,
    user: User = Depends(require_any_admin_access),
    session: AsyncSession = Depends(get_async_session)
):
    """Revoke a device's authentication token (superadmin or location admin)"""
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Check permissions for location admins
    if not user.is_superuser:
        admin_result = await session.execute(
            select(UserLocationRole).where(
                UserLocationRole.user_id == user.id,
                UserLocationRole.role == 'location_admin'
            )
        )
        admin_locations = admin_result.scalars().all()
        admin_location_ids = [loc.location_id for loc in admin_locations]

        if device.location_id not in admin_location_ids:
            raise HTTPException(
                status_code=403,
                detail="You can only revoke tokens for devices from locations you manage"
            )

    # Revoke the token and reset device to pending state
    import random
    import string

    # Generate new registration code
    while True:
        new_registration_code = ''.join(random.choices(string.digits, k=6))
        # Check if code is unique
        check_result = await session.execute(
            select(Device).where(Device.registration_code == new_registration_code)
        )
        if not check_result.scalar_one_or_none():
            break

    device.device_token = None
    device.token_created_at = None
    device.token_rotated_at = None
    device.is_approved = False
    device.registration_code = new_registration_code
    device.registered_at = datetime.utcnow()
    # Clear device configuration - will be set again on re-approval
    device.device_name = None
    device.device_type = None
    device.codeproject_endpoint = None
    await session.commit()

    print(f"[TOKEN] Token revoked for device {device.device_id[:8]} by {user.email}. New code: {new_registration_code}")

    return {
        "success": True,
        "message": f"Token revoked. Device must re-register with new code."
    }


@app.delete("/api/devices/{device_id}")
async def delete_device(
    device_id: str,
    user: User = Depends(require_any_admin_access),
    session: AsyncSession = Depends(get_async_session)
):
    """Delete a device (superadmin or location admin)"""
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Check permissions for location admins
    if not user.is_superuser:
        # Get admin locations for this user
        admin_result = await session.execute(
            select(UserLocationRole).where(
                UserLocationRole.user_id == user.id,
                UserLocationRole.role == 'location_admin'
            )
        )
        admin_locations = admin_result.scalars().all()
        admin_location_ids = [loc.location_id for loc in admin_locations]

        # Check if device belongs to one of their admin locations
        if device.location_id not in admin_location_ids:
            raise HTTPException(
                status_code=403,
                detail="You can only delete devices from locations you manage"
            )

    await session.delete(device)
    await session.commit()

    print(f"[DEVICE] Device deleted by {user.email}: {device_id}")

    return {
        "success": True,
        "message": "Device deleted successfully"
    }


# ============================================================================
# DEVICE-AUTHENTICATED FACIAL RECOGNITION ROUTES
# ============================================================================

@app.post("/api/devices/register-face")
async def device_register_face(
    data: DeviceRegisterRequest,
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_async_session)
):
    """Register face images to CodeProject.AI (device-authenticated)"""
    try:
        print(f"\n{'='*60}")
        print(f"[DEVICE-REGISTER] Device: {device.device_name} ({device.device_id[:8]}...)")
        print(f"[DEVICE-REGISTER] Location: {device.location_id}")
        print(f"[DEVICE-REGISTER] Person: {data.name}")
        print(f"[DEVICE-REGISTER] Photos: {len(data.photos)}")

        # Get the device's CodeProject endpoint
        codeproject_url = device.codeproject_endpoint
        if not codeproject_url:
            raise HTTPException(
                status_code=400,
                detail="Device has no CodeProject endpoint configured"
            )

        successful_registrations = 0
        errors = []

        for idx, photo_data in enumerate(data.photos):
            try:
                print(f"[DEVICE-REGISTER] Processing photo {idx+1}/{len(data.photos)}")

                # Extract base64 data from data URL
                if ',' in photo_data:
                    photo_data = photo_data.split(',')[1]

                # Decode base64 image
                image_bytes = base64.b64decode(photo_data)
                image_size_kb = len(image_bytes) / 1024
                print(f"[DEVICE-REGISTER]   Image size: {image_size_kb:.2f} KB")

                # Save locally for backup
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{data.name.replace(' ', '_')}_{timestamp}_{idx}.jpg"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                with open(filepath, 'wb') as f:
                    f.write(image_bytes)
                print(f"[DEVICE-REGISTER]   Saved locally: {filename}")

                # Register with CodeProject.AI
                files = {
                    'image': (filename, BytesIO(image_bytes), 'image/jpeg')
                }
                params = {
                    'userid': data.name
                }

                print(f"[DEVICE-REGISTER]   Sending to CodeProject.AI at {codeproject_url}...")

                response = requests.post(
                    f"{codeproject_url}/vision/face/register",
                    files=files,
                    data=params,
                    timeout=60
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        successful_registrations += 1
                        print(f"[DEVICE-REGISTER]   ✓ Photo {idx+1} registered successfully")

                        # Save to database (no user_id for device registrations)
                        registered_face = RegisteredFace(
                            person_name=data.name,
                            codeproject_user_id=data.name,
                            file_path=filepath,
                            codeproject_endpoint=codeproject_url,
                            location_id=device.location_id,  # Tag with device's location
                            registered_by_user_id=None,  # Device registration
                            profile_photo=data.profile_photo  # Profile photo for dashboard thumbnail
                        )
                        session.add(registered_face)
                        await session.commit()
                        print(f"[DEVICE-REGISTER]   ✓ Saved to database (location_id: {device.location_id})")
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        errors.append(f"Photo {idx+1}: {error_msg}")
                        print(f"[DEVICE-REGISTER]   ✗ Photo {idx+1} failed: {error_msg}")
                else:
                    errors.append(f"Photo {idx+1}: HTTP {response.status_code}")
                    print(f"[DEVICE-REGISTER]   ✗ Photo {idx+1} failed with status {response.status_code}")

            except Exception as e:
                errors.append(f"Photo {idx+1}: {str(e)}")
                print(f"[DEVICE-REGISTER]   ✗ Error on photo {idx+1}: {str(e)}")

        print(f"[DEVICE-REGISTER] Registration complete: {successful_registrations}/{len(data.photos)} successful")
        print(f"{'='*60}\n")

        if successful_registrations == 0:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": "Failed to register any images",
                    "details": errors
                }
            )

        return {
            "success": True,
            "message": f"Successfully registered {successful_registrations} of {len(data.photos)} images to CodeProject.AI",
            "registered_count": successful_registrations,
            "total_count": len(data.photos),
            "errors": errors if errors else None
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[DEVICE-REGISTER] Error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


@app.post("/api/devices/recognize-face")
async def device_recognize_face(
    data: DeviceRecognizeRequest,
    device: Device = Depends(get_current_device)
):
    """Recognize face in image using CodeProject.AI (device-authenticated)"""
    try:
        print(f"\n{'='*60}")
        print(f"[DEVICE-RECOGNIZE] Device: {device.device_name} ({device.device_id[:8]}...)")
        print(f"[DEVICE-RECOGNIZE] Location: {device.location_id}")

        # Get the device's CodeProject endpoint
        codeproject_url = device.codeproject_endpoint
        if not codeproject_url:
            raise HTTPException(
                status_code=400,
                detail="Device has no CodeProject endpoint configured"
            )

        # Extract base64 data from data URL
        image_data = data.image
        if ',' in image_data:
            image_data = image_data.split(',')[1]

        # Decode base64 image
        image_bytes = base64.b64decode(image_data)
        image_size_kb = len(image_bytes) / 1024
        print(f"[DEVICE-RECOGNIZE] Image size: {image_size_kb:.2f} KB")

        # Send to CodeProject.AI for recognition
        files = {
            'image': ('frame.jpg', BytesIO(image_bytes), 'image/jpeg')
        }

        print(f"[DEVICE-RECOGNIZE] Sending to CodeProject.AI at {codeproject_url}...")

        response = requests.post(
            f"{codeproject_url}/vision/face/recognize",
            files=files,
            data={'min_confidence': 0.4},
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()

            if result.get('success'):
                predictions = result.get('predictions', [])
                print(f"[DEVICE-RECOGNIZE] Faces detected: {len(predictions)}")

                faces = []
                for pred in predictions:
                    face_data = {
                        'userid': pred.get('userid', 'unknown'),
                        'confidence': pred.get('confidence', 0),
                        'x_min': pred.get('x_min', 0),
                        'y_min': pred.get('y_min', 0),
                        'x_max': pred.get('x_max', 0),
                        'y_max': pred.get('y_max', 0)
                    }
                    faces.append(face_data)
                    print(f"[DEVICE-RECOGNIZE]   - {face_data['userid']}: {face_data['confidence']:.2f}")

                print(f"{'='*60}\n")

                return {
                    "success": True,
                    "faces": faces,
                    "count": len(faces)
                }
            else:
                error = result.get('error', 'Unknown error')
                print(f"[DEVICE-RECOGNIZE] CodeProject.AI error: {error}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "success": False,
                        "error": error
                    }
                )
        else:
            print(f"[DEVICE-RECOGNIZE] HTTP error: {response.status_code}")
            return JSONResponse(
                status_code=response.status_code,
                content={
                    "success": False,
                    "error": f"CodeProject.AI returned status {response.status_code}"
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[DEVICE-RECOGNIZE] Error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


# ============================================================================
# FACIAL RECOGNITION API ROUTES (from original Flask app)
# ============================================================================

@app.get("/register", response_class=HTMLResponse)
async def register_face_page(request: Request, user: User = Depends(current_active_user)):
    """Face registration page (requires authentication)"""
    return templates.TemplateResponse("register.html", {"request": request, "user": user})


@app.get("/recognize-face", response_class=HTMLResponse)
async def recognize_face_page(request: Request, user: User = Depends(current_active_user)):
    """Face recognition page (requires authentication)"""
    return templates.TemplateResponse("recognize.html", {"request": request, "user": user})


@app.get("/registered-faces", response_class=HTMLResponse)
async def registered_faces_page(request: Request, user: User = Depends(current_active_user)):
    """Registered faces gallery page (requires authentication)"""
    return templates.TemplateResponse("registered_faces.html", {"request": request, "user": user})


@app.get("/api/registered-faces")
async def get_registered_faces(
    location_id: Optional[int] = None,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get registered faces filtered by location (optional query parameter)"""
    try:
        from collections import defaultdict

        print(f"[GET-REGISTERED-FACES] User: {user.email} (ID: {user.id})")
        print(f"[GET-REGISTERED-FACES] Location filter: {location_id}")

        # Check user permissions
        if user.is_superuser:
            # Superadmin can see all or filter by specific location
            if location_id:
                result = await session.execute(
                    select(RegisteredFace).where(RegisteredFace.location_id == location_id)
                )
            else:
                # No filter - show all faces across all locations
                result = await session.execute(select(RegisteredFace))
        else:
            # Location admin - get their managed locations
            admin_result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.role == 'location_admin'
                )
            )
            admin_locations = [ulr.location_id for ulr in admin_result.scalars().all()]

            if not admin_locations:
                return {
                    "success": True,
                    "faces": [],
                    "total": 0,
                    "message": "No locations assigned"
                }

            # Filter based on query parameter
            if location_id:
                # Specific location requested - verify access
                if location_id not in admin_locations:
                    raise HTTPException(status_code=403, detail="Access denied to this location")
                result = await session.execute(
                    select(RegisteredFace).where(RegisteredFace.location_id == location_id)
                )
            else:
                # No filter - show all faces from managed locations
                result = await session.execute(
                    select(RegisteredFace).where(RegisteredFace.location_id.in_(admin_locations))
                )


        all_face_records = result.scalars().all()
        print(f"[GET-REGISTERED-FACES] Found {len(all_face_records)} face records")

        # Group by person name
        faces_dict = defaultdict(list)

        for face_record in all_face_records:
            # Convert absolute path to relative URL path
            filename = os.path.basename(face_record.file_path)
            photo_url = f"/uploads/{filename}"
            print(f"[GET-REGISTERED-FACES] Face: {face_record.person_name}, location_id: {face_record.location_id}")
            faces_dict[face_record.person_name].append(photo_url)

        # Convert to list format with one sample photo per person
        # Also get the codeproject_user_id and location info for each person
        registered_faces = []
        for name, photos in sorted(faces_dict.items()):
            # Get the codeproject_user_id and location_id from the first record for this person
            result = await session.execute(
                select(RegisteredFace).where(RegisteredFace.person_name == name).limit(1)
            )
            face_record = result.scalar_one_or_none()

            # Get location name if available
            location_name = None
            if face_record and face_record.location_id:
                loc_result = await session.execute(
                    select(Location).where(Location.id == face_record.location_id)
                )
                location = loc_result.scalar_one_or_none()
                if location:
                    location_name = location.name

            registered_faces.append({
                "person_name": name,  # Changed from "name" to match JavaScript expectation
                "photo": photos[0] if photos else None,  # Use first photo as profile picture
                "photo_count": len(photos),
                "all_photos": photos,
                "codeproject_user_id": face_record.codeproject_user_id if face_record else name,
                "location_id": face_record.location_id if face_record else None,
                "location_name": location_name
            })

        print(f"[GET-REGISTERED-FACES] Returning {len(registered_faces)} unique people")

        return {
            "success": True,
            "faces": registered_faces,
            "total": len(registered_faces)
        }

    except Exception as e:
        print(f"[REGISTERED-FACES] ERROR: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/register")
async def register_face(
    data: RegisterRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Register face images to CodeProject.AI"""
    try:
        print(f"\n{'='*60}")
        print(f"[REGISTER] New registration request at {datetime.now().strftime('%H:%M:%S')}")
        print(f"[REGISTER] User: {data.name}")
        print(f"[REGISTER] Photos to register: {len(data.photos)}")

        successful_registrations = 0
        errors = []

        for idx, photo_data in enumerate(data.photos):
            try:
                print(f"[REGISTER] Processing photo {idx+1}/{len(data.photos)}")

                # Extract base64 data from data URL
                if ',' in photo_data:
                    photo_data = photo_data.split(',')[1]

                # Decode base64 image
                image_bytes = base64.b64decode(photo_data)
                image_size_kb = len(image_bytes) / 1024
                print(f"[REGISTER]   Image size: {image_size_kb:.2f} KB")

                # Save locally for backup
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{data.name.replace(' ', '_')}_{timestamp}_{idx}.jpg"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                with open(filepath, 'wb') as f:
                    f.write(image_bytes)
                print(f"[REGISTER]   Saved locally: {filename}")

                # Register with CodeProject.AI
                files = {
                    'image': (filename, BytesIO(image_bytes), 'image/jpeg')
                }
                params = {
                    'userid': data.name
                }

                print(f"[REGISTER]   Sending to CodeProject.AI...")

                response = requests.post(
                    f"{CODEPROJECT_BASE_URL}/vision/face/register",
                    files=files,
                    data=params,
                    timeout=60
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        successful_registrations += 1
                        print(f"[REGISTER]   ✓ Photo {idx+1} registered successfully")

                        # Get user's selected location
                        location_context = await get_user_selected_location_and_role(user, session)
                        location_id = location_context.get("location_id") if location_context else None

                        # Save to database
                        registered_face = RegisteredFace(
                            person_name=data.name,
                            codeproject_user_id=data.name,
                            file_path=filepath,
                            codeproject_endpoint=CODEPROJECT_BASE_URL,
                            location_id=location_id,
                            registered_by_user_id=user.id
                        )
                        session.add(registered_face)
                        await session.commit()
                        print(f"[REGISTER]   ✓ Saved to database (location_id: {location_id})")
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        errors.append(f"Photo {idx+1}: {error_msg}")
                        print(f"[REGISTER]   ✗ Photo {idx+1} failed: {error_msg}")
                else:
                    errors.append(f"Photo {idx+1}: HTTP {response.status_code}")
                    print(f"[REGISTER]   ✗ Photo {idx+1} failed with status {response.status_code}")

            except Exception as e:
                errors.append(f"Photo {idx+1}: {str(e)}")
                print(f"[REGISTER]   ✗ Photo {idx+1} exception: {e}")

        print(f"[REGISTER] Registration complete: {successful_registrations}/{len(data.photos)} successful")
        print(f"{'='*60}\n")

        if successful_registrations > 0:
            return {
                "success": True,
                "message": f"Successfully registered {successful_registrations} out of {len(data.photos)} photos for {data.name}",
                "registered_count": successful_registrations,
                "total_count": len(data.photos),
                "errors": errors if errors else None
            }
        else:
            raise HTTPException(
                status_code=500,
                detail={"success": False, "error": "Failed to register any photos", "details": errors}
            )

    except Exception as e:
        print(f"[REGISTER] ✗ EXCEPTION: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/recognize")
async def recognize_face(
    data: RecognizeRequest,
    user: User = Depends(current_active_user)
):
    """Recognize face in image using CodeProject.AI"""
    try:
        print(f"\n{'='*60}")
        print(f"[RECOGNIZE] New recognition request at {datetime.now().strftime('%H:%M:%S')}")

        # Extract base64 data from data URL
        image_data = data.image
        if ',' in image_data:
            image_data = image_data.split(',')[1]

        # Decode base64 image
        image_bytes = base64.b64decode(image_data)

        # Send to CodeProject.AI for recognition
        files = {
            'image': ('frame.jpg', BytesIO(image_bytes), 'image/jpeg')
        }

        response = requests.post(
            f"{CODEPROJECT_BASE_URL}/vision/face/recognize",
            files=files,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            predictions = result.get('predictions', [])

            recognized_faces = []
            for pred in predictions:
                recognized_faces.append({
                    "userid": pred.get('userid', 'unknown'),
                    "confidence": pred.get('confidence', 0),
                    "x_min": pred.get('x_min', 0),
                    "y_min": pred.get('y_min', 0),
                    "x_max": pred.get('x_max', 0),
                    "y_max": pred.get('y_max', 0)
                })

            print(f"[RECOGNIZE] ✓ SUCCESS - Found {len(recognized_faces)} face(s)")
            print(f"{'='*60}\n")

            return {
                "success": True,
                "faces": recognized_faces,
                "count": len(recognized_faces)
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"CodeProject.AI returned status {response.status_code}"
            )

    except Exception as e:
        print(f"[RECOGNIZE] ✗ EXCEPTION: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/registered-faces/{person_name}")
async def delete_registered_face(
    person_name: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Delete a person's registered face from CodeProject.AI and remove all associated files"""
    try:
        print(f"\n{'='*60}")
        print(f"[DELETE] Deleting registered face: {person_name}")

        # Get all registered face records for this person
        result = await session.execute(
            select(RegisteredFace).where(RegisteredFace.person_name == person_name)
        )
        face_records = result.scalars().all()

        if not face_records:
            raise HTTPException(status_code=404, detail=f"No registered faces found for {person_name}")

        # Check permissions - location admins can only delete faces from their locations
        if not user.is_superuser:
            # Get user's admin locations
            admin_result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.role == 'location_admin'
                )
            )
            admin_location_ids = [ulr.location_id for ulr in admin_result.scalars().all()]

            # Check if all face records belong to locations the user manages
            for face_record in face_records:
                if face_record.location_id not in admin_location_ids:
                    raise HTTPException(
                        status_code=403,
                        detail=f"You don't have permission to delete this face (belongs to another location)"
                    )

        print(f"[DELETE] Found {len(face_records)} file(s) to delete")

        # Group face records by CodeProject endpoint
        endpoints = {}
        for face_record in face_records:
            endpoint = face_record.codeproject_endpoint
            if endpoint not in endpoints:
                endpoints[endpoint] = []
            endpoints[endpoint].append(face_record)

        # Delete from each CodeProject.AI server
        print(f"[DELETE] Removing from {len(endpoints)} CodeProject.AI server(s)...")
        for endpoint, records in endpoints.items():
            try:
                print(f"[DELETE]   Deleting from {endpoint}...")
                response = requests.post(
                    f"{endpoint}/vision/face/delete",
                    data={'userid': person_name},
                    timeout=30
                )

                if response.status_code == 200:
                    result_data = response.json()
                    if result_data.get('success'):
                        print(f"[DELETE]     ✓ Removed from {endpoint} ({len(records)} record(s))")
                    else:
                        print(f"[DELETE]     ⚠ CodeProject.AI response: {result_data.get('error', 'Unknown error')}")
                else:
                    print(f"[DELETE]     ⚠ CodeProject.AI returned status {response.status_code}")
            except Exception as e:
                print(f"[DELETE]     ⚠ Error removing from {endpoint}: {e}")
                # Continue with file deletion even if CodeProject.AI fails

        # Delete files from disk
        deleted_files = 0
        for face_record in face_records:
            try:
                if os.path.exists(face_record.file_path):
                    os.remove(face_record.file_path)
                    deleted_files += 1
                    print(f"[DELETE]   ✓ Deleted file: {os.path.basename(face_record.file_path)}")
                else:
                    print(f"[DELETE]   ⚠ File not found: {face_record.file_path}")
            except Exception as e:
                print(f"[DELETE]   ✗ Error deleting file {face_record.file_path}: {e}")

        # Delete from database
        for face_record in face_records:
            await session.delete(face_record)
        await session.commit()
        print(f"[DELETE]   ✓ Removed {len(face_records)} record(s) from database")

        print(f"[DELETE] Deletion complete for {person_name}")
        print(f"{'='*60}\n")

        return {
            "success": True,
            "message": f"Successfully deleted {person_name}",
            "files_deleted": deleted_files,
            "records_deleted": len(face_records)
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[DELETE] ✗ EXCEPTION: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print(f"\n{'*'*60}")
    print(f"*{' '*58}*")
    print(f"*  Facial Recognition App with Authentication{' '*14}*")
    print(f"*{' '*58}*")
    print(f"{'*'*60}\n")
    print(f"Server will start at: http://localhost:5000")
    print(f"Login page: http://localhost:5000/login")
    print(f"Dashboard: http://localhost:5000/dashboard")
    print(f"\nPress Ctrl+C to stop\n")

    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)

