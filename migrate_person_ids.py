#!/usr/bin/env python3
"""
Migration script to populate person_id for existing registered faces
Groups by person_name and location_id, assigns one UUID per person/location
"""
import asyncio
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database import RegisteredFace
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "mariadb+aiomysql://app_user:testpass123@172.16.1.150:3306/facial_recognition")

async def migrate_person_ids():
    """Populate person_id for all records that have NULL person_id"""

    print("=" * 60)
    print("[MIGRATION] Starting person_id migration")
    print("=" * 60)

    # Create async engine
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get all registered faces with NULL person_id
        result = await session.execute(
            select(RegisteredFace).where(RegisteredFace.person_id.is_(None))
        )
        faces_with_null = result.scalars().all()

        print(f"[MIGRATION] Found {len(faces_with_null)} records with NULL person_id")

        if len(faces_with_null) == 0:
            print("[MIGRATION] ✓ No records to migrate")
            return

        # Group by person_name and location_id
        person_location_map = {}

        for face in faces_with_null:
            key = (face.person_name, face.location_id)
            if key not in person_location_map:
                person_location_map[key] = []
            person_location_map[key].append(face)

        print(f"[MIGRATION] Found {len(person_location_map)} unique person/location combinations")
        print()

        # Assign UUIDs and update database
        total_updated = 0

        for (person_name, location_id), face_list in person_location_map.items():
            # Generate new UUID for this person/location
            person_id = str(uuid.uuid4())

            print(f"[MIGRATION] Person: '{person_name}' at location {location_id}")
            print(f"[MIGRATION]   Generated UUID: {person_id}")
            print(f"[MIGRATION]   Updating {len(face_list)} records...")

            # Update all faces for this person/location
            for face in face_list:
                face.person_id = person_id
                # Also update codeproject_user_id to use UUID if it's currently the name
                if face.codeproject_user_id == person_name:
                    face.codeproject_user_id = person_id
                    print(f"[MIGRATION]     - Face ID {face.id}: Updated person_id and codeproject_user_id")
                else:
                    print(f"[MIGRATION]     - Face ID {face.id}: Updated person_id (kept existing codeproject_user_id: {face.codeproject_user_id})")

                total_updated += 1

            # Commit after each person/location group
            await session.commit()
            print(f"[MIGRATION]   ✓ Committed changes")
            print()

        print("=" * 60)
        print(f"[MIGRATION] ✓ Migration complete: {total_updated} records updated")
        print("=" * 60)

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate_person_ids())
