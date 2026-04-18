"""Unit tests for backend protocol and types."""

from __future__ import annotations

from autovisiontest.backends.protocol import ChatBackend, GroundingBackend
from autovisiontest.backends.types import ChatResponse, GroundingResponse, Message


class TestTypes:
    def test_message_creation(self) -> None:
        msg = Message(role="system", content="You are a helpful assistant.")
        assert msg.role == "system"
        assert msg.content == "You are a helpful assistant."
        assert msg.images == []

    def test_message_with_images(self) -> None:
        msg = Message(role="user", content="What is this?", images=[b"\x89PNG"])
        assert len(msg.images) == 1

    def test_chat_response(self) -> None:
        resp = ChatResponse(content='{"action": "click"}', raw={}, usage={"tokens": 10})
        assert resp.content == '{"action": "click"}'
        assert resp.usage is not None

    def test_chat_response_no_usage(self) -> None:
        resp = ChatResponse(content="hello", raw={})
        assert resp.usage is None

    def test_grounding_response(self) -> None:
        resp = GroundingResponse(x=100, y=200, confidence=0.85, raw={})
        assert resp.x == 100
        assert resp.y == 200
        assert resp.confidence == 0.85


class TestProtocol:
    def test_chat_backend_is_runtime_checkable(self) -> None:
        """A class implementing ChatBackend should pass isinstance check."""

        class MyChatBackend:
            def chat(self, messages, images=None, response_format="json"):
                return ChatResponse(content="", raw={})

        instance = MyChatBackend()
        assert isinstance(instance, ChatBackend)

    def test_grounding_backend_is_runtime_checkable(self) -> None:
        """A class implementing GroundingBackend should pass isinstance check."""

        class MyGroundingBackend:
            def ground(self, image, query):
                return GroundingResponse(x=0, y=0, confidence=0.0, raw={})

        instance = MyGroundingBackend()
        assert isinstance(instance, GroundingBackend)

    def test_non_compliant_class_not_chat_backend(self) -> None:
        """A class without chat() should not satisfy ChatBackend."""

        class NotABackend:
            pass

        assert not isinstance(NotABackend(), ChatBackend)

    def test_non_compliant_class_not_grounding_backend(self) -> None:
        """A class without ground() should not satisfy GroundingBackend."""

        class NotABackend:
            pass

        assert not isinstance(NotABackend(), GroundingBackend)
