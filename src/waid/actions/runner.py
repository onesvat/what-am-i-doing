from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..config import CommandConfig
from ..debug import DebugLogger
from ..models import ToolCall


@dataclass(slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    def __init__(self, debug: DebugLogger | None = None) -> None:
        self.debug = debug

    async def run(self, tool: CommandConfig, args: list[str]) -> CommandResult:
        if self.debug is not None:
            self.debug.log("tool_run", command=tool.run, args=args, timeout_seconds=tool.timeout_seconds)
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
            if self.debug is not None:
                self.debug.log("tool_timeout", command=tool.run, args=args)
            raise RuntimeError(f"tool timed out: {' '.join(tool.run)}")
        result = CommandResult(
            returncode=proc.returncode,
            stdout=stdout.decode("utf-8", errors="replace").strip(),
            stderr=stderr.decode("utf-8", errors="replace").strip(),
        )
        if self.debug is not None:
            self.debug.log(
                "tool_result",
                command=tool.run,
                args=args,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return result

    async def run_calls(self, tools: dict[str, CommandConfig], calls: list[ToolCall]) -> list[CommandResult]:
        results: list[CommandResult] = []
        for call in calls:
            tool = tools.get(call.tool)
            if tool is None:
                raise KeyError(f"unknown action tool: {call.tool}")
            results.append(await self.run(tool, call.args))
        return results
