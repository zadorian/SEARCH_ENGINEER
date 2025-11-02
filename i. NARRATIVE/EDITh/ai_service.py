#!/usr/bin/env python3
"""
FastAPI service for AI operations in EDITh
Replaces the spawn-based Python script approach with a persistent service
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

# Import existing processors
from ai_command_processor_v2 import SmartCommandProcessor
try:
    from ai_chat_processor import process_chat
except ImportError:
    async def process_chat(message: str, context: dict):
        return "Chat processor not available."
try:
    from CommandAnalyzer import CommandAnalyzer
except ImportError:
    class CommandAnalyzer:
        def analyzeCommand(self, command: str, document_info: dict):
            return {"intent": "general", "confidence": 0.5}
try:
    from ModelScheduler import ModelScheduler
except ImportError:
    class ModelScheduler:
        def get_available_models(self):
            return ["gpt-5-mini", "gpt-5-thinking", "claude-sonnet-4-1m", "gemini-2.0-flash"]

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
smart_processor = None
command_analyzer = None
model_scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup"""
    global smart_processor, command_analyzer, model_scheduler
    
    logger.info("Starting AI service...")
    
    # Initialize processors
    smart_processor = SmartCommandProcessor()
    command_analyzer = CommandAnalyzer()
    model_scheduler = ModelScheduler()
    
    logger.info("AI service initialized successfully")
    yield
    
    # Cleanup on shutdown
    logger.info("Shutting down AI service...")

app = FastAPI(
    title="EDITh AI Service",
    description="Persistent AI processing service for EDITh document editor",
    version="1.0.0",
    lifespan=lifespan
)

# Request models
class EditRequest(BaseModel):
    command: str
    context: Dict[str, Any]
    session_id: Optional[str] = None
    streaming: bool = True

class ChatRequest(BaseModel):
    message: str
    context: Dict[str, Any]
    session_id: Optional[str] = None

class AnalyzeRequest(BaseModel):
    command: str
    document_info: Dict[str, Any]

class HealthResponse(BaseModel):
    status: str
    services: Dict[str, str]

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        services={
            "smart_processor": "ready" if smart_processor else "not_ready",
            "command_analyzer": "ready" if command_analyzer else "not_ready",
            "model_scheduler": "ready" if model_scheduler else "not_ready"
        }
    )

@app.post("/api/v1/edit")
async def handle_edit(request: EditRequest):
    """Handle AI edit requests with streaming support"""
    if not smart_processor:
        raise HTTPException(status_code=503, detail="Smart processor not ready")
    
    try:
        if request.streaming:
            # Return streaming response
            async def generate_stream():
                async for chunk in smart_processor.process_stream(
                    request.command,
                    request.context,
                    request.session_id
                ):
                    yield f"data: {json.dumps(chunk)}\n\n"
                yield "data: [DONE]\n\n"
            
            return StreamingResponse(
                generate_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*"
                }
            )
        else:
            # Return single response
            result = await smart_processor.process_command(
                request.command,
                request.context,
                request.session_id
            )
            return {"result": result}
    
    except Exception as e:
        logger.error(f"Edit processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/chat")
async def handle_chat(request: ChatRequest):
    """Handle non-edit chat requests"""
    try:
        result = await process_chat(request.message, request.context)
        return {"result": result}
    
    except Exception as e:
        logger.error(f"Chat processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/analyze")
async def analyze_command(request: AnalyzeRequest):
    """Analyze command to determine processing strategy"""
    if not command_analyzer:
        raise HTTPException(status_code=503, detail="Command analyzer not ready")
    
    try:
        analysis = command_analyzer.analyzeCommand(
            request.command,
            request.document_info
        )
        return {"analysis": analysis}
    
    except Exception as e:
        logger.error(f"Command analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/models")
async def get_available_models():
    """Get list of available AI models"""
    if not model_scheduler:
        raise HTTPException(status_code=503, detail="Model scheduler not ready")
    
    try:
        models = model_scheduler.get_available_models()
        return {"models": models}
    
    except Exception as e:
        logger.error(f"Model listing error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/session/{session_id}/clear")
async def clear_session(session_id: str):
    """Clear session data"""
    try:
        if smart_processor:
            smart_processor.clear_session(session_id)
        return {"status": "cleared"}
    
    except Exception as e:
        logger.error(f"Session clear error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "ai_service:app",
        host="127.0.0.1",
        port=8001,
        reload=True,
        log_level="info"
    )