from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkippedSensitiveFileEvent:
    event: str
    path: str
    reason: str


def skipped_sensitive_file(path: str, reason: str) -> SkippedSensitiveFileEvent:
    # IMPORTANT: never include contents; only metadata.
    return SkippedSensitiveFileEvent(event="skipped_sensitive_file", path=path, reason=reason)

