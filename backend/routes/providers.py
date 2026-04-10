from fastapi import APIRouter, HTTPException
from typing import List
import backend.config
from backend.database import get_db
from backend.services.output_sanitizer import sanitize_output
from backend.models.provider import (
    CLIProviderResponse,
    CLIProviderUpdate,
    CostRateResponse,
    CostRateUpdate
)

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("", response_model=List[CLIProviderResponse])
async def list_providers():
    """List all CLI providers"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, name, command, api_key_env, enabled
            FROM cli_providers
            ORDER BY name
            """
        )
        rows = await cursor.fetchall()

        return [
            CLIProviderResponse(
                id=row[0],
                name=row[1],
                command=row[2],
                api_key_env=row[3],
                enabled=bool(row[4])
            )
            for row in rows
        ]


@router.put("/{provider_id}", response_model=CLIProviderResponse)
async def update_provider(provider_id: int, update: CLIProviderUpdate):
    """Update provider settings"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Check if provider exists
        cursor = await db.execute(
            "SELECT id, name, command, api_key_env, enabled FROM cli_providers WHERE id = ?",
            (provider_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Provider not found")

        # Build update query
        updates = []
        params = []
        if update.command is not None:
            updates.append("command = ?")
            params.append(update.command)
        if update.api_key_env is not None:
            updates.append("api_key_env = ?")
            params.append(update.api_key_env)
        if update.enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if update.enabled else 0)

        if updates:
            params.append(provider_id)
            await db.execute(
                f"UPDATE cli_providers SET {', '.join(updates)} WHERE id = ?",
                params
            )
            await db.commit()

        # Fetch updated record
        cursor = await db.execute(
            "SELECT id, name, command, api_key_env, enabled FROM cli_providers WHERE id = ?",
            (provider_id,)
        )
        row = await cursor.fetchone()

        return CLIProviderResponse(
            id=row[0],
            name=row[1],
            command=row[2],
            api_key_env=row[3],
            enabled=bool(row[4])
        )


@router.post("/{provider_id}/test")
async def test_provider(provider_id: int):
    """Test if a CLI provider command works by sending a simple prompt"""
    from backend.services.cli_runner import CLIRunner

    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT command FROM cli_providers WHERE id = ?",
            (provider_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Provider not found")

        command = row[0]

    try:
        import asyncio
        runner = CLIRunner()
        test_command = command
        if "codex" in command.lower():
            test_command = f"{command} --skip-git-repo-check"
        result = await asyncio.wait_for(
            runner.run(
                command=test_command,
                prompt='Respond with exactly: {"status":"ok"}',
                work_dir="/tmp",
                env={}
            ),
            timeout=30
        )

        if result["return_code"] == 0 and result["stdout"].strip():
            return {"success": True, "message": sanitize_output(result["stdout"].strip()[:200])}
        else:
            error = result["stderr"].strip() or result["stdout"].strip() or f"Exit code: {result['return_code']}"
            return {"success": False, "message": sanitize_output(error[:500])}
    except asyncio.TimeoutError:
        return {"success": False, "message": "Command timed out (30s)"}
    except FileNotFoundError:
        return {"success": False, "message": f"Command not found: {command}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/rates", response_model=List[CostRateResponse])
async def list_cost_rates():
    """List all cost rates"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, provider, model, input_rate, output_rate, updated_at
            FROM cost_rates
            ORDER BY provider, model
            """
        )
        rows = await cursor.fetchall()

        return [
            CostRateResponse(
                id=row[0],
                provider=row[1],
                model=row[2],
                input_rate=row[3],
                output_rate=row[4],
                updated_at=row[5]
            )
            for row in rows
        ]


@router.put("/rates/{rate_id}", response_model=CostRateResponse)
async def update_cost_rate(rate_id: int, update: CostRateUpdate):
    """Update cost rate"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Check if rate exists
        cursor = await db.execute(
            "SELECT id FROM cost_rates WHERE id = ?",
            (rate_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Cost rate not found")

        # Build update query
        updates = []
        params = []
        if update.input_rate is not None:
            updates.append("input_rate = ?")
            params.append(update.input_rate)
        if update.output_rate is not None:
            updates.append("output_rate = ?")
            params.append(update.output_rate)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(rate_id)
            await db.execute(
                f"UPDATE cost_rates SET {', '.join(updates)} WHERE id = ?",
                params
            )
            await db.commit()

        # Fetch updated record
        cursor = await db.execute(
            "SELECT id, provider, model, input_rate, output_rate, updated_at FROM cost_rates WHERE id = ?",
            (rate_id,)
        )
        row = await cursor.fetchone()

        return CostRateResponse(
            id=row[0],
            provider=row[1],
            model=row[2],
            input_rate=row[3],
            output_rate=row[4],
            updated_at=row[5]
        )
