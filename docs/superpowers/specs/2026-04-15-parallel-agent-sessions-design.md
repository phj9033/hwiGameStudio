# Parallel Agent Sessions Design

## Summary

티켓 내 에이전트들을 독립 세션으로 병렬 실행하고, 파일 기반 공유 컨텍스트를 통해 에이전트 간 협업을 지원하는 아키텍처 재설계.

## 핵심 변경

- **스텝(step) 계층 제거** → 티켓 아래 에이전트 세션이 flat하게 존재
- **파일 기반 공유 컨텍스트** → `workspace/` 폴더를 통해 에이전트 간 결과 공유
- **의존성 기반 자동 스케줄링** → `depends_on`/`produces` 파일 선언으로 실행 순서 결정
- **`.writing` 컨벤션** → 작성 중/완료 상태를 파일 확장자로 구분

## 핵심 개념 모델

### 세션(Session)

티켓 내 에이전트 하나의 독립 실행 단위:
- 자체 CLI 프로세스로 병렬 실행
- `workspace/` 폴더를 공유 컨텍스트로 사용
- 세션 로그를 `sessions/` 폴더에 기록
- 선행 문서가 필요하면 `.writing` 없는 파일이 나타날 때까지 대기

### 공유 문서(Shared Document)

에이전트가 `workspace/`에 작성하는 결과물:
- 작성 중: `xxx.md.writing`
- 완료 시: `xxx.md`로 rename

### 의존성

에이전트별로 선언:
```
mechanics_developer:
  depends_on: ["gdd.md"]           # 이 파일이 workspace/에 있어야 시작
  produces: ["mechanics_spec.md"]   # 완료 시 이 파일을 생성
```

### 실행 흐름 예시

```
티켓 실행 시작
  ├─ sr_game_designer  → 의존성 없음 → 즉시 시작 → gdd.md 작성
  ├─ sr_game_artist    → 의존성 없음 → 즉시 시작 → art_direction.md 작성
  ├─ mechanics_developer → gdd.md 대기 → 생성 감지 → 시작 → mechanics_spec.md 작성
  └─ game_feel_developer → mechanics_spec.md 대기 → 생성 감지 → 시작
```

## 파일 구조

```
projects/{project}/
  workspace/                          # 공유 컨텍스트 (에이전트 간 협업 공간)
    ticket_{id}/
      gdd.md                          # 완료된 문서
      mechanics_spec.md.writing       # 작성 중인 문서
      art_direction.md

  sessions/                           # 에이전트별 세션 기록
    ticket_{id}/
      sr_game_designer.md             # 전체 세션 로그
      mechanics_developer.md
      sr_game_artist.md
```

### 컨벤션 규칙

- `workspace/ticket_{id}/` — 티켓별 격리
- `.writing` 확장자 — 작성 중 표시. 에이전트가 `xxx.md.writing`으로 생성, 완료 시 `xxx.md`로 rename
- `sessions/ticket_{id}/` — 에이전트 이름으로 파일 생성, CLI stdout 전체 기록
- 에이전트 instruction에 이 컨벤션을 포함

### 파일 감시

- 파이프라인 executor가 `workspace/ticket_{id}/` 폴더를 5초 간격으로 폴링
- `.writing` 확장자가 없는 파일 목록으로 의존성 충족 여부 판단
- 충족되면 대기 중인 에이전트 세션 시작

## DB 스키마 변경

### 삭제

- `ticket_steps` 테이블
- `step_agents` 테이블
- 기존 프로젝트/캐시 데이터 전부 초기화

### 새 테이블: `agent_sessions`

```sql
CREATE TABLE agent_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    agent_name TEXT NOT NULL,
    cli_provider TEXT NOT NULL DEFAULT 'claude',
    instruction TEXT NOT NULL,
    depends_on TEXT DEFAULT '[]',           -- JSON array: ["gdd.md"]
    produces TEXT DEFAULT '[]',             -- JSON array: ["mechanics_spec.md"]
    status TEXT NOT NULL DEFAULT 'pending', -- pending/waiting/running/completed/failed
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    estimated_cost REAL DEFAULT 0,
    session_log_path TEXT,                  -- sessions/ticket_{id}/{agent}.md
    pid INTEGER,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 상태 머신

```
pending   → 티켓 실행 전
waiting   → 의존 문서 대기 중
running   → CLI 프로세스 실행 중
completed → 완료, produces 파일 생성됨
failed    → 실패
```

## 파이프라인 실행 로직

```python
async def execute_ticket(ticket_id):
    sessions = get_sessions(ticket_id)

    # 의존성 없는 에이전트 즉시 시작
    for session in sessions:
        if not session.depends_on:
            asyncio.create_task(run_session(session))

    # 폴링 루프: 대기 중인 에이전트 체크
    while has_pending_or_waiting(ticket_id):
        for session in get_waiting_sessions(ticket_id):
            workspace = f"projects/{project}/workspace/ticket_{ticket_id}/"

            all_ready = all(
                os.path.exists(workspace + doc)
                and not os.path.exists(workspace + doc + ".writing")
                for doc in session.depends_on
            )

            if all_ready:
                asyncio.create_task(run_session(session))

        await asyncio.sleep(5)

    update_ticket_status(ticket_id)

async def run_session(session):
    update_status(session, "running")

    # 프롬프트 빌드: 에이전트 정의 + instruction + workspace 경로 + 컨벤션
    prompt = build_prompt(session, workspace_path, conventions)

    # CLI 실행
    result = await cli_runner.run(prompt, session.cli_provider)

    # 세션 로그 저장
    save_session_log(session, result.stdout)

    # produces 파일은 에이전트가 직접 작성 (.writing → rename)
    update_status(session, "completed" if result.success else "failed")
```

### 실패 처리

- 에이전트 하나가 실패해도 다른 독립 에이전트는 계속 진행
- 실패한 에이전트에 의존하는 에이전트만 대기 상태로 남음
- 타임아웃: 설정 가능한 최대 대기 시간 (기본 30분), 초과 시 failed

## API 변경

### 제거

- `ticket_steps` 관련 엔드포인트 전부

### 티켓 생성 변경

```
POST /api/tickets/
{
  "project_id": 1,
  "title": "캐릭터 시스템 설계",
  "description": "...",
  "sessions": [
    {
      "agent_name": "sr_game_designer",
      "instruction": "캐릭터 시스템 GDD 작성",
      "depends_on": [],
      "produces": ["gdd.md"]
    },
    {
      "agent_name": "mechanics_developer",
      "instruction": "GDD 기반 메카닉 스펙 작성",
      "depends_on": ["gdd.md"],
      "produces": ["mechanics_spec.md"]
    },
    {
      "agent_name": "sr_game_artist",
      "instruction": "아트 디렉션 문서 작성",
      "depends_on": [],
      "produces": ["art_direction.md"]
    }
  ]
}
```

### 새 엔드포인트

```
GET  /api/sessions/{id}                      # 세션 메타데이터
GET  /api/sessions/{id}/log                  # 세션 로그 파일 내용
GET  /api/tickets/{id}/workspace             # 공유 문서 목록
GET  /api/tickets/{id}/workspace/{filename}  # 공유 문서 내용
```

### 유지 (변경 없음)

```
POST /api/tickets/{id}/run
POST /api/tickets/{id}/cancel
GET  /api/usage/*
```

### AI 분해 변경

```
POST /api/tickets/decompose
```

응답이 steps/agents 대신 sessions 배열로 반환. `depends_on`/`produces` 자동 추론.

## 프론트엔드 변경

### 티켓 보드 (3_ticket_board.py)

- 스텝 트리 뷰 → 에이전트 세션 플랫 리스트
- 각 세션 카드에 상태 표시: `pending` `waiting (gdd.md 대기)` `running` `completed`
- 의존성 화살표 간단하게 표시

### 새 세션 뷰어

- 세션 클릭 시 → 세션 로그 전체를 마크다운으로 렌더링
- 해당 에이전트가 생성한 공유 문서도 함께 표시

### 티켓 생성 폼

- 에이전트 추가 시 `depends_on` / `produces` 입력 필드
- AI 분해로 자동 생성 가능

## 향후 확장

- **실시간 스트리밍**: 세션 로그를 WebSocket/SSE로 실시간 전송
- **이벤트 기반 전환**: 폴링 → asyncio Event + DB 하이브리드
- **에이전트 간 직접 메시지**: 공유 문서 외에 채팅 채널 추가
