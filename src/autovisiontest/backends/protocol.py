"""Backend protocol definitions for type checking."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from autovisiontest.backends.types import ChatResponse, GroundingResponse, Message


@runtime_checkable
class ChatBackend(Protocol):
    """Protocol for chat-based model backends (Planner/Reflector)."""

    def chat(
        self,
        messages: list[Message],
        images: list[bytes] | None = None,
        response_format: str = "json",
    ) -> ChatResponse:
        """Send a chat request and return the response.

        Args:
            messages: Conversation history.
            images: Optional images to include (as PNG/JPEG bytes).
            response_format: "json" to request JSON output, "text" for plain text.

        Returns:
            ChatResponse with the model's reply.
        """
        ...


@runtime_checkable
class GroundingBackend(Protocol):
    """Protocol for grounding backends (Actor)."""

    def ground(self, image: bytes, query: str) -> GroundingResponse:
        """Locate an element in the image matching the query.

        Args:
            image: Screenshot as PNG/JPEG bytes.
            query: Natural language description of the target element.

        Returns:
            GroundingResponse with coordinates and confidence.
        """
        ...
