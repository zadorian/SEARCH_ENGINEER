#!/usr/bin/env python3
import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://attic@localhost:5432/search_engineer_db"
SPOCK_ID = "e2ad59923de2d103551e86bab6421260"

try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    user_id = 8 # dev@localhost

    # 1. Ensure Spock Project is owned by User 8
    print("Updating Spock Project ownership...")
    cur.execute("""
        UPDATE nodes 
        SET \"userId\" = %s 
        WHERE id = %s
    """, (user_id, SPOCK_ID))
    
    # 2. Ensure Spock is type 'Project'
    cur.execute("SELECT id FROM \"nodeTypes\" WHERE name = 'project'")
    pt = cur.fetchone()
    if pt:
        cur.execute("""
            UPDATE nodes 
            SET \"typeId\" = %s 
            WHERE id = %s
        """, (pt[0], SPOCK_ID))

    # 3. Link orphans to Spock (projectId column)
    print("Linking nodes to Spock project...")
    cur.execute("""
        UPDATE nodes 
        SET \"projectId\" = %s
        WHERE metadata->>'imported_from' = 'EYE-D'
        AND id != %s
    """, (SPOCK_ID, SPOCK_ID))
    
    # 4. Try to update userId for items, ignoring conflicts (if possible)
    # Postgres doesn't support IGNORE on UPDATE directly like that.
    # We will do it loop style to be safe and specific.
    
    cur.execute("""
        SELECT id FROM nodes 
        WHERE metadata->>'imported_from' = 'EYE-D' 
        AND \"userId\" IS NULL
    """)
    orphans = cur.fetchall()
    print(f"Found {len(orphans)} orphan nodes to assign.")
    
    success = 0
    for row in orphans:
        node_id = row[0]
        try:
            # Create a new cursor for each to isolate transactions if needed, 
            # but here we just wrap in sub-transaction/savepoint
            cur.execute(f"SAVEPOINT sp_{node_id}")
            cur.execute("""
                UPDATE nodes SET \"userId\" = %s WHERE id = %s
            """, (user_id, node_id))
            cur.execute(f"RELEASE SAVEPOINT sp_{node_id}") # Success
            success += 1
        except psycopg2.IntegrityError:
            cur.execute(f"ROLLBACK TO SAVEPOINT sp_{node_id}")
            # Duplicate exists. We should DELETE this orphan and maybe relink the edge?
            # For now, just leave it or log it.
            print(f"Skipping duplicate node {node_id}")

    print(f"Successfully assigned {success} nodes.")
    conn.commit()
    conn.close()

except Exception as e:
    print(f"Error: {e}")