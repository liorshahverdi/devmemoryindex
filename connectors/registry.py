from connectors.git_connector import GitConnector
from connectors.diff_connector import DiffConnector
from connectors.claude_connector import ClaudeConnector
from connectors.terminal_connector import TerminalConnector
from connectors.markdown_connector import MarkdownConnector
from connectors.filesystem_connector import FilesystemConnector
from connectors.copilot_connector import CopilotConnector
from connectors.browser_connector import BrowserConnector
from connectors.meeting_connector import MeetingConnector
from connectors.markdown_notes_connector import MarkdownNotesApiConnector

# VoiceConnector intentionally excluded from ALL_CONNECTORS.
# It is triggered only by explicit user commands:
#   devmemory dictate
#   devmemory search --voice
# Running it on a schedule records silence, noise, and other people's speech.
ALL_CONNECTORS = [
    GitConnector,
    DiffConnector,
    ClaudeConnector,
    TerminalConnector,
    MarkdownConnector,
    FilesystemConnector,
    CopilotConnector,
    BrowserConnector,
    MeetingConnector,
    MarkdownNotesApiConnector,
    # VoiceConnector — NOT here. Use VoiceConnector() directly in CLI commands.
]

ACTIVE_CONNECTOR_NAMES = [C.name for C in ALL_CONNECTORS]

# For explicit CLI use only (devmemory dictate, devmemory search --voice).
# VoiceConnector needs optional audio deps: uv pip install "devmemoryindex[voice]"
try:
    from connectors.voice_connector import VoiceConnector
    VOICE_ONLY_CONNECTORS = [VoiceConnector]
except ImportError:
    VOICE_ONLY_CONNECTORS = []  # audio deps not installed


def get_connectors(names: list[str] | None = None) -> list:
    if names is None:
        return [C() for C in ALL_CONNECTORS]
    return [C() for C in ALL_CONNECTORS if C.name in names]
