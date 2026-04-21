"""Provider port + null implementation (T061)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderResult:
    provider_message_id: str | None
    accepted: bool
    error: str | None = None


class MessagingProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def send(self, *, channel: str, to_address: str, subject: str | None, body: str) -> ProviderResult:
        ...


class NullProvider(MessagingProvider):
    """Default no-op provider for dev — accepts every send and assigns a fake id."""

    name = "null"

    def send(self, *, channel: str, to_address: str, subject: str | None, body: str) -> ProviderResult:
        del channel, to_address, subject, body
        return ProviderResult(provider_message_id="null:accepted", accepted=True)


_DEFAULT: MessagingProvider = NullProvider()


def get_provider() -> MessagingProvider:
    return _DEFAULT
