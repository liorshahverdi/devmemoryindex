import re

# Patterns that must never be stored in raw_text
_BLOCKLIST = [
    re.compile(r'(?i)(api[_-]?key|token|password|secret|passwd)\s*[:=]\s*\S+'),
    re.compile(r'(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*'),
    re.compile(r'[A-Za-z0-9+/]{40,}={0,2}'),          # long base64 blobs (JWT, keys)
    re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),              # US SSN
    re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),  # email
]

_REDACT_PLACEHOLDER = "[REDACTED]"


def redact(text: str) -> str:
    """Replace sensitive patterns with [REDACTED]. Returns cleaned text."""
    for pattern in _BLOCKLIST:
        text = pattern.sub(_REDACT_PLACEHOLDER, text)
    return text
