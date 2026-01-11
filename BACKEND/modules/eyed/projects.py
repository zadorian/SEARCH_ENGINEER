import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Optional
import uuid

class ProjectManager:
    def __init__(self, db_path: str = "projects.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database with projects table"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Create projects table
        c.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                is_active BOOLEAN DEFAULT 0,
                graph_data TEXT,
                metadata TEXT
            )
        ''')
        
        # Create project_data table for storing investigation data
        c.execute('''
            CREATE TABLE IF NOT EXISTS project_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                data_type TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def create_project(self, name: str, description: str = "") -> Dict:
        """Create a new project"""
        project_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Deactivate all other projects
        c.execute("UPDATE projects SET is_active = 0")
        
        # Insert new project
        c.execute('''
            INSERT INTO projects (id, name, description, created_at, updated_at, is_active, graph_data, metadata)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        ''', (project_id, name, description, created_at, created_at, 
              json.dumps({"nodes": [], "edges": []}), json.dumps({})))
        
        conn.commit()
        conn.close()
        
        return {
            "id": project_id,
            "name": name,
            "description": description,
            "created_at": created_at,
            "updated_at": created_at,
            "is_active": True
        }
    
    def get_all_projects(self) -> List[Dict]:
        """Get all projects"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute('''
            SELECT id, name, description, created_at, updated_at, is_active 
            FROM projects 
            ORDER BY updated_at DESC
        ''')
        
        projects = []
        for row in c.fetchall():
            projects.append(dict(row))
        
        conn.close()
        return projects
    
    def get_active_project(self) -> Optional[Dict]:
        """Get the currently active project"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute('''
            SELECT id, name, description, created_at, updated_at, is_active, graph_data
            FROM projects 
            WHERE is_active = 1
        ''')
        
        row = c.fetchone()
        conn.close()
        
        if row:
            project = dict(row)
            project['graph_data'] = json.loads(project['graph_data'])
            return project
        return None
    
    def switch_project(self, project_id: str) -> bool:
        """Switch to a different project"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Check if project exists
        c.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if not c.fetchone():
            conn.close()
            return False
        
        # Deactivate all projects
        c.execute("UPDATE projects SET is_active = 0")
        
        # Activate selected project
        c.execute("UPDATE projects SET is_active = 1 WHERE id = ?", (project_id,))
        
        conn.commit()
        conn.close()
        return True
    
    def update_project_graph(self, project_id: str, graph_data: Dict) -> bool:
        """Update the graph data for a project"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        updated_at = datetime.now().isoformat()
        
        c.execute('''
            UPDATE projects 
            SET graph_data = ?, updated_at = ? 
            WHERE id = ?
        ''', (json.dumps(graph_data), updated_at, project_id))
        
        conn.commit()
        affected = c.rowcount
        conn.close()
        
        return affected > 0
    
    def delete_project(self, project_id: str) -> bool:
        """Delete a project and all associated data"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Delete project data
        c.execute("DELETE FROM project_data WHERE project_id = ?", (project_id,))
        
        # Delete project
        c.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        
        conn.commit()
        affected = c.rowcount
        conn.close()
        
        # If we deleted the active project, activate the most recent one
        if affected > 0:
            projects = self.get_all_projects()
            if projects:
                self.switch_project(projects[0]['id'])
        
        return affected > 0
    
    def save_project_data(self, project_id: str, data_type: str, data: Dict) -> bool:
        """Save investigation data associated with a project"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        created_at = datetime.now().isoformat()
        
        c.execute('''
            INSERT INTO project_data (project_id, data_type, data, created_at)
            VALUES (?, ?, ?, ?)
        ''', (project_id, data_type, json.dumps(data), created_at))
        
        conn.commit()
        conn.close()
        return True
    
    def get_project_data(self, project_id: str, data_type: Optional[str] = None) -> List[Dict]:
        """Get investigation data for a project"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        if data_type:
            c.execute('''
                SELECT data_type, data, created_at 
                FROM project_data 
                WHERE project_id = ? AND data_type = ?
                ORDER BY created_at DESC
            ''', (project_id, data_type))
        else:
            c.execute('''
                SELECT data_type, data, created_at 
                FROM project_data 
                WHERE project_id = ?
                ORDER BY created_at DESC
            ''', (project_id,))
        
        results = []
        for row in c.fetchall():
            result = dict(row)
            result['data'] = json.loads(result['data'])
            results.append(result)
        
        conn.close()
        return results