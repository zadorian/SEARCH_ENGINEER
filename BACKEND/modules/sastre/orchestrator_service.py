#!/usr/bin/env python3
"""
SASTRE ORCHESTRATOR SERVICE - The Control Loop
===============================================
FastAPI wrapper for ThinOrchestrator and MultiAgentRunner.

This is the CONTROL LAYER that closes the automation loop:
- enrichment_server_v3.py (port 8200) = DATA layer (individual lookups)
- orchestrator_service.py (port 8201) = CONTROL layer (autonomous investigation)

The difference:
- DATA layer: "Give me company officers" → returns officers
- CONTROL layer: "Investigate this company" → autonomously runs full DD

Flow:
    Client → /investigate → ThinOrchestrator → EDITH routing →
    → Complexity scoring → Watcher setup → Action execution →
    → Validation → Complete report

Start: uvicorn orchestrator_service:app --host 0.0.0.0 --port 8201
"""

import sys
import os
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, AsyncGenerator
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import json

# Load environment
from dotenv import load_dotenv
load_dotenv(Path("/data/SEARCH_ENGINEER/BACKEND/modules/sastre/.env"))

# Add module paths - /data as root so SASTRE is a package
sys.path.insert(0, "/data")  # Makes SASTRE importable as SASTRE.orchestrator.thin
sys.path.insert(0, "/data/ENRICHMENT")
sys.path.insert(0, "/data/EDITH")
sys.path.insert(0, "/data/CYMONIDES")
sys.path.insert(0, "/data/BRUTE")
sys.path.insert(0, "/data/EYE-D")

# Import Auth
from modules.sastre.auth import require_auth, verify_user, create_token_pair
from fastapi import Depends, Body
from fastapi.security import HTTPBearer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SASTRE Orchestrator Service",
    description="Autonomous Investigation Control Loop - ThinOrchestrator + MultiAgentRunner",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============ LAZY IMPORTS ============
_orchestrator = None
_multi_agent_runner = None


def get_orchestrator():
    """Get ThinOrchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        try:
            from SASTRE.orchestrator.thin import ThinOrchestrator
            _orchestrator = ThinOrchestrator()
            logger.info("ThinOrchestrator initialized")
        except Exception as e:
            logger.error(f"Failed to initialize ThinOrchestrator: {e}")
            import traceback
            logger.error(traceback.format_exc())
    return _orchestrator


def get_multi_agent_runner():
    """Get MultiAgentRunner instance."""
    global _multi_agent_runner
    if _multi_agent_runner is None:
        try:
            from SASTRE.multi_agent_runner import MultiAgentRunner
            _multi_agent_runner = MultiAgentRunner()
            logger.info("MultiAgentRunner initialized")
        except Exception as e:
            logger.error(f"Failed to initialize MultiAgentRunner: {e}")
            import traceback
            logger.error(traceback.format_exc())
    return _multi_agent_runner


# ============ REQUEST MODELS ============

class InvestigationRequest(BaseModel):
    """Full investigation request."""
    query: str = Field(..., description="Investigation query (e.g., 'DD on UK company Test Ltd')")
    project_id: Optional[str] = Field(None, description="Graph project ID for watchers")
    document_id: Optional[str] = Field(None, description="Parent document ID")
    stream: bool = Field(True, description="Stream events as they happen")
    max_iterations: int = Field(10, description="Max action iterations")


class MultiAgentRequest(BaseModel):
    """Multi-agent investigation request."""
    query: str = Field(..., description="Investigation query")
    project_id: Optional[str] = None
    document_id: Optional[str] = None
    max_agent_loops: int = Field(5, description="Max agent loop iterations")


class GapAnalysisRequest(BaseModel):
    """Gap analysis request for existing document."""
    document_id: str = Field(..., description="Document to analyze")
    project_id: Optional[str] = None
    mode: str = Field("NARRATIVE", description="Cognitive mode: NARRATIVE, SUBJECT, LOCATION, NEXUS")


class GridRotationRequest(BaseModel):
    """Full grid rotation through all 4 cognitive modes."""
    document_id: str = Field(..., description="Document to analyze")
    project_id: Optional[str] = None
    max_gaps_per_mode: int = Field(10, description="Max gaps to return per mode")
    cross_pollinate: bool = Field(True, description="Enable cross-pollination between modes")


class CognitoRequest(BaseModel):
    """C0GN1T0 AI co-author request."""
    message: str = Field(..., description="User message to C0GN1T0")
    document_id: Optional[str] = Field(None, description="Current document context")
    project_id: Optional[str] = None
    context_cells: Optional[List[str]] = Field(None, description="Selected grid cells")
    mode: str = Field("assist", description="Mode: assist, fill, research, disambiguate")


# ============ SSE HELPERS ============

async def event_generator(investigation_id: str, events: AsyncGenerator) -> AsyncGenerator[str, None]:
    """Generate SSE events from investigation stream."""
    try:
        async for event in events:
            yield f"data: {json.dumps(event.to_dict() if hasattr(event, 'to_dict') else event)}\n\n"
        yield f"data: {json.dumps({'type': 'complete', 'investigation_id': investigation_id})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"


# ============ API ROUTES ============

@app.post("/api/login")
async def login(credentials: dict = Body(...)):
    """
    Login to get access token.
    Requires 'username' and 'password'.
    """
    username = credentials.get("username")
    password = credentials.get("password")
    
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
        
    user = verify_user(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    return create_token_pair(user)


@app.post("/api/investigate")
async def investigate(request: InvestigationRequest, user: dict = Depends(require_auth)):
    """
    Run full autonomous investigation via ThinOrchestrator.

    Phases:
    1. ROUTING - EDITH routes query to jurisdiction/genre
    2. COMPLEXITY - Scores complexity for model selection
    3. CONTEXT - Builds template context
    4. WATCHER_SETUP - Creates watchers for document sections
    5. EXECUTION - Runs allowed actions
    6. VALIDATION - Validates completeness
    7. COMPLETE - Returns results
    """
    logger.info(f"[Investigate] {request.query}")

    orchestrator = get_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="ThinOrchestrator not available")

    if request.stream:
        # Return SSE stream
        events = orchestrator.investigate_stream(
            query=request.query,
            project_id=request.project_id,
            document_id=request.document_id
        )

        return StreamingResponse(
            event_generator(f"inv_{hash(request.query)}", events),
            media_type="text/event-stream"
        )
    else:
        # Return full result
        try:
            result = await orchestrator.investigate(
                query=request.query,
                project_id=request.project_id,
                document_id=request.document_id,
                max_iterations=request.max_iterations
            )
            return {
                "investigation_id": result.investigation_id if hasattr(result, 'investigation_id') else None,
                "query": request.query,
                "phase": result.phase.value if hasattr(result, 'phase') else "complete",
                "jurisdiction": result.jurisdiction if hasattr(result, 'jurisdiction') else None,
                "genre": result.genre if hasattr(result, 'genre') else None,
                "complexity_score": result.complexity_score if hasattr(result, 'complexity_score') else None,
                "results": result.results if hasattr(result, 'results') else {},
                "watcher_ids": result.watcher_ids if hasattr(result, 'watcher_ids') else [],
                "elapsed_ms": result.elapsed_ms() if hasattr(result, 'elapsed_ms') else None
            }
        except Exception as e:
            logger.error(f"Investigation error: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/investigate/multi-agent")
async def investigate_multi_agent(request: MultiAgentRequest, user: dict = Depends(require_auth)):
    """
    Run multi-agent investigation.

    Agent Loop:
    1. ORCHESTRATOR (Opus) - Strategy and routing
    2. INVESTIGATOR (Opus) - Deep research
    3. DISAMBIGUATOR (Sonnet) - Entity resolution
    4. WRITER (Sonnet) - Report drafting

    Loops until complete or max iterations reached.
    """
    logger.info(f"[MultiAgent] {request.query}")

    runner = get_multi_agent_runner()
    if not runner:
        raise HTTPException(status_code=503, detail="MultiAgentRunner not available")

    try:
        result = await runner.run(
            query=request.query,
            project_id=request.project_id,
            document_id=request.document_id,
            max_loops=request.max_agent_loops
        )
        return result
    except Exception as e:
        logger.error(f"Multi-agent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/investigate/gap-analysis")
async def gap_analysis(request: GapAnalysisRequest, user: dict = Depends(require_auth)):
    """
    Run gap analysis on existing document.

    Uses CognitiveEngine in specified mode:
    - NARRATIVE: Editor perspective (section completeness)
    - SUBJECT: Biographer perspective (entity profiles)
    - LOCATION: Cartographer perspective (jurisdiction coverage)
    - NEXUS: Detective perspective (relationship verification)
    """
    logger.info(f"[GapAnalysis] {request.document_id} in {request.mode} mode")

    try:
        from SASTRE.grid.cognitive_engine import CognitiveEngine
        engine = CognitiveEngine()

        gaps = await engine.analyze(
            document_id=request.document_id,
            project_id=request.project_id,
            mode=request.mode
        )

        return {
            "document_id": request.document_id,
            "mode": request.mode,
            "gaps": gaps
        }
    except ImportError:
        raise HTTPException(status_code=503, detail="CognitiveEngine not available")
    except Exception as e:
        logger.error(f"Gap analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/grid/rotate")
async def grid_rotation(request: GridRotationRequest, user: dict = Depends(require_auth)):
    """
    Full Grid Rotation - The Brain's 4-Mode Analysis Cycle.

    Rotates through all cognitive perspectives:
    1. NARRATIVE (Editor) - Story coherence, section gaps
    2. SUBJECT (Biographer) - Entity profile completeness
    3. LOCATION (Cartographer) - Jurisdiction coverage
    4. NEXUS (Detective) - Relationship verification

    Each mode reveals gaps the others miss.
    Cross-pollination spawns actions from insights.

    Gap = (Subject Axis × Location Axis × Nexus Axis)
    """
    logger.info(f"[GridRotation] {request.document_id}")

    try:
        from SASTRE.grid.cognitive_engine import CognitiveEngine
        engine = CognitiveEngine()

        results = {
            "document_id": request.document_id,
            "rotation_complete": False,
            "modes_analyzed": [],
            "gaps_by_mode": {},
            "cross_pollination": [],
            "total_gaps": 0,
            "priority_actions": []
        }

        modes = ["NARRATIVE", "SUBJECT", "LOCATION", "NEXUS"]

        for mode in modes:
            try:
                gaps = await engine.analyze(
                    document_id=request.document_id,
                    project_id=request.project_id,
                    mode=mode
                )

                # Limit gaps per mode
                if isinstance(gaps, list):
                    gaps = gaps[:request.max_gaps_per_mode]

                results["modes_analyzed"].append(mode)
                results["gaps_by_mode"][mode] = gaps
                results["total_gaps"] += len(gaps) if isinstance(gaps, list) else 1

            except Exception as e:
                logger.warning(f"Mode {mode} failed: {e}")
                results["gaps_by_mode"][mode] = {"error": str(e)}

        # Cross-pollination if enabled
        if request.cross_pollinate and hasattr(engine, 'cross_pollinate'):
            try:
                xpoll = await engine.cross_pollinate(results["gaps_by_mode"])
                results["cross_pollination"] = xpoll
            except Exception as e:
                logger.warning(f"Cross-pollination failed: {e}")

        # Extract priority actions
        for mode, gaps in results["gaps_by_mode"].items():
            if isinstance(gaps, list):
                for gap in gaps[:3]:  # Top 3 per mode
                    if isinstance(gap, dict) and gap.get("action"):
                        results["priority_actions"].append({
                            "mode": mode,
                            "action": gap.get("action"),
                            "target": gap.get("target"),
                            "priority": gap.get("priority", 50)
                        })

        results["rotation_complete"] = len(results["modes_analyzed"]) == 4
        return results

    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"CognitiveEngine not available: {e}")
    except Exception as e:
        logger.error(f"Grid rotation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/grid/modes")
async def grid_modes():
    """Get available cognitive modes and their descriptions."""
    return {
        "modes": {
            "NARRATIVE": {
                "persona": "The Editor",
                "focus": "Story coherence, section completeness",
                "questions": [
                    "Is the narrative arc complete?",
                    "Are there orphan sections?",
                    "Does the timeline flow?"
                ]
            },
            "SUBJECT": {
                "persona": "The Biographer",
                "focus": "Entity profile completeness",
                "questions": [
                    "Do we have full profile for each entity?",
                    "What attributes are missing?",
                    "Which entities need enrichment?"
                ]
            },
            "LOCATION": {
                "persona": "The Cartographer",
                "focus": "Jurisdiction and terrain coverage",
                "questions": [
                    "Which jurisdictions are covered?",
                    "Are there unreachable registries?",
                    "What dead-ends exist?"
                ]
            },
            "NEXUS": {
                "persona": "The Detective",
                "focus": "Relationship verification and connection logic",
                "questions": [
                    "Do we know both parties?",
                    "What is the relationship certainty?",
                    "Are there contradictions?"
                ],
                "certainty_levels": [
                    "CONFIRMED", "PROBABLE", "POSSIBLE",
                    "UNKNOWN", "CONTRADICTED"
                ]
            }
        },
        "gap_formula": "Gap = (Subject Axis × Location Axis × Nexus Axis)",
        "ku_quadrants": ["VERIFY", "TRACE", "EXTRACT", "DISCOVER"]
    }


@app.post("/api/cognito/chat")
async def cognito_chat(request: CognitoRequest):
    """
    C0GN1T0 AI Co-Author Endpoint.

    Modes:
    - assist: General help and guidance
    - fill: Fill empty section using EDITH templates
    - research: Trigger investigation for specific gap
    - disambiguate: Resolve entity conflicts

    Uses EDITH templates + Orchestrator + Claude for responses.
    """
    logger.info(f"[C0GN1T0] Mode: {request.mode}, Message: {request.message[:50]}...")

    try:
        import anthropic
        from pathlib import Path

        client = anthropic.Anthropic()

        # Build context from EDITH templates
        templates_dir = Path("/data/EDITH/templates")
        system_context = """You are C0GN1T0, the AI co-author for SASTRE investigation reports.

Your capabilities:
1. Fill empty report sections using EDITH templates
2. Suggest research actions based on gaps
3. Disambiguate entities when conflicts arise
4. Guide investigators through the DD process

You have access to:
- 217 jurisdiction templates
- 31 DD genre templates
- Grid rotation (NARRATIVE, SUBJECT, LOCATION, NEXUS modes)
- Full investigation pipeline

Respond concisely. Use markdown. Reference specific sections when suggesting fills."""

        # Add document context if available
        if request.document_id:
            system_context += f"\n\nCurrent document: {request.document_id}"

        if request.context_cells:
            system_context += f"\nSelected cells: {', '.join(request.context_cells[:5])}"

        # Mode-specific instructions
        mode_prompts = {
            "assist": "Help the user with their request.",
            "fill": "Suggest content to fill the empty section based on EDITH templates. Be specific about what data to include.",
            "research": "Identify what research actions are needed and suggest queries for the orchestrator.",
            "disambiguate": "Help resolve entity conflicts. Ask clarifying questions if needed."
        }

        system_context += f"\n\nMode: {request.mode}\nInstruction: {mode_prompts.get(request.mode, mode_prompts['assist'])}"

        # Call Claude
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2048,
            system=system_context,
            messages=[{"role": "user", "content": request.message}]
        )

        assistant_message = response.content[0].text

        # Check if response suggests actions
        suggested_actions = []
        if request.mode == "research" and "investigate" in assistant_message.lower():
            suggested_actions.append({
                "type": "investigate",
                "endpoint": "/api/investigate",
                "description": "Run full investigation"
            })
        if request.mode == "fill" and "section" in assistant_message.lower():
            suggested_actions.append({
                "type": "fill_section",
                "endpoint": "/api/edith/compose",
                "description": "Fill section from template"
            })

        return {
            "response": assistant_message,
            "mode": request.mode,
            "document_id": request.document_id,
            "suggested_actions": suggested_actions,
            "model": "claude-sonnet-4-5-20250929"
        }

    except Exception as e:
        logger.error(f"C0GN1T0 error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cognito/templates")
async def cognito_templates():
    """Get available EDITH templates for C0GN1T0."""
    from pathlib import Path

    templates_dir = Path("/data/EDITH/templates")

    genres = []
    jurisdictions = []
    sections = []

    try:
        genres_dir = templates_dir / "genres"
        if genres_dir.exists():
            genres = [f.stem.replace(".skill", "") for f in genres_dir.glob("*.skill.md")]

        jurisdictions_dir = templates_dir / "jurisdictions"
        if jurisdictions_dir.exists():
            jurisdictions = [f.stem.replace(".skill", "") for f in jurisdictions_dir.glob("*.skill.md")]

        sections_dir = templates_dir / "sections"
        if sections_dir.exists():
            sections = [f.stem for f in sections_dir.glob("*.md")]

    except Exception as e:
        logger.warning(f"Template scan error: {e}")

    return {
        "genres": sorted(genres)[:31],
        "jurisdictions": sorted(jurisdictions)[:217],
        "sections": sorted(sections),
        "total": {
            "genres": len(genres),
            "jurisdictions": len(jurisdictions),
            "sections": len(sections)
        }
    }


@app.get("/api/orchestrator/status")
async def orchestrator_status():
    """Get orchestrator status and capabilities."""
    orchestrator = get_orchestrator()
    runner = get_multi_agent_runner()

    return {
        "orchestrator_available": orchestrator is not None,
        "multi_agent_available": runner is not None,
        "anthropic_key_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
        "capabilities": {
            "investigate": "Full autonomous investigation via ThinOrchestrator",
            "multi_agent": "Multi-agent loop (Orchestrator→Investigator→Disambiguator→Writer)",
            "gap_analysis": "Cognitive gap detection in 4 modes",
            "stream": "SSE streaming of investigation events"
        },
        "phases": [
            "ROUTING", "COMPLEXITY", "CONTEXT", "WATCHER_SETUP",
            "EXECUTION", "VALIDATION", "COMPLETE"
        ],
        "cognitive_modes": ["NARRATIVE", "SUBJECT", "LOCATION", "NEXUS"]
    }


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "SASTRE Orchestrator Service",
        "version": "1.0.0",
        "port": 8201,
        "role": "CONTROL LAYER (autonomous investigation)",
        "data_layer": "http://localhost:8200 (enrichment_server_v3)"
    }


@app.get("/health")
async def health():
    # Check CognitiveEngine
    cognitive_available = False
    try:
        from SASTRE.grid.cognitive_engine import CognitiveEngine
        cognitive_available = True
    except:
        pass

    # Check EDITH templates
    from pathlib import Path
    templates_available = Path("/data/EDITH/templates/genres").exists()

    return {
        "status": "healthy",
        "orchestrator": get_orchestrator() is not None,
        "multi_agent": get_multi_agent_runner() is not None,
        "cognitive_engine": cognitive_available,
        "cognito": True,  # C0GN1T0 endpoint available
        "edith_templates": templates_available,
        "anthropic_key": bool(os.getenv("ANTHROPIC_API_KEY"))
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8201)
