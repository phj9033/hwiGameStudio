# Usage Tracking Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove manual cost rate settings, integrate ccusage for overall usage tracking, and fix studio's own token parsing.

**Architecture:** Hybrid approach — studio tracks tokens per agent run (step_agents table), ccusage provides overall daily/monthly usage with accurate pricing. Settings page loses Cost Rates section; Usage page gains two tabs.

**Tech Stack:** Python/FastAPI backend, Streamlit frontend, ccusage CLI (via `npx ccusage@latest`)

---

### Task 1: Remove Cost Rates from Settings Page

**Files:**
- Modify: `frontend/pages/7_settings.py:53-80`

- [ ] **Step 1: Remove Cost Rates UI section**

Remove lines 53-80 (the divider and entire Cost Rates section) from `7_settings.py`. The file should end after the providers `except` block at line 51.

```python
# File should end at:
except Exception as e:
    st.error(f"Failed to connect to backend: {e}")
```

- [ ] **Step 2: Verify settings page loads**

Run: `python -c "import frontend.pages.7_settings as m; print('OK')"`
Or manually open settings page to confirm no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/7_settings.py
git commit -m "refactor: remove cost rates UI from settings page"
```

---

### Task 2: Remove Cost Rates Backend (API + Model + DB)

**Files:**
- Modify: `backend/routes/providers.py:136-208` — remove rates endpoints
- Modify: `backend/models/provider.py:19-30` — remove CostRate models
- Modify: `backend/database.py:56-63,95-103,114-118` — remove cost_rates table/seeds/cleanup

- [ ] **Step 1: Remove rates endpoints from providers.py**

Remove the two endpoints `list_cost_rates` and `update_cost_rate` (lines 136-208). Also remove `CostRateResponse` and `CostRateUpdate` from the imports at lines 9-10.

Updated imports:
```python
from backend.models.provider import (
    CLIProviderResponse,
    CLIProviderUpdate,
)
```

- [ ] **Step 2: Remove CostRate models from provider.py**

Remove `CostRateResponse` and `CostRateUpdate` classes (lines 19-30). Keep `CLIProviderResponse` and `CLIProviderUpdate`.

- [ ] **Step 3: Remove cost_rates from database.py**

Remove from `SCHEMA`:
```sql
CREATE TABLE IF NOT EXISTS cost_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_rate REAL NOT NULL,
    output_rate REAL NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

Remove entire `SEED_COST_RATES` constant and its usage in `init_db`.

Remove from `init_db` the duplicate cleanup query:
```python
await db.execute("""
    DELETE FROM cost_rates WHERE id NOT IN (
        SELECT MIN(id) FROM cost_rates GROUP BY provider, model
    )
""")
```

- [ ] **Step 4: Remove cost calculation from pipeline_executor.py**

In `_run_agent` method, replace the cost calculation block (lines 204-219) with simply setting cost to `None`:

```python
                # Update agent with results
                await db.execute(
                    """UPDATE step_agents
                       SET status = ?, input_tokens = ?, output_tokens = ?,
                           result_summary = ?, result_path = ?, pid = ?, completed_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (
                        status,
                        result["input_tokens"],
                        result["output_tokens"],
                        sanitize_output(result["stdout"][:1000]) if result["stdout"] else sanitize_output(result["stderr"][:1000]),
                        result_path,
                        result["pid"],
                        agent_id
                    )
                )
```

Also remove the `calculate_cost` import from the top of the file.

- [ ] **Step 5: Remove calculate_cost from token_parser.py**

Remove the `calculate_cost` function (lines 34-46). Keep `parse_claude_output` and `parse_codex_output`.

- [ ] **Step 6: Update tests**

In `tests/test_token_parser.py`: remove `calculate_cost` from imports and remove `test_calculate_cost`, `test_calculate_cost_zero_tokens`, `test_calculate_cost_codex_rates` tests.

In `tests/test_database.py`: remove assertion `assert "cost_rates" in tables`.

In `tests/test_usage.py`: remove `test_cost_rates_list` test, and remove `estimated_cost` from test fixture data where it's used to seed step_agents.

- [ ] **Step 7: Run tests**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/ tests/ frontend/
git commit -m "refactor: remove cost rates system (table, API, models, cost calculation)"
```

---

### Task 3: Add ccusage Backend Endpoint

**Files:**
- Create: `backend/routes/ccusage.py`
- Modify: `backend/main.py` — register new router

- [ ] **Step 1: Create ccusage route**

Create `backend/routes/ccusage.py`:

```python
import asyncio
import json
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/ccusage", tags=["ccusage"])


@router.get("")
async def get_ccusage(
    period: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    since: Optional[str] = Query(None, regex="^\\d{8}$"),
    until: Optional[str] = Query(None, regex="^\\d{8}$"),
):
    """Fetch usage data from ccusage CLI tool.

    Returns ccusage JSON output or error message if ccusage is unavailable.
    """
    if not since:
        since = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")

    cmd = f"npx ccusage@latest {period} --json --since {since} --breakdown"
    if until:
        cmd += f" --until {until}"

    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=30
        )

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            return {
                "success": False,
                "error": f"ccusage 실행 실패: {error_msg}",
                "help": "npx ccusage@latest 명령어가 동작하는지 터미널에서 확인해주세요. Node.js가 설치되어 있어야 합니다.",
            }

        data = json.loads(stdout.decode("utf-8"))
        return {"success": True, "data": data}

    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "ccusage 실행 시간 초과 (30초)",
            "help": "npx ccusage@latest 명령어가 동작하는지 터미널에서 확인해주세요.",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "npx 명령어를 찾을 수 없습니다.",
            "help": "Node.js와 npm이 설치되어 있는지 확인해주세요.",
        }
    except json.JSONDecodeError:
        return {
            "success": False,
            "error": "ccusage 출력을 파싱할 수 없습니다.",
            "help": "npx ccusage@latest --json 명령어가 정상 동작하는지 확인해주세요.",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "help": "npx ccusage@latest 명령어가 동작하는지 터미널에서 확인해주세요.",
        }
```

- [ ] **Step 2: Register router in main.py**

Add to `backend/main.py`:

```python
from backend.routes.ccusage import router as ccusage_router
# ...
app.include_router(ccusage_router)
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add backend/routes/ccusage.py backend/main.py
git commit -m "feat: add ccusage CLI integration endpoint"
```

---

### Task 4: Redesign Usage Frontend Page (2 Tabs)

**Files:**
- Modify: `frontend/pages/6_usage.py` — complete rewrite

- [ ] **Step 1: Rewrite usage page with two tabs**

Replace entire `frontend/pages/6_usage.py`:

```python
import streamlit as st
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from api_client import get

st.set_page_config(page_title="Usage Monitoring", page_icon="📊", layout="wide")

st.title("📊 Usage Monitoring")

tab_studio, tab_ccusage = st.tabs(["🏭 Studio Usage", "📈 Overall Usage (ccusage)"])

# --- Tab 1: Studio Usage ---
with tab_studio:
    if st.button("🔄 Refresh", key="refresh_studio"):
        st.rerun()

    try:
        summary = get("/api/usage/summary")

        st.subheader("Overall Studio Usage")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Input Tokens", f"{summary['total_input_tokens']:,}")
        with col2:
            st.metric("Total Output Tokens", f"{summary['total_output_tokens']:,}")

        st.divider()

        # Usage by project
        st.subheader("Usage by Project")
        projects = get("/api/usage/by-project")
        if not projects:
            st.info("No usage data available yet.")
        else:
            import pandas as pd
            df = pd.DataFrame(projects)[['project_display_name', 'total_input_tokens', 'total_output_tokens']]
            df.columns = ['Project', 'Input Tokens', 'Output Tokens']
            df['Input Tokens'] = df['Input Tokens'].apply(lambda x: f"{x:,}")
            df['Output Tokens'] = df['Output Tokens'].apply(lambda x: f"{x:,}")
            st.dataframe(df, use_container_width=True, hide_index=True)

        st.divider()

        # Usage by agent
        st.subheader("Usage by Agent")
        agents = get("/api/usage/by-agent")
        if not agents:
            st.info("No usage data available yet.")
        else:
            import pandas as pd
            df = pd.DataFrame(agents)[['agent_name', 'total_input_tokens', 'total_output_tokens']]
            df.columns = ['Agent', 'Input Tokens', 'Output Tokens']
            df['Input Tokens'] = df['Input Tokens'].apply(lambda x: f"{x:,}")
            df['Output Tokens'] = df['Output Tokens'].apply(lambda x: f"{x:,}")
            st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Failed to connect to backend: {e}")
        st.info("Make sure the backend server is running on http://localhost:8000")


# --- Tab 2: Overall Usage (ccusage) ---
with tab_ccusage:
    col_refresh, col_period = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 Refresh", key="refresh_ccusage"):
            st.rerun()
    with col_period:
        period = st.selectbox("Period", ["daily", "weekly", "monthly"], index=0)

    try:
        result = get(f"/api/ccusage?period={period}")

        if not result.get("success"):
            st.error(result.get("error", "Unknown error"))
            st.warning(result.get("help", ""))
            st.code("npx ccusage@latest", language="bash")
            st.stop()

        data = result["data"]
        totals = data.get("totals", {})

        # Summary metrics
        st.subheader("Total Usage")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Cost", f"${totals.get('totalCost', 0):.2f}")
        with col2:
            st.metric("Input Tokens", f"{totals.get('inputTokens', 0):,}")
        with col3:
            st.metric("Output Tokens", f"{totals.get('outputTokens', 0):,}")
        with col4:
            total_cache = totals.get('cacheCreationTokens', 0) + totals.get('cacheReadTokens', 0)
            st.metric("Cache Tokens", f"{total_cache:,}")

        st.divider()

        # Period breakdown
        period_key = period  # daily, weekly, monthly
        rows = data.get(period_key, [])
        if not rows:
            st.info("No usage data for this period.")
        else:
            import pandas as pd

            st.subheader(f"{period.capitalize()} Breakdown")
            date_col = "date" if period == "daily" else ("week" if period == "weekly" else "month")
            df_data = []
            for row in rows:
                df_data.append({
                    "Date": row.get(date_col, row.get("date", "?")),
                    "Input": f"{row.get('inputTokens', 0):,}",
                    "Output": f"{row.get('outputTokens', 0):,}",
                    "Cache Create": f"{row.get('cacheCreationTokens', 0):,}",
                    "Cache Read": f"{row.get('cacheReadTokens', 0):,}",
                    "Cost": f"${row.get('totalCost', 0):.2f}",
                    "Models": ", ".join(row.get("modelsUsed", [])),
                })
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Model breakdown (expandable)
            st.subheader("Model Breakdown")
            for row in rows:
                date_val = row.get(date_col, row.get("date", "?"))
                breakdowns = row.get("modelBreakdowns", [])
                if breakdowns:
                    with st.expander(f"📅 {date_val} — ${row.get('totalCost', 0):.2f}"):
                        bd_data = []
                        for bd in breakdowns:
                            bd_data.append({
                                "Model": bd.get("modelName", "?"),
                                "Input": f"{bd.get('inputTokens', 0):,}",
                                "Output": f"{bd.get('outputTokens', 0):,}",
                                "Cache Create": f"{bd.get('cacheCreationTokens', 0):,}",
                                "Cache Read": f"{bd.get('cacheReadTokens', 0):,}",
                                "Cost": f"${bd.get('cost', 0):.2f}",
                            })
                        st.dataframe(pd.DataFrame(bd_data), use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Failed to load ccusage data: {e}")
        st.info("Make sure the backend server is running on http://localhost:8000")
```

- [ ] **Step 2: Verify page renders**

Open http://localhost:8501 and navigate to Usage page. Both tabs should render.

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/6_usage.py
git commit -m "feat: redesign usage page with studio usage and ccusage tabs"
```

---

### Task 5: Clean Up Usage Backend (Remove Cost from Aggregation)

**Files:**
- Modify: `backend/routes/usage.py` — remove cost fields from responses
- Modify: `frontend/pages/3_ticket_board.py:228-229` — remove cost display
- Modify: `frontend/pages/5_agents.py:89-90` — remove cost display
- Modify: `frontend/components/result_viewer.py:39` — remove cost usage

- [ ] **Step 1: Update usage.py to remove cost from responses**

Update `get_usage_summary`:
```python
@router.get("/summary")
async def get_usage_summary() -> Dict[str, Any]:
    """Total token summary across all"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                COALESCE(SUM(input_tokens), 0) as total_input,
                COALESCE(SUM(output_tokens), 0) as total_output
            FROM step_agents
            """
        )
        row = await cursor.fetchone()

        return {
            "total_input_tokens": row[0],
            "total_output_tokens": row[1]
        }
```

Update `get_usage_by_project`:
```python
@router.get("/by-project")
async def get_usage_by_project() -> List[Dict[str, Any]]:
    """Token usage grouped by project"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                p.id as project_id,
                p.name as project_name,
                p.display_name as project_display_name,
                COALESCE(SUM(sa.input_tokens), 0) as total_input,
                COALESCE(SUM(sa.output_tokens), 0) as total_output
            FROM projects p
            LEFT JOIN tickets t ON t.project_id = p.id
            LEFT JOIN ticket_steps ts ON ts.ticket_id = t.id
            LEFT JOIN step_agents sa ON sa.step_id = ts.id
            GROUP BY p.id, p.name, p.display_name
            HAVING total_input > 0 OR total_output > 0
            ORDER BY total_input DESC
            """
        )
        rows = await cursor.fetchall()

        return [
            {
                "project_id": row[0],
                "project_name": row[1],
                "project_display_name": row[2],
                "total_input_tokens": row[3],
                "total_output_tokens": row[4]
            }
            for row in rows
        ]
```

Update `get_usage_by_agent`:
```python
@router.get("/by-agent")
async def get_usage_by_agent() -> List[Dict[str, Any]]:
    """Token usage grouped by agent_name"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                agent_name,
                COALESCE(SUM(input_tokens), 0) as total_input,
                COALESCE(SUM(output_tokens), 0) as total_output
            FROM step_agents
            GROUP BY agent_name
            HAVING total_input > 0 OR total_output > 0
            ORDER BY total_input DESC
            """
        )
        rows = await cursor.fetchall()

        return [
            {
                "agent_name": row[0],
                "total_input_tokens": row[1],
                "total_output_tokens": row[2]
            }
            for row in rows
        ]
```

- [ ] **Step 2: Remove cost display from ticket_board.py**

In `frontend/pages/3_ticket_board.py`, remove lines 228-229:
```python
                        if agent.get("estimated_cost"):
                            st.caption(f"Cost: ${agent['estimated_cost']:.4f}")
```

- [ ] **Step 3: Remove cost display from agents.py**

In `frontend/pages/5_agents.py`, remove lines 89-90:
```python
                                if run.get("estimated_cost"):
                                    st.metric("Cost", f"${run['estimated_cost']:.4f}")
```

- [ ] **Step 4: Remove cost from result_viewer.py**

In `frontend/components/result_viewer.py`, update line 39 to not reference `estimated_cost`. Check usage and remove cost display.

- [ ] **Step 5: Update usage tests**

Fix `tests/test_usage.py` to match new response shapes (no `total_cost` field).

- [ ] **Step 6: Run tests**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add backend/routes/usage.py frontend/ tests/
git commit -m "refactor: remove cost display from studio usage, show tokens only"
```

---

### Task 6: Improve Token Parsing for Claude CLI

**Files:**
- Modify: `backend/services/token_parser.py`
- Modify: `tests/test_token_parser.py`

- [ ] **Step 1: Research Claude CLI actual output**

Run a quick test to see what Claude CLI outputs for token info:
```bash
echo "say hi" | claude --dangerously-skip-permissions -p 2>&1 | tail -20
```

Capture the actual format of token output.

- [ ] **Step 2: Update token parsing regex**

Update `parse_claude_output` to handle known Claude CLI output patterns. Common patterns include:
- `Total input tokens: 1234` / `Total output tokens: 5678`
- `input: 1234, output: 5678`
- `Input tokens: 1,234` (with comma formatting)
- JSON output with `"input_tokens"` and `"output_tokens"` fields

```python
import re
import json


def parse_claude_output(output: str) -> dict:
    """Parse Claude CLI output for token counts.

    Tries multiple known formats from Claude CLI output.
    """
    # Try JSON format first (--output-format json)
    try:
        data = json.loads(output)
        if isinstance(data, dict):
            inp = data.get("input_tokens") or data.get("inputTokens")
            out = data.get("output_tokens") or data.get("outputTokens")
            if inp is not None and out is not None:
                return {"input_tokens": int(inp), "output_tokens": int(out)}
    except (json.JSONDecodeError, ValueError):
        pass

    # Pattern: "Total input tokens: 1234" style
    inp_match = re.search(r'(?:total\s+)?input[\s_]*tokens?[=:\s]+([0-9,]+)', output, re.IGNORECASE)
    out_match = re.search(r'(?:total\s+)?output[\s_]*tokens?[=:\s]+([0-9,]+)', output, re.IGNORECASE)
    if inp_match and out_match:
        return {
            "input_tokens": int(inp_match.group(1).replace(",", "")),
            "output_tokens": int(out_match.group(1).replace(",", "")),
        }

    # Pattern: "input: 1234, output: 5678" or "input=1234 output=5678"
    match = re.search(r'input[=:\s]+([0-9,]+).*?output[=:\s]+([0-9,]+)', output, re.IGNORECASE | re.DOTALL)
    if match:
        return {
            "input_tokens": int(match.group(1).replace(",", "")),
            "output_tokens": int(match.group(2).replace(",", "")),
        }

    return {"input_tokens": None, "output_tokens": None}


def parse_codex_output(output: str) -> dict:
    """Parse Codex CLI output for token counts."""
    # Reuse same parsing logic
    return parse_claude_output(output)
```

- [ ] **Step 3: Update tests**

Update `tests/test_token_parser.py` with tests for the new patterns:

```python
from backend.services.token_parser import parse_claude_output, parse_codex_output


def test_parse_claude_output_input_output():
    output = "Some text\ninput: 8230 output: 3120\nDone"
    result = parse_claude_output(output)
    assert result["input_tokens"] == 8230
    assert result["output_tokens"] == 3120


def test_parse_claude_output_with_equals():
    output = "input=500 output=200"
    result = parse_claude_output(output)
    assert result["input_tokens"] == 500
    assert result["output_tokens"] == 200


def test_parse_claude_output_total_tokens():
    output = "Total input tokens: 1,234\nTotal output tokens: 5,678"
    result = parse_claude_output(output)
    assert result["input_tokens"] == 1234
    assert result["output_tokens"] == 5678


def test_parse_claude_output_json():
    output = '{"input_tokens": 100, "output_tokens": 200}'
    result = parse_claude_output(output)
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 200


def test_parse_claude_output_no_tokens():
    output = "Hello world"
    result = parse_claude_output(output)
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None


def test_parse_codex_output():
    output = "input: 1000 output: 500"
    result = parse_codex_output(output)
    assert result["input_tokens"] == 1000
    assert result["output_tokens"] == 500
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_token_parser.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add backend/services/token_parser.py tests/test_token_parser.py
git commit -m "feat: improve token parsing with multiple format support"
```

---

### Task 7: Final Integration Test

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 2: Verify no remaining cost_rates references in active code**

Run: `grep -r "cost_rates" backend/ frontend/ --include="*.py"`
Expected: No matches (except possibly in migration notes).

- [ ] **Step 3: Commit any fixes**

If any issues found, fix and commit.
