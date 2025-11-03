"""
Facial Recognition App with FastAPI and User Authentication
Based on plant_logs_server authentication system
"""
import os
import sys
from datetime import datetime, timedelta, date
from typing import Optional, AsyncGenerator, List
import secrets
import base64
from io import BytesIO
import json
import asyncio
import uuid
import traceback

from fastapi import FastAPI, Depends, HTTPException, Request, Form, status, WebSocket, WebSocketDisconnect, File, UploadFile
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import Boolean, Integer, String, Text, Column, ForeignKey, select, DateTime, func, Numeric, or_, and_, delete
from sqlalchemy.dialects.mysql import LONGTEXT
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
DEFAULT_DASHBOARD_DISPLAY_TIMEOUT_MINUTES = int(os.getenv("DEFAULT_DASHBOARD_DISPLAY_TIMEOUT_MINUTES", "2"))

# User expiration configuration
DEFAULT_EXPIRATION_DAYS = int(os.getenv("DEFAULT_EXPIRATION_DAYS", "1"))  # Number of days until visitor expires

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
# TOKEN CACHE
# ============================================================================

# In-memory cache for device token validation
# Structure: { device_id: { 'token': str, 'device': Device, 'expires_at': datetime, 'is_approved': bool } }
DEVICE_TOKEN_CACHE = {}
DEVICE_TOKEN_CACHE_TTL = 300  # 5 minutes in seconds

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
    # Unique identifier for this person (UUID)
    person_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    # The person's name - for display purposes
    person_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # The CodeProject.AI user_id (will be person_id instead of person_name)
    codeproject_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Path to the image file
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    # CodeProject.AI server where this face was registered
    codeproject_server_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("codeproject_server.id"), nullable=True)
    # Location where this face was registered
    location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("location.id"), nullable=True)
    # When it was registered
    registered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    # User who registered this face
    registered_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("user.id"), nullable=True)
    # Profile photo (base64 encoded image for dashboard thumbnails)
    profile_photo: Mapped[Optional[str]] = mapped_column(LONGTEXT, nullable=True)
    # Whether this person is an employee or visitor
    is_employee: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    # User expiration date (ISO date string or "never")
    user_expiration: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)


class Location(Base):
    """Physical locations where devices will be deployed"""
    __tablename__ = "location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    address: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default='UTC')
    contact_info: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    codeproject_server_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("codeproject_server.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False)


class Area(Base):
    """Areas within a location (e.g., Lobby, Kitchen, Bedroom)"""
    __tablename__ = "area"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(Integer, ForeignKey("location.id", ondelete="CASCADE"), nullable=False)
    area_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Category(Base):
    """Categories for organizing tags (can be global or location-specific)"""
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default='global')  # 'global' or 'location'
    location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("location.id", ondelete="CASCADE"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Tag(Base):
    """Tags within categories"""
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("category.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PersonTag(Base):
    """Many-to-many relationship between registered faces and tags"""
    __tablename__ = "person_tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Unique identifier for the person (UUID) - primary way to link
    person_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    # Kept for backward compatibility, but person_id is the source of truth
    person_name: Mapped[str] = mapped_column(String(255), nullable=False)
    location_id: Mapped[int] = mapped_column(Integer, ForeignKey("location.id", ondelete="CASCADE"), nullable=False)
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("tag.id", ondelete="CASCADE"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


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
    area_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("area.id", ondelete="SET NULL"), nullable=True)
    # Device type: 'registration_kiosk' or 'people_scanner'
    device_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    codeproject_server_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("codeproject_server.id"), nullable=True)
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
    # Processing mode for image recognition: 'direct' (device calls CodeProject.AI directly) or 'server' (device -> flask -> CodeProject.AI)
    processing_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default='server')
    # Dashboard-specific display timeout (how long to show someone after last detection)
    dashboard_display_timeout_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class RegistrationLink(Base):
    """Public registration links with QR codes for remote user registration"""
    __tablename__ = "registration_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    link_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)  # UUID for public URL
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(Integer, ForeignKey("location.id"), nullable=False)
    # Expiration for users registered via this link (ISO date or "never")
    user_expiration: Mapped[str] = mapped_column(String(50), nullable=False)
    # When the link itself expires (ISO datetime)
    link_expiration: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Maximum number of times this link can be used (NULL = unlimited)
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Current number of times used
    current_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Whether users registered are employees or visitors
    is_employee: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Link status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    # Optional link name/description
    link_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class LinkRegistration(Base):
    """Tracks which people were registered via which registration links"""
    __tablename__ = "link_registration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    link_id: Mapped[str] = mapped_column(String(36), ForeignKey("registration_link.link_id", ondelete="CASCADE"), nullable=False, index=True)
    person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)  # UUID of registered person
    person_name: Mapped[str] = mapped_column(String(255), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


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


# ============================================================================
# TOKEN CACHE FUNCTIONS
# ============================================================================

def invalidate_device_cache(device_id: str):
    """Invalidate cache entry for a specific device"""
    if device_id in DEVICE_TOKEN_CACHE:
        del DEVICE_TOKEN_CACHE[device_id]
        print(f"[CACHE] Invalidated cache for device {device_id[:8]}...")


def get_device_from_cache(device_id: str, token: str) -> Optional[Device]:
    """
    Get device from cache if valid.
    Returns Device object if cache hit and valid, None otherwise.
    """
    if device_id not in DEVICE_TOKEN_CACHE:
        return None

    cache_entry = DEVICE_TOKEN_CACHE[device_id]

    # Check if cache expired
    if datetime.utcnow() > cache_entry['expires_at']:
        del DEVICE_TOKEN_CACHE[device_id]
        return None

    # Check if token matches
    if cache_entry['token'] != token:
        # Token changed - invalidate cache
        del DEVICE_TOKEN_CACHE[device_id]
        return None

    # Check if still approved
    if not cache_entry['is_approved']:
        # Device was unapproved - invalidate cache
        del DEVICE_TOKEN_CACHE[device_id]
        return None

    return cache_entry['device']


def add_device_to_cache(device_id: str, token: str, device: Device):
    """Add device to cache with TTL"""
    DEVICE_TOKEN_CACHE[device_id] = {
        'token': token,
        'device': device,
        'is_approved': device.is_approved,
        'expires_at': datetime.utcnow() + timedelta(seconds=DEVICE_TOKEN_CACHE_TTL)
    }


# Device authentication dependency
async def get_current_device(
    request: Request,
    session: AsyncSession = Depends(get_async_session)
) -> Device:
    """Authenticate device by device_id and token from request headers (with caching)"""
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

    if not device_token:
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing device token"
        )

    # Check cache first
    cached_device = get_device_from_cache(device_id, device_token)
    if cached_device:
        # Cache hit - update last_seen asynchronously without blocking
        try:
            cached_device.last_seen = datetime.utcnow()
            await session.commit()
        except:
            await session.rollback()
        return cached_device

    # Cache miss - fetch from database
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

    if device_token != device.device_token:
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing device token"
        )

    # Check if token needs rotation
    new_token = await rotate_device_token_if_needed(device, session)
    if new_token:
        # Token was rotated - include in response header for client to update
        request.state.new_device_token = new_token
        # Invalidate cache since token changed
        invalidate_device_cache(device_id)

    # Update last_seen (ignore concurrency errors since this is not critical)
    try:
        device.last_seen = datetime.utcnow()
        await session.commit()
    except Exception as e:
        # If update fails due to concurrent modification, that's okay
        # Another request already updated it
        await session.rollback()
        # Re-fetch the device to get the latest state
        await session.refresh(device)

    # Add to cache if token wasn't rotated (if rotated, we'll cache on next request with new token)
    if not new_token:
        add_device_to_cache(device_id, device_token, device)

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


class AdminRegisterRequest(BaseModel):
    person_name: str
    location_id: int
    photos: List[dict]  # List of {position: str, image: str}


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
    area_id: Optional[int] = None
    device_type: str  # 'registration_kiosk', 'people_scanner', or 'location_dashboard'
    codeproject_server_id: Optional[int] = None  # Not required for location_dashboard
    # Processing mode: 'direct' (device -> CodeProject.AI) or 'server' (device -> flask -> CodeProject.AI)
    processing_mode: Optional[str] = 'server'  # Default to 'server'
    # Scanner detection settings (optional, defaults to .env values)
    confidence_threshold: Optional[float] = None
    presence_timeout_minutes: Optional[int] = None
    detection_cooldown_seconds: Optional[int] = None
    # Dashboard display timeout (optional, defaults to .env value)
    dashboard_display_timeout_minutes: Optional[int] = None


class UpdateDeviceRequest(BaseModel):
    device_name: Optional[str] = None
    location_id: Optional[int] = None
    area_id: Optional[int] = None
    device_type: Optional[str] = None
    codeproject_server_id: Optional[int] = None
    # Processing mode: 'direct' or 'server'
    processing_mode: Optional[str] = None
    # Scanner detection settings
    confidence_threshold: Optional[float] = None
    presence_timeout_minutes: Optional[int] = None
    detection_cooldown_seconds: Optional[int] = None
    # Dashboard display timeout
    dashboard_display_timeout_minutes: Optional[int] = None


class CreateLocationRequest(BaseModel):
    name: str
    address: Optional[str] = None
    description: Optional[str] = None
    timezone: Optional[str] = 'UTC'
    contact_info: Optional[str] = None
    codeproject_server_id: Optional[int] = None


class UpdateLocationRequest(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None
    timezone: Optional[str] = None
    contact_info: Optional[str] = None
    codeproject_server_id: Optional[int] = None


class CreateAreaRequest(BaseModel):
    location_id: int
    area_name: str
    description: Optional[str] = None


class UpdateAreaRequest(BaseModel):
    area_name: Optional[str] = None
    description: Optional[str] = None


class CreateCategoryRequest(BaseModel):
    name: str
    description: Optional[str] = None
    scope: str  # 'global' or 'location'
    location_id: Optional[int] = None


class UpdateCategoryRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class CreateTagRequest(BaseModel):
    category_id: int
    name: str
    description: Optional[str] = None


class UpdateTagRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class AssignPersonTagsRequest(BaseModel):
    person_id: str  # UUID
    person_name: str  # For display/logging purposes
    location_id: int
    tag_ids: list[int]


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


class CreateRegistrationLinkRequest(BaseModel):
    location_id: int
    link_name: Optional[str] = None
    user_expiration: str  # ISO date or "never"
    link_expiration: str  # ISO datetime
    max_uses: Optional[int] = None  # NULL = unlimited
    is_employee: bool = False


class PublicRegisterRequest(BaseModel):
    link_id: str
    person_name: str
    photos: list[str]  # Base64 data URLs


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


# Custom dependency that redirects to login for browser requests
async def current_active_user_with_redirect(
    request: Request,
    user: User = Depends(current_active_user)
) -> User:
    """Get current user, but redirect to login instead of JSON error for browser requests"""
    return user


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

    async def broadcast_to_all(self, message: dict):
        """Send a message to all WebSocket connections across all locations"""
        for location_id in list(self.active_connections.keys()):
            await self.broadcast_to_location(location_id, message)

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


# Exception handler to redirect browser requests to login
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """Custom exception handler that redirects to login for 401 errors from browsers"""
    # Check if this is a 401 Unauthorized error
    if exc.status_code == 401:
        # Check if this is a browser request (looks for text/html in Accept header)
        accept_header = request.headers.get("accept", "")
        if "text/html" in accept_header:
            # Browser request - redirect to login
            return RedirectResponse(url="/login", status_code=302)

    # For all other cases, return the default JSON response
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# ============================================================================
# BACKGROUND TASKS
# ============================================================================

async def cleanup_stale_pending_devices():
    """Background task to remove pending devices that haven't checked in for 5+ minutes"""
    PENDING_DEVICE_TIMEOUT_MINUTES = 5
    CHECK_INTERVAL_SECONDS = 60  # Check every minute

    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

            # Get database session
            async for session in get_async_session():
                try:
                    # Find pending devices that haven't checked in for 5+ minutes
                    timeout_threshold = datetime.utcnow() - timedelta(minutes=PENDING_DEVICE_TIMEOUT_MINUTES)

                    result = await session.execute(
                        select(Device).where(
                            Device.is_approved == False,
                            Device.last_seen.isnot(None),
                            Device.last_seen < timeout_threshold
                        )
                    )
                    stale_devices = result.scalars().all()

                    if stale_devices:
                        device_ids = [d.device_id for d in stale_devices]
                        print(f"[CLEANUP] Removing {len(stale_devices)} stale pending device(s): {', '.join(d.device_id[:8] for d in stale_devices)}")

                        # Delete stale pending devices
                        await session.execute(
                            delete(Device).where(Device.device_id.in_(device_ids))
                        )
                        await session.commit()

                        # Broadcast removal to all connected dashboards
                        await manager.broadcast_to_all({
                            "type": "pending_devices_removed",
                            "device_ids": device_ids,
                            "reason": "timeout"
                        })

                except Exception as e:
                    print(f"[CLEANUP] Error cleaning up stale pending devices: {e}")
                    await session.rollback()
                finally:
                    break  # Exit the session loop after one iteration

        except Exception as e:
            print(f"[CLEANUP] Unexpected error in cleanup task: {e}")


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

    # Start background cleanup task for stale pending devices
    asyncio.create_task(cleanup_stale_pending_devices())
    print(f"[STARTUP] ✓ Background cleanup task started (pending device timeout: 5 minutes)")

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
        "total_categories": 0,
        "total_tags": 0,
        "total_servers": 0,
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

            # Count categories (global + this location's)
            category_count = await session.execute(
                select(func.count(Category.id)).where(
                    or_(Category.scope == 'global', Category.location_id == location_id)
                )
            )
            stats["total_categories"] = category_count.scalar()

            # Count tags for accessible categories
            tag_count = await session.execute(
                select(func.count(Tag.id)).where(
                    Tag.category_id.in_(
                        select(Category.id).where(
                            or_(Category.scope == 'global', Category.location_id == location_id)
                        )
                    )
                )
            )
            stats["total_tags"] = tag_count.scalar()
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

            # Count categories (all)
            category_count = await session.execute(select(func.count(Category.id)))
            stats["total_categories"] = category_count.scalar()

            # Count tags (all)
            tag_count = await session.execute(select(func.count(Tag.id)))
            stats["total_tags"] = tag_count.scalar()

        # Get all locations for managed_locations dropdown (always show all for superadmin)
        locations_result = await session.execute(select(Location))
        all_locations = locations_result.scalars().all()
        stats["managed_locations"] = [
            {"id": loc.id, "name": loc.name} for loc in all_locations
        ]

        # Count servers (always all for superadmin)
        server_count = await session.execute(select(func.count(CodeProjectServer.id)))
        stats["total_servers"] = server_count.scalar()

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

            # Count categories (global + their locations')
            category_count = await session.execute(
                select(func.count(Category.id)).where(
                    or_(Category.scope == 'global', Category.location_id.in_(location_ids))
                )
            )
            stats["total_categories"] = category_count.scalar()

            # Count tags for accessible categories
            tag_count = await session.execute(
                select(func.count(Tag.id)).where(
                    Tag.category_id.in_(
                        select(Category.id).where(
                            or_(Category.scope == 'global', Category.location_id.in_(location_ids))
                        )
                    )
                )
            )
            stats["total_tags"] = tag_count.scalar()

            # Count servers (location admins can see all servers)
            server_count = await session.execute(select(func.count(CodeProjectServer.id)))
            stats["total_servers"] = server_count.scalar()

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
            codeproject_server_id=location_data.codeproject_server_id,
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
            # Get server name for this location
            server_name = None
            if loc.codeproject_server_id:
                server_result = await session.execute(
                    select(CodeProjectServer).where(CodeProjectServer.id == loc.codeproject_server_id)
                )
                server = server_result.scalar_one_or_none()
                if server:
                    server_name = server.friendly_name

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
                "codeproject_server_id": loc.codeproject_server_id,
                "codeproject_server_name": server_name,
                "created_at": loc.created_at.isoformat(),
                "approved_devices": [
                    {
                        "device_id": d.device_id,
                        "device_name": d.device_name,
                        "device_type": d.device_type,
                        "codeproject_server_id": d.codeproject_server_id,
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

    # Get all servers for lookup
    servers_result = await session.execute(select(CodeProjectServer))
    servers_dict = {s.id: s.endpoint_url for s in servers_result.scalars().all()}

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
                    "codeproject_endpoint": servers_dict.get(d.codeproject_server_id) if d.codeproject_server_id else None,
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
    if location_data.codeproject_server_id is not None:
        location.codeproject_server_id = location_data.codeproject_server_id

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
# AREA MANAGEMENT ENDPOINTS
# ============================================================================

@app.post("/api/areas")
async def create_area(
    data: CreateAreaRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Create a new area for a location"""
    try:
        # Check if user has access to this location
        if not user.is_superuser:
            result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.location_id == data.location_id,
                    UserLocationRole.role == 'location_admin'
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Access denied to this location")

        # Check if area name already exists for this location
        result = await session.execute(
            select(Area).where(
                Area.location_id == data.location_id,
                Area.area_name == data.area_name
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Area name already exists for this location")

        # Create area
        area = Area(
            location_id=data.location_id,
            area_name=data.area_name,
            description=data.description
        )
        session.add(area)
        await session.commit()
        await session.refresh(area)

        return {
            "success": True,
            "area": {
                "id": area.id,
                "location_id": area.location_id,
                "area_name": area.area_name,
                "description": area.description,
                "created_at": area.created_at.isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/locations/{location_id}/areas")
async def get_areas_for_location(
    location_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get all areas for a location"""
    try:
        # Check if user has access to this location
        if not user.is_superuser:
            result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.location_id == location_id
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Access denied to this location")

        # Get areas
        result = await session.execute(
            select(Area).where(Area.location_id == location_id).order_by(Area.area_name)
        )
        areas = result.scalars().all()

        return {
            "success": True,
            "areas": [
                {
                    "id": area.id,
                    "location_id": area.location_id,
                    "area_name": area.area_name,
                    "description": area.description,
                    "created_at": area.created_at.isoformat(),
                    "updated_at": area.updated_at.isoformat()
                }
                for area in areas
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/areas/{area_id}")
async def update_area(
    area_id: int,
    data: UpdateAreaRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Update an area"""
    try:
        # Get area
        result = await session.execute(select(Area).where(Area.id == area_id))
        area = result.scalar_one_or_none()
        if not area:
            raise HTTPException(status_code=404, detail="Area not found")

        # Check if user has access to this location
        if not user.is_superuser:
            result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.location_id == area.location_id,
                    UserLocationRole.role == 'location_admin'
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Access denied to this location")

        # Check if new name conflicts
        if data.area_name:
            result = await session.execute(
                select(Area).where(
                    Area.location_id == area.location_id,
                    Area.area_name == data.area_name,
                    Area.id != area_id
                )
            )
            if result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Area name already exists for this location")

            area.area_name = data.area_name

        if data.description is not None:
            area.description = data.description

        await session.commit()
        await session.refresh(area)

        return {
            "success": True,
            "area": {
                "id": area.id,
                "location_id": area.location_id,
                "area_name": area.area_name,
                "description": area.description,
                "updated_at": area.updated_at.isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/areas/{area_id}")
async def delete_area(
    area_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Delete an area"""
    try:
        # Get area
        result = await session.execute(select(Area).where(Area.id == area_id))
        area = result.scalar_one_or_none()
        if not area:
            raise HTTPException(status_code=404, detail="Area not found")

        # Check if user has access to this location
        if not user.is_superuser:
            result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.location_id == area.location_id,
                    UserLocationRole.role == 'location_admin'
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Access denied to this location")

        # Delete area (devices will have area_id set to NULL due to ON DELETE SET NULL)
        await session.delete(area)
        await session.commit()

        return {"success": True, "message": "Area deleted"}
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CATEGORY & TAG MANAGEMENT API ROUTES
# ============================================================================

@app.post("/api/categories")
async def create_category(
    data: CreateCategoryRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Create a new category"""
    try:
        # Validate scope
        if data.scope not in ['global', 'location']:
            raise HTTPException(status_code=400, detail="Scope must be 'global' or 'location'")

        # If location-specific, validate location_id and access
        if data.scope == 'location':
            if not data.location_id:
                raise HTTPException(status_code=400, detail="location_id required for location-specific categories")

            # Check if user has access to this location
            if not user.is_superuser:
                result = await session.execute(
                    select(UserLocationRole).where(
                        UserLocationRole.user_id == user.id,
                        UserLocationRole.location_id == data.location_id,
                        UserLocationRole.role == 'location_admin'
                    )
                )
                if not result.scalar_one_or_none():
                    raise HTTPException(status_code=403, detail="Access denied to this location")

        # Global categories require superadmin
        if data.scope == 'global' and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Only superadmins can create global categories")

        category = Category(
            name=data.name,
            description=data.description,
            scope=data.scope,
            location_id=data.location_id if data.scope == 'location' else None
        )
        session.add(category)
        await session.commit()
        await session.refresh(category)

        return {
            "success": True,
            "category": {
                "id": category.id,
                "name": category.name,
                "description": category.description,
                "scope": category.scope,
                "location_id": category.location_id,
                "created_at": category.created_at.isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/categories")
async def get_categories(
    location_id: Optional[int] = None,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get all categories (global + location-specific for given location)"""
    try:
        # If location_id provided, check access
        if location_id and not user.is_superuser:
            result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.location_id == location_id
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Access denied to this location")

        # Get global categories + location-specific ones
        if location_id:
            result = await session.execute(
                select(Category).where(
                    or_(
                        Category.scope == 'global',
                        and_(Category.scope == 'location', Category.location_id == location_id)
                    )
                )
            )
        else:
            # No location specified - return only global categories
            result = await session.execute(
                select(Category).where(Category.scope == 'global')
            )

        categories = result.scalars().all()

        return {
            "success": True,
            "categories": [
                {
                    "id": cat.id,
                    "name": cat.name,
                    "description": cat.description,
                    "scope": cat.scope,
                    "location_id": cat.location_id,
                    "created_at": cat.created_at.isoformat()
                }
                for cat in categories
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/categories/{category_id}")
async def update_category(
    category_id: int,
    data: UpdateCategoryRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Update a category"""
    try:
        result = await session.execute(select(Category).where(Category.id == category_id))
        category = result.scalar_one_or_none()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        # Check permissions
        if category.scope == 'global' and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Only superadmins can edit global categories")

        if category.scope == 'location' and not user.is_superuser:
            result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.location_id == category.location_id,
                    UserLocationRole.role == 'location_admin'
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Access denied to this location")

        if data.name is not None:
            category.name = data.name
        if data.description is not None:
            category.description = data.description
        category.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(category)

        return {
            "success": True,
            "category": {
                "id": category.id,
                "name": category.name,
                "description": category.description,
                "scope": category.scope,
                "location_id": category.location_id,
                "updated_at": category.updated_at.isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/categories/{category_id}")
async def delete_category(
    category_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Delete a category (will cascade delete tags)"""
    try:
        result = await session.execute(select(Category).where(Category.id == category_id))
        category = result.scalar_one_or_none()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        # Check permissions
        if category.scope == 'global' and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Only superadmins can delete global categories")

        if category.scope == 'location' and not user.is_superuser:
            result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.location_id == category.location_id,
                    UserLocationRole.role == 'location_admin'
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Access denied to this location")

        await session.delete(category)
        await session.commit()

        return {"success": True, "message": "Category deleted"}
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tags")
async def create_tag(
    data: CreateTagRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Create a new tag within a category"""
    try:
        # Get category to check permissions
        result = await session.execute(select(Category).where(Category.id == data.category_id))
        category = result.scalar_one_or_none()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        # Check permissions
        if category.scope == 'global' and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Only superadmins can add tags to global categories")

        if category.scope == 'location' and not user.is_superuser:
            result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.location_id == category.location_id,
                    UserLocationRole.role == 'location_admin'
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Access denied to this location")

        tag = Tag(
            category_id=data.category_id,
            name=data.name,
            description=data.description
        )
        session.add(tag)
        await session.commit()
        await session.refresh(tag)

        return {
            "success": True,
            "tag": {
                "id": tag.id,
                "category_id": tag.category_id,
                "name": tag.name,
                "description": tag.description,
                "created_at": tag.created_at.isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/categories/{category_id}/tags")
async def get_tags_by_category(
    category_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get all tags for a category"""
    try:
        result = await session.execute(select(Tag).where(Tag.category_id == category_id))
        tags = result.scalars().all()

        return {
            "success": True,
            "tags": [
                {
                    "id": tag.id,
                    "category_id": tag.category_id,
                    "name": tag.name,
                    "description": tag.description,
                    "created_at": tag.created_at.isoformat()
                }
                for tag in tags
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/tags/{tag_id}")
async def update_tag(
    tag_id: int,
    data: UpdateTagRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Update a tag"""
    try:
        result = await session.execute(select(Tag).where(Tag.id == tag_id))
        tag = result.scalar_one_or_none()
        if not tag:
            raise HTTPException(status_code=404, detail="Tag not found")

        # Get category for permission check
        result = await session.execute(select(Category).where(Category.id == tag.category_id))
        category = result.scalar_one_or_none()

        # Check permissions
        if category.scope == 'global' and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Only superadmins can edit tags in global categories")

        if category.scope == 'location' and not user.is_superuser:
            result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.location_id == category.location_id,
                    UserLocationRole.role == 'location_admin'
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Access denied to this location")

        if data.name is not None:
            tag.name = data.name
        if data.description is not None:
            tag.description = data.description
        tag.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(tag)

        return {
            "success": True,
            "tag": {
                "id": tag.id,
                "category_id": tag.category_id,
                "name": tag.name,
                "description": tag.description,
                "updated_at": tag.updated_at.isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/tags/{tag_id}")
async def delete_tag(
    tag_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Delete a tag"""
    try:
        result = await session.execute(select(Tag).where(Tag.id == tag_id))
        tag = result.scalar_one_or_none()
        if not tag:
            raise HTTPException(status_code=404, detail="Tag not found")

        # Get category for permission check
        result = await session.execute(select(Category).where(Category.id == tag.category_id))
        category = result.scalar_one_or_none()

        # Check permissions
        if category.scope == 'global' and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Only superadmins can delete tags in global categories")

        if category.scope == 'location' and not user.is_superuser:
            result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.location_id == category.location_id,
                    UserLocationRole.role == 'location_admin'
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Access denied to this location")

        await session.delete(tag)
        await session.commit()

        return {"success": True, "message": "Tag deleted"}
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/person-tags")
async def assign_person_tags(
    data: AssignPersonTagsRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Assign tags to a registered person (replaces existing tags)"""
    try:
        # Check if user has access to location
        if not user.is_superuser:
            result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.location_id == data.location_id,
                    UserLocationRole.role == 'location_admin'
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Access denied to this location")

        # Verify person exists at this location
        face_result = await session.execute(
            select(RegisteredFace).where(
                RegisteredFace.person_id == data.person_id,
                RegisteredFace.location_id == data.location_id
            ).limit(1)
        )
        registered_face = face_result.scalar_one_or_none()
        if not registered_face:
            raise HTTPException(status_code=404, detail="Person not found at this location")

        # Delete existing tags for this person (using person_id)
        await session.execute(
            delete(PersonTag).where(
                PersonTag.person_id == data.person_id,
                PersonTag.location_id == data.location_id
            )
        )

        # Add new tags
        for tag_id in data.tag_ids:
            person_tag = PersonTag(
                person_id=data.person_id,
                person_name=data.person_name,  # Keep for backward compatibility
                location_id=data.location_id,
                tag_id=tag_id
            )
            session.add(person_tag)

        await session.commit()

        return {
            "success": True,
            "message": f"Assigned {len(data.tag_ids)} tags to {data.person_name}"
        }
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/person-tags/{person_id}")
async def get_person_tags(
    person_id: str,
    location_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get all tags assigned to a person (by person_id UUID)"""
    try:
        # Check access
        if not user.is_superuser:
            result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.location_id == location_id
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Access denied to this location")

        # Get person tags with tag and category info (using person_id)
        result = await session.execute(
            select(PersonTag, Tag, Category).join(
                Tag, PersonTag.tag_id == Tag.id
            ).join(
                Category, Tag.category_id == Category.id
            ).where(
                PersonTag.person_id == person_id,
                PersonTag.location_id == location_id
            )
        )
        person_tags = result.all()

        return {
            "success": True,
            "tags": [
                {
                    "tag_id": tag.id,
                    "tag_name": tag.name,
                    "tag_description": tag.description,
                    "category_id": category.id,
                    "category_name": category.name,
                    "category_scope": category.scope,
                    "assigned_at": person_tag.assigned_at.isoformat()
                }
                for person_tag, tag, category in person_tags
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        select(Device).where(Device.codeproject_server_id == server_id)
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
                    RegisteredFace.codeproject_server_id == server_id
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
            RegisteredFace.codeproject_server_id == server_id
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
        # Get CodeProject endpoint from server
        codeproject_endpoint = None
        if existing_device.codeproject_server_id:
            server_result = await session.execute(
                select(CodeProjectServer).where(CodeProjectServer.id == existing_device.codeproject_server_id)
            )
            server = server_result.scalar_one_or_none()
            if server:
                codeproject_endpoint = server.endpoint_url

        # Device already registered, return existing registration code
        return {
            "success": True,
            "device_id": existing_device.device_id,
            "registration_code": existing_device.registration_code,
            "is_approved": existing_device.is_approved,
            "device_name": existing_device.device_name,
            "device_type": existing_device.device_type,
            "location_id": existing_device.location_id,
            "codeproject_endpoint": codeproject_endpoint
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

    # Get CodeProject endpoint from server
    codeproject_endpoint = None
    if device.codeproject_server_id:
        server_result = await session.execute(
            select(CodeProjectServer).where(CodeProjectServer.id == device.codeproject_server_id)
        )
        server = server_result.scalar_one_or_none()
        if server:
            codeproject_endpoint = server.endpoint_url

    response_data = {
        "device_id": device.device_id,
        "registration_code": device.registration_code,
        "is_approved": device.is_approved,
        "device_name": device.device_name,
        "device_type": device.device_type,
        "location_id": device.location_id,
        "codeproject_endpoint": codeproject_endpoint
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

    # Get area information if device has an area assigned
    area_name = None
    if device.area_id:
        area_result = await session.execute(select(Area).where(Area.id == device.area_id))
        area = area_result.scalar_one_or_none()
        if area:
            area_name = area.area_name

    # Get CodeProject endpoint from server
    codeproject_endpoint = None
    if device.codeproject_server_id:
        server_result = await session.execute(
            select(CodeProjectServer).where(CodeProjectServer.id == device.codeproject_server_id)
        )
        server = server_result.scalar_one_or_none()
        if server:
            codeproject_endpoint = server.endpoint_url

    # Return current device configuration
    response_data = {
        "status": "ok",
        "device_id": device.device_id,
        "device_name": device.device_name,
        "device_type": device.device_type,
        "location_id": device.location_id,
        "area_id": device.area_id,
        "area_name": area_name,
        "codeproject_endpoint": codeproject_endpoint,
        "is_approved": device.is_approved,
        # Processing mode (default to 'server' if not set)
        "processing_mode": device.processing_mode or 'server',
        # Detection settings (use device-specific or fall back to .env defaults)
        "confidence_threshold": float(device.confidence_threshold) if device.confidence_threshold is not None else DEFAULT_CONFIDENCE_THRESHOLD,
        "presence_timeout_minutes": device.presence_timeout_minutes if device.presence_timeout_minutes is not None else DEFAULT_PRESENCE_TIMEOUT_MINUTES,
        "detection_cooldown_seconds": device.detection_cooldown_seconds if device.detection_cooldown_seconds is not None else DEFAULT_DETECTION_COOLDOWN_SECONDS,
        # Dashboard display timeout (use device-specific or fall back to .env default)
        "dashboard_display_timeout_minutes": device.dashboard_display_timeout_minutes if device.dashboard_display_timeout_minutes is not None else DEFAULT_DASHBOARD_DISPLAY_TIMEOUT_MINUTES
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
            {"person_name": "uuid-here", "confidence": 0.95},
            {"person_name": "uuid-here-2", "confidence": 0.87}
        ]
    }
    Note: person_name field contains person_id (UUID) from CodeProject.AI
    """
    try:
        data = await request.json()
        detections = data.get("detections", [])

        if not detections:
            raise HTTPException(status_code=400, detail="No detections provided")

        if not device.location_id:
            raise HTTPException(status_code=400, detail="Device must have a location assigned")

        # Get area name if device has an area assigned
        area_name = None
        if device.area_id:
            area_result = await session.execute(select(Area).where(Area.id == device.area_id))
            area = area_result.scalar_one_or_none()
            if area:
                area_name = area.area_name

        # Extract person_ids from detections (scanner sends person_id in 'person_name' field)
        person_ids = []
        for det in detections:
            person_id = det.get("person_name")  # Scanner sends person_id here
            if person_id:
                person_ids.append(person_id)

        if not person_ids:
            return {"status": "ok", "logged": 0}

        # Get person metadata (person_name, profile_photo, is_employee) using person_id
        face_result = await session.execute(
            select(RegisteredFace.person_id, RegisteredFace.person_name, RegisteredFace.profile_photo, RegisteredFace.is_employee)
            .where(RegisteredFace.location_id == device.location_id)
            .where(RegisteredFace.person_id.in_(person_ids))
            .distinct(RegisteredFace.person_id)
        )
        person_data = {row.person_id: {"person_name": row.person_name, "profile_photo": row.profile_photo, "is_employee": row.is_employee, "tags": []} for row in face_result.all()}

        # Get tags for detected people (using person_id)
        tag_result = await session.execute(
            select(PersonTag, Tag, Category).join(
                Tag, PersonTag.tag_id == Tag.id
            ).join(
                Category, Tag.category_id == Category.id
            ).where(
                PersonTag.person_id.in_(person_ids),
                PersonTag.location_id == device.location_id
            )
        )
        for person_tag, tag, category in tag_result.all():
            if person_tag.person_id in person_data:
                person_data[person_tag.person_id]["tags"].append({
                    "tag_id": tag.id,
                    "tag_name": tag.name,
                    "category_id": category.id,
                    "category_name": category.name,
                    "category_scope": category.scope
                })

        # Create detection records for database and broadcast
        detection_records = []
        for det in detections:
            person_id = det.get("person_name")  # Scanner sends person_id here
            confidence = det.get("confidence")

            if not person_id or confidence is None:
                continue

            # Get person data
            data = person_data.get(person_id, {})
            person_name = data.get("person_name", "Unknown")

            # Save detection to database (using person_name for historical logging)
            detection = Detection(
                device_id=device.device_id,
                person_name=person_name,
                confidence=float(confidence),
                location_id=device.location_id,
                detected_at=datetime.utcnow()
            )
            session.add(detection)

            # Build detection record for broadcast
            detection_records.append({
                "person_id": person_id,
                "person_name": person_name,
                "confidence": confidence,
                "device_name": device.device_name or device.device_id[:8],
                "area_name": area_name,
                "detected_at": detection.detected_at.isoformat(),
                "profile_photo": data.get("profile_photo"),
                "is_employee": data.get("is_employee", False),
                "tags": data.get("tags", []),
                "device_id": device.device_id
            })

        await session.commit()

        # Broadcast to dashboards for this location via WebSocket
        if detection_records:
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

            # Get device names and areas
            device_result = await session.execute(
                select(Device).where(Device.location_id == location_id)
            )
            devices = {d.device_id: {"name": d.device_name, "area_id": d.area_id} for d in device_result.scalars().all()}

            # Get area names
            area_result = await session.execute(
                select(Area).where(Area.location_id == location_id)
            )
            areas = {a.id: a.area_name for a in area_result.scalars().all()}

            # Get profile photos and employee status from registered_face table
            # Group by person_name to get one record per person
            face_result = await session.execute(
                select(RegisteredFace.person_name, RegisteredFace.profile_photo, RegisteredFace.is_employee)
                .where(RegisteredFace.location_id == location_id)
            )
            person_data = {}
            for row in face_result.all():
                if row.person_name not in person_data:
                    person_data[row.person_name] = {
                        "profile_photo": row.profile_photo,
                        "is_employee": row.is_employee,
                        "tags": []
                    }

            # Get tags for people in this location
            tag_result = await session.execute(
                select(PersonTag, Tag, Category).join(
                    Tag, PersonTag.tag_id == Tag.id
                ).join(
                    Category, Tag.category_id == Category.id
                ).where(
                    PersonTag.location_id == location_id
                )
            )
            for person_tag, tag, category in tag_result.all():
                if person_tag.person_name in person_data:
                    person_data[person_tag.person_name]["tags"].append({
                        "tag_id": tag.id,
                        "tag_name": tag.name,
                        "category_id": category.id,
                        "category_name": category.name,
                        "category_scope": category.scope
                    })

            # Add device names, area names, profile photos, employee status, and tags to detections
            for detection in person_latest.values():
                device_info = devices.get(detection["device_id"], {})
                detection["device_name"] = device_info.get("name", detection["device_id"][:8])
                area_id = device_info.get("area_id")
                detection["area_name"] = areas.get(area_id) if area_id else None
                data = person_data.get(detection["person_name"], {})
                detection["profile_photo"] = data.get("profile_photo")
                detection["is_employee"] = data.get("is_employee", False)
                detection["tags"] = data.get("tags", [])

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

    # Validate device type and determine CodeProject server
    if data.device_type in ['registration_kiosk', 'people_scanner']:
        # These devices need a CodeProject server
        server_id = data.codeproject_server_id

        if not server_id:
            # Default to location's server
            location = location_result.scalar_one()
            server_id = location.codeproject_server_id

        if not server_id:
            # Default to first available server
            first_server_result = await session.execute(
                select(CodeProjectServer).order_by(CodeProjectServer.id).limit(1)
            )
            first_server = first_server_result.scalar_one_or_none()
            if first_server:
                server_id = first_server.id
            else:
                raise HTTPException(
                    status_code=400,
                    detail="No CodeProject servers available. Please add a CodeProject server first."
                )

        # Verify the server exists
        server_check = await session.execute(
            select(CodeProjectServer).where(CodeProjectServer.id == server_id)
        )
        if not server_check.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="CodeProject server not found")

        data.codeproject_server_id = server_id
    elif data.device_type == 'location_dashboard':
        # Dashboard doesn't need CodeProject server
        data.codeproject_server_id = None
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
    device.area_id = data.area_id
    device.device_type = data.device_type
    device.codeproject_server_id = data.codeproject_server_id
    device.approved_at = datetime.utcnow()
    device.approved_by_user_id = user.id
    device.device_token = device_token
    device.token_created_at = datetime.utcnow()

    # Set scanner detection settings if provided
    if data.confidence_threshold is not None:
        device.confidence_threshold = data.confidence_threshold
    if data.presence_timeout_minutes is not None:
        device.presence_timeout_minutes = data.presence_timeout_minutes
    if data.detection_cooldown_seconds is not None:
        device.detection_cooldown_seconds = data.detection_cooldown_seconds

    # Set dashboard display timeout if provided
    if data.dashboard_display_timeout_minutes is not None:
        device.dashboard_display_timeout_minutes = data.dashboard_display_timeout_minutes

    # Set processing mode (default to 'server' if not specified)
    device.processing_mode = data.processing_mode or 'server'

    # Commit with retry on concurrency error
    try:
        await session.commit()
    except Exception as e:
        # If concurrent modification (heartbeat updated last_seen), retry
        await session.rollback()
        await session.refresh(device)
        # Reapply all changes
        device.device_name = data.device_name
        device.location_id = data.location_id
        device.area_id = data.area_id
        device.device_type = data.device_type
        device.codeproject_server_id = data.codeproject_server_id
        device.is_approved = True
        device.approved_at = datetime.utcnow()
        device.approved_by_user_id = user.id
        device.device_token = device_token
        device.token_created_at = datetime.utcnow()
        if data.confidence_threshold is not None:
            device.confidence_threshold = data.confidence_threshold
        if data.presence_timeout_minutes is not None:
            device.presence_timeout_minutes = data.presence_timeout_minutes
        if data.detection_cooldown_seconds is not None:
            device.detection_cooldown_seconds = data.detection_cooldown_seconds
        if data.dashboard_display_timeout_minutes is not None:
            device.dashboard_display_timeout_minutes = data.dashboard_display_timeout_minutes
        device.processing_mode = data.processing_mode or 'server'
        await session.commit()

    # Invalidate cache for this device
    invalidate_device_cache(device_id)

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

    # Get location and area names
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

        area_name = None
        if device.area_id:
            area_result = await session.execute(
                select(Area).where(Area.id == device.area_id)
            )
            area = area_result.scalar_one_or_none()
            if area:
                area_name = area.area_name

        # Get server name
        server_name = None
        if device.codeproject_server_id:
            server_result = await session.execute(
                select(CodeProjectServer).where(CodeProjectServer.id == device.codeproject_server_id)
            )
            server = server_result.scalar_one_or_none()
            if server:
                server_name = server.friendly_name

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
            "area_id": device.area_id,
            "area_name": area_name,
            "codeproject_server_id": device.codeproject_server_id,
            "codeproject_server_name": server_name,
            "processing_mode": device.processing_mode or 'server',
            "registered_at": device.registered_at.isoformat(),
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "token_status": token_status,
            "token_age_days": token_age_days,
            "token_created_at": device.token_created_at.isoformat() if device.token_created_at else None,
            # Scanner detection settings
            "confidence_threshold": float(device.confidence_threshold) if device.confidence_threshold is not None else None,
            "presence_timeout_minutes": device.presence_timeout_minutes,
            "detection_cooldown_seconds": device.detection_cooldown_seconds,
            # Dashboard display timeout
            "dashboard_display_timeout_minutes": device.dashboard_display_timeout_minutes
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

    # Validate device type and codeproject_server_id compatibility
    target_device_type = data.device_type if data.device_type is not None else device.device_type

    if target_device_type in ['registration_kiosk', 'people_scanner']:
        # These types require a CodeProject server
        target_server_id = data.codeproject_server_id if data.codeproject_server_id is not None else device.codeproject_server_id
        if not target_server_id:
            raise HTTPException(
                status_code=400,
                detail=f"CodeProject server is required for {target_device_type}"
            )
        # Verify server exists if being updated
        if data.codeproject_server_id is not None:
            server_check = await session.execute(
                select(CodeProjectServer).where(CodeProjectServer.id == data.codeproject_server_id)
            )
            if not server_check.scalar_one_or_none():
                raise HTTPException(status_code=404, detail="CodeProject server not found")
    elif target_device_type == 'location_dashboard':
        # Dashboard doesn't use CodeProject, clear it if changing to this type
        if data.device_type == 'location_dashboard':
            data.codeproject_server_id = None

    # Update device
    if data.device_name is not None:
        device.device_name = data.device_name
    if data.location_id is not None:
        device.location_id = data.location_id
    if data.area_id is not None:
        device.area_id = data.area_id
    if data.device_type is not None:
        device.device_type = data.device_type
    if data.codeproject_server_id is not None:
        device.codeproject_server_id = data.codeproject_server_id
    elif data.device_type == 'location_dashboard':
        # Explicitly clear codeproject_server_id when switching to dashboard
        device.codeproject_server_id = None

    # Update scanner detection settings
    if data.confidence_threshold is not None:
        device.confidence_threshold = data.confidence_threshold
    if data.presence_timeout_minutes is not None:
        device.presence_timeout_minutes = data.presence_timeout_minutes
    if data.detection_cooldown_seconds is not None:
        device.detection_cooldown_seconds = data.detection_cooldown_seconds

    # Update dashboard display timeout
    if data.dashboard_display_timeout_minutes is not None:
        device.dashboard_display_timeout_minutes = data.dashboard_display_timeout_minutes

    # Update processing mode
    if data.processing_mode is not None:
        device.processing_mode = data.processing_mode

    # Commit with retry on concurrency error
    try:
        await session.commit()
    except Exception as e:
        # If concurrent modification (heartbeat updated last_seen), retry
        await session.rollback()
        await session.refresh(device)
        # Reapply all changes
        if data.device_name is not None:
            device.device_name = data.device_name
        if data.location_id is not None:
            device.location_id = data.location_id
        if data.device_type is not None:
            device.device_type = data.device_type
        if data.codeproject_server_id is not None:
            device.codeproject_server_id = data.codeproject_server_id
        elif data.device_type == 'location_dashboard':
            device.codeproject_server_id = None
        if data.confidence_threshold is not None:
            device.confidence_threshold = data.confidence_threshold
        if data.presence_timeout_minutes is not None:
            device.presence_timeout_minutes = data.presence_timeout_minutes
        if data.detection_cooldown_seconds is not None:
            device.detection_cooldown_seconds = data.detection_cooldown_seconds
        if data.dashboard_display_timeout_minutes is not None:
            device.dashboard_display_timeout_minutes = data.dashboard_display_timeout_minutes
        if data.processing_mode is not None:
            device.processing_mode = data.processing_mode
        await session.commit()

    # Invalidate cache for this device since settings changed
    invalidate_device_cache(device_id)

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
    device.codeproject_server_id = None
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

    # Invalidate cache for this device
    invalidate_device_cache(device_id)

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

        # Get the device's CodeProject endpoint from server
        if not device.codeproject_server_id:
            raise HTTPException(
                status_code=400,
                detail="Device has no CodeProject server configured"
            )

        server_result = await session.execute(
            select(CodeProjectServer).where(CodeProjectServer.id == device.codeproject_server_id)
        )
        server = server_result.scalar_one_or_none()
        if not server:
            raise HTTPException(
                status_code=500,
                detail="CodeProject server not found"
            )

        codeproject_url = server.endpoint_url

        successful_registrations = 0
        errors = []
        profile_photo_path = None

        # Save profile photo to file if provided
        if data.profile_photo:
            try:
                print(f"[DEVICE-REGISTER] Saving profile photo...")
                profile_data = data.profile_photo
                if ',' in profile_data:
                    profile_data = profile_data.split(',')[1]

                profile_bytes = base64.b64decode(profile_data)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                profile_filename = f"{data.name.replace(' ', '_')}_{timestamp}_profile.jpg"
                profile_filepath = os.path.join(UPLOAD_FOLDER, profile_filename)

                with open(profile_filepath, 'wb') as f:
                    f.write(profile_bytes)
                # Store web-accessible path (not file system path)
                profile_photo_path = f"/uploads/{profile_filename}"
                print(f"[DEVICE-REGISTER]   ✓ Profile photo saved: {profile_filename}")
            except Exception as e:
                print(f"[DEVICE-REGISTER]   ✗ Error saving profile photo: {e}")
                profile_photo_path = None

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
                        # Only set profile_photo on the first database entry
                        registered_face = RegisteredFace(
                            person_name=data.name,
                            codeproject_user_id=data.name,
                            file_path=filepath,
                            codeproject_server_id=device.codeproject_server_id,
                            location_id=device.location_id,  # Tag with device's location
                            registered_by_user_id=None,  # Device registration
                            profile_photo=profile_photo_path if idx == 0 and profile_photo_path else None,
                            is_employee=False  # Default to visitor
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
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_async_session)
):
    """Recognize face in image using CodeProject.AI (device-authenticated)"""
    try:
        print(f"\n{'='*60}")
        print(f"[DEVICE-RECOGNIZE] Device: {device.device_name} ({device.device_id[:8]}...)")
        print(f"[DEVICE-RECOGNIZE] Location: {device.location_id}")

        # Get the device's CodeProject endpoint from server
        if not device.codeproject_server_id:
            raise HTTPException(
                status_code=400,
                detail="Device has no CodeProject server configured"
            )

        server_result = await session.execute(
            select(CodeProjectServer).where(CodeProjectServer.id == device.codeproject_server_id)
        )
        server = server_result.scalar_one_or_none()
        if not server:
            raise HTTPException(
                status_code=500,
                detail="CodeProject server not found"
            )

        codeproject_url = server.endpoint_url

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
                person_ids = []

                for pred in predictions:
                    person_id = pred.get('userid', 'unknown')  # This is now person_id from CodeProject
                    face_data = {
                        'userid': person_id,  # This is person_id
                        'confidence': pred.get('confidence', 0),
                        'x_min': pred.get('x_min', 0),
                        'y_min': pred.get('y_min', 0),
                        'x_max': pred.get('x_max', 0),
                        'y_max': pred.get('y_max', 0)
                    }
                    faces.append(face_data)
                    person_ids.append(person_id)
                    print(f"[DEVICE-RECOGNIZE]   - person_id {person_id}: {face_data['confidence']:.2f}")

                # Get metadata (person_name, profile photos, employee status, tags) using person_id
                if person_ids:
                    face_result = await session.execute(
                        select(RegisteredFace.person_id, RegisteredFace.person_name, RegisteredFace.profile_photo, RegisteredFace.is_employee)
                        .where(RegisteredFace.location_id == device.location_id)
                        .where(RegisteredFace.person_id.in_(person_ids))
                        .distinct(RegisteredFace.person_id)
                    )
                    person_data = {row.person_id: {"person_name": row.person_name, "profile_photo": row.profile_photo, "is_employee": row.is_employee, "tags": []} for row in face_result.all()}

                    # Get tags for recognized people (using person_id)
                    tag_result = await session.execute(
                        select(PersonTag, Tag, Category).join(
                            Tag, PersonTag.tag_id == Tag.id
                        ).join(
                            Category, Tag.category_id == Category.id
                        ).where(
                            PersonTag.person_id.in_(person_ids),
                            PersonTag.location_id == device.location_id
                        )
                    )
                    for person_tag, tag, category in tag_result.all():
                        if person_tag.person_id in person_data:
                            person_data[person_tag.person_id]["tags"].append({
                                "tag_id": tag.id,
                                "tag_name": tag.name,
                                "category_id": category.id,
                                "category_name": category.name,
                                "category_scope": category.scope
                            })

                    # Add metadata to face data and map person_id to person_name for display
                    for face in faces:
                        person_id = face['userid']
                        data = person_data.get(person_id, {})
                        face['person_name'] = data.get('person_name', 'Unknown')  # Add person_name for display
                        face['profile_photo'] = data.get('profile_photo')
                        face['is_employee'] = data.get('is_employee', False)
                        face['tags'] = data.get('tags', [])

                print(f"{'='*60}\n")

                return {
                    "success": True,
                    "faces": faces,
                    "count": len(faces)
                }
            else:
                # CodeProject.AI returned success=false (e.g., "No face found in image")
                # This is a valid response, not an error - return empty faces array
                error = result.get('error', 'Unknown error')
                print(f"[DEVICE-RECOGNIZE] No faces found: {error}")
                print(f"{'='*60}\n")

                return {
                    "success": True,
                    "faces": [],
                    "count": 0
                }
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
                "person_name": name,  # Display name
                "person_id": face_record.person_id if face_record else None,  # Unique identifier (UUID)
                "photo": photos[0] if photos else None,  # Use first photo as profile picture
                "photo_count": len(photos),
                "all_photos": photos,
                "codeproject_user_id": face_record.codeproject_user_id if face_record else name,
                "location_id": face_record.location_id if face_record else None,
                "location_name": location_name,
                "is_employee": face_record.is_employee if face_record else False,
                "registered_at": face_record.registered_at.isoformat() if face_record and hasattr(face_record, 'registered_at') and face_record.registered_at else None,
                "user_expiration": getattr(face_record, 'user_expiration', None) if face_record else None
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

        # Get user's location and its CodeProject server
        location_context = await get_user_selected_location_and_role(user, session)
        location_id = location_context.get("location_id") if location_context else None

        if not location_id:
            raise HTTPException(
                status_code=400,
                detail="No location selected. Please select a location first."
            )

        # Get location's CodeProject server
        location_result = await session.execute(
            select(Location).where(Location.id == location_id)
        )
        location = location_result.scalar_one_or_none()

        if not location or not location.codeproject_server_id:
            raise HTTPException(
                status_code=400,
                detail="Location has no CodeProject server configured. Please configure a server for this location."
            )

        # Get the server endpoint
        server_result = await session.execute(
            select(CodeProjectServer).where(CodeProjectServer.id == location.codeproject_server_id)
        )
        server = server_result.scalar_one_or_none()

        if not server:
            raise HTTPException(
                status_code=500,
                detail="CodeProject server not found"
            )

        codeproject_url = server.endpoint_url
        print(f"[REGISTER] Using CodeProject server: {server.friendly_name} ({codeproject_url})")

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
                    f"{codeproject_url}/vision/face/register",
                    files=files,
                    data=params,
                    timeout=60
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        successful_registrations += 1
                        print(f"[REGISTER]   ✓ Photo {idx+1} registered successfully")

                        # Save to database
                        registered_face = RegisteredFace(
                            person_name=data.name,
                            codeproject_user_id=data.name,
                            file_path=filepath,
                            codeproject_server_id=location.codeproject_server_id,
                            location_id=location_id,
                            registered_by_user_id=user.id,
                            is_employee=False  # Default to visitor
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


@app.post("/api/admin/register-face")
async def admin_register_face(
    data: AdminRegisterRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Admin endpoint to register face images with specified location"""
    try:
        print(f"\n{'='*60}")
        print(f"[ADMIN-REGISTER] New registration request")
        print(f"[ADMIN-REGISTER] Person: {data.person_name}")
        print(f"[ADMIN-REGISTER] Location ID: {data.location_id}")
        print(f"[ADMIN-REGISTER] Photos: {len(data.photos)}")

        # Verify user has access to this location
        if not user.is_superuser:
            result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.location_id == data.location_id
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Access denied to this location")

        # Get location's CodeProject server
        location_result = await session.execute(
            select(Location).where(Location.id == data.location_id)
        )
        location = location_result.scalar_one_or_none()
        if not location:
            raise HTTPException(status_code=404, detail="Location not found")

        # Get the location's server, or use first available if not set
        if location.codeproject_server_id:
            server_result = await session.execute(
                select(CodeProjectServer).where(CodeProjectServer.id == location.codeproject_server_id)
            )
        else:
            server_result = await session.execute(select(CodeProjectServer).limit(1))

        server = server_result.scalar_one_or_none()
        if not server:
            raise HTTPException(status_code=500, detail="No CodeProject.AI server configured")

        codeproject_endpoint = server.endpoint_url
        server_id = server.id

        # Check if person already exists at this location, and get or create person_id
        existing_face_result = await session.execute(
            select(RegisteredFace).where(
                RegisteredFace.person_name == data.person_name,
                RegisteredFace.location_id == data.location_id
            ).limit(1)
        )
        existing_face = existing_face_result.scalar_one_or_none()

        if existing_face and existing_face.person_id:
            # Reuse existing person_id
            person_id = existing_face.person_id
            print(f"[ADMIN-REGISTER] Existing person found, reusing person_id: {person_id}")
        else:
            # Generate new person_id for new person
            person_id = str(uuid.uuid4())
            print(f"[ADMIN-REGISTER] New person, generated person_id: {person_id}")

        successful_registrations = 0
        errors = []
        profile_photo_path = None

        for idx, photo_obj in enumerate(data.photos):
            try:
                photo_data = photo_obj.get('image', '')
                position = photo_obj.get('position', '')

                print(f"[ADMIN-REGISTER] Processing photo {idx+1}/{len(data.photos)} ({position})")

                # Extract base64 data from data URL
                if ',' in photo_data:
                    photo_data = photo_data.split(',')[1]

                # Decode base64 image
                image_bytes = base64.b64decode(photo_data)
                image_size_kb = len(image_bytes) / 1024
                print(f"[ADMIN-REGISTER]   Image size: {image_size_kb:.2f} KB")

                # Save locally for backup
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                filename = f"{data.person_name.replace(' ', '_')}_{timestamp}_{idx}.jpg"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                with open(filepath, 'wb') as f:
                    f.write(image_bytes)
                print(f"[ADMIN-REGISTER]   Saved locally: {filename}")

                # Use last photo (straight and smile) as profile photo
                # Store web-accessible path (not file system path)
                if idx == len(data.photos) - 1:
                    profile_photo_path = f"/uploads/{filename}"

                # Register with CodeProject.AI using person_id as userid
                files = {
                    'image': (filename, BytesIO(image_bytes), 'image/jpeg')
                }
                params = {
                    'userid': person_id  # Use person_id instead of person_name
                }

                print(f"[ADMIN-REGISTER]   Sending to CodeProject.AI...")

                response = requests.post(
                    f"{codeproject_endpoint}/vision/face/register",
                    files=files,
                    data=params,
                    timeout=60
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        successful_registrations += 1
                        print(f"[ADMIN-REGISTER]   ✓ Photo {idx+1} registered successfully")

                        # Calculate expiration date (today + DEFAULT_EXPIRATION_DAYS)
                        from datetime import date
                        expiration_date = date.today() + timedelta(days=DEFAULT_EXPIRATION_DAYS)

                        # Save to database
                        registered_face = RegisteredFace(
                            person_id=person_id,
                            person_name=data.person_name,
                            codeproject_user_id=person_id,  # Store person_id as codeproject_user_id
                            file_path=filepath,
                            codeproject_server_id=server_id,
                            location_id=data.location_id,
                            registered_by_user_id=user.id,
                            profile_photo=profile_photo_path if idx == len(data.photos) - 1 else None,
                            is_employee=False,  # Default to visitor
                            user_expiration=expiration_date.isoformat()  # Default expiration
                        )
                        session.add(registered_face)
                        await session.commit()
                        print(f"[ADMIN-REGISTER]   ✓ Saved to database")
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        errors.append(f"Photo {idx+1}: {error_msg}")
                        print(f"[ADMIN-REGISTER]   ✗ Photo {idx+1} failed: {error_msg}")
                else:
                    errors.append(f"Photo {idx+1}: HTTP {response.status_code}")
                    print(f"[ADMIN-REGISTER]   ✗ Photo {idx+1} failed with status {response.status_code}")

            except Exception as e:
                errors.append(f"Photo {idx+1}: {str(e)}")
                print(f"[ADMIN-REGISTER]   ✗ Photo {idx+1} exception: {e}")

        print(f"[ADMIN-REGISTER] Registration complete: {successful_registrations}/{len(data.photos)} successful")
        print(f"{'='*60}\n")

        if successful_registrations > 0:
            return {
                "success": True,
                "message": f"Successfully registered {successful_registrations} out of {len(data.photos)} photos for {data.person_name}",
                "registered_count": successful_registrations,
                "total_count": len(data.photos),
                "errors": errors if errors else None
            }
        else:
            raise HTTPException(
                status_code=500,
                detail={"success": False, "error": "Failed to register any photos", "details": errors}
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ADMIN-REGISTER] ✗ EXCEPTION: {e}")
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/detect-face-bounds")
async def detect_face_bounds(
    image: UploadFile = File(...),
    user: User = Depends(current_active_user)
):
    """Detect face boundaries in an image for cropping suggestions"""
    try:
        print(f"\n{'='*60}")
        print(f"[DETECT-FACE] Detecting face bounds for cropping")

        # Read image
        image_data = await image.read()

        # Call CodeProject.AI face detection using default server
        files = {'image': ('image.jpg', image_data, 'image/jpeg')}

        response = requests.post(
            f"{CODEPROJECT_BASE_URL}/vision/face/detect",
            files=files,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('predictions'):
                # Extract face bounds
                faces = []
                for prediction in data['predictions']:
                    faces.append({
                        'x_min': prediction['x_min'],
                        'y_min': prediction['y_min'],
                        'x_max': prediction['x_max'],
                        'y_max': prediction['y_max'],
                        'confidence': prediction.get('confidence', 0)
                    })

                print(f"[DETECT-FACE] ✓ Detected {len(faces)} face(s)")
                return {"success": True, "faces": faces}
            else:
                print(f"[DETECT-FACE] No faces detected")
                return {"success": True, "faces": []}
        else:
            print(f"[DETECT-FACE] ✗ Detection failed: {response.status_code}")
            raise HTTPException(status_code=500, detail="Face detection failed")

    except HTTPException:
        raise
    except Exception as e:
        print(f"[DETECT-FACE] ✗ EXCEPTION: {e}")
        print(f"[DETECT-FACE] ✗ Exception type: {type(e).__name__}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")


@app.post("/api/admin/replace-photos")
async def replace_photos(
    person_id: str = Form(...),
    person_name: str = Form(...),
    photos: List[UploadFile] = File(...),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Replace photos for a registered person (deletes from CodeProject and re-registers)"""
    try:
        print(f"\n{'='*60}")
        print(f"[REPLACE-PHOTOS] Replacing photos for {person_name} (person_id: {person_id})")

        # Get all registered face records for this person
        result = await session.execute(
            select(RegisteredFace).where(RegisteredFace.person_id == person_id)
        )
        face_records = result.scalars().all()

        if not face_records:
            raise HTTPException(status_code=404, detail=f"No registered faces found for person_id {person_id}")

        # Check permissions
        if not user.is_superuser:
            admin_result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.role == 'location_admin'
                )
            )
            admin_location_ids = [ulr.location_id for ulr in admin_result.scalars().all()]

            for face_record in face_records:
                if face_record.location_id not in admin_location_ids:
                    raise HTTPException(
                        status_code=403,
                        detail="You don't have permission to edit photos for this person"
                    )

        # Save metadata from old records BEFORE deleting anything
        location_id = face_records[0].location_id
        codeproject_server_id = face_records[0].codeproject_server_id
        is_employee = face_records[0].is_employee
        user_expiration = face_records[0].user_expiration

        # Get the server endpoint for CodeProject operations
        if codeproject_server_id:
            server_result = await session.execute(
                select(CodeProjectServer).where(CodeProjectServer.id == codeproject_server_id)
            )
            server = server_result.scalar_one_or_none()
            if server:
                codeproject_endpoint = server.endpoint_url
            else:
                raise HTTPException(status_code=500, detail="CodeProject server not found")
        else:
            raise HTTPException(status_code=500, detail="No CodeProject server configured for this face")

        # Collect old file paths for deletion later
        old_file_paths = [record.file_path for record in face_records if record.file_path]

        # Save new photos to disk
        saved_photos = []
        for idx, photo_file in enumerate(photos):
            # Read photo data
            photo_data = await photo_file.read()

            # Save to disk
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"{person_id}_{timestamp}_{idx}.jpg"
            filepath = os.path.join(UPLOAD_FOLDER, filename)

            with open(filepath, "wb") as f:
                f.write(photo_data)

            saved_photos.append({
                'filepath': filepath,
                'data': photo_data,
                'filename': filename
            })

        print(f"[REPLACE-PHOTOS] Saved {len(saved_photos)} new photos to disk")

        # Create new database records
        profile_photo_path = None
        for idx, photo in enumerate(saved_photos):
            # Extract base64 for profile photo (last image)
            if idx == len(saved_photos) - 1:
                with open(photo['filepath'], 'rb') as f:
                    photo_bytes = f.read()
                    profile_photo_path = base64.b64encode(photo_bytes).decode('utf-8')

            registered_face = RegisteredFace(
                person_id=person_id,
                person_name=person_name,
                codeproject_user_id=person_id,
                file_path=photo['filepath'],
                codeproject_server_id=codeproject_server_id,
                location_id=location_id,
                registered_by_user_id=user.id,
                profile_photo=profile_photo_path if idx == len(saved_photos) - 1 else None,
                is_employee=is_employee,
                user_expiration=user_expiration
            )
            session.add(registered_face)

        await session.commit()

        print(f"[REPLACE-PHOTOS] ✓ Created {len(saved_photos)} new database records")

        # NOW delete old records and files (only after new ones are successfully created)
        print(f"[REPLACE-PHOTOS] Deleting old records and files...")

        # Delete from CodeProject.AI
        try:
            print(f"[REPLACE-PHOTOS]   Deleting old registration from CodeProject.AI...")
            response = requests.post(
                f"{codeproject_endpoint}/vision/face/delete",
                data={'userid': person_id},
                timeout=30
            )
            if response.status_code == 200:
                print(f"[REPLACE-PHOTOS]   ✓ Deleted old registration")
            else:
                print(f"[REPLACE-PHOTOS]   ⚠ Delete returned {response.status_code}")
        except Exception as e:
            print(f"[REPLACE-PHOTOS]   ⚠ Error deleting old registration: {e}")

        # Re-register with new photos
        print(f"[REPLACE-PHOTOS]   Re-registering with new photos...")
        files = []
        for idx, photo in enumerate(saved_photos):
            files.append(('images', (photo['filename'], photo['data'], 'image/jpeg')))

        params = {'userid': person_id}

        try:
            response = requests.post(
                f"{codeproject_endpoint}/vision/face/register",
                files=files,
                data=params,
                timeout=60
            )
            if response.status_code == 200:
                print(f"[REPLACE-PHOTOS]   ✓ Re-registered successfully")
            else:
                print(f"[REPLACE-PHOTOS]   ⚠ Re-register returned {response.status_code}")
        except Exception as e:
            print(f"[REPLACE-PHOTOS]   ⚠ Error re-registering: {e}")

        # Delete old database records
        for record in face_records:
            await session.delete(record)
        await session.commit()
        print(f"[REPLACE-PHOTOS] ✓ Deleted {len(face_records)} old database records")

        # Delete old files from disk
        for filepath in old_file_paths:
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    print(f"[REPLACE-PHOTOS] Deleted old file: {filepath}")
                except Exception as e:
                    print(f"[REPLACE-PHOTOS] ⚠ Error deleting {filepath}: {e}")

        print(f"{'='*60}\n")

        return {
            "success": True,
            "message": f"Successfully replaced {len(saved_photos)} photo(s) for {person_name}",
            "photos_replaced": len(saved_photos)
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[REPLACE-PHOTOS] ✗ EXCEPTION: {e}")
        print(f"[REPLACE-PHOTOS] ✗ Exception type: {type(e).__name__}")
        traceback.print_exc()
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")


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


@app.delete("/api/registered-faces/{person_id}")
async def delete_registered_face(
    person_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Delete a person's registered face from CodeProject.AI and remove all associated files"""
    try:
        print(f"\n{'='*60}")
        print(f"[DELETE] Deleting registered face with person_id: {person_id}")

        # Get all registered face records for this person
        result = await session.execute(
            select(RegisteredFace).where(RegisteredFace.person_id == person_id)
        )
        face_records = result.scalars().all()

        if not face_records:
            raise HTTPException(status_code=404, detail=f"No registered faces found for person_id {person_id}")

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

        # Get all servers for lookup
        servers_result = await session.execute(select(CodeProjectServer))
        servers_dict = {s.id: s.endpoint_url for s in servers_result.scalars().all()}

        # Group face records by CodeProject server
        server_groups = {}
        for face_record in face_records:
            server_id = face_record.codeproject_server_id
            if server_id not in server_groups:
                server_groups[server_id] = []
            server_groups[server_id].append(face_record)

        # Get person_name for logging
        person_name = face_records[0].person_name if face_records else "Unknown"

        # Delete from each CodeProject.AI server
        print(f"[DELETE] Removing {person_name} (person_id: {person_id}) from {len(server_groups)} CodeProject.AI server(s)...")
        for server_id, records in server_groups.items():
            endpoint = servers_dict.get(server_id)
            if not endpoint:
                print(f"[DELETE]   ⚠ Server ID {server_id} not found, skipping...")
                continue
            try:
                print(f"[DELETE]   Deleting from {endpoint}...")
                response = requests.post(
                    f"{endpoint}/vision/face/delete",
                    data={'userid': person_id},  # Use person_id (UUID) not person_name
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


@app.put("/api/registered-faces/{person_id}/employee-status")
async def update_employee_status(
    person_id: str,
    is_employee: bool,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Update employee status for a registered face"""
    try:
        print(f"\n{'='*60}")
        print(f"[UPDATE-EMPLOYEE] Updating person_id {person_id} to is_employee={is_employee}")

        # Get all registered face records for this person
        result = await session.execute(
            select(RegisteredFace).where(RegisteredFace.person_id == person_id)
        )
        face_records = result.scalars().all()

        if not face_records:
            raise HTTPException(status_code=404, detail=f"No registered faces found for person_id {person_id}")

        # Check permissions - location admins can only edit faces from their locations
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
                        detail=f"You don't have permission to edit this face (belongs to another location)"
                    )

        # Update all records for this person
        from datetime import date
        for face_record in face_records:
            face_record.is_employee = is_employee
            # Update expiration: "never" for employees, today + DEFAULT_EXPIRATION_DAYS for visitors
            if is_employee:
                face_record.user_expiration = "never"
            else:
                expiration_date = date.today() + timedelta(days=DEFAULT_EXPIRATION_DAYS)
                face_record.user_expiration = expiration_date.isoformat()

        await session.commit()

        # Get person_name for response message
        person_name = face_records[0].person_name if face_records else "Person"

        print(f"[UPDATE-EMPLOYEE] ✓ Updated {len(face_records)} record(s) for {person_name}")
        print(f"{'='*60}\n")

        return {
            "success": True,
            "message": f"Updated {person_name} to {'employee' if is_employee else 'visitor'}",
            "records_updated": len(face_records)
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[UPDATE-EMPLOYEE] ✗ EXCEPTION: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/registered-faces/{person_id}/expiration")
async def update_user_expiration(
    person_id: str,
    expiration: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Update user expiration date for a registered face"""
    try:
        print(f"\n{'='*60}")
        print(f"[UPDATE-EXPIRATION] Updating person_id {person_id} to expiration={expiration}")

        # Validate expiration format (must be ISO date or "never")
        if expiration != "never":
            try:
                # Try to parse as ISO date
                from datetime import date
                date.fromisoformat(expiration)
            except ValueError:
                raise HTTPException(status_code=400, detail="Expiration must be ISO date (YYYY-MM-DD) or 'never'")

        # Get all registered face records for this person
        result = await session.execute(
            select(RegisteredFace).where(RegisteredFace.person_id == person_id)
        )
        face_records = result.scalars().all()

        if not face_records:
            raise HTTPException(status_code=404, detail=f"No registered faces found for person_id {person_id}")

        # Check permissions - location admins can only edit faces from their locations
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
                        detail=f"You don't have permission to edit this face (belongs to another location)"
                    )

        # Update all records for this person
        for face_record in face_records:
            face_record.user_expiration = expiration

        await session.commit()

        # Get person_name for response message
        person_name = face_records[0].person_name if face_records else "Person"

        print(f"[UPDATE-EXPIRATION] ✓ Updated {len(face_records)} record(s) for {person_name}")
        print(f"{'='*60}\n")

        return {
            "success": True,
            "message": f"Updated expiration for {person_name}",
            "records_updated": len(face_records)
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[UPDATE-EXPIRATION] ✗ EXCEPTION: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# REGISTRATION LINK API ROUTES
# ============================================================================

@app.post("/api/registration-links")
async def create_registration_link(
    data: CreateRegistrationLinkRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Create a public registration link with QR code"""
    try:
        print(f"\n{'='*60}")
        print(f"[CREATE-LINK] Creating registration link for location {data.location_id}")

        # Check permissions - user must have access to this location
        if not user.is_superuser:
            result = await session.execute(
                select(UserLocationRole).where(
                    UserLocationRole.user_id == user.id,
                    UserLocationRole.location_id == data.location_id
                )
            )
            user_location = result.scalar_one_or_none()
            if not user_location:
                raise HTTPException(status_code=403, detail="You don't have access to this location")

        # Validate expiration formats
        if data.user_expiration != "never":
            try:
                date.fromisoformat(data.user_expiration)
            except ValueError:
                raise HTTPException(status_code=400, detail="user_expiration must be ISO date (YYYY-MM-DD) or 'never'")

        try:
            link_exp = datetime.fromisoformat(data.link_expiration)
        except ValueError:
            raise HTTPException(status_code=400, detail="link_expiration must be ISO datetime")

        # Generate unique link ID
        link_id = str(uuid.uuid4())

        # Create link
        link = RegistrationLink(
            link_id=link_id,
            created_by_user_id=user.id,
            location_id=data.location_id,
            user_expiration=data.user_expiration,
            link_expiration=link_exp,
            max_uses=data.max_uses,
            is_employee=data.is_employee,
            link_name=data.link_name
        )
        session.add(link)
        await session.commit()

        print(f"[CREATE-LINK] ✓ Created link {link_id}")
        print(f"{'='*60}\n")

        return {
            "success": True,
            "link_id": link_id,
            "link_url": f"/register-public/{link_id}",
            "message": "Registration link created successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[CREATE-LINK] ✗ EXCEPTION: {e}")
        traceback.print_exc()
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/registration-links")
async def list_registration_links(
    location_id: Optional[int] = None,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """List registration links created by user or for their locations"""
    try:
        # Build query
        if user.is_superuser:
            # Superadmins see all links (optionally filtered by location)
            if location_id:
                query = select(RegistrationLink).where(RegistrationLink.location_id == location_id)
            else:
                query = select(RegistrationLink)
        else:
            # Get user's locations
            user_locations_result = await session.execute(
                select(UserLocationRole.location_id).where(UserLocationRole.user_id == user.id)
            )
            user_location_ids = [row[0] for row in user_locations_result.all()]

            if not user_location_ids:
                return {"links": []}

            # Filter by user's locations
            if location_id:
                if location_id not in user_location_ids:
                    raise HTTPException(status_code=403, detail="You don't have access to this location")
                query = select(RegistrationLink).where(RegistrationLink.location_id == location_id)
            else:
                query = select(RegistrationLink).where(RegistrationLink.location_id.in_(user_location_ids))

        query = query.order_by(RegistrationLink.created_at.desc())
        result = await session.execute(query)
        links = result.scalars().all()

        # Get location names
        location_result = await session.execute(select(Location))
        locations = {loc.id: loc.name for loc in location_result.scalars().all()}

        # Format response
        links_data = []
        for link in links:
            # Count registrations
            reg_result = await session.execute(
                select(func.count(LinkRegistration.id)).where(LinkRegistration.link_id == link.link_id)
            )
            registration_count = reg_result.scalar() or 0

            # Check if expired
            is_expired = datetime.utcnow() > link.link_expiration
            is_max_uses_reached = link.max_uses is not None and link.current_uses >= link.max_uses

            links_data.append({
                "link_id": link.link_id,
                "link_name": link.link_name,
                "location_id": link.location_id,
                "location_name": locations.get(link.location_id, "Unknown"),
                "user_expiration": link.user_expiration,
                "link_expiration": link.link_expiration.isoformat(),
                "max_uses": link.max_uses,
                "current_uses": link.current_uses,
                "registration_count": registration_count,
                "is_employee": link.is_employee,
                "is_active": link.is_active,
                "is_expired": is_expired,
                "is_max_uses_reached": is_max_uses_reached,
                "created_at": link.created_at.isoformat(),
                "link_url": f"/register-public/{link.link_id}"
            })

        return {"links": links_data}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[LIST-LINKS] ✗ EXCEPTION: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/registration-links/{link_id}/registrations")
async def get_link_registrations(
    link_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get list of people who registered via this link"""
    try:
        # Get link
        result = await session.execute(
            select(RegistrationLink).where(RegistrationLink.link_id == link_id)
        )
        link = result.scalar_one_or_none()

        if not link:
            raise HTTPException(status_code=404, detail="Link not found")

        # Check permissions
        if not user.is_superuser:
            user_locations_result = await session.execute(
                select(UserLocationRole.location_id).where(UserLocationRole.user_id == user.id)
            )
            user_location_ids = [row[0] for row in user_locations_result.all()]

            if link.location_id not in user_location_ids:
                raise HTTPException(status_code=403, detail="You don't have access to this link")

        # Get registrations
        reg_result = await session.execute(
            select(LinkRegistration)
            .where(LinkRegistration.link_id == link_id)
            .order_by(LinkRegistration.registered_at.desc())
        )
        registrations = reg_result.scalars().all()

        return {
            "registrations": [
                {
                    "person_id": reg.person_id,
                    "person_name": reg.person_name,
                    "registered_at": reg.registered_at.isoformat()
                }
                for reg in registrations
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[GET-LINK-REGS] ✗ EXCEPTION: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/registration-links/{link_id}")
async def delete_registration_link(
    link_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Delete a registration link"""
    try:
        # Get link
        result = await session.execute(
            select(RegistrationLink).where(RegistrationLink.link_id == link_id)
        )
        link = result.scalar_one_or_none()

        if not link:
            raise HTTPException(status_code=404, detail="Link not found")

        # Check permissions
        if not user.is_superuser:
            user_locations_result = await session.execute(
                select(UserLocationRole.location_id).where(UserLocationRole.user_id == user.id)
            )
            user_location_ids = [row[0] for row in user_locations_result.all()]

            if link.location_id not in user_location_ids:
                raise HTTPException(status_code=403, detail="You don't have access to this link")

        # Delete link (registrations will cascade delete)
        await session.delete(link)
        await session.commit()

        return {"success": True, "message": "Link deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[DELETE-LINK] ✗ EXCEPTION: {e}")
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/registration-links/{link_id}/toggle")
async def toggle_registration_link(
    link_id: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Toggle a registration link active/inactive"""
    try:
        # Get link
        result = await session.execute(
            select(RegistrationLink).where(RegistrationLink.link_id == link_id)
        )
        link = result.scalar_one_or_none()

        if not link:
            raise HTTPException(status_code=404, detail="Link not found")

        # Check permissions
        if not user.is_superuser:
            user_locations_result = await session.execute(
                select(UserLocationRole.location_id).where(UserLocationRole.user_id == user.id)
            )
            user_location_ids = [row[0] for row in user_locations_result.all()]

            if link.location_id not in user_location_ids:
                raise HTTPException(status_code=403, detail="You don't have access to this link")

        # Toggle
        link.is_active = not link.is_active
        await session.commit()

        return {
            "success": True,
            "is_active": link.is_active,
            "message": f"Link {'activated' if link.is_active else 'deactivated'}"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[TOGGLE-LINK] ✗ EXCEPTION: {e}")
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# Public registration endpoint (no auth required)
@app.get("/register-public/{link_id}", response_class=HTMLResponse)
async def public_registration_page(
    link_id: str,
    request: Request,
    session: AsyncSession = Depends(get_async_session)
):
    """Public registration page for link-based registration"""
    # Will create this template next
    return templates.TemplateResponse("register_public.html", {
        "request": request,
        "link_id": link_id
    })


@app.get("/api/registration-links/{link_id}/info")
async def get_link_info(
    link_id: str,
    session: AsyncSession = Depends(get_async_session)
):
    """Get public info about a registration link (no auth required)"""
    try:
        result = await session.execute(
            select(RegistrationLink).where(RegistrationLink.link_id == link_id)
        )
        link = result.scalar_one_or_none()

        if not link:
            raise HTTPException(status_code=404, detail="Link not found")

        # Check if link is valid
        is_expired = datetime.utcnow() > link.link_expiration
        is_max_uses_reached = link.max_uses is not None and link.current_uses >= link.max_uses

        if not link.is_active:
            return {"valid": False, "message": "This registration link has been deactivated"}

        if is_expired:
            return {"valid": False, "message": "This registration link has expired"}

        if is_max_uses_reached:
            return {"valid": False, "message": "This registration link has reached its maximum number of uses"}

        # Get location name
        loc_result = await session.execute(
            select(Location).where(Location.id == link.location_id)
        )
        location = loc_result.scalar_one_or_none()

        return {
            "valid": True,
            "link_name": link.link_name,
            "location_name": location.name if location else "Unknown",
            "remaining_uses": (link.max_uses - link.current_uses) if link.max_uses else None,
            "link_expiration": link.link_expiration.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[GET-LINK-INFO] ✗ EXCEPTION: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/register-public")
async def register_via_public_link(
    data: PublicRegisterRequest,
    session: AsyncSession = Depends(get_async_session)
):
    """Register a face via public link (no auth required)"""
    try:
        print(f"\n{'='*60}")
        print(f"[PUBLIC-REGISTER] Registration via link {data.link_id} for {data.person_name}")

        # Get and validate link
        result = await session.execute(
            select(RegistrationLink).where(RegistrationLink.link_id == data.link_id)
        )
        link = result.scalar_one_or_none()

        if not link:
            raise HTTPException(status_code=404, detail="Link not found")

        # Check if link is valid
        is_expired = datetime.utcnow() > link.link_expiration
        is_max_uses_reached = link.max_uses is not None and link.current_uses >= link.max_uses

        if not link.is_active:
            raise HTTPException(status_code=400, detail="This registration link has been deactivated")

        if is_expired:
            raise HTTPException(status_code=400, detail="This registration link has expired")

        if is_max_uses_reached:
            raise HTTPException(status_code=400, detail="This registration link has reached its maximum number of uses")

        # Get location's CodeProject endpoint
        loc_result = await session.execute(
            select(Location).where(Location.id == link.location_id)
        )
        location = loc_result.scalar_one_or_none()

        if not location or not location.codeproject_server_id:
            raise HTTPException(status_code=500, detail="Location configuration error")

        server_result = await session.execute(
            select(CodeProjectServer).where(CodeProjectServer.id == location.codeproject_server_id)
        )
        server = server_result.scalar_one_or_none()

        if not server:
            raise HTTPException(status_code=500, detail="CodeProject server not found")

        codeproject_endpoint = server.endpoint_url

        # Generate person_id
        person_id = str(uuid.uuid4())

        # Save photos and register
        saved_photos = []
        for idx, photo_data in enumerate(data.photos):
            # Extract base64 data from data URL
            if photo_data.startswith('data:image'):
                photo_data = photo_data.split(',')[1]

            photo_bytes = base64.b64decode(photo_data)

            # Save to disk
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"{person_id}_{timestamp}_{idx}.jpg"
            filepath = os.path.join(UPLOAD_FOLDER, filename)

            with open(filepath, "wb") as f:
                f.write(photo_bytes)

            saved_photos.append({
                'filepath': filepath,
                'data': photo_bytes,
                'filename': filename
            })

        # Register with CodeProject.AI
        files = []
        for photo in saved_photos:
            files.append(('images', (photo['filename'], photo['data'], 'image/jpeg')))

        params = {'userid': person_id}

        response = requests.post(
            f"{codeproject_endpoint}/vision/face/register",
            files=files,
            data=params,
            timeout=60
        )

        if response.status_code != 200:
            # Cleanup
            for photo in saved_photos:
                if os.path.exists(photo['filepath']):
                    os.remove(photo['filepath'])
            raise HTTPException(status_code=500, detail="Failed to register with facial recognition system")

        # Save to database
        profile_photo_path = None
        for idx, photo in enumerate(saved_photos):
            # Extract base64 for profile photo (last image)
            if idx == len(saved_photos) - 1:
                with open(photo['filepath'], 'rb') as f:
                    photo_bytes = f.read()
                    profile_photo_path = base64.b64encode(photo_bytes).decode('utf-8')

            registered_face = RegisteredFace(
                person_id=person_id,
                person_name=data.person_name,
                codeproject_user_id=person_id,
                file_path=photo['filepath'],
                codeproject_server_id=server.id,
                location_id=link.location_id,
                registered_by_user_id=link.created_by_user_id,
                profile_photo=profile_photo_path if idx == len(saved_photos) - 1 else None,
                is_employee=link.is_employee,
                user_expiration=link.user_expiration
            )
            session.add(registered_face)

        # Track registration via link
        link_reg = LinkRegistration(
            link_id=link.link_id,
            person_id=person_id,
            person_name=data.person_name
        )
        session.add(link_reg)

        # Increment link usage
        link.current_uses += 1

        await session.commit()

        print(f"[PUBLIC-REGISTER] ✓ Registered {data.person_name} via link")
        print(f"{'='*60}\n")

        return {
            "success": True,
            "message": f"Successfully registered {data.person_name}",
            "person_id": person_id
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[PUBLIC-REGISTER] ✗ EXCEPTION: {e}")
        traceback.print_exc()
        await session.rollback()
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

