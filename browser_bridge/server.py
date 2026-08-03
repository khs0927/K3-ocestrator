from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.security import verify_bearer

from .config import settings
from .profiles import load_profiles
from .runtime import BrowserChatRuntime

settings.prepare()
profiles = load_profiles(settings.browser_bridge_profiles_file)
runtimes = {
    profile.model: BrowserChatRuntime(
        profile,
        settings.browser_bridge_data_dir,
        headless=settings.browser_bridge_headless,
    )
    for profile in profiles.values()
}


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    stream: bool = False


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.browser_bridge_api_key and settings.browser_bridge_host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("BROWSER_BRIDGE_API_KEY is required outside loopback")
    try:
        yield
    finally:
        for runtime in runtimes.values():
            await runtime.close()


app = FastAPI(title="Personal Web Advisory Bridge", version="0.1.0", lifespan=lifespan)


def auth(authorization: str | None) -> None:
    if not verify_bearer(authorization, settings.browser_bridge_api_key):
        raise HTTPException(status_code=401, detail="Invalid browser bridge key")


@app.get("/health")
async def health(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    auth(authorization)
    return {"status": "ok", "models": list(runtimes)}


@app.get("/v1/models")
async def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    auth(authorization)
    return {"object": "list", "data": [{"id": model, "object": "model"} for model in runtimes]}


@app.post("/v1/chat/completions")
async def chat(request: ChatRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    auth(authorization)
    if request.stream:
        raise HTTPException(status_code=400, detail="Browser advisory streaming is not supported")
    runtime = runtimes.get(request.model)
    if runtime is None:
        raise HTTPException(status_code=404, detail=f"Unknown browser model: {request.model}")
    prompt = "\n\n".join(f"[{m.role.upper()}]\n{m.content}" for m in request.messages if m.content.strip())
    try:
        text = await runtime.chat(prompt)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "id": f"browser-{request.model}",
        "object": "chat.completion",
        "model": request.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


if __name__ == "__main__":
    uvicorn.run("browser_bridge.server:app", host=settings.browser_bridge_host, port=settings.browser_bridge_port)
