import re

# Patterns that must never be stored in raw_text
_BLOCKLIST = [
    # key=value assignments for known sensitive field names
    re.compile(r'(?i)(api[_-]?key|token|password|secret|passwd)\s*[:=]\s*\S+'),
    # HTTP Bearer tokens
    re.compile(r'(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*'),
    # JWTs — three base64url segments separated by dots (eyXXX.XXX.XXX)
    re.compile(r'ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'),
    # Padded base64 blobs (real encoded data ends with = or ==, hex hashes do not)
    re.compile(r'[A-Za-z0-9+/]{40,}={1,2}'),
    # US SSN
    re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    # email addresses
    re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
]

_REDACT_PLACEHOLDER = "[REDACTED]"


def redact(text: str) -> str:
    """Replace sensitive patterns with [REDACTED]. Returns cleaned text."""
    for pattern in _BLOCKLIST:
        text = pattern.sub(_REDACT_PLACEHOLDER, text)
    return text
