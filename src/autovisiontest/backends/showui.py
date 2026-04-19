"""ShowUI-2B grounding backend via vLLM."""

from __future__ import annotations

import base64
import json
import logging
import re

import httpx

from autovisiontest.backends.types import GroundingResponse
from autovisiontest.exceptions import GroundingBackendError

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "http://localhost:8001/v1"
_DEFAULT_TIMEOUT = 30.0

# Screenshot compression settings
# ShowUI-2B visual tokens scale with resolution; for 4K screens,
# we need aggressive downscaling to stay within context limits.
_SHORT_EDGE_TARGET = 768
_JPEG_QUALITY = 85

# ShowUI prompt template
_SHOWUI_PROMPT_TEMPLATE = (
    "You are a GUI agent. You are given a task and a screenshot. "
    "Find the element described as: {query}. "
    "Output the click coordinates as a JSON object with 'x' and 'y' fields, "
    "where x and y are normalized to [0, 1] relative to the image width and height. "
    "Example: {{\"x\": 0.5, \"y\": 0.3}}"
)


class ShowUIGroundingBackend:
    """Grounding backend using ShowUI-2B via vLLM OpenAI-compatible API."""

    def __init__(
        self,
        model: str = "showlab/ShowUI-2B",
        endpoint: str = _DEFAULT_ENDPOINT,
        confidence_threshold: float = 0.6,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._model = model
        self._endpoint = endpoint.rstrip("/")
        self._confidence_threshold = confidence_threshold
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def ground(self, image: bytes, query: str) -> GroundingResponse:
        """Locate an element in the image matching the query.

        Args:
            image: Screenshot as PNG/JPEG bytes.
            query: Natural language description of the target element.

        Returns:
            GroundingResponse with absolute coordinates and confidence.

        Raises:
            GroundingBackendError: On API errors.
        """
        # Compress screenshot to fit model context (D9)
        compressed, orig_w, orig_h = self._compress_image(image)

        b64 = base64.b64encode(compressed).decode("utf-8")

        prompt = _SHOWUI_PROMPT_TEMPLATE.format(query=query)

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                },
            ],
            "max_tokens": 128,
            "temperature": 0.0,
        }

        try:
            resp = self._client.post(
                f"{self._endpoint}/chat/completions",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

            content = data["choices"][0]["message"]["content"]

            # Parse coordinates from response
            rel_x, rel_y, confidence = self._parse_coordinates(content)

            # Get ORIGINAL image dimensions for absolute coordinate conversion
            img_w, img_h = orig_w, orig_h

            abs_x = int(rel_x * img_w)
            abs_y = int(rel_y * img_h)

            # Clamp to image bounds
            abs_x = max(0, min(abs_x, img_w - 1))
            abs_y = max(0, min(abs_y, img_h - 1))

            return GroundingResponse(
                x=abs_x,
                y=abs_y,
                confidence=confidence,
                raw=data,
            )

        except httpx.HTTPStatusError as exc:
            raise GroundingBackendError(
                f"ShowUI API error: {exc}",
                context={"status_code": exc.response.status_code},
            ) from exc
        except httpx.ConnectError as exc:
            raise GroundingBackendError(
                f"ShowUI connection error: {exc}",
                context={"endpoint": self._endpoint},
            ) from exc
        except GroundingBackendError:
            raise
        except Exception as exc:
            raise GroundingBackendError(
                f"ShowUI grounding error: {exc}",
            ) from exc

    def _parse_coordinates(self, content: str) -> tuple[float, float, float]:
        """Parse normalized (x, y) coordinates from model output.

        Returns:
            (rel_x, rel_y, confidence) where rel_x and rel_y are in [0, 1].
        """
        # Try to find JSON in the response
        try:
            # Look for JSON object
            json_match = re.search(r"\{[^}]+\}", content)
            if json_match:
                raw_json = json_match.group()
                # Models may return single-quoted "JSON" — normalize to double quotes
                if "'" in raw_json:
                    raw_json = raw_json.replace("'", '"')
                coords = json.loads(raw_json)
                rel_x = float(coords.get("x", coords.get("X", 0.5)))
                rel_y = float(coords.get("y", coords.get("Y", 0.5)))
                # Clamp to [0, 1]
                rel_x = max(0.0, min(1.0, rel_x))
                rel_y = max(0.0, min(1.0, rel_y))
                # TODO: Parse actual confidence from model output when available
                # For now, use a fixed confidence (will be refined with prompt engineering)
                confidence = 0.8
                return rel_x, rel_y, confidence
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: try to find "x=0.5, y=0.3" pattern
        match = re.search(r"x\s*=\s*([0-9.]+).*?y\s*=\s*([0-9.]+)", content, re.IGNORECASE)
        if match:
            rel_x = max(0.0, min(1.0, float(match.group(1))))
            rel_y = max(0.0, min(1.0, float(match.group(2))))
            return rel_x, rel_y, 0.8

        raise GroundingBackendError(
            f"Failed to parse coordinates from ShowUI response: {content[:200]}"
        )

    def _compress_image(self, image: bytes) -> tuple[bytes, int, int]:
        """Compress screenshot: resize short edge to 1080px, encode as JPEG Q85.

        Returns:
            (compressed_jpeg_bytes, original_width, original_height)
        """
        import cv2
        import numpy as np

        arr = np.frombuffer(image, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return image, 1920, 1080

        orig_h, orig_w = img.shape[:2]

        # Resize if short edge > target
        short_edge = min(orig_w, orig_h)
        if short_edge > _SHORT_EDGE_TARGET:
            scale = _SHORT_EDGE_TARGET / short_edge
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            logger.debug("Compressed screenshot: %dx%d -> %dx%d", orig_w, orig_h, new_w, new_h)

        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
        if not ok:
            return image, orig_w, orig_h
        return buf.tobytes(), orig_w, orig_h

    def _get_image_dimensions(self, image: bytes) -> tuple[int, int]:
        """Get image width and height from PNG/JPEG bytes."""
        import cv2
        import numpy as np

        arr = np.frombuffer(image, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return (1920, 1080)  # fallback
        h, w = img.shape[:2]
        return w, h
