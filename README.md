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
- **보안** — CLI 출력 시크릿 자동 마스킹, Docker non-root 사용자 실행

## 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| Frontend | Streamlit 1.38 |
| Backend | FastAPI 0.115 + Uvicorn 0.30 |
| Database | SQLite (WAL 모드) + aiosqlite 0.20 |
| Language | Python 3.11+ |
| Container | Docker Compose |
| AI CLI | Claude Code, OpenAI Codex |

## 프로젝트 구조

```
hwire/
├── backend/                          # FastAPI REST API 서버
│   ├── main.py                       # 앱 초기화, CORS, 라이프사이클, 라우터 등록
│   ├── config.py                     # 환경 변수 설정
│   ├── database.py                   # SQLite 스키마, 시드 데이터, 연결 관리
│   ├── models/                       # Pydantic 스키마
│   │   ├── common.py                 # PaginatedResponse
│   │   ├── project.py                # Project CRUD 모델
│   │   ├── ticket.py                 # Ticket/Step/Agent 모델
│   │   ├── document.py               # Document 모델
│   │   └── provider.py               # CLI Provider/CostRate 모델
│   ├── routes/                       # API 엔드포인트 핸들러
│   │   ├── projects.py               # 프로젝트 CRUD + freeze/resume/startover
│   │   ├── tickets.py                # 티켓 CRUD + decompose/run/cancel/retry
│   │   ├── agents.py                 # 에이전트 목록/조회/수정 + 실행 이력
│   │   ├── runs.py                   # 에이전트 실행 상세 + 결과 파일 조회
│   │   ├── usage.py                  # 사용량 요약 (전체/프로젝트별/에이전트별)
│   │   ├── providers.py              # 프로바이더 설정 + 비용 단가
│   │   └── documents.py              # 문서 CRUD + diff 생성
│   ├── services/                     # 핵심 비즈니스 로직
│   │   ├── cli_runner.py             # AI CLI 서브프로세스 실행기
│   │   ├── pipeline_executor.py      # 티켓 파이프라인 오케스트레이터
│   │   ├── ticket_analyzer.py        # AI 분해 및 diff 분석
│   │   ├── prompt_builder.py         # 프롬프트 템플릿 구성
│   │   ├── token_parser.py           # 토큰 수 추출 파서
│   │   └── output_sanitizer.py       # CLI 출력 시크릿 마스킹
│   └── prompts/                      # AI 프롬프트 템플릿
│       ├── decompose_task.md         # 태스크 분해 프롬프트
│       └── analyze_diff.md           # diff 분석 프롬프트
├── frontend/                         # Streamlit 웹 UI
│   ├── app.py                        # 메인 엔트리포인트
│   ├── api_client.py                 # 백엔드 HTTP 클라이언트
│   ├── pages/                        # 멀티페이지 앱
│   │   ├── 1_dashboard.py            # 프로젝트 목록 및 생성
│   │   ├── 2_project_detail.py       # 프로젝트 상세/편집/상태관리
│   │   ├── 3_ticket_board.py         # 칸반 보드 (상태별 컬럼)
│   │   ├── 4_ticket_create.py        # 수동/AI 자동 티켓 생성
│   │   ├── 5_agents.py               # 에이전트 편집 및 실행 이력
│   │   ├── 6_usage.py                # 사용량 및 비용 모니터링
│   │   └── 7_settings.py             # CLI 프로바이더 및 단가 설정
│   └── components/                   # 재사용 UI 컴포넌트
│       ├── pipeline_editor.py        # 단계/에이전트 파이프라인 빌더
│       └── result_viewer.py          # 실행 결과 표시
├── agents/                           # AI 에이전트 정의 (마크다운, 한글)
├── tests/                            # 테스트 스위트
├── docker-compose.yml                # 컨테이너 오케스트레이션
├── Dockerfile.backend                # 백엔드 컨테이너
├── Dockerfile.frontend               # 프론트엔드 컨테이너
└── entrypoint.sh                     # Docker 권한 설정 스크립트
```

## 에이전트 구성

20종의 게임 개발 전문 에이전트가 `agents/` 디렉토리에 마크다운으로 정의되어 있습니다.

### 코어 에이전트 (12종)

| 에이전트 | 역할 |
|---------|------|
| 마스터 오케스트레이터 | 프로젝트 초기화, 에이전트 활성화, 워크플로우 조율 |
| 시니어 게임 디자이너 | 비전 수립, GDD 작성, 디자인 최종 결정 |
| 미드 게임 디자이너 | 기능 명세서 작성, 콘텐츠 생성, 밸런싱 |
| 메카닉스 개발자 | 핵심 게임플레이 시스템 설계 및 구현 |
| 게임 필 개발자 | 플레이어 피드백, 주스, 폴리시 |
| UI/UX 에이전트 | 인터페이스 디자인, 접근성, 사용성 |
| 시니어 게임 아티스트 | 아트 디렉션, 스타일 가이드, 시각적 일관성 |
| 테크니컬 아티스트 | 셰이더, VFX, 에셋 최적화 |
| QA 에이전트 | 테스트 계획, 버그 추적, 품질 게이트 |
| 데이터 사이언티스트 | 분석, 지표 설계, A/B 테스트 |
| 프로듀서 에이전트 | 일정/마일스톤 관리, 리스크 관리 |
| 시장 분석가 | 경쟁 분석, 시장 포지셔닝 |

### 전문 에이전트 (8종, 신규)

| 에이전트 | 역할 |
|---------|------|
| AI 프로그래머 | 행동트리, 상태머신, 길찾기, 인식, 그룹 행동 |
| 네트워크 프로그래머 | 상태 동기화, 지연 보상, 매치메이킹, 대역폭 관리 |
| 내러티브 디렉터 | 스토리 아키텍처, 세계관, 캐릭터, 대사 시스템 |
| 사운드 디자이너 | SFX 명세, 오디오 이벤트, 믹싱, 앰비언스 |
| 레벨 디자이너 | 레벨 레이아웃, 인카운터, 페이싱, 환경 스토리텔링 |
| 경제 디자이너 | 자원 경제, 루트 시스템, 진행 곡선, 밸런싱 |
| 성능 분석가 | 성능 프로파일링, 병목 식별, 최적화 권고 |
| 보안 엔지니어 | 안티치트, 데이터 보안, 네트워크 보안, 개인정보 보호 |

## 설치 및 실행

### 방법 1: Docker Compose (권장)

```bash
# 1. 환경 변수 설정
cp .env.example .env
# .env 파일에서 AUTH_MODE 및 필요한 API 키 입력

# 2. 빌드 및 실행
docker-compose up --build
```

- Frontend: http://localhost:8501
- Backend API: http://localhost:8000

### 방법 2: 로컬 개발 환경

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
source venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

**터미널 2 — Frontend:**

```bash
source venv/bin/activate
streamlit run frontend/app.py
```

## 환경 변수

`.env.example`을 `.env`로 복사한 뒤 값을 설정합니다.

### 인증 모드 (`AUTH_MODE`)

| 모드 | 설명 | 필요한 변수 |
|------|------|------------|
| `cli` | 로컬 CLI OAuth (호스트의 ~/.claude 마운트) | — |
| `api` | API 키 직접 사용 | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` |
| `bedrock` | AWS Bedrock 게이트웨이 | `AWS_*`, `ANTHROPIC_BEDROCK_BASE_URL` |

### 전체 변수 목록

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `AUTH_MODE` | 인증 모드 (cli / api / bedrock) | `cli` |
| `ANTHROPIC_API_KEY` | Claude API 키 | — |
| `OPENAI_API_KEY` | OpenAI API 키 | — |
| `OPENAI_CODEX_API_KEY` | Codex 게이트웨이 API 키 | — |
| `CLAUDE_CODE_USE_BEDROCK` | Bedrock 사용 여부 | — |
| `ANTHROPIC_MODEL` | Bedrock 모델 ID | `us.anthropic.claude-opus-4-6-v1` |
| `ANTHROPIC_BEDROCK_BASE_URL` | Bedrock 게이트웨이 URL | — |
| `AWS_REGION` | AWS 리전 | `us-east-1` |
| `AWS_ACCESS_KEY_ID` | AWS 액세스 키 | — |
| `AWS_SECRET_ACCESS_KEY` | AWS 시크릿 키 | — |
| `AWS_SESSION_TOKEN` | AWS 세션 토큰 | — |
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

### 프로젝트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/projects` | 프로젝트 목록 (쿼리: `page`, `per_page`, `status`) |
| `POST` | `/api/projects` | 프로젝트 생성 |
| `GET` | `/api/projects/{id}` | 프로젝트 상세 |
| `PATCH` | `/api/projects/{id}` | 프로젝트 수정 |
| `POST` | `/api/projects/{id}/freeze` | 프로젝트 동결 |
| `POST` | `/api/projects/{id}/resume` | 프로젝트 재개 |
| `POST` | `/api/projects/{id}/startover` | 프로젝트 초기화 |

### 티켓

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/tickets` | 티켓 목록 (쿼리: `project_id`, `page`, `per_page`) |
| `POST` | `/api/tickets` | 티켓 생성 (단계/에이전트 포함) |
| `GET` | `/api/tickets/{id}` | 티켓 상세 (단계/에이전트 포함) |
| `PUT` | `/api/tickets/{id}` | 티켓 수정 |
| `DELETE` | `/api/tickets/{id}` | 티켓 삭제 (실행 중 아닌 경우만) |
| `POST` | `/api/tickets/{id}/assign` | 티켓 할당 (status → assigned) |
| `POST` | `/api/tickets/{id}/auto-assign` | AI 에이전트 자동 추천 |
| `POST` | `/api/tickets/{id}/run` | 파이프라인 실행 |
| `POST` | `/api/tickets/{id}/cancel` | 실행 취소 |
| `POST` | `/api/tickets/{id}/retry` | 실패 단계 재시도 |
| `POST` | `/api/tickets/from-diff` | 문서 diff로 티켓 생성 |
| `POST` | `/api/tickets/decompose` | AI 태스크 분해 (비동기, `job_id` 반환) |
| `GET` | `/api/tickets/decompose/{job_id}` | 분해 작업 상태 확인 |

### 에이전트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/agents` | 에이전트 목록 |
| `GET` | `/api/agents/{name}` | 에이전트 마크다운 조회 |
| `PUT` | `/api/agents/{name}` | 에이전트 마크다운 수정 |
| `GET` | `/api/agents/{name}/runs` | 에이전트 실행 이력 |
| `PUT` | `/api/agents/runs/{run_id}` | 실행 데이터 수정 |

### 실행/사용량/프로바이더

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/runs/{run_id}` | 에이전트 실행 상세 |
| `GET` | `/api/runs/{run_id}/result` | 결과 파일 내용 조회 |
| `GET` | `/api/usage/summary` | 전체 비용 요약 |
| `GET` | `/api/usage/by-project` | 프로젝트별 비용 |
| `GET` | `/api/usage/by-agent` | 에이전트별 비용 |
| `GET` | `/api/providers` | CLI 프로바이더 목록 |
| `PUT` | `/api/providers/{id}` | 프로바이더 수정 |
| `POST` | `/api/providers/{id}/test` | 프로바이더 테스트 |
| `GET` | `/api/providers/rates` | 비용 단가 목록 |
| `PUT` | `/api/providers/rates/{id}` | 비용 단가 수정 |

### 문서

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/documents` | 문서 목록 (쿼리: `project_id`) |
| `POST` | `/api/documents` | 문서 생성 |
| `GET` | `/api/documents/{id}` | 문서 조회 |
| `PUT` | `/api/documents/{id}` | 문서 수정 |
| `GET` | `/api/documents/{id}/diff` | 문서 diff 조회 |

### 헬스체크

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/health` | 서버 상태 확인 |

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

Frontend(Streamlit)가 Backend(FastAPI)에 REST API로 요청을 보내고, Backend는 AI CLI 도구를 subprocess로 실행하여 결과를 수집합니다. 모든 상태는 SQLite에 저장되며, WAL 모드로 동시 접근을 지원합니다. CLI 출력은 `output_sanitizer`를 통해 시크릿이 자동으로 마스킹됩니다.
