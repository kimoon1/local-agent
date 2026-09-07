# Local Web Agent

LM Studio의 로컬 LLM이 최신 웹 검색 결과를 근거로 답하는 에이전트입니다. 프론트엔드는 Next.js, 검색·모델 연결 백엔드는 Python FastAPI로 구성했습니다.

## 실행

LM Studio에서 채팅 모델을 로드하고 `Developer` 탭에서 서버를 시작한 다음, 각각의 터미널에서 실행합니다.

```powershell
# 터미널 1: FastAPI
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

```powershell
# 터미널 2: Next.js
cd frontend
npm install
npm run dev
```

`http://localhost:3000`을 여세요. 기본 LM Studio 주소는 `http://localhost:1234/v1`이며, 화면의 **연결 설정**에서 모델 목록을 새로고침하고 `openai/gpt-oss-20b`를 선택할 수 있습니다.

> 이전 버전의 화면(`http://localhost:3333`)은 더 이상 사용하지 않습니다. FastAPI와 Next.js를 실행한 뒤 `http://localhost:3000`으로 접속하세요. API 토큰이 필요한 경우 연결 설정에서 입력합니다. 토큰은 현재 화면 메모리에만 유지됩니다.

### LM Studio 연결 문제

- LM Studio의 **Developer** 화면에서 모델을 먼저 로드하고 서버를 시작하세요.
- API 주소는 `http://localhost:1234/v1`이어야 합니다. 주소 끝에 `/chat/completions`를 붙이지 마세요.
- `POST /v1/chat/completions`는 LM Studio의 공식 OpenAI 호환 엔드포인트입니다. 이 경로를 "Unexpected endpoint"로 표시하는 구버전 서버라면 LM Studio를 최신 버전으로 업데이트하세요.

## 구조

`Next.js UI → Next.js /api/chat 프록시 → FastAPI → Bing RSS + DuckDuckGo 검색 → LM Studio OpenAI 호환 API`

FastAPI는 중복 제거·정렬된 검색 결과 최대 8개를 모델에 전달합니다. 답변에 검색어·엔진·결과 수와 출처를 표시합니다. 현재 검색 과정은 최종 응답 후 표시되며 실시간 스트리밍은 구현되지 않았습니다. 중요한 사실의 정확성은 원문 대조가 필요합니다.

## Codex AI-DLC

이 폴더를 Codex 프로젝트 루트로 여세요. 프로젝트 규칙은 `aidlc/spaces/default/memory/project.md`,
작업 상태와 감사 기록은 `aidlc/spaces/default/intents/`에 있습니다.
Codex CLI 0.145.0 이상과 Bun이 필요합니다. 이 PC는 0.153.4 / 1.4.2로 준비됐습니다.
새 PC에서는 프로젝트 및 훅 신뢰를 직접 확인해야 합니다.

```powershell
bun .codex/tools/aidlc-utility.ts doctor
```

Codex 대화창에서 `$aidlc --status`, `$aidlc --resume`으로 확인/재개합니다.
PowerShell에 스킬 호출을 직접 입력하지 않습니다.

[오늘의 작업 기록과 미해결 사항](docs/handoff-2026-09-07.md)을 먼저 확인하세요.
