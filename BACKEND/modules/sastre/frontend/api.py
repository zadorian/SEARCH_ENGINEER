"""
SASTRE Frontend API
WebSocket + REST API for the SASTRE investigation dashboard
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Set
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys

sys.path.insert(0, "/data")

app = FastAPI(title="SASTRE Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# CONNECTION MANAGER
# ═══════════════════════════════════════════════════════════════

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.agent_logs: Dict[str, List[dict]] = {}  # session_id -> logs
        self.notes: Dict[str, str] = {}  # session_id -> notes content
        
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        
    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            
    async def send_to_client(self, client_id: str, message: dict):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)
            
    async def broadcast(self, message: dict):
        for conn in self.active_connections.values():
            await conn.send_json(message)


manager = ConnectionManager()


# ═══════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════

class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None

class BruteSearchRequest(BaseModel):
    query: str
    engines: Optional[List[str]] = None
    
class CymonSearch(BaseModel):
    query: str
    index: str = "cymonides-3"
    size: int = 100

class NotesUpdate(BaseModel):
    session_id: str
    content: str

class InvestigationRequest(BaseModel):
    query: str  # e.g., "p:John Smith" or "c:Acme Corp"
    project_id: Optional[str] = "default"


# ═══════════════════════════════════════════════════════════════
# AGENT SESSIONS
# ═══════════════════════════════════════════════════════════════

active_sessions: Dict[str, dict] = {}

async def stream_agent_event(session_id: str, event: dict):
    """Stream an agent event to all connected clients watching this session."""
    if session_id not in manager.agent_logs:
        manager.agent_logs[session_id] = []
    manager.agent_logs[session_id].append(event)
    
    await manager.broadcast({
        "type": "agent_event",
        "session_id": session_id,
        "event": event
    })


# ═══════════════════════════════════════════════════════════════
# WEBSOCKET ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    
    # Send current sessions on connect
    await manager.send_to_client(client_id, {
        "type": "sessions_list",
        "sessions": list(active_sessions.keys())
    })
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "chat":
                # Chat with SASTRE AI
                await handle_chat(client_id, data)
                
            elif msg_type == "subscribe_session":
                # Subscribe to agent session logs
                session_id = data.get("session_id")
                if session_id in manager.agent_logs:
                    # Send existing logs
                    for log in manager.agent_logs[session_id]:
                        await manager.send_to_client(client_id, {
                            "type": "agent_event",
                            "session_id": session_id,
                            "event": log
                        })
                        
            elif msg_type == "torpedo_crawl":
                await handle_torpedo_crawl(client_id, data)
            elif msg_type == "notes_update":
                # Update notes and broadcast
                session_id = data.get("session_id", "default")
                content = data.get("content", "")
                manager.notes[session_id] = content
                await manager.broadcast({
                    "type": "notes_changed",
                    "session_id": session_id,
                    "content": content
                })
                
    except WebSocketDisconnect:
        manager.disconnect(client_id)


async def handle_chat(client_id: str, data: dict):
    """Handle chat message - route to SASTRE AI."""
    message = data.get("message", "")
    session_id = data.get("session_id") or str(uuid.uuid4())[:8]
    
    # Create session if new
    if session_id not in active_sessions:
        active_sessions[session_id] = {
            "id": session_id,
            "started": datetime.now().isoformat(),
            "query": message,
            "status": "running"
        }
        await manager.broadcast({
            "type": "session_created",
            "session": active_sessions[session_id]
        })
    
    # Stream thinking indicator
    await manager.send_to_client(client_id, {
        "type": "chat_thinking",
        "session_id": session_id
    })
    
    try:
        # Import and call SASTRE
        from SASTRE.cli import run_investigation
        
        # Run investigation with event callback
        async def event_callback(event):
            await stream_agent_event(session_id, event)
            
        result = await run_investigation(message, event_callback=event_callback)
        
        await manager.send_to_client(client_id, {
            "type": "chat_response",
            "session_id": session_id,
            "response": result.get("summary", "Investigation complete."),
            "findings": result.get("findings", [])
        })
        
    except Exception as e:
        # Fallback: direct execution via CLI
        import subprocess
        proc = subprocess.Popen(
            ["python3", "-m", "SASTRE.cli", message],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd="/data",
            env={"PYTHONPATH": "/data"}
        )
        
        output_lines = []
        for line in iter(proc.stdout.readline, b''):
            line_str = line.decode('utf-8', errors='replace').strip()
            if line_str:
                output_lines.append(line_str)
                await stream_agent_event(session_id, {
                    "type": "log",
                    "message": line_str,
                    "timestamp": datetime.now().isoformat()
                })
        
        proc.wait()
        
        await manager.send_to_client(client_id, {
            "type": "chat_response", 
            "session_id": session_id,
            "response": "\n".join(output_lines[-10:]) if output_lines else "Investigation complete."
        })
    
    active_sessions[session_id]["status"] = "complete"


# ═══════════════════════════════════════════════════════════════
# REST ENDPOINTS
# ═══════════════════════════════════════════════════════════════


async def handle_torpedo_crawl(client_id: str, data: dict):
    """Handle TORPEDO crawl with visualization streaming."""
    query = data.get("query", "")
    jurisdiction = data.get("jurisdiction", ":cuk!")
    
    if not query:
        return
    
    # Send initial node
    await manager.send_to_client(client_id, {
        "type": "torpedo_node",
        "url": query,
        "parent": None,
        "extractions": []
    })
    
    try:
        # Import TORPEDO and JESTER for crawling
        import sys
        sys.path.insert(0, "/data")
        
        from TORPEDO import Torpedo
        from JESTER import Jester
        
        torpedo = Torpedo()
        await torpedo.load_sources()
        
        jester = Jester()
        
        # Search corporate registry
        jur_code = jurisdiction.replace(":c", "").replace("!", "")
        result = await torpedo.search_cr(query, jur_code, max_sources=3)
        
        sources_searched = result.get("sources_searched", [])
        
        for source in sources_searched:
            source_url = source.get("url", source.get("name", "unknown"))
            extractions = []
            
            # Extract entities from results
            if source.get("results"):
                for r in source.get("results", [])[:5]:
                    if r.get("name"):
                        extractions.append({"type": "company", "value": r["name"]})
                    if r.get("registration_number"):
                        extractions.append({"type": "reg_no", "value": r["registration_number"]})
                    if r.get("directors"):
                        for d in r.get("directors", [])[:3]:
                            extractions.append({"type": "person", "value": d})
            
            await manager.send_to_client(client_id, {
                "type": "torpedo_node",
                "url": source_url,
                "parent": query,
                "extractions": extractions
            })
            
            await asyncio.sleep(0.1)  # Small delay for visual effect
        
        await jester.close()
        
    except Exception as e:
        await manager.send_to_client(client_id, {
            "type": "torpedo_error",
            "error": str(e)
        })


@app.get("/")
async def root():
    return FileResponse("/data/SEARCH_ENGINEER/BACKEND/modules/sastre/frontend/index.html")


@app.get("/api/sessions")
async def get_sessions():
    """Get all active/recent sessions."""
    return {"sessions": list(active_sessions.values())}


@app.get("/api/sessions/{session_id}/logs")
async def get_session_logs(session_id: str):
    """Get logs for a specific session."""
    return {"logs": manager.agent_logs.get(session_id, [])}


@app.post("/api/investigate")
async def start_investigation(req: InvestigationRequest):
    """Start a new investigation."""
    session_id = str(uuid.uuid4())[:8]
    active_sessions[session_id] = {
        "id": session_id,
        "started": datetime.now().isoformat(),
        "query": req.query,
        "status": "running"
    }
    
    # Run async
    asyncio.create_task(_run_investigation(session_id, req.query))
    
    return {"session_id": session_id, "status": "started"}


async def _run_investigation(session_id: str, query: str):
    """Background investigation runner."""
    try:
        import subprocess
        proc = subprocess.Popen(
            ["python3", "-m", "SASTRE.cli", query],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd="/data",
            env={"PYTHONPATH": "/data"}
        )
        
        for line in iter(proc.stdout.readline, b''):
            line_str = line.decode('utf-8', errors='replace').strip()
            if line_str:
                await stream_agent_event(session_id, {
                    "type": "log",
                    "message": line_str,
                    "timestamp": datetime.now().isoformat()
                })
        
        proc.wait()
        active_sessions[session_id]["status"] = "complete"
        
    except Exception as e:
        active_sessions[session_id]["status"] = "error"
        await stream_agent_event(session_id, {
            "type": "error",
            "message": str(e)
        })


@app.post("/api/brute")
async def brute_search(req: BruteSearchRequest):
    """Run BRUTE multi-engine search."""
    try:
        from brute.fast_search import FastSearch
        searcher = FastSearch()
        results = await searcher.search(req.query, engines=req.engines)
        return {"results": results}
    except Exception as e:
        # Fallback to cymonides brute index
        return await cymon_search(CymonSearch(query=req.query, index="brute-results"))


@app.post("/api/cymonides")
async def cymon_search(req: CymonSearch):
    """Search Cymonides-3 or other ES indices."""
    try:
        from elasticsearch import AsyncElasticsearch
        es = AsyncElasticsearch(["http://localhost:9200"])
        
        body = {
            "query": {
                "query_string": {
                    "query": req.query,
                    "default_operator": "AND"
                }
            },
            "size": req.size
        }
        
        result = await es.search(index=req.index, body=body)
        await es.close()
        
        hits = [
            {
                "id": h["_id"],
                "score": h["_score"],
                "source": h["_source"]
            }
            for h in result["hits"]["hits"]
        ]
        
        return {
            "total": result["hits"]["total"]["value"],
            "hits": hits
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/notes/{session_id}")
async def get_notes(session_id: str):
    """Get notes for a session."""
    return {"content": manager.notes.get(session_id, "")}


@app.post("/api/notes")
async def update_notes(req: NotesUpdate):
    """Update notes for a session."""
    manager.notes[req.session_id] = req.content
    await manager.broadcast({
        "type": "notes_changed",
        "session_id": req.session_id,
        "content": req.content
    })
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════
# STATIC FILES
# ═══════════════════════════════════════════════════════════════

# Serve static files after all routes
    app.mount("/static", StaticFiles(directory="/data/SEARCH_ENGINEER/BACKEND/modules/sastre/frontend/static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8202)


# ═══════════════════════════════════════════════════════════════
# TORPEDO ENDPOINT
# ═══════════════════════════════════════════════════════════════

class TorpedoRequest(BaseModel):
    query: str
    jurisdiction: Optional[str] = None

@app.post("/api/torpedo")
async def torpedo_search(req: TorpedoRequest):
    """Search company registries via TORPEDO."""
    try:
        # Parse query for jurisdiction
        query = req.query
        jurisdiction = req.jurisdiction
        
        # Try to extract jurisdiction from query like "c: Acme :cuk!"
        import re
        jur_match = re.search(r":c([a-z]{2})!", query, re.I)
        if jur_match:
            jurisdiction = jur_match.group(1).upper()
            query = re.sub(r":c[a-z]{2}!", "", query).strip()
        
        # Clean query
        query = re.sub(r"^[cp]:\s*", "", query).strip()
        
        if not jurisdiction:
            jurisdiction = "UK"  # Default
        
        # Call TORPEDO bridge
        sys.path.insert(0, "/data")
        from SASTRE.bridges import TorpedoBridge
        
        bridge = TorpedoBridge()
        result = await bridge.fetch_profile(query, jurisdiction)
        await bridge.close()
        
        if result.get("success"):
            return {
                "results": [result.get("profile", {})],
                "source": result.get("source"),
                "profile_url": result.get("profile_url")
            }
        else:
            return {"results": [], "error": result.get("error")}
            
    except Exception as e:
        return {"results": [], "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# EDITH COMPOSE ENDPOINT
# ═══════════════════════════════════════════════════════════════

class EdithComposeRequest(BaseModel):
    template: str
    subject: str

@app.post("/api/edith/compose")
async def edith_compose(req: EdithComposeRequest):
    """Compose document section via EDITH templates."""
    try:
        # For now, return a placeholder
        # TODO: Connect to actual EDITH template system
        return {
            "content": f"[{req.template.upper()} Report]\n\nSubject: {req.subject}\n\n(Template composition pending EDITH integration)",
            "template": req.template,
            "subject": req.subject
        }
    except Exception as e:
        return {"error": str(e)}
