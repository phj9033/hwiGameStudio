import asyncio
import json
import os
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/ccusage", tags=["ccusage"])


def _find_claude_config_dir() -> Optional[str]:
    """Find Claude data directory for ccusage."""
    # Respect explicit env var
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        return os.environ["CLAUDE_CONFIG_DIR"]
    # Check common locations
    home = os.path.expanduser("~")
    for candidate in [
        os.path.join(home, ".claude"),
        os.path.join(home, ".config", "claude"),
    ]:
        if os.path.isdir(os.path.join(candidate, "projects")):
            return candidate
    return None


@router.get("")
async def get_ccusage(
    period: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    since: Optional[str] = Query(None, pattern=r"^\d{8}$"),
    until: Optional[str] = Query(None, pattern=r"^\d{8}$"),
):
    """Fetch usage data from ccusage CLI tool."""
    claude_dir = _find_claude_config_dir()
    if not claude_dir:
        return {
            "success": False,
            "error": "Claude 데이터 디렉토리를 찾을 수 없습니다.",
            "help": (
                "Docker 환경에서는 docker-compose.yml에 "
                "'~/.claude:/home/appuser/.claude:ro' 볼륨 마운트가 필요합니다. "
                "또는 CLAUDE_CONFIG_DIR 환경변수를 설정해주세요."
            ),
        }

    if not since:
        since = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")

    cmd = f"npx ccusage@latest {period} --json --since {since} --breakdown"
    if until:
        cmd += f" --until {until}"

    # Pass CLAUDE_CONFIG_DIR so ccusage can find the data
    env = os.environ.copy()
    env["CLAUDE_CONFIG_DIR"] = claude_dir

    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=30
        )

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            # Detect common errors and provide specific guidance
            if "No valid Claude data directories" in error_msg:
                return {
                    "success": False,
                    "error": "ccusage가 Claude 데이터 디렉토리를 찾을 수 없습니다.",
                    "help": (
                        "Docker 환경: docker-compose.yml에 "
                        "'~/.claude:/home/appuser/.claude:ro' 볼륨 마운트를 추가하고 컨테이너를 재시작해주세요. "
                        "로컬 환경: ~/.claude/projects 디렉토리가 존재하는지 확인해주세요."
                    ),
                }
            return {
                "success": False,
                "error": f"ccusage 실행 실패: {error_msg[:500]}",
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
