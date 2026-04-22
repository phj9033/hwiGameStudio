# 에이전트 관계도 및 필수 분석 가이드

## 조직 계층 구조

```
                        ┌─────────────────────┐
                        │  Master Orchestrator │  ← 최상위 조율자
                        │   (마스터 오케스트레이터)  │
                        └─────────┬───────────┘
                                  │
          ┌───────────────┬───────┼───────┬────────────────┐
          │               │       │       │                │
    ┌─────┴─────┐  ┌──────┴──┐ ┌──┴───┐ ┌─┴──────────┐ ┌──┴──────────┐
    │ Producer  │  │Sr Game  │ │Sr Game│ │Performance │ │  Security   │
    │ (프로듀서) │  │Designer │ │Artist │ │ Analyst    │ │  Engineer   │
    └─────┬─────┘  │(시니어GD)│ │(시니어GA)│ │(성능 분석가) │ │ (보안 엔지니어) │
          │        └────┬────┘ └───┬───┘ └────────────┘ └─────────────┘
    ┌─────┼─────┐       │         │
    │     │     │       │    ┌────┴─────┐
┌───┴──┐┌─┴──┐┌┴────┐  │    │Technical │
│Market││Data││ QA  │  │    │  Artist  │
│Analyst│Sci. │Agent │  │    │(테크니컬AT)│
└──────┘└────┘└─────┘  │    └──────────┘
                        │
        ┌───────┬───────┼───────┬──────────┐
        │       │       │       │          │
   ┌────┴───┐┌──┴───┐┌──┴──┐┌──┴────┐┌────┴─────┐
   │Mid Game││Level ││Narr-││Economy││  UI/UX   │
   │Designer││Design││ative││Design.││  Agent   │
   └────────┘└──────┘└─────┘└───────┘└──────────┘
        │
   ┌────┴──────────────────────┐
   │                           │
┌──┴──────────┐  ┌─────────────┴──┐
│  Mechanics  │  │   Game Feel    │
│  Developer  │  │   Developer    │
│(메카닉스 개발자)│  │ (게임필 개발자)   │
└──────┬──────┘  └────────────────┘
       │
  ┌────┼────────┐
  │             │
┌─┴──────┐ ┌───┴────────┐
│   AI   │ │  Network   │
│Programr│ │ Programmer │
└────────┘ └────────────┘
```

---

## 보고 체계 요약

| 에이전트 | 상위 보고 | 하위 위임 |
|---------|----------|----------|
| Master Orchestrator | 없음 (최상위) | 전체 |
| Producer | Master Orchestrator | 없음 (조율) |
| Sr. Game Designer | Master Orchestrator | Mid Game Designer |
| Sr. Game Artist | Master Orchestrator | Technical Artist |
| Mid Game Designer | Sr. Game Designer | 없음 |
| Mechanics Developer | Sr. Game Designer | 없음 |
| Game Feel Developer | Mechanics Developer | 없음 |
| AI Programmer | Mechanics Developer | 없음 |
| Network Programmer | Mechanics Developer | 없음 |
| Level Designer | Sr. Game Designer | 없음 |
| Narrative Director | Sr. Game Designer | 없음 |
| Economy Designer | Sr. Game Designer | 없음 |
| UI/UX Agent | Sr. Game Designer | 없음 |
| Technical Artist | Sr. Game Artist | 없음 |
| Sound Designer | Sr. Game Artist | 없음 |
| QA Agent | Producer | 없음 |
| Data Scientist | Producer | 없음 |
| Market Analyst | Producer | 없음 |
| Performance Analyst | Master Orchestrator | 없음 |
| Security Engineer | Master Orchestrator | 없음 |

---

## 게임 장르별 필수 에이전트 선별

### Tier 1 - 어떤 게임이든 반드시 필요 (Core)

| 에이전트 | 이유 |
|---------|------|
| **Master Orchestrator** | 전체 워크플로우 조율 - 없으면 에이전트간 협업 불가 |
| **Sr. Game Designer** | GDD, 핵심 기둥, 코어 루프 정의 - 게임의 비전 자체 |
| **Mechanics Developer** | 실제 게임플레이 코드 구현 - 코드를 쓰는 유일한 핵심 에이전트 |
| **QA Agent** | 품질 게이트 - 없으면 버그투성이 릴리스 |
| **Producer** | 일정/스코프 관리 - 없으면 프로젝트가 표류 |

### Tier 2 - 대부분의 게임에 필요 (Important)

| 에이전트 | 필요 조건 |
|---------|----------|
| **Mid Game Designer** | 기능이 3개 이상인 게임 (상세 명세 필요) |
| **UI/UX Agent** | 메뉴/HUD가 있는 모든 게임 |
| **Game Feel Developer** | 액션/아케이드 등 감각적 피드백이 중요한 게임 |
| **Sr. Game Artist** | 스타일 가이드 + 비주얼 일관성 필요 |

### Tier 3 - 장르/규모에 따라 선택 (Conditional)

| 에이전트 | 필요 조건 |
|---------|----------|
| **Level Designer** | 레벨 기반 게임 (플랫포머, RPG, FPS) |
| **Narrative Director** | 스토리가 있는 게임 (RPG, 어드벤처, 비주얼노벨) |
| **Economy Designer** | 자원/루트/진행 시스템이 있는 게임 (F2P, RPG, 경영) |
| **AI Programmer** | NPC/적 AI가 있는 게임 |
| **Network Programmer** | 멀티플레이어 게임만 |
| **Sound Designer** | 사운드가 중요한 게임 (리듬, 호러, 몰입형) |
| **Technical Artist** | 3D 게임 또는 커스텀 셰이더/VFX 필요 시 |
| **Security Engineer** | 온라인/멀티플레이어 게임만 |
| **Performance Analyst** | 모바일 또는 대규모 게임 (성능 민감) |
| **Market Analyst** | 상업 출시 목적 게임 |
| **Data Scientist** | 라이브 서비스/F2P 게임 |

---

## 실제 게임 유형별 추천 구성

| 유형 | 추천 에이전트 (Tier 1 + 추가) | 총 |
|------|-------------------------------|---|
| **인디 싱글 2D** | Core 5 + UI/UX, Game Feel | **7** |
| **스토리 RPG** | Core 5 + Mid GD, UI/UX, Level, Narrative, Economy, AI, Sound | **12** |
| **모바일 F2P** | Core 5 + Mid GD, UI/UX, Economy, Market, Data Sci, Performance | **11** |
| **멀티플레이어 FPS** | Core 5 + Mid GD, UI/UX, Game Feel, Level, AI, Network, Security, Performance, Tech Artist | **14** |
| **풀 AAA** | 전체 **20** |

---

## 핵심 요약

**최소 5개(Orchestrator, Sr.Designer, Mechanics Dev, QA, Producer)**는 어떤 게임이든 빠지면 안 됩니다. 나머지는 게임 장르와 규모에 맞춰 선택적으로 활성화하면 됩니다.
