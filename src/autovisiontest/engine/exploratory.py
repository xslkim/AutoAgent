"""Exploratory runner — runs a test session in exploratory mode.

In exploratory mode, the Planner dynamically decides each step based on
the current screen state and the goal.  The runner:
1. Launches the application
2. Creates and runs a StepLoop
3. Closes the application (cleanup)
4. Returns the completed SessionContext
"""

from __future__ import annotations

import logging
import time

from autovisiontest.backends.protocol import ChatBackend, GroundingBackend
from autovisiontest.control.executor import ActionExecutor
from autovisiontest.control.process import AppHandle, close_app, kill_processes_by_exe, launch_app
from autovisiontest.engine.actor import Actor
from autovisiontest.engine.models import SessionContext, TerminationReason
from autovisiontest.engine.planner import Planner
from autovisiontest.engine.step_loop import StepLoop
from autovisiontest.engine.terminator import Terminator
from autovisiontest.perception.facade import Perception
from autovisiontest.safety.guard import SafetyGuard
from autovisiontest.safety.second_check import SecondCheck

logger = logging.getLogger(__name__)


class ExploratoryRunner:
    """Run a test session in exploratory mode.

    Args:
        chat_backend: Chat backend for Planner and SecondCheck.
        grounding_backend: Grounding backend for Actor.
        max_steps: Maximum number of steps per session.
        confidence_threshold: Minimum grounding confidence.
    """

    def __init__(
        self,
        chat_backend: ChatBackend,
        grounding_backend: GroundingBackend,
        max_steps: int = 30,
        confidence_threshold: float = 0.6,
    ) -> None:
        self._chat_backend = chat_backend
        self._grounding_backend = grounding_backend
        self._max_steps = max_steps
        self._confidence_threshold = confidence_threshold

    def run(
        self,
        goal: str,
        app_path: str,
        app_args: list[str] | None = None,
    ) -> SessionContext:
        """Run an exploratory test session.

        Args:
            goal: Natural language goal for the test.
            app_path: Path to the application executable.
            app_args: Optional command-line arguments for the application.

        Returns:
            The completed SessionContext with all results.
        """
        session = SessionContext(
            goal=goal,
            mode="exploratory",
            app_path=app_path,
            app_args=app_args or [],
            start_time=time.time(),
        )

        handle: AppHandle | None = None
        try:
            # Step 1: Kill any leftover instances
            exe_name = app_path.rsplit("\\", 1)[-1] if "\\" in app_path else app_path.rsplit("/", 1)[-1]
            kill_processes_by_exe(exe_name)

            # Step 2: Launch the application
            handle = launch_app(app_path, app_args)
            logger.info("app_launched", extra={"app_path": app_path, "pid": handle.pid})

            # Step 3: Create components
            perception = Perception()
            planner = Planner(chat_backend=self._chat_backend)
            actor = Actor(
                grounding_backend=self._grounding_backend,
                confidence_threshold=self._confidence_threshold,
            )
            terminator = Terminator(
                app_handle=handle,
                max_steps=self._max_steps,
            )
            second_check = SecondCheck(chat_backend=self._chat_backend)
            safety_guard = SafetyGuard(second_check=second_check)
            executor = ActionExecutor()

            # Step 4: Create and run step loop
            loop = StepLoop(
                planner=planner,
                actor=actor,
                terminator=terminator,
                safety_guard=safety_guard,
                executor=executor,
                perception=perception,
            )

            reason = loop.run(session)
            logger.info("session_ended", extra={"reason": reason.value})

        except Exception:
            logger.exception("exploratory_run_failed")
            session.termination_reason = TerminationReason.CRASH

        finally:
            # Step 5: Cleanup — close the application
            if handle is not None:
                try:
                    close_app(handle)
                    logger.info("app_closed", extra={"pid": handle.pid})
                except Exception:
                    logger.exception("app_close_failed")
                    # Force kill as fallback
                    try:
                        kill_processes_by_exe(handle.exe_name)
                    except Exception:
                        pass

        return session
