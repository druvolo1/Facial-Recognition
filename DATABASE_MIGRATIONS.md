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

## Future Migrations

Add new migrations below this line with date, purpose, and SQL commands.
