"""Contract for anything that can post a message."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class PublishError(RuntimeError):
    """Raised when a publisher could not deliver the message."""


@runtime_checkable
class Publisher(Protocol):
    """A destination for composed posts."""

    name: str

    def publish(self, text: str, *, url: str | None = None) -> str:
        """Post ``text`` and return a receipt (post id / URL).

        Args:
            text: Fully composed message.
            url: The job URL, for publishers that attach links separately.

        Raises:
            PublishError: On any delivery failure.
        """
        ...
