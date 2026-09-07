import asyncio
import html
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

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
    api_key: str | None = Field(default=None, max_length=500)


class ModelsRequest(BaseModel):
    base_url: str = "http://localhost:1234/v1"
    api_key: str | None = Field(default=None, max_length=500)


def validate_lm_studio_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(400, "LM Studio 주소는 localhost 주소만 허용됩니다.")
    return base_url.rstrip("/")


def make_search_queries(question: str) -> list[str]:
    """Produce explicit, domain-aware search queries that are shown to the user."""
    normalized = re.sub(r"\s+", " ", question.lower()).strip()
    is_t1_lol = ("skt t1" in normalized or ("skt" in normalized and "t1" in normalized) or "t1" in normalized) and (
        "롤" in normalized or "lol" in normalized or "league of legends" in normalized
    )
    if is_t1_lol:
        return [
            "T1 League of Legends recent 5 matches results",
            "T1 League of Legends match history Liquipedia",
            "T1 롤 최근 5경기 결과",
            "site:escharts.com/matches T1 League of Legends recent matches",
        ]
    return [question.strip()]


async def search_bing_rss(query: str) -> list[dict[str, str]]:
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


def strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def unwrap_duckduckgo_url(value: str) -> str:
    url = html.unescape(value)
    if url.startswith("//"):
        url = f"https:{url}"
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc:
        destination = parse_qs(parsed.query).get("uddg", [""])[0]
        if destination:
            return unquote(destination)
    return url


def needs_primary_evidence(question: str) -> bool:
    normalized = question.lower()
    return any(term in normalized for term in ("최근", "latest", "경기", "결과", "전적", "score", "match", "schedule"))


async def fetch_source_evidence(source: dict[str, str]) -> str:
    """Fetch a small plain-text excerpt from a result page for fact-sensitive answers."""
    parsed = urlparse(source["url"])
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return ""
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            response = await client.get(source["url"], headers={"User-Agent": "Mozilla/5.0 LocalWebAgent/1.0"})
            response.raise_for_status()
        if "html" not in response.headers.get("content-type", "").lower():
            return ""
        text = strip_html(response.text)
        return text[:6000] if len(text) > 250 else ""
    except httpx.HTTPError:
        return ""


async def enrich_with_primary_evidence(sources: list[dict[str, str]]) -> list[dict[str, str]]:
    excerpts = await asyncio.gather(*(fetch_source_evidence(source) for source in sources[:4]))
    for source, excerpt in zip(sources, excerpts):
        if excerpt:
            source["evidence"] = excerpt
    return sources


async def search_duckduckgo(query: str) -> list[dict[str, str]]:
    """A second, public search index to improve coverage of esports result pages."""
    url = f"https://html.duckduckgo.com/html/?kl=kr-ko&q={quote_plus(query)}"
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0 LocalWebAgent/1.0"})
            response.raise_for_status()
        document = response.text
    except httpx.HTTPError as error:
        raise RuntimeError(f"DuckDuckGo 검색 실패: {error}") from error

    results = []
    # DuckDuckGo's HTML and Lite surfaces use either result__a or result-link.
    for anchor in re.finditer(r"<a\b(?P<attrs>[^>]*)>(?P<title>[\s\S]*?)</a>", document, re.IGNORECASE):
        attrs = anchor.group("attrs")
        if not re.search(r"class=[\"'][^\"']*(?:result__a|result-link)[^\"']*[\"']", attrs, re.IGNORECASE):
            continue
        href_match = re.search(r"href=[\"'](?P<href>[^\"']+)[\"']", attrs, re.IGNORECASE)
        if not href_match:
            continue
        title = strip_html(anchor.group("title"))
        link = unwrap_duckduckgo_url(href_match.group("href"))
        nearby_html = document[anchor.end():anchor.end() + 2500]
        snippet_match = re.search(r"class=[\"'][^\"']*result__snippet[^\"']*[\"'][^>]*>([\s\S]*?)</(?:a|div)", nearby_html, re.IGNORECASE)
        snippet = strip_html(snippet_match.group(1)) if snippet_match else ""
        if title and link.startswith(("http://", "https://")):
            results.append({"title": title, "url": link, "snippet": snippet})
        if len(results) == 6:
            break
    return results


async def search_web(question: str) -> tuple[list[dict[str, str]], list[dict[str, str | int]]]:
    queries = make_search_queries(question)
    planned_searches = [
        (provider, query, search_fn(query))
        for query in queries
        for provider, search_fn in (("Bing RSS", search_bing_rss), ("DuckDuckGo", search_duckduckgo))
    ]
    outcomes = await asyncio.gather(*(search for _, _, search in planned_searches), return_exceptions=True)
    trace: list[dict[str, str | int]] = []
    sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for (provider, query, _), outcome in zip(planned_searches, outcomes):
        if isinstance(outcome, Exception):
            trace.append({"provider": provider, "query": query, "result_count": 0, "status": "실패"})
            continue
        trace.append({"provider": provider, "query": query, "result_count": len(outcome), "status": "완료"})
        for source in outcome:
            if source["url"] not in seen_urls:
                seen_urls.add(source["url"])
                sources.append(source)

    # Search pages can contain unrelated promoted results. For the T1 LoL intent,
    # prefer actual esports/match sources over SK Telecom references.
    if len(queries) > 1:
        relevant_terms = ("t1", "league", "lol", "롤", "lck", "match", "esports", "game", "경기", "result", "history", "전적")
        match_domains = ("liquipedia.net", "lol.fandom.com", "gol.gg", "escharts.com", "gamesoflegends", "scorebase")
        def relevance(source: dict[str, str]) -> int:
            text = f"{source['title']} {source['snippet']}".lower()
            domain_bonus = 5 if any(domain in source["url"].lower() for domain in match_domains) else 0
            return domain_bonus + sum(term in text for term in relevant_terms)
        sources.sort(key=relevance, reverse=True)

    if not sources:
        raise HTTPException(502, "웹 검색 결과를 가져오지 못했습니다. 잠시 후 다시 시도하세요.")
    final_sources = sources[:8]
    if needs_primary_evidence(question):
        final_sources = await enrich_with_primary_evidence(final_sources)
    return final_sources, trace


def lm_studio_headers(api_key: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key.strip()}"} if api_key and api_key.strip() else {}


async def get_loaded_models(base_url: str, api_key: str | None = None) -> list[dict[str, str]]:
    """Return the model IDs exposed by LM Studio's OpenAI-compatible API."""
    base_url = validate_lm_studio_url(base_url)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{base_url}/models", headers=lm_studio_headers(api_key))
            response.raise_for_status()
            raw_models = response.json().get("data", [])
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 401:
            raise HTTPException(401, "LM Studio API 토큰이 필요합니다. 연결 설정에 토큰을 입력하세요.") from error
        raise HTTPException(502, f"LM Studio 모델 목록을 읽지 못했습니다: HTTP {error.response.status_code}") from error
    except (httpx.HTTPError, ValueError, AttributeError) as error:
        raise HTTPException(502, f"LM Studio 모델 목록을 읽지 못했습니다: {error}") from error
    return [
        {"id": item["id"], "object": item.get("object", "model")}
        for item in raw_models
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]
    ]


def make_system_prompt(sources: list[dict[str, str]]) -> str:
    evidence = "\n\n".join(
        f"[{index}] {source['title']}\n검색 요약: {source['snippet']}\n"
        f"본문 발췌: {source.get('evidence', '(본문 확인 실패)')}\nURL: {source['url']}"
        for index, source in enumerate(sources, 1)
    ) or "검색 결과가 없습니다. 검색되지 않았다는 점을 명확히 밝히세요."
    return f"""당신은 최신 웹 정보를 바탕으로 답하는 AI 에이전트입니다.
답변은 한국어로 작성하세요. 아래 검색 근거 안에서만 사실을 판단하고, 최신성이 불확실하면 한계를 밝혀 주세요.
사실 주장 뒤에는 반드시 [1]처럼 출처 번호를 붙이세요. 근거에 없는 내용을 사실처럼 추측하지 마세요.
특히 경기 날짜·상대·스코어·최근 N경기 표는 반드시 아래 '검색 요약' 또는 '본문 발췌'에 그 값이 정확히 있을 때만 작성하세요.
URL 제목이나 팀 소개만으로 경기 결과를 만들면 안 됩니다. 검증 가능한 결과가 부족하면 표를 만들지 말고 '검색된 근거만으로 최근 경기 결과를 확정할 수 없다'고 답하세요.

검색 근거:
{evidence}"""


async def query_lm_studio(request: ChatRequest, sources: list[dict[str, str]]) -> str:
    base_url = validate_lm_studio_url(request.base_url)
    model = request.model.strip()
    if not model:
        # LM Studio requires the loaded model's identifier. Resolve it instead
        # of relying on the legacy "local-model" placeholder.
        models = await get_loaded_models(base_url, request.api_key)
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
                headers=lm_studio_headers(request.api_key),
                json={"model": model, "messages": messages,
                      "temperature": request.temperature, "stream": False},
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise ValueError(str(payload["error"]))
            answer = payload["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 401:
            raise HTTPException(401, "LM Studio API 토큰이 필요합니다. 연결 설정에 토큰을 입력하세요.") from error
        raise HTTPException(502, f"LM Studio 요청에 실패했습니다: HTTP {error.response.status_code}") from error
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
    return {"models": await get_loaded_models(request.base_url, request.api_key)}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict:
    sources, search_trace = await search_web(request.question)
    answer = await query_lm_studio(request, sources)
    return {"answer": answer, "sources": sources, "search_trace": search_trace}
