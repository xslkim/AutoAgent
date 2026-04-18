"""Action executor — dispatches actions to mouse/keyboard modules."""

from __future__ import annotations

import time

from autovisiontest.control import keyboard, mouse
from autovisiontest.control.actions import NEED_TARGET, Action, ActionResult
from autovisiontest.exceptions import ActionExecutionError


class ActionExecutor:
    """Execute desktop actions by dispatching to mouse/keyboard modules."""

    def execute(
        self,
        action: Action,
        coords: tuple[int, int] | None = None,
    ) -> ActionResult:
        """Execute an action.

        For NEED_TARGET actions, *coords* must be provided.
        """
        t0 = time.monotonic()
        try:
            if action.type in NEED_TARGET and coords is None:
                raise ActionExecutionError(
                    f"Action '{action.type}' requires coords but none provided",
                    context={"action_type": action.type, "params": action.params},
                )

            self._dispatch(action, coords)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            return ActionResult(success=True, duration_ms=elapsed_ms)

        except ActionExecutionError:
            raise
        except Exception as e:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            raise ActionExecutionError(
                f"Failed to execute action '{action.type}': {e}",
                context={"action_type": action.type, "params": action.params},
            ) from e

    def _dispatch(
        self,
        action: Action,
        coords: tuple[int, int] | None,
    ) -> None:
        """Internal dispatch to the appropriate control module."""
        x, y = coords or (0, 0)
        params = action.params

        match action.type:
            case "click":
                button = params.get("button", "left")
                mouse.click(x, y, button=button)

            case "double_click":
                mouse.double_click(x, y)

            case "right_click":
                mouse.right_click(x, y)

            case "drag":
                to_xy = (params.get("to_x", x), params.get("to_y", y))
                duration_ms = params.get("duration_ms", 300)
                mouse.drag((x, y), to_xy, duration_ms=duration_ms)

            case "scroll":
                dy = params.get("dy", 1)
                mouse.scroll(x, y, dy=dy)

            case "type":
                text = params.get("text", "")
                interval_ms = params.get("interval_ms", 20)
                keyboard.type_text(text, interval_ms=interval_ms)

            case "key_combo":
                keys = params.get("keys", [])
                keyboard.key_combo(*keys)

            case "wait":
                import time as _time
                duration_s = params.get("duration_s", 1.0)
                _time.sleep(duration_s)

            case _:
                raise ActionExecutionError(
                    f"Unknown action type: {action.type}",
                    context={"action_type": action.type},
                )
