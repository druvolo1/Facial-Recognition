"""
Database initialization script for Facial Recognition App
Creates the database and required tables if they don't exist
"""
import os
import sys
from dotenv import load_dotenv
import aiomysql
import asyncio

# Get the directory paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(CURRENT_DIR)

# Load environment variables from the parent directory
env_path = os.path.join(BASE_DIR, '.env')
print(f"[DB-INIT] Looking for .env file at: {env_path}")
print(f"[DB-INIT] .env file exists: {os.path.exists(env_path)}")
load_dotenv(env_path)

# Parse database URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print(f"[DB-INIT] ERROR: DATABASE_URL not found in environment")
    print(f"[DB-INIT] Current directory: {CURRENT_DIR}")
    print(f"[DB-INIT] Base directory: {BASE_DIR}")
    print(f"[DB-INIT] Tried to load .env from: {env_path}")
    print(f"[DB-INIT] Please ensure .env file exists at: {env_path}")
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

print(f"[DB-INIT] Connecting to MariaDB server at {DB_HOST}:{DB_PORT}")
print(f"[DB-INIT] User: {DB_USER}")
print(f"[DB-INIT] Target database: {DB_NAME}")


async def create_database():
    """Create the database if it doesn't exist"""
    print(f"\n{'='*60}")
    print(f"[DATABASE] Initializing database: {DB_NAME}")
    print(f"[DATABASE] Host: {DB_HOST}:{DB_PORT}")
    print(f"[DATABASE] User: {DB_USER}")

    conn = None
    try:
        # First, try to connect to the specific database
        # If it exists, we're done
        try:
            test_conn = await aiomysql.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                db=DB_NAME,
                autocommit=True
            )
            test_conn.close()
            print(f"[DATABASE] ✓ Database '{DB_NAME}' already exists and is accessible")
            return True
        except aiomysql.OperationalError as e:
            if "Access denied" in str(e) and "database" in str(e):
                # Database doesn't exist, we'll try to create it
                print(f"[DATABASE] Database '{DB_NAME}' does not exist, attempting to create...")
            else:
                raise

        # Connect to MySQL server (without specifying database)
        conn = await aiomysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            autocommit=True
        )

        async with conn.cursor() as cursor:
            # Create database
            try:
                await cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                print(f"[DATABASE] ✓ Created database '{DB_NAME}'")
            except aiomysql.OperationalError as e:
                if "Access denied" in str(e):
                    print(f"[DATABASE] ✗ Cannot create database - insufficient permissions")
                    print(f"[DATABASE] Please run this SQL command as root user:")
                    print(f"[DATABASE]   CREATE DATABASE {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
                    print(f"[DATABASE]   GRANT ALL PRIVILEGES ON {DB_NAME}.* TO '{DB_USER}'@'%';")
                    print(f"[DATABASE]   FLUSH PRIVILEGES;")
                    return False
                raise

        conn.close()

        print(f"[DATABASE] ✓ Database initialization complete")
        print(f"[DATABASE] Tables will be created by FastAPI on first run")
        print(f"{'='*60}\n")

        return True

    except Exception as e:
        print(f"[DATABASE] ✗ Error initializing database: {e}")
        print(f"[DATABASE] Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        print(f"{'='*60}\n")
        return False
    finally:
        if conn and not conn.closed:
            conn.close()


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
