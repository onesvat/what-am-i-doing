from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from ..models import ProviderSnapshot


ProviderCallback = Callable[[ProviderSnapshot], Awaitable[None]]


class Provider(ABC):
    @abstractmethod
    async def snapshot(self) -> ProviderSnapshot:
        raise NotImplementedError

    @abstractmethod
    async def monitor(self, callback: ProviderCallback) -> None:
        raise NotImplementedError
