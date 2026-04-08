# Game Studio Sub-Agents Web UI & Orchestration Platform

**Date:** 2026-04-07
**Status:** Draft
**Base:** Fork of [pamirtuna/gamestudio-subagents](https://github.com/pamirtuna/gamestudio-subagents)

---

## 1. Overview

gamestudio-subagents(AI 에이전트 기반 게임 개발 시스템)를 확장하여, Web UI 대시보드와 티켓 기반 작업 관리, 멀티 CLI 지원, 비용 모니터링을 추가하는 프로젝트.

### Goals

1. Web UI로 프로젝트, 에이전트, 티켓을 조작
2. 에이전트별 AI CLI 선택 (Claude Code, Codex / 나중에 확장 가능)
3. 토큰 사용량 및 비용을 에이전트별/프로젝트별 집계 표시
4. 프로젝트 단위의 관리 (생성, 재개, 동결, 리셋)
5. 티켓 시스템으로 유동적 추가/수정 개발 (일회성 파이프라인이 아닌 지속적 개발)

### Non-Goals

- 사용자 인증/권한 관리 (나중에 확장)
- 실시간 터미널 로그 스트리밍 (완료 후 결과 요약만 제공)
- 예산 한도/차단 기능 (단순 집계만)

### Target Users

소규모 팀 (2~5명), 동일 권한으로 동시 접속하여 협업.

---

## 2. Architecture

### High-Level

```
┌─────────────────────────────────────────────────┐
│                  Docker Compose                  │
│                                                  │
│  ┌──────────────┐       ┌──────────────────┐    │
│  │  Streamlit    │──API──│    FastAPI        │    │
│  │  (UI, :8501)  │       │  (Backend, :8000) │    │
│  │               │       │                   │    │
│  │ - 대시보드     │       │ - REST API        │    │
│  │ - 티켓 관리    │       │ - CLI Runner      │    │
│  │ - 결과물 뷰어  │       │ - Background Jobs │    │
│  │ - 비용 모니터  │       │ - Prompt Builder  │    │
│  └──────────────┘       └───────┬───────────┘    │
│                                 │                │
│                          ┌──────┴──────┐         │
│                          │   SQLite     │         │
│                          └─────────────┘         │
│                                                  │
│         ┌──────────────────────────────┐         │
│         │  gamestudio-subagents (fork)  │         │
│         │  ├── agents/*.md             │         │
│         │  ├── projects/               │         │
│         │  └── scripts/                │         │
│         └──────────────────────────────┘         │
└─────────────────────────────────────────────────┘
                         │
              ┌──────────┼──────────┐
              ▼                     ▼
        Claude Code CLI        Codex CLI
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Streamlit |
| Backend | FastAPI + uvicorn |
| Database | SQLite (WAL mode) |
| CLI Execution | subprocess (격리, stdin으로 프롬프트 전달) |
| Container | Docker Compose |
| Language | Python 3.11+ |

### Local Development (Docker 없이)

```bash
# Terminal 1
cd backend && uvicorn main:app --reload --port 8000

# Terminal 2
cd frontend && streamlit run app.py
```

---

## 3. Data Model

### projects

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| name | TEXT | 프로젝트 슬러그 |
| display_name | TEXT | 표시 이름 |
| engine | TEXT | godot / unity / unreal |
| mode | TEXT | design / prototype / development |
| status | TEXT | active / paused / frozen / completed / cancelled |
| config_json | TEXT | project-config.json 내용 |
| created_at | DATETIME | |
| updated_at | DATETIME | |

### tickets

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| project_id | INTEGER FK | |
| title | TEXT | |
| description | TEXT | 전체 설명 |
| status | TEXT | open / assigned / running / completed / failed / cancelled |
| source | TEXT | manual / ai_generated / doc_change |
| created_by | TEXT | 생성자 이름 |
| created_at | DATETIME | |
| updated_at | DATETIME | |

### ticket_steps

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| ticket_id | INTEGER FK | |
| step_order | INTEGER | 실행 순서 (1, 2, 3...) |
| status | TEXT | pending / running / completed / failed |

### step_agents

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| step_id | INTEGER FK | |
| agent_name | TEXT | agents/ 디렉토리의 md 파일명 |
| cli_provider | TEXT | claude / codex |
| instruction | TEXT | 이 에이전트에 대한 세부 지시 |
| context_refs | TEXT (JSON) | 참조 파일 경로 배열, 예: `["path/to/file.md", "path/to/other.gd"]` |
| status | TEXT | pending / running / completed / failed |
| input_tokens | INTEGER | |
| output_tokens | INTEGER | |
| estimated_cost | REAL | |
| result_summary | TEXT | AI가 생성한 결과 요약 |
| result_path | TEXT | 결과물 디렉토리 경로 |
| started_at | DATETIME | |
| completed_at | DATETIME | |
| retry_count | INTEGER | 재시도 횟수 (기본 0) |

### cost_rates

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| provider | TEXT | claude / codex |
| model | TEXT | 모델명 (예: opus-4, codex) |
| input_rate | REAL | 입력 토큰당 비용 ($/1K tokens) |
| output_rate | REAL | 출력 토큰당 비용 ($/1K tokens) |
| updated_at | DATETIME | |

비용 계산: `(input_tokens / 1000 * input_rate) + (output_tokens / 1000 * output_rate)`

### cli_providers

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| name | TEXT | claude / codex |
| command | TEXT | CLI 실행 명령어 |
| api_key_env | TEXT | 환경변수 이름 |
| enabled | BOOLEAN | |

### documents

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| project_id | INTEGER FK | |
| file_path | TEXT | 문서 경로 |
| content | TEXT | 현재 내용 |
| previous_content | TEXT | 직전 버전 (diff용) |
| updated_by | TEXT | |
| updated_at | DATETIME | |

---

## 4. API Design (FastAPI)

### Projects

```
GET    /api/projects                 # 프로젝트 목록
POST   /api/projects                 # 프로젝트 생성
GET    /api/projects/{id}            # 프로젝트 상세
PUT    /api/projects/{id}            # 프로젝트 설정 수정
POST   /api/projects/{id}/freeze     # 동결
POST   /api/projects/{id}/resume     # 재개
POST   /api/projects/{id}/startover  # 리셋 (프로젝트 설정 초기화, 기존 티켓/결과물은 archived/ 로 이동)
```

### Tickets

```
GET    /api/tickets/?project_id=     # 티켓 목록 (프로젝트별 필터)
POST   /api/tickets                  # 티켓 등록
GET    /api/tickets/{id}             # 티켓 상세 + 실행 이력
PUT    /api/tickets/{id}             # 티켓 수정
POST   /api/tickets/{id}/assign      # 수동 에이전트 할당
POST   /api/tickets/{id}/auto-assign # 자동 에이전트 할당
POST   /api/tickets/{id}/run         # 할당된 에이전트 실행
POST   /api/tickets/{id}/cancel      # 실행 중인 티켓 취소 (subprocess kill)
POST   /api/tickets/{id}/retry       # 실패한 step부터 재실행
POST   /api/tickets/from-diff        # 문서 변경 → 자동 티켓 생성
```

### Agents

```
GET    /api/agents                   # 에이전트 목록 (md 파일 스캔)
GET    /api/agents/{name}            # 에이전트 md 내용 조회
PUT    /api/agents/{name}            # 에이전트 md 편집/저장
GET    /api/agents/{name}/runs       # 에이전트별 실행 이력
```

### Runs & Results

`runs`는 `step_agents` 테이블의 레코드를 가리킨다. `{id}`는 `step_agents.id`.

```
GET    /api/runs/{id}                # step_agents 실행 결과 상세 (요약 + 파일 경로)
GET    /api/runs/{id}/result         # 결과물 파일 내용 반환
```

### Documents

```
GET    /api/documents/?project_id=   # 프로젝트 문서 목록
GET    /api/documents/{id}           # 문서 내용
PUT    /api/documents/{id}           # 문서 편집/저장 (diff 감지 트리거)
```

### Providers & Usage

```
GET    /api/providers                # CLI 프로바이더 목록
PUT    /api/providers/{id}           # 프로바이더 설정 수정
GET    /api/usage/summary            # 전체 토큰/비용 집계
GET    /api/usage/by-project?id=     # 프로젝트별 토큰/비용
GET    /api/health                   # 서버 상태 확인
```

### Pagination

목록 조회 API는 모두 페이지네이션 지원:
- `?page=1&per_page=50` (기본값: page=1, per_page=50)
- 응답: `{ "items": [...], "total": 123, "page": 1, "per_page": 50 }`

---

## 5. CLI Runner & Pipeline Executor

### Prompt Assembly

에이전트 실행 시 프롬프트는 다음 요소를 조합:

```
[에이전트 md 파일 내용]
+ [project-config.json]
+ [티켓 전체 설명]
+ [이 에이전트에 대한 개별 지시 (instruction)]
+ [참조 결과물 경로 (context_refs)]
+ [결과물 저장 경로 지정]
```

### CLI Provider Abstraction

프롬프트는 OS 인자 길이 제한을 피하기 위해 **임시 파일**로 전달한다.

```python
class CLIRunner:
    providers = {
        "claude": {
            "cmd": ["claude", "--print"],  # non-interactive mode
            "api_key_env": "ANTHROPIC_API_KEY"
        },
        "codex": {
            "cmd": ["codex", "--quiet"],
            "api_key_env": "OPENAI_API_KEY"
        }
    }

    async def run(self, provider, prompt, cwd):
        cfg = self.providers[provider]
        # 프롬프트를 임시 파일로 작성 후 stdin redirect
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(prompt)
            prompt_file = f.name
        try:
            proc = await asyncio.create_subprocess_exec(
                *cfg["cmd"], prompt_file,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            # 결과 파싱...
        finally:
            os.unlink(prompt_file)
```

나중에 Gemini CLI 등을 추가할 때는 providers dict에 항목만 추가.

### Pipeline Execution

```python
class PipelineExecutor:
    async def run_ticket(self, ticket_id):
        steps = get_steps_ordered(ticket_id)
        
        for step in steps:
            agents = get_step_agents(step.id)
            
            if len(agents) == 1:
                await self.run_agent(agents[0])
            else:
                # 같은 step 내 에이전트는 병렬 실행
                await asyncio.gather(
                    *[self.run_agent(a) for a in agents]
                )
            
            # step 내 모든 에이전트 완료 확인 후 다음 step
            # 하나라도 failed → 티켓 중단, 사용자에게 알림
```

### Token/Cost Parsing

각 CLI의 출력에서 토큰 사용량을 정규식으로 추출한다.

**Claude Code:** 실행 종료 시 `Total tokens: input=XXXX, output=XXXX` 형태로 출력. `--output-format json` 플래그 사용 시 JSON 파싱 가능.

**Codex:** 마찬가지로 실행 완료 시 토큰 정보 출력. CLI 버전에 따라 포맷이 다를 수 있으므로 여러 패턴을 시도.

**비용 계산:** `cost_rates` 테이블에서 프로바이더별 토큰 단가를 조회하여 계산. 단가는 설정 페이지에서 수동 업데이트.

**파싱 실패 시:** `input_tokens=NULL`, `estimated_cost=NULL`로 기록. 대시보드에 "측정 불가"로 표시.

### Result Storage

```
projects/{name}/outputs/ticket-{id}/
  step-{n}/
    {agent_name}/
      summary.md          # AI 생성 요약
      files_changed.json  # 변경된 파일 목록 + 경로
      raw_output.log      # CLI 원본 출력
```

### Background Execution

- FastAPI `BackgroundTasks`로 비동기 실행
- 실행 상태를 DB에 실시간 업데이트
- Streamlit에서 **3초 간격** 폴링으로 상태 확인
- 실행 중인 subprocess의 PID를 `step_agents` 메타데이터에 저장 (cancel 시 kill용)

### Cancellation

`POST /api/tickets/{id}/cancel` 호출 시:
1. 실행 중인 step_agents의 subprocess PID로 `SIGTERM` 전송
2. 5초 내 종료되지 않으면 `SIGKILL`
3. 해당 agent 및 후속 step 모두 status를 `cancelled`로 업데이트

### SQLite Concurrency

병렬 에이전트 실행 시 동시 DB 쓰기 충돌을 방지하기 위해:
- **WAL (Write-Ahead Logging) 모드** 활성화: `PRAGMA journal_mode=WAL`
- **busy_timeout 설정:** `PRAGMA busy_timeout=5000` (5초 대기 후 재시도)
- DB 쓰기는 모두 FastAPI 서버 프로세스 내에서 수행 (subprocess는 DB 직접 접근 안 함)

---

## 6. Ticket System

### Ticket Creation — 3 Paths

#### Path 1: Manual (Web UI Form)

사용자가 직접 입력:
- 제목, 설명
- Step별 에이전트 배치 (같은 step = 병렬, 다음 step = 순차)
- 에이전트별 개별 지시(instruction) 작성
- 에이전트별 CLI 선택
- 참조 파일 지정

#### Path 2: AI Auto-Decompose

자연어 입력 (예: "전투 시스템 구현해줘") → AI가 분석하여:
- 세부 티켓으로 분해
- Step별 에이전트 할당 + 개별 지시 자동 생성
- 사용자 확인/수정 후 실행

#### Path 3: Document Change Detection

Web UI 문서 편집기에서 기획문서 저장 시:
1. 이전 버전과 diff 생성
2. diff를 AI에게 전달하여 영향 분석
3. 추천 티켓 목록 반환
4. 사용자 확인 후 생성

모든 자동 생성은 **사용자 확인 단계**를 거친 후 실행.

#### AI 분석 호출 방식

Path 2, 3에서 사용하는 AI 분석은 **기본 CLI 프로바이더** (cli_providers에서 enabled인 첫 번째)를 사용한다. 별도의 분석 전용 프롬프트 템플릿을 `backend/prompts/` 디렉토리에 보관:

- `prompts/decompose_task.md` — 자연어 지시 → 티켓 분해
- `prompts/analyze_diff.md` — 문서 diff → 영향 분석

AI 응답은 JSON 형태로 구조화하여 반환받는다:
```json
{
  "recommended_tickets": [
    {
      "title": "전투 데미지 계산 로직 수정",
      "description": "...",
      "steps": [
        {
          "step_order": 1,
          "agents": [
            {"agent_name": "mechanics_developer", "instruction": "...", "cli_provider": "claude"}
          ]
        }
      ]
    }
  ]
}
```

### Ticket Status Flow

```
open → assigned → running → completed
                          → failed → (retry: 실패한 step부터 재실행)
              ↓
           cancelled (실행 중 취소 시 subprocess kill)
```

**Ticket vs Step vs Agent 상태 관계:**
- 모든 step이 completed → 티켓 completed
- 어떤 step_agent가 running → 해당 step은 running → 티켓은 running
- step 내 모든 agent가 pending이고 이전 step 완료 → step은 pending, 티켓은 running
- 어떤 step_agent가 failed → 티켓 failed (후속 step은 실행하지 않음)
- cancel 시 → 실행 중인 subprocess kill, 해당 agent와 후속 step 모두 cancelled

**Retry:** `POST /api/tickets/{id}/retry` 호출 시 failed된 step부터 재실행. 이전에 완료된 step 결과물은 유지.

---

## 7. Web UI Pages (Streamlit)

### Sidebar Menu

```
📁 프로젝트
  ├── 대시보드
  └── 프로젝트 상세
🎫 티켓
  ├── 티켓 보드 (칸반)
  ├── 티켓 생성 (직접 입력)
  └── AI 티켓 생성
🤖 에이전트
  ├── 에이전트 목록
  └── 에이전트 편집기 (md)
📊 비용 모니터링
⚙️ 설정 (CLI 프로바이더)
```

### Key Pages

**프로젝트 대시보드:** 전체 프로젝트 현황, 상태 아이콘, 티켓 진행률, 새 프로젝트 생성.

**프로젝트 상세:** 프로젝트 정보, 최근 티켓 현황, 비용 요약, 결과물 목록 (파일 경로 포함), 프로젝트 조작 (재개/동결/리셋).

**티켓 보드:** 칸반 형태 (open → assigned → running → completed). 티켓 클릭 시 상세 (step별 진행 상태, 에이전트별 결과).

**티켓 생성:** 탭 2개 — 직접 입력 폼 (파이프라인 에디터 포함) / AI 자동 생성 (자연어 → 분해 → 확인).

**에이전트 편집기:** 마크다운 에디터로 에이전트 md 파일 직접 편집/저장.

**결과물 뷰어:** 실행 결과 요약, 토큰/비용, 결과물 파일 위치, 마크다운 렌더링.

**비용 모니터링:** 프로젝트별/에이전트별 토큰 사용량 + 예상 비용 테이블.

---

## 8. Directory Structure

```
gamestudio-subagents/              # fork
├── agents/                        # 기존 12개 에이전트 md
├── projects/                      # 게임 프로젝트들
│   └── {project-name}/
│       ├── project-config.json
│       ├── agents/
│       ├── source/
│       ├── documentation/
│       ├── qa/
│       └── outputs/               # 티켓 실행 결과물
│           └── ticket-{id}/
│               └── step-{n}/
│                   └── {agent_name}/
│                       ├── summary.md
│                       ├── files_changed.json
│                       └── raw_output.log
├── scripts/                       # 기존 스크립트
│
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/
│   │   ├── project.py
│   │   ├── ticket.py
│   │   └── agent_run.py
│   ├── routes/
│   │   ├── projects.py
│   │   ├── tickets.py
│   │   ├── agents.py
│   │   ├── runs.py
│   │   ├── documents.py
│   │   ├── providers.py
│   │   └── usage.py
│   ├── services/
│   │   ├── cli_runner.py
│   │   ├── pipeline_executor.py
│   │   ├── prompt_builder.py
│   │   ├── ticket_analyzer.py
│   │   └── token_parser.py
│   ├── prompts/
│   │   ├── decompose_task.md      # 자연어 → 티켓 분해 프롬프트
│   │   └── analyze_diff.md        # diff → 영향 분석 프롬프트
│   └── requirements.txt
│
├── frontend/
│   ├── app.py
│   ├── pages/
│   │   ├── 1_dashboard.py
│   │   ├── 2_project_detail.py
│   │   ├── 3_ticket_board.py
│   │   ├── 4_ticket_create.py
│   │   ├── 5_agents.py
│   │   ├── 6_usage.py
│   │   └── 7_settings.py
│   ├── components/
│   │   ├── pipeline_editor.py
│   │   └── result_viewer.py
│   └── requirements.txt
│
├── data/
│   └── studio.db
│
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
└── .env.example
```

---

## 9. Docker Configuration

### docker-compose.yml

```yaml
version: "3.8"

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "8000:8000"
    volumes:
      - ./agents:/app/agents
      - ./projects:/app/projects
      - ./scripts:/app/scripts
      - ./data:/app/data
    env_file:
      - .env

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "8501:8501"
    env_file:
      - .env
    depends_on:
      - backend
```

### Dockerfile.backend

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y nodejs npm git
RUN npm install -g @anthropic-ai/claude-code@latest
RUN npm install -g @openai/codex@latest

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ ./backend/
COPY scripts/ ./scripts/

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### .env.example

```env
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx
DATABASE_PATH=./data/studio.db
BACKEND_URL=http://backend:8000
```

---

## 10. Future Extensibility

현재 스코프에서 제외하되, 설계 시 확장 가능하도록 고려한 항목:

- **인증/권한:** FastAPI middleware로 추가 가능
- **추가 CLI:** cli_providers 테이블에 행 추가 + CLIRunner.providers에 설정 추가
- **예산 관리:** usage 집계 기반으로 한도/알림 추가 가능
- **실시간 로그:** WebSocket 엔드포인트 추가로 확장 가능
- **프론트엔드 교체:** API가 분리되어 있으므로 React/Next.js 등으로 교체 가능
