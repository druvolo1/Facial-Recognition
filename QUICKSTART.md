# Quick Start Guide - Facial Recognition App

## Database Setup (3 Options)

### ✅ Option 1: Fully Automatic (Try This First!)

The application automatically creates the database on startup:

```bash
cd app
python main.py
```

If you see:
```
[DATABASE] ✓ Created database 'facial_recognition'
[STARTUP] ✓ Database tables created/verified
```

**You're done!** Skip to "First Login" below.

---

### 🔧 Option 2: Use the Setup Script

If automatic creation fails with permission errors, run:

```bash
python create_database.py
```

Then start the app:
```bash
cd app
python main.py
```

---

### 🛠️ Option 3: Manual SQL (Last Resort)

If Options 1 and 2 fail, the `app_user` doesn't have CREATE DATABASE permission.

Connect to MariaDB as root:
```bash
mysql -h 172.16.1.150 -u root -p
```

Run these commands:
```sql
CREATE DATABASE facial_recognition CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON facial_recognition.* TO 'app_user'@'%';
FLUSH PRIVILEGES;
EXIT;
```

Then start the app:
```bash
cd app
python main.py
```

---

## First Login

1. Open your browser: **http://your-raspberry-pi-ip:5000/login**

2. Login with admin credentials (from `.env` file):
   - Email: `admin@example.com`
   - Password: `admin123!`

3. You're in! 🎉

---

## What Happens on First Run?

The application will:
1. ✅ Create the `facial_recognition` database (if it doesn't exist)
2. ✅ Create the `user` and `accesstoken` tables
3. ✅ Create an admin user account (from `.env`)
4. ✅ Start the web server on port 5000

---

## Troubleshooting

### Error: "Access denied for user 'app_user' to database 'facial_recognition'"

**Solution:** Use Option 3 (Manual SQL) above.

### Error: "Can't connect to MySQL server"

**Check:**
- MariaDB is running: `sudo systemctl status mariadb`
- Host IP is correct in `.env`: `172.16.1.150`
- Port 3306 is open

### App starts but can't login

**Check:**
- Database was created successfully (look for ✓ in startup logs)
- Admin user was created (look for "Admin user created" in logs)
- Try the credentials from your `.env` file

---

## Next Steps

After logging in successfully:

1. **Register New Users:** Go to http://your-pi-ip:5000/register-account
2. **Approve Users:** Admin → "Manage Users" → Click "Approve"
3. **Register Faces:** Dashboard → "Register Faces"
4. **Recognize Faces:** Dashboard → "Recognize Faces"

---

## Support Files

- **Full Guide:** See `DEPLOYMENT.md` for complete installation instructions
- **Database Script:** `create_database.py` - Standalone database creator
- **Init Script:** `app/init_database.py` - Database initialization module
- **Configuration:** `.env` - All settings (database, admin credentials, etc.)

---

## Quick Reference

**Application URLs:**
- Login: http://your-pi:5000/login
- Registration: http://your-pi:5000/register-account
- Dashboard: http://your-pi:5000/dashboard
- Admin Users: http://your-pi:5000/admin/users

**Database Info:**
- Server: 172.16.1.150:3306
- Database: `facial_recognition`
- User: `app_user`

**Default Admin:**
- Email: `admin@example.com` (change in `.env`)
- Password: `admin123!` (change in `.env`)

---

Good luck! 🚀
