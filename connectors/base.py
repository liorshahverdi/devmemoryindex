from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from core.store_provider import get_store
from core.privacy import redact

if TYPE_CHECKING:
    from core.memory_store import MemoryStore


class Connector(ABC):
    name: str = "base"

    def __init__(self):
        self.store: "MemoryStore" = get_store()

    def _redact(self, text: str) -> str:
        """Redact sensitive data before storing. Call on raw_text in collect()."""
        return redact(text)

    @abstractmethod
    def collect(self) -> int:
        """Ingest memories. Return count of new memories added."""
        ...
