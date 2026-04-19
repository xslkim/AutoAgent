"""Notepad target scripts for T J.3 broken/fix cycle.

These are placeholder scripts that would simulate broken vs correct Notepad
behavior in a real E2E scenario. In practice, the "broken" version might use
AutoHotkey to interfere with the save dialog, while the "correct" version
allows normal operation.

Currently, the E2E test (test_notepad_broken_fix.py) handles the broken/fix
logic inline by manipulating the output file directly. These scripts are
provided as templates for more sophisticated broken-scenario simulation.
"""


def main_broken():
    """Broken version: simulates a scenario where save doesn't work correctly.

    In a real implementation, this might:
    - Use AutoHotkey to dismiss the save dialog prematurely
    - Redirect the save to a wrong path
    - Corrupt the file content after save

    Currently a placeholder — see test_notepad_broken_fix.py for the actual
    broken-scenario simulation logic.
    """
    print("notepad_target_broken: Simulating broken save behavior")
    print("(placeholder — actual logic in test_notepad_broken_fix.py)")


if __name__ == "__main__":
    main_broken()
