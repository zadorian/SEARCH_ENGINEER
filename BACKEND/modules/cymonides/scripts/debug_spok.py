#!/usr/bin/env python3
import psycopg2
import sys
from psycopg2.extras import RealDictCursor

# Hardcoded DB URL (same as sync script)
DB_URL = "postgresql://attic@localhost:5432/search_engineer_db"

try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    print("--- SEARCHING FOR PROJECTS ---")
    cur.execute("SELECT * FROM nodes WHERE label ILIKE '%Spok%' OR label ILIKE '%Memory%' OR label ILIKE '%Default%'")
    rows = cur.fetchall()
    
    for row in rows:
        print(f"ID: {row['id']}")
        print(f"Label: {row['label']}")
        print(f"ClassID: {row['classId']}")
        print(f"TypeID: {row['typeId']}")
        print(f"UserID: {row['userId']}")
        print(f"Status: {row['status']}")
        print("-" * 20)
        
    print("\n--- CHECKING USERS ---")
    cur.execute("SELECT * FROM users")
    users = cur.fetchall()
    for u in users:
        print(f"ID: {u['id']} | Email: {u['email']} | Role: {u['role']}")

    conn.close()

except Exception as e:
    print(f"Error: {e}")
