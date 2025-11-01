"""
Database initialization script for Facial Recognition App
Creates the database and required tables if they don't exist
"""
import os
from dotenv import load_dotenv
import aiomysql
import asyncio

# Load environment variables
load_dotenv()

# Parse database URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in .env file")

# Extract connection details from DATABASE_URL
# Format: mariadb+aiomysql://user:password@host:port/database
import re
match = re.match(r'mariadb\+aiomysql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', DATABASE_URL)
if not match:
    raise ValueError(f"Invalid DATABASE_URL format: {DATABASE_URL}")

DB_USER = match.group(1)
DB_PASSWORD = match.group(2)
DB_HOST = match.group(3)
DB_PORT = int(match.group(4))
DB_NAME = match.group(5)


async def create_database():
    """Create the database if it doesn't exist"""
    print(f"\n{'='*60}")
    print(f"[DATABASE] Initializing database: {DB_NAME}")
    print(f"[DATABASE] Host: {DB_HOST}:{DB_PORT}")
    print(f"[DATABASE] User: {DB_USER}")

    try:
        # Connect to MySQL server (without specifying database)
        conn = await aiomysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            autocommit=True
        )

        async with conn.cursor() as cursor:
            # Check if database exists
            await cursor.execute(f"SHOW DATABASES LIKE '{DB_NAME}'")
            result = await cursor.fetchone()

            if result:
                print(f"[DATABASE] ✓ Database '{DB_NAME}' already exists")
            else:
                # Create database
                await cursor.execute(f"CREATE DATABASE {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                print(f"[DATABASE] ✓ Created database '{DB_NAME}'")

        conn.close()
        await conn.wait_closed()

        # Now connect to the specific database to create tables
        conn = await aiomysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
            autocommit=True
        )

        async with conn.cursor() as cursor:
            # Check and add columns to users table if needed
            # This allows upgrading existing databases
            await cursor.execute(f"""
                SELECT TABLE_NAME
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = '{DB_NAME}'
                AND TABLE_NAME = 'user'
            """)

            table_exists = await cursor.fetchone()

            if table_exists:
                print(f"[DATABASE] User table exists, checking schema...")

                # Check for custom columns
                columns_to_add = [
                    ("first_name", "VARCHAR(255) NULL"),
                    ("last_name", "VARCHAR(255) NULL"),
                    ("is_suspended", "BOOLEAN NOT NULL DEFAULT FALSE"),
                    ("dashboard_preferences", "TEXT NULL")
                ]

                for column_name, column_def in columns_to_add:
                    await cursor.execute(f"""
                        SELECT COLUMN_NAME
                        FROM information_schema.COLUMNS
                        WHERE TABLE_SCHEMA = '{DB_NAME}'
                        AND TABLE_NAME = 'user'
                        AND COLUMN_NAME = '{column_name}'
                    """)

                    column_exists = await cursor.fetchone()

                    if not column_exists:
                        print(f"[DATABASE]   Adding column '{column_name}'...")
                        await cursor.execute(f"ALTER TABLE user ADD COLUMN {column_name} {column_def}")
                        print(f"[DATABASE]   ✓ Column '{column_name}' added")
                    else:
                        print(f"[DATABASE]   Column '{column_name}' already exists")

                # Modify is_active default to FALSE (pending approval)
                print(f"[DATABASE]   Setting is_active default to FALSE...")
                await cursor.execute("""
                    ALTER TABLE user
                    MODIFY COLUMN is_active BOOLEAN NOT NULL DEFAULT FALSE
                """)
                print(f"[DATABASE]   ✓ is_active default set to FALSE (pending approval)")
            else:
                print(f"[DATABASE] User table will be created by FastAPI-Users on first run")

        conn.close()
        await conn.wait_closed()

        print(f"[DATABASE] ✓ Database initialization complete")
        print(f"{'='*60}\n")

        return True

    except Exception as e:
        print(f"[DATABASE] ✗ Error initializing database: {e}")
        import traceback
        traceback.print_exc()
        print(f"{'='*60}\n")
        return False


async def init_database():
    """Main initialization function"""
    return await create_database()


if __name__ == "__main__":
    # Run the initialization
    success = asyncio.run(init_database())
    if success:
        print("Database initialization successful!")
    else:
        print("Database initialization failed!")
        exit(1)
