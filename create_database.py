#!/usr/bin/env python3
"""
Standalone script to create the facial_recognition database
Run this if the application cannot create the database automatically
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

import asyncio
from app.init_database import init_database

def main():
    print("="*60)
    print("Facial Recognition Database Setup")
    print("="*60)
    print()

    # Run the async database initialization
    success = asyncio.run(init_database())

    print()
    if success:
        print("✓ Database setup completed successfully!")
        print()
        print("You can now run the application:")
        print("  cd app")
        print("  python main.py")
        return 0
    else:
        print("✗ Database setup failed!")
        print()
        print("If you see permission errors, you need to:")
        print("1. Connect to MariaDB as root:")
        print("   mysql -h 172.16.1.150 -u root -p")
        print()
        print("2. Run these SQL commands:")
        print("   CREATE DATABASE facial_recognition CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        print("   GRANT ALL PRIVILEGES ON facial_recognition.* TO 'app_user'@'%';")
        print("   FLUSH PRIVILEGES;")
        print()
        print("3. Then run this script again")
        return 1

if __name__ == "__main__":
    sys.exit(main())
