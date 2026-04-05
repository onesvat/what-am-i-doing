from __future__ import annotations

import asyncio
import ast

from ..constants import TRACKER_BUS_NAME, TRACKER_INTERFACE, TRACKER_OBJECT_PATH
from ..models import ProviderState
from .base import Provider, ProviderCallback


class GnomeProvider(Provider):
    async def snapshot(self) -> ProviderState:
        proc = await asyncio.create_subprocess_exec(
            "gdbus",
            "call",
            "--session",
            "--dest",
            TRACKER_BUS_NAME,
            "--object-path",
            TRACKER_OBJECT_PATH,
            "--method",
            f"{TRACKER_INTERFACE}.GetCurrentState",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="replace").strip())
        payload = stdout.decode("utf-8", errors="replace").strip()
        try:
            result = ast.literal_eval(payload)
        except (SyntaxError, ValueError) as exc:
            raise RuntimeError(f"unable to parse gdbus payload: {payload}") from exc
        if not result or not isinstance(result[0], str):
            raise RuntimeError(f"unexpected GetCurrentState payload: {payload}")
        return ProviderState.model_validate_json(result[0])

    async def monitor(self, callback: ProviderCallback) -> None:
        proc = await asyncio.create_subprocess_exec(
            "gdbus",
            "monitor",
            "--session",
            "--dest",
            TRACKER_BUS_NAME,
            "--object-path",
            TRACKER_OBJECT_PATH,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                await proc.wait()
                stderr = ""
                if proc.stderr is not None:
                    stderr = (await proc.stderr.read()).decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"gdbus monitor exited: {stderr}")
            text = line.decode("utf-8", errors="replace")
            if "StateChanged" not in text:
                continue
            state = await self.snapshot()
            await callback(state)
