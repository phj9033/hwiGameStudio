# hwire

AI 기반 게임 개발 자동화 플랫폼. 여러 AI CLI 에이전트(Claude Code, Codex 등)를 오케스트레이션하여 게임 개발 워크플로우를 관리합니다.

## 주요 기능

- **프로젝트 관리** — Godot/Unity/Unreal 프로젝트 생성, 동결(freeze), 재개(resume), 초기화(startover) 등 라이프사이클 관리
- **티켓 기반 태스크 관리** — 칸반 보드 스타일의 티켓 시스템 (open → assigned → running → completed)
- **AI 자동 분해** — 자연어 설명을 구조화된 티켓과 실행 단계로 자동 분해
- **파이프라인 실행** — 순차/병렬 에이전트 실행, 실패 시 재시도, 실행 중 취소 지원
- **문서 변경 감지** — 문서 업데이트 시 diff를 분석하여 관련 티켓 자동 생성
- **에이전트 관리** — 마크다운 기반 에이전트 정의, 웹 UI에서 편집 가능
- **비용 모니터링** — 프로젝트/에이전트별 토큰 사용량 및 비용 추적

## 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| Frontend | Streamlit 1.38 |
| Backend | FastAPI 0.115 + Uvicorn |
| Database | SQLite (WAL 모드) |
| Language | Python 3.11+ |
| Container | Docker Compose |
| AI CLI | Claude Code, Codex |

## 프로젝트 구조

```
hwire/
├── backend/                # FastAPI REST API 서버
│   ├── main.py             # 앱 초기화, 미들웨어, 라우터
│   ├── config.py           # 환경 변수 설정
│   ├── database.py         # SQLite 스키마 및 연결 관리
│   ├── models/             # Pydantic 스키마
│   ├── routes/             # API 엔드포인트 핸들러
│   ├── services/           # 핵심 비즈니스 로직
│   └── prompts/            # AI 프롬프트 템플릿
├── frontend/               # Streamlit 웹 UI
│   ├── app.py              # 메인 엔트리포인트
│   ├── api_client.py       # 백엔드 API 호출 래퍼
│   ├── pages/              # 멀티페이지 앱 (대시보드, 티켓보드 등)
│   └── components/         # 재사용 UI 컴포넌트
├── agents/                 # AI 에이전트 정의 (마크다운)
├── data/                   # 런타임 데이터 (SQLite DB)
├── tests/                  # 테스트 스위트
├── docker-compose.yml      # 컨테이너 오케스트레이션
├── Dockerfile.backend
└── Dockerfile.frontend
```

## 설치 및 실행

### 방법 1: Docker Compose (권장)

```bash
# 1. 환경 변수 설정
cp .env.example .env
# .env 파일에 API 키 입력

# 2. 빌드 및 실행
docker-compose up --build
```

- Frontend: http://localhost:8501
- Backend API: http://localhost:8000

### 방법 2: 로컬 개발 환경 (가상환경)

터미널 두 개가 필요합니다.

**가상환경 생성 및 패키지 설치 (최초 1회):**

```bash
cd /path/to/hwire
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt -r frontend/requirements.txt
```

**터미널 1 — Backend:**

```bash
cd /path/to/hwire
source venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

**터미널 2 — Frontend:**

```bash
cd /path/to/hwire
source venv/bin/activate
streamlit run frontend/app.py
```

## 환경 변수

`.env.example`을 `.env`로 복사한 뒤 값을 설정합니다.

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `ANTHROPIC_API_KEY` | Claude API 키 | — |
| `OPENAI_API_KEY` | OpenAI API 키 | — |
| `DATABASE_PATH` | SQLite DB 경로 | `./data/studio.db` |
| `BACKEND_URL` | 백엔드 URL | `http://localhost:8000` |
| `AGENTS_DIR` | 에이전트 정의 디렉토리 | `./agents` |
| `PROJECTS_DIR` | 프로젝트 디렉토리 | `./projects` |

## 사용법

### 1. 프로젝트 생성

대시보드에서 새 프로젝트를 생성합니다. 게임 엔진(Godot/Unity/Unreal)과 개발 모드(design/prototype/development)를 선택합니다.

### 2. 에이전트 설정

Settings 페이지에서 CLI 프로바이더(Claude, Codex)를 활성화하고, Agents 페이지에서 에이전트 마크다운을 편집합니다.

### 3. 티켓 생성

- **수동 생성** — 티켓 제목, 설명, 실행 파이프라인(단계별 에이전트)을 직접 구성
- **AI 자동 생성** — 자연어로 작업을 설명하면 AI가 티켓과 실행 단계를 자동 분해
- **문서 변경 기반** — 문서 업데이트 시 변경 내용을 분석하여 관련 티켓 자동 생성

### 4. 파이프라인 실행

티켓의 Run 버튼을 클릭하면 정의된 파이프라인이 실행됩니다:
- 각 단계(step)는 순차적으로 실행
- 단계 내 에이전트들은 병렬 실행 가능
- 실행 중 취소, 실패 시 재시도 지원

### 5. 결과 확인 및 비용 모니터링

칸반 보드에서 실행 결과를 확인하고, Usage 페이지에서 프로젝트/에이전트별 토큰 사용량과 비용을 확인합니다.

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/health` | 서버 상태 확인 |
| `GET/POST` | `/api/projects` | 프로젝트 목록 조회 / 생성 |
| `POST` | `/api/projects/{id}/freeze` | 프로젝트 동결 |
| `POST` | `/api/projects/{id}/resume` | 프로젝트 재개 |
| `GET/POST` | `/api/tickets` | 티켓 목록 조회 / 생성 |
| `POST` | `/api/tickets/{id}/run` | 파이프라인 실행 |
| `POST` | `/api/tickets/{id}/cancel` | 실행 취소 |
| `POST` | `/api/tickets/{id}/retry` | 실패 단계 재시도 |
| `POST` | `/api/tickets/from-diff` | 문서 변경으로 티켓 생성 |
| `GET/PUT` | `/api/agents/{name}` | 에이전트 조회 / 수정 |
| `GET` | `/api/usage/summary` | 전체 비용 요약 |
| `GET` | `/api/usage/by-project` | 프로젝트별 비용 |

모든 목록 API는 `page`, `per_page` 파라미터로 페이지네이션을 지원합니다.

## 테스트

```bash
source venv/bin/activate
pip install -r backend/requirements.txt
pytest tests/ -v
```

## 아키텍처

```
┌─────────────┐     HTTP      ┌──────────────┐     subprocess     ┌───────────┐
│  Streamlit  │ ────────────> │   FastAPI    │ ─────────────────> │ Claude    │
│  Frontend   │ <──────────── │   Backend    │ <───────────────── │ Codex     │
└─────────────┘               └──────┬───────┘                    └───────────┘
                                     │
                                     v
                              ┌──────────────┐
                              │   SQLite DB  │
                              │  (WAL mode)  │
                              └──────────────┘
```

Frontend(Streamlit)가 Backend(FastAPI)에 REST API로 요청을 보내고, Backend는 AI CLI 도구를 subprocess로 실행하여 결과를 수집합니다. 모든 상태는 SQLite에 저장되며, WAL 모드로 동시 접근을 지원합니다.
