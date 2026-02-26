from abc import ABC, abstractmethod
from core.store_provider import get_store
from core.memory_store import MemoryStore


class Connector(ABC):
    name: str = "base"

    def __init__(self):
        self.store: MemoryStore = get_store()

    @abstractmethod
    def collect(self) -> int:
        """Ingest memories. Return count of new memories added."""
        ...
