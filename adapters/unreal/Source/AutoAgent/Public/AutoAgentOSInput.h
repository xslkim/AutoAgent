#pragma once

#include "CoreMinimal.h"

/**
 * Platform-specific OS-level input injection.
 *
 * Each static method switches on the current platform (#if PLATFORM_WINDOWS /
 * PLATFORM_MAC / PLATFORM_LINUX) and calls the matching native API:
 *   - Windows: SendInput (user32.dll)
 *   - macOS:   CGEventPost (CoreGraphics)
 *   - Linux:   XTest (libX11 / libXtst)
 *
 * Coordinate convention
 * ---------------------
 * All methods accept screen-space coordinates with (0,0) at the top-left of
 * the primary display.  The Unity adapter's coordinate helpers (Win32, Mac,
 * Linux drivers) serve as the reference implementation.
 *
 * Window offset (non-fullscreen)
 * ------------------------------
 * The initial implementation assumes the game window fills the primary
 * display.  Precise window-offset queries (GetWindowRect / NSWindow.frame /
 * XGetWindowAttributes) can be layered on later.
 */
struct FAutoAgentOSInput
{
	/** Inject a mouse click at *ScreenPos* (display coords, top-left origin). */
	static void Click(FVector2D ScreenPos, const FString& Button = TEXT("left"));

	/**
	 * Multi-step drag from *From* to *To*, holding the left button.
	 * *DurationMs* is spread across *Steps* equally-spaced motion events.
	 */
	static void Drag(FVector2D From, FVector2D To, int32 DurationMs = 100, int32 Steps = 8);

	/** Inject a mouse-wheel event at *ScreenPos*.  Positive *Delta* = up. */
	static void Scroll(FVector2D ScreenPos, float Delta);

	/** Inject a virtual-key press (key-down followed by key-up). */
	static void KeyPress(int32 VkCode);

	/** Inject Shift+Tab (Shift-down, Tab-down, Tab-up, Shift-up). */
	static void ShiftTab();

	/** Map a protocol key string to a platform virtual-key code. */
	static int32 MapKey(const FString& Key);

	// ---- key-code constants ----
	static constexpr int32 VK_RETURN = 0x0D;
	static constexpr int32 VK_ESCAPE = 0x1B;
	static constexpr int32 VK_TAB = 0x09;
	static constexpr int32 VK_SHIFT = 0x10;

	static constexpr int32 CGKEY_RETURN = 0x24;
	static constexpr int32 CGKEY_ESCAPE = 0x35;
	static constexpr int32 CGKEY_TAB = 0x30;
	static constexpr int32 CGKEY_LSHIFT = 0x38;

	static constexpr int32 XK_RETURN = 36;
	static constexpr int32 XK_ESCAPE = 9;
	static constexpr int32 XK_TAB = 23;
	static constexpr int32 XK_LSHIFT = 50;
};
