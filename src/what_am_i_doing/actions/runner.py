from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..config import CommandConfig
from ..models import ToolCall


@dataclass(slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    async def run(self, tool: CommandConfig, args: list[str]) -> CommandResult:
        proc = await asyncio.create_subprocess_exec(
            *tool.run,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=tool.timeout_seconds)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"tool timed out: {' '.join(tool.run)}")
        return CommandResult(
            returncode=proc.returncode,
            stdout=stdout.decode("utf-8", errors="replace").strip(),
            stderr=stderr.decode("utf-8", errors="replace").strip(),
        )

    async def run_calls(self, tools: dict[str, CommandConfig], calls: list[ToolCall]) -> list[CommandResult]:
        results: list[CommandResult] = []
        for call in calls:
            tool = tools.get(call.tool)
            if tool is None:
                raise KeyError(f"unknown action tool: {call.tool}")
            results.append(await self.run(tool, call.args))
        return results
