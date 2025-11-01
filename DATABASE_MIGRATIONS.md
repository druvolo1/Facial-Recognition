# Database Migrations

This document tracks manual database schema changes that need to be applied.

## Migration History

### 2025-11-01: Add Password Change Requirement Feature

**Purpose**: Added ability for admins to force users to change passwords on first login or after password reset.

**SQL Command**:
```sql
ALTER TABLE user ADD COLUMN password_change_required BOOLEAN NOT NULL DEFAULT FALSE;
```

**What this does**:
- Adds a new column `password_change_required` to the `user` table
- Sets default value to `FALSE` for all existing users
- When set to `TRUE`, users will be redirected to change password page on login

**Related Features**:
- Admin can create users with temporary passwords
- Admin can reset user passwords (generates temporary password)
- Users are forced to change password on first login after creation/reset
- Password change page at `/change-password`

**Endpoints Added**:
- `POST /api/admin/users/create` - Create user with temporary password
- `POST /api/admin/users/{user_id}/reset-password` - Reset user password
- `POST /api/change-password` - User changes their own password
- `GET /change-password` - Password change page

**How to Apply**:
1. Connect to MariaDB: `docker exec -it <container_name> mariadb -u app_user -p`
2. Select database: `USE facial_recognition;`
3. Run the ALTER TABLE command above
4. Verify: `DESCRIBE user;`

---

### 2025-11-01: Add Server Settings and Device Management Tables

**Purpose**: Added device management system for registration kiosks and people scanners, plus server settings storage.

**SQL Commands**:
```sql
-- Server Settings table
CREATE TABLE server_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(100) NOT NULL UNIQUE,
    setting_value TEXT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    updated_by_user_id INT NULL,
    FOREIGN KEY (updated_by_user_id) REFERENCES user(id) ON DELETE SET NULL
);

-- Device table for kiosks and scanners
CREATE TABLE device (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(36) NOT NULL UNIQUE,
    registration_code VARCHAR(6) NOT NULL UNIQUE,
    device_name VARCHAR(255) NULL,
    location_id INT NULL,
    device_type VARCHAR(50) NULL,
    codeproject_endpoint VARCHAR(512) NULL,
    is_approved BOOLEAN NOT NULL DEFAULT FALSE,
    registered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at DATETIME NULL,
    approved_by_user_id INT NULL,
    last_seen DATETIME NULL,
    FOREIGN KEY (location_id) REFERENCES location(id) ON DELETE SET NULL,
    FOREIGN KEY (approved_by_user_id) REFERENCES user(id) ON DELETE SET NULL
);
```

**What this does**:
- Creates `server_settings` table for storing global configuration (like default CodeProject.AI URL)
- Creates `device` table for managing kiosks and scanners
- Devices get a unique UUID (`device_id`) and 6-digit `registration_code`
- Devices can be assigned to locations and configured as 'registration_kiosk' or 'people_scanner'
- Each device has its own `codeproject_endpoint` for facial recognition

**Related Features**:
- Server settings management page (superadmin only)
- Device registration workflow with 6-digit codes
- Location admins can approve devices for their locations
- Facial_Display client app for kiosks/scanners
- Device heartbeat tracking (last_seen)

**How to Apply**:
1. Connect to MariaDB: `docker exec -it <container_name> mariadb -u app_user -p`
2. Select database: `USE facial_recognition;`
3. Run both CREATE TABLE commands above
4. Verify: `SHOW TABLES;` and `DESCRIBE server_settings;` and `DESCRIBE device;`

---

## Future Migrations

Add new migrations below this line with date, purpose, and SQL commands.
