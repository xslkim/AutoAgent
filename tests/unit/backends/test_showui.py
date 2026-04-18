"""Unit tests for ShowUI grounding backend (mocked httpx)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from autovisiontest.backends.showui import ShowUIGroundingBackend
from autovisiontest.exceptions import GroundingBackendError


@pytest.fixture
def backend():
    return ShowUIGroundingBackend(
        model="showlab/ShowUI-2B",
        endpoint="http://localhost:8001/v1",
    )


class TestShowUIGroundingBackend:
    @patch("autovisiontest.backends.showui.httpx.Client")
    def test_ground_parses_relative_coords(self, mock_client_cls) -> None:
        """Test that relative coordinates are parsed and converted to absolute."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"x": 0.5, "y": 0.3}'}}],
        }
        mock_client.post.return_value = mock_response

        # Create a 1920x1080 test image
        import cv2
        import numpy as np

        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        _, encoded = cv2.imencode(".png", img)
        image_bytes = encoded.tobytes()

        backend = ShowUIGroundingBackend()
        result = backend.ground(image_bytes, "Save button")

        assert result.x == 960  # 0.5 * 1920
        assert result.y == 324  # 0.3 * 1080
        assert result.confidence == 0.8

    @patch("autovisiontest.backends.showui.httpx.Client")
    def test_ground_out_of_bounds_clamped(self, mock_client_cls) -> None:
        """Test that coordinates are clamped to image bounds."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"x": 1.5, "y": -0.1}'}}],
        }
        mock_client.post.return_value = mock_response

        import cv2
        import numpy as np

        img = np.zeros((100, 200, 3), dtype=np.uint8)
        _, encoded = cv2.imencode(".png", img)
        image_bytes = encoded.tobytes()

        backend = ShowUIGroundingBackend()
        result = backend.ground(image_bytes, "button")

        # x=1.5 clamped to 1.0 → 200-1=199, y=-0.1 clamped to 0 → 0
        assert result.x == 199
        assert result.y == 0

    @patch("autovisiontest.backends.showui.httpx.Client")
    def test_ground_connection_error(self, mock_client_cls) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")

        backend = ShowUIGroundingBackend()
        with pytest.raises(GroundingBackendError, match="connection error"):
            backend.ground(b"\x89PNG", "button")

    @patch("autovisiontest.backends.showui.httpx.Client")
    def test_ground_unparseable_response(self, mock_client_cls) -> None:
        """Test that unparseable model output raises GroundingBackendError."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "I cannot find the element"}}],
        }
        mock_client.post.return_value = mock_response

        import cv2
        import numpy as np

        img = np.zeros((100, 200, 3), dtype=np.uint8)
        _, encoded = cv2.imencode(".png", img)
        image_bytes = encoded.tobytes()

        backend = ShowUIGroundingBackend()
        with pytest.raises(GroundingBackendError, match="Failed to parse"):
            backend.ground(image_bytes, "button")

    @patch("autovisiontest.backends.showui.httpx.Client")
    def test_ground_x_y_pattern_fallback(self, mock_client_cls) -> None:
        """Test parsing 'x=0.5, y=0.3' pattern as fallback."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "The coordinates are x=0.25, y=0.75"}}],
        }
        mock_client.post.return_value = mock_response

        import cv2
        import numpy as np

        img = np.zeros((100, 400, 3), dtype=np.uint8)
        _, encoded = cv2.imencode(".png", img)
        image_bytes = encoded.tobytes()

        backend = ShowUIGroundingBackend()
        result = backend.ground(image_bytes, "button")

        assert result.x == 100  # 0.25 * 400
        assert result.y == 75   # 0.75 * 100
