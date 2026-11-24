"""
R34PER chat server: FastAPI backend serving the chat UI and streaming the
agent loop to the browser over Server-Sent Events.
"""
import json
import uuid

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import agent

app = FastAPI(title="R34PER Agent")

SESSIONS = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    reset: bool = False


def _sse(obj) -> str:
    return "data: " + json.dumps(obj, default=str) + "\n\n"


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "model": agent.MODEL,
        "workdir": str(agent.WORKDIR),
        "api_key_set": bool(agent.VENICE_API_KEY),
    }


@app.post("/api/chat")
def chat(req: ChatRequest):
    sid = req.session_id or uuid.uuid4().hex
    if req.reset:
        SESSIONS[sid] = []
    if sid not in SESSIONS:
        SESSIONS[sid] = []

    def gen():
        yield _sse({"type": "session", "session_id": sid})
        try:
            for event in agent.run_agent_stream(req.message, SESSIONS[sid]):
                yield _sse(event)
        except Exception as exc:
            yield _sse({"type": "error", "content": "Server error: " + str(exc)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/clear")
def clear(req: ChatRequest):
    SESSIONS.pop(req.session_id or "", None)
    return {"ok": True}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
