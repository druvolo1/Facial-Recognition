# Facial Recognition App - Deployment Guide

## Overview
This application has been converted from Flask to FastAPI with a complete authentication system based on the plant_logs_server reference project.

## Features Implemented

### ✅ Database & Authentication
- **MariaDB database** (uses same server as plant_logs, new database: `facial_recognition`)
- **User registration** with admin approval workflow
- **Google OAuth** integration (same credentials as plant_logs)
- **User management** with suspend/unsuspend capabilities
- **JWT authentication** with HTTP-only cookies
- **Admin dashboard** for user approval

### ✅ Templates Created
- `login.html` - Login page with Google OAuth button
- `register_account.html` - User registration page
- `registration_pending.html` - Post-registration confirmation
- `pending_approval.html` - Shown when user is not yet approved
- `suspended.html` - Shown when user account is suspended
- `dashboard.html` - Main dashboard after login
- `admin_users.html` - Admin user management interface

### ✅ API Endpoints
- `/login` - Login page
- `/register-account` - Registration page
- `/auth/register` (POST) - Register new user
- `/auth/google/authorize` - Google OAuth flow
- `/auth/google/callback` - Google OAuth callback
- `/auth/logout` - Logout
- `/dashboard` - Main dashboard (requires auth)
- `/register` - Face registration page (requires auth)
- `/recognize-face` - Face recognition page (requires auth)
- `/admin/users` - User management (admin only)
- `/api/admin/users` - List all users (admin only)
- `/api/admin/users/{id}/approve` - Approve pending user
- `/api/admin/users/{id}/suspend` - Suspend user
- `/api/admin/users/{id}/unsuspend` - Unsuspend user
- `/api/register` - Register face to CodeProject.AI
- `/api/recognize` - Recognize face

## Installation on Raspberry Pi

### 1. Prerequisites
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.9+ and pip
sudo apt install python3 python3-pip python3-venv -y

# Install MariaDB client libraries (for Python MySQL connector)
sudo apt install libmariadb-dev libmariadb-dev-compat -y
```

### 2. Transfer Files
Transfer the entire `Facial Recognition` directory to your Raspberry Pi.

### 3. Create Virtual Environment
```bash
cd "Facial Recognition"
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure Environment
Edit the `.env` file and verify/update settings:

```bash
nano .env
```

**Important settings to check:**
- `DATABASE_URL` - Should point to your MariaDB server
- `SECRET_KEY` - Generate a secure random key for production
- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` - Your OAuth credentials
- `GOOGLE_REDIRECT_URI` - Update if not using localhost
- `ADMIN_EMAIL` and `ADMIN_PASSWORD` - Your admin account credentials

### 6. Create Database
The database will be created automatically on first run, but you can test it manually:

```bash
cd app
python init_database.py
```

This will:
- Create the `facial_recognition` database if it doesn't exist
- Set up required tables
- Configure schema for user approval workflow

### 7. Run the Application

**Development mode (with auto-reload):**
```bash
cd app
python main.py
```

**Production mode with uvicorn:**
```bash
cd app
uvicorn main:app --host 0.0.0.0 --port 5000
```

**Production mode with specific workers:**
```bash
cd app
uvicorn main:app --host 0.0.0.0 --port 5000 --workers 2
```

### 8. Create Systemd Service (Production)

Create a service file to run the app automatically:

```bash
sudo nano /etc/systemd/system/facial-recognition.service
```

Add this content (adjust paths as needed):
```ini
[Unit]
Description=Facial Recognition App
After=network.target mariadb.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/Facial Recognition/app
Environment="PATH=/home/pi/Facial Recognition/venv/bin"
ExecStart=/home/pi/Facial Recognition/venv/bin/uvicorn main:app --host 0.0.0.0 --port 5000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable facial-recognition.service
sudo systemctl start facial-recognition.service

# Check status
sudo systemctl status facial-recognition.service

# View logs
sudo journalctl -u facial-recognition.service -f
```

## First-Time Setup

### 1. Access the Application
Open your browser and navigate to:
- **Local:** http://localhost:5000/login
- **Network:** http://<raspberry-pi-ip>:5000/login

### 2. Login as Admin
Use the admin credentials from your `.env` file:
- Email: `admin@example.com` (or whatever you set)
- Password: `admin123!` (or whatever you set)

### 3. Register Additional Users
Users can register at: http://<raspberry-pi-ip>:5000/register-account

New users will be in "Pending Approval" status until an admin approves them.

### 4. Approve Users
As admin:
1. Go to Dashboard → "Manage Users"
2. You'll see all pending users
3. Click "Approve" to activate their accounts

## Google OAuth Configuration

If your redirect URI changes (e.g., using a domain instead of localhost):

1. Update `.env`:
   ```
   GOOGLE_REDIRECT_URI=https://your-domain.com/auth/google/callback
   ```

2. Update Google Cloud Console:
   - Go to: https://console.cloud.google.com/
   - Navigate to: APIs & Services → Credentials
   - Edit your OAuth 2.0 Client ID
   - Add authorized redirect URI: `https://your-domain.com/auth/google/callback`

## Database Management

### View Users
```sql
mysql -h 172.16.1.150 -u app_user -p
USE facial_recognition;
SELECT id, email, first_name, last_name, is_active, is_superuser, is_suspended FROM user;
```

### Manually Approve a User
```sql
UPDATE user SET is_active = TRUE WHERE email = 'user@example.com';
```

### Make a User Admin
```sql
UPDATE user SET is_superuser = TRUE WHERE email = 'user@example.com';
```

## Troubleshooting

### Can't Connect to Database
```bash
# Test connection
mysql -h 172.16.1.150 -u app_user -p

# If fails, check:
# 1. MariaDB is running on 172.16.1.150
# 2. User 'app_user' has permissions
# 3. Firewall allows port 3306
```

### Google OAuth Fails
- Check `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`
- Verify redirect URI matches Google Cloud Console settings
- Check browser console for errors

### Users Can't Login After Approval
```bash
# Check user status in database
mysql -h 172.16.1.150 -u app_user -p facial_recognition -e "SELECT email, is_active, is_suspended FROM user;"

# Manually activate if needed
mysql -h 172.16.1.150 -u app_user -p facial_recognition -e "UPDATE user SET is_active = TRUE WHERE email = 'user@example.com';"
```

## Migrating from Old Flask App

The old Flask app (`app.py`) used JSON files for user storage. This new FastAPI app uses MariaDB.

**To migrate existing facial recognition data:**
1. The facial recognition data is stored in CodeProject.AI, not in the app database
2. No migration needed - existing registered faces will continue to work
3. Only the user accounts need to be re-registered in the new system

## Next Steps

After the database and login portal are working, you mentioned wanting to add more functionality. The current setup provides:

1. ✅ Database (MariaDB with `facial_recognition` database)
2. ✅ User authentication (email/password + Google OAuth)
3. ✅ User approval workflow
4. ✅ Admin dashboard
5. ✅ Face registration and recognition endpoints (migrated from Flask)

You can now add additional features on top of this authentication system!

## Port Information

- **FastAPI App:** Port 5000
- **MariaDB:** Port 3306
- **CodeProject.AI:** Port 32168

## Security Notes

⚠️ **For Production:**
1. Change `SECRET_KEY` to a strong random value
2. Use HTTPS (configure reverse proxy with nginx/apache)
3. Update `ADMIN_PASSWORD` to something secure
4. Consider rate limiting for login endpoints
5. Enable CORS only for trusted domains
6. Use environment variables for secrets (not committed .env file)

## File Structure

```
Facial Recognition/
├── app/
│   ├── main.py              # Main FastAPI application
│   └── init_database.py     # Database initialization
├── templates/
│   ├── login.html           # Login page
│   ├── register_account.html
│   ├── registration_pending.html
│   ├── pending_approval.html
│   ├── suspended.html
│   ├── dashboard.html       # Main dashboard
│   ├── admin_users.html     # Admin user management
│   ├── register.html        # Face registration (existing)
│   └── recognize.html       # Face recognition (existing)
├── uploads/                 # Face images
├── audio/                   # TTS audio files
├── .env                     # Configuration (NOT in git)
├── .env.example             # Example configuration
├── requirements.txt         # Python dependencies
└── DEPLOYMENT.md            # This file
```

## Support

For issues or questions:
1. Check logs: `sudo journalctl -u facial-recognition.service -f`
2. Test database: `python app/init_database.py`
3. Verify .env configuration
4. Check CodeProject.AI is running at 172.16.1.150:32168
