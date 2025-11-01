"""
Facial Recognition App with FastAPI and User Authentication
Based on plant_logs_server authentication system
"""
import os
import sys
from datetime import datetime
from typing import Optional, AsyncGenerator, List
import secrets
import base64
from io import BytesIO
import json

from fastapi import FastAPI, Depends, HTTPException, Request, Form, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import Boolean, Integer, String, Text, Column, ForeignKey, select, DateTime
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
    # When it was registered
    registered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    # User who registered this face
    registered_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("user.id"), nullable=True)


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


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)


async def get_access_token_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyAccessTokenDatabase(session, AccessToken)


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

cookie_transport = CookieTransport(cookie_name="auth_cookie", cookie_max_age=3600)


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


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page - redirects to login if not authenticated"""
    try:
        # Try to get current user from cookie
        # If no cookie or invalid, redirect to login
        return RedirectResponse(url="/login", status_code=302)
    except:
        return RedirectResponse(url="/login", status_code=302)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: User = Depends(current_active_user)):
    """Main dashboard (requires authentication)"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user
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

        # Return success response
        response = JSONResponse(content={"detail": "Login successful"})

        # Set the auth cookie
        response.set_cookie(
            key="auth_cookie",
            value=token,
            httponly=True,
            max_age=3600,
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

@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, user: User = Depends(current_superuser)):
    """Admin user management page"""
    return templates.TemplateResponse("admin_users.html", {"request": request, "user": user})


@app.get("/api/admin/users")
async def list_all_users(
    user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """List all users (admin only)"""
    result = await session.execute(select(User))
    users = result.scalars().all()

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
                "is_verified": u.is_verified
            }
            for u in users
        ]
    }


@app.post("/api/admin/users/{user_id}/approve")
async def approve_user(
    user_id: int,
    admin: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session)
):
    """Approve a pending user"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = True
    await session.commit()

    print(f"[ADMIN] User approved: {user.email}")

    return {"success": True, "message": f"User {user.email} approved"}


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


# ============================================================================
# FACIAL RECOGNITION API ROUTES (from original Flask app)
# ============================================================================

class RegisterRequest(BaseModel):
    name: str
    photos: List[str]


class RecognizeRequest(BaseModel):
    image: str


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
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get all registered faces and their photos from database"""
    try:
        from collections import defaultdict

        # Get all registered faces from database
        result = await session.execute(select(RegisteredFace))
        all_face_records = result.scalars().all()

        # Group by person name
        faces_dict = defaultdict(list)

        for face_record in all_face_records:
            # Convert absolute path to relative URL path
            filename = os.path.basename(face_record.file_path)
            photo_url = f"/uploads/{filename}"
            faces_dict[face_record.person_name].append(photo_url)

        # Convert to list format with one sample photo per person
        # Also get the codeproject_user_id for each person
        registered_faces = []
        for name, photos in sorted(faces_dict.items()):
            # Get the codeproject_user_id from the first record for this person
            result = await session.execute(
                select(RegisteredFace).where(RegisteredFace.person_name == name).limit(1)
            )
            face_record = result.scalar_one_or_none()

            registered_faces.append({
                "name": name,
                "photo": photos[0] if photos else None,  # Use first photo as profile picture
                "photo_count": len(photos),
                "all_photos": photos,
                "codeproject_user_id": face_record.codeproject_user_id if face_record else name
            })

        return {
            "success": True,
            "faces": registered_faces,
            "total": len(registered_faces)
        }

    except Exception as e:
        print(f"[REGISTERED-FACES] Error: {e}")
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

                        # Save to database
                        registered_face = RegisteredFace(
                            person_name=data.name,
                            codeproject_user_id=data.name,
                            file_path=filepath,
                            registered_by_user_id=user.id
                        )
                        session.add(registered_face)
                        await session.commit()
                        print(f"[REGISTER]   ✓ Saved to database")
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

        print(f"[DELETE] Found {len(face_records)} file(s) to delete")

        # Delete from CodeProject.AI
        print(f"[DELETE] Removing from CodeProject.AI...")
        try:
            response = requests.post(
                f"{CODEPROJECT_BASE_URL}/vision/face/delete",
                data={'userid': person_name},
                timeout=30
            )

            if response.status_code == 200:
                result_data = response.json()
                if result_data.get('success'):
                    print(f"[DELETE]   ✓ Removed from CodeProject.AI")
                else:
                    print(f"[DELETE]   ⚠ CodeProject.AI response: {result_data.get('error', 'Unknown error')}")
            else:
                print(f"[DELETE]   ⚠ CodeProject.AI returned status {response.status_code}")
        except Exception as e:
            print(f"[DELETE]   ⚠ Error removing from CodeProject.AI: {e}")
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

