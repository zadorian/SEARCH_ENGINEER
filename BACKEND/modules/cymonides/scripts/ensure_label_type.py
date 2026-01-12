#!/usr/bin/env python3
import psycopg2
import os

# Hardcoded for speed, matching previous scripts
DB_URL = "postgresql://attic@localhost:5432/search_engineer_db"

def ensure_label_type():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        
        # 1. Get 'narrative' class ID
        cur.execute("SELECT id FROM \"nodeClasses\" WHERE name = 'narrative'")
        res = cur.fetchone()
        if not res:
            print("Error: 'narrative' class not found!")
            return
        class_id = res[0]
        
        # 2. Check/Insert 'label' type
        cur.execute("SELECT id FROM \"nodeTypes\" WHERE name = 'label' AND \"classId\" = %s", (class_id,))
        if cur.fetchone():
            print("'label' type already exists.")
        else:
            print("Creating 'label' type...")
            cur.execute("""
                INSERT INTO \"nodeTypes\" (\"classId\", name, \"displayLabel\", \"enforceUniqueness\", color)
                VALUES (%s, 'label', 'Label', false, '#8b5cf6')
            """, (class_id,))
            print("Created 'label' type.")
            
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    ensure_label_type()
