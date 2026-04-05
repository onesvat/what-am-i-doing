from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from ..models import ProviderState


ProviderCallback = Callable[[ProviderState], Awaitable[None]]


class Provider(ABC):
    @abstractmethod
    async def snapshot(self) -> ProviderState:
        raise NotImplementedError

    @abstractmethod
    async def monitor(self, callback: ProviderCallback) -> None:
        raise NotImplementedError
