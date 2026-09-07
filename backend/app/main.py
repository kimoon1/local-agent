import asyncio
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus, urlparse

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Local Web Agent API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    role: str
    content: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    history: list[Message] = Field(default_factory=list)
    base_url: str = "http://localhost:1234/v1"
    model: str = "local-model"
    temperature: float = Field(default=0.2, ge=0, le=2)


class ModelsRequest(BaseModel):
    base_url: str = "http://localhost:1234/v1"


def validate_lm_studio_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(400, "LM Studio 주소는 localhost 주소만 허용됩니다.")
    return base_url.rstrip("/")


async def search_web(query: str) -> list[dict[str, str]]:
    """Search Bing's public RSS endpoint; no separate search API key is needed."""
    url = f"https://www.bing.com/search?format=rss&q={quote_plus(query)}"
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "LocalWebAgent/1.0"})
            response.raise_for_status()
        root = ET.fromstring(response.text)
    except (httpx.HTTPError, ET.ParseError) as error:
        raise HTTPException(502, f"웹 검색에 실패했습니다: {error}") from error

    sources = []
    for item in root.findall("./channel/item")[:6]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = re.sub(r"<[^>]+>", " ", item.findtext("description") or "").strip()
        if title and link:
            sources.append({"title": title, "url": link, "snippet": description})
    return sources


async def get_loaded_models(base_url: str) -> list[dict[str, str]]:
    """Return the model IDs exposed by LM Studio's OpenAI-compatible API."""
    base_url = validate_lm_studio_url(base_url)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{base_url}/models")
            response.raise_for_status()
            raw_models = response.json().get("data", [])
    except (httpx.HTTPError, ValueError, AttributeError) as error:
        raise HTTPException(502, f"LM Studio 모델 목록을 읽지 못했습니다: {error}") from error
    return [
        {"id": item["id"], "object": item.get("object", "model")}
        for item in raw_models
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]
    ]


def make_system_prompt(sources: list[dict[str, str]]) -> str:
    evidence = "\n\n".join(
        f"[{index}] {source['title']}\n{source['snippet']}\nURL: {source['url']}"
        for index, source in enumerate(sources, 1)
    ) or "검색 결과가 없습니다. 검색되지 않았다는 점을 명확히 밝히세요."
    return f"""당신은 최신 웹 정보를 바탕으로 답하는 AI 에이전트입니다.
답변은 한국어로 작성하세요. 아래 검색 근거 안에서만 사실을 판단하고, 최신성이 불확실하면 한계를 밝혀 주세요.
사실 주장 뒤에는 반드시 [1]처럼 출처 번호를 붙이세요. 근거에 없는 내용을 사실처럼 추측하지 마세요.

검색 근거:
{evidence}"""


async def query_lm_studio(request: ChatRequest, sources: list[dict[str, str]]) -> str:
    base_url = validate_lm_studio_url(request.base_url)
    model = request.model.strip()
    if not model:
        # LM Studio requires the loaded model's identifier. Resolve it instead
        # of relying on the legacy "local-model" placeholder.
        models = await get_loaded_models(base_url)
        model = next((item["id"] for item in models), "")
        if not model:
            raise HTTPException(400, "LM Studio에 로드된 모델이 없습니다. 모델을 로드한 뒤 Start Server를 누르세요.")
    history = [message.model_dump() for message in request.history[-10:] if message.role in {"user", "assistant"}]
    messages = [{"role": "system", "content": make_system_prompt(sources)}, *history,
                {"role": "user", "content": request.question.strip()}]
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                json={"model": model, "messages": messages,
                      "temperature": request.temperature, "stream": False},
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise ValueError(str(payload["error"]))
            answer = payload["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
        raise HTTPException(502, f"LM Studio 요청에 실패했습니다: {error}") from error
    if not answer:
        raise HTTPException(502, "LM Studio가 빈 응답을 반환했습니다.")
    return answer


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/models")
async def models(request: ModelsRequest) -> dict:
    return {"models": await get_loaded_models(request.base_url)}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict:
    sources = await search_web(request.question)
    answer = await query_lm_studio(request, sources)
    return {"answer": answer, "sources": sources}
