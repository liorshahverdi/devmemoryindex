from connectors.git_connector import GitConnector
from connectors.claude_connector import ClaudeConnector
from connectors.terminal_connector import TerminalConnector
# Connectors added here as each Phase 2.x is implemented:
# from connectors.filesystem_connector import FilesystemConnector
# from connectors.markdown_connector import MarkdownConnector
# from connectors.copilot_connector import CopilotConnector
# from connectors.browser_connector import BrowserConnector

# VoiceConnector intentionally excluded from ALL_CONNECTORS.
# It is triggered only by explicit user commands:
#   devmemory dictate
#   devmemory search --voice
# Running it on a schedule records silence, noise, and other people's speech.
ALL_CONNECTORS = [
    GitConnector,
    ClaudeConnector,
    TerminalConnector,
    # FilesystemConnector,
    # MarkdownConnector,
    # ClaudeConnector,
    # CopilotConnector,
    # VoiceConnector — NOT here. Use VoiceConnector() directly in CLI commands.
    # BrowserConnector,
]

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
