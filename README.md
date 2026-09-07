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

`http://localhost:3000`을 여세요. 기본 LM Studio 주소는 `http://localhost:1234/v1`이며, 화면의 **연결 설정**에서 모델 ID를 설정할 수 있습니다.

> 이전 버전의 화면(`http://localhost:3333`)은 더 이상 사용하지 않습니다. FastAPI와 Next.js를 실행한 뒤 반드시 `http://localhost:3000`으로 접속하세요. 모델 ID를 비워 두면 백엔드가 LM Studio의 `/v1/models`에서 현재 로드한 모델을 자동으로 선택합니다.

### LM Studio 연결 문제

- LM Studio의 **Developer** 화면에서 모델을 먼저 로드하고 서버를 시작하세요.
- API 주소는 `http://localhost:1234/v1`이어야 합니다. 주소 끝에 `/chat/completions`를 붙이지 마세요.
- `POST /v1/chat/completions`는 LM Studio의 공식 OpenAI 호환 엔드포인트입니다. 이 경로를 "Unexpected endpoint"로 표시하는 구버전 서버라면 LM Studio를 최신 버전으로 업데이트하세요.

## 구조

`Next.js UI → Next.js /api/chat 프록시 → FastAPI → Bing RSS 검색 + LM Studio OpenAI 호환 API`

FastAPI는 검색 결과 최대 6개를 프롬프트에 주입하고, 로컬 모델이 출처 번호를 붙여 답하도록 지시합니다. LM Studio 주소는 `localhost`만 허용합니다.
