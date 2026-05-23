#pragma once

#include "CoreMinimal.h"

class UWidget;
class FAutoAgentStableIdResolver;

/**
 * Executes the four wire-protocol input actions on UMG widgets located by
 * their stable id.
 *
 * Thread safety
 * -------------
 * All public methods marshal to the game thread internally using a blocking
 * dispatch (FFunctionGraphTask + WaitUntilTaskCompletes).  Callers on any
 * thread are safe; the call blocks until the action completes on the game
 * thread and returns.
 *
 * Input path (priority order per action)
 * ---------------------------------------
 * 1. FindWidget          — locate UWidget by stable id via StableIdResolver.
 * 2. FSlateApplication   — event injection when the widget has a cached
 *    SWidget (i.e. it is part of a visible viewport hierarchy).
 * 3. Direct UMG API      — fallback for headless / unit-test contexts where
 *    no Slate window is rendered (GetCachedWidget() returns null).
 */
class FAutoAgentSlateInputDriver
{
public:
	explicit FAutoAgentSlateInputDriver(
		const TSharedRef<FAutoAgentStableIdResolver>& InResolver);

	/**
	 * Click a widget.
	 *
	 * @param InputLayer  "engine" (default): FSlateApplication injection;
	 *                    "os": OS-level SendInput / CGEventPost / XTest.
	 * @param Button      "left" (default), "right", or "middle".
	 */
	bool Click(const FString& NodeId,
	           const FString& InputLayer = TEXT("engine"),
	           const FString& Button     = TEXT("left")) const;

	/** See Click. */
	bool SendText(const FString& NodeId, const FString& Text) const;

	/** See Click. */
	bool Scroll(const FString& NodeId, float DeltaX, float DeltaY) const;

	/**
	 * Drag from FromId to ToId.
	 * @param Steps  Move events along the straight-line path (min 1; default 8).
	 */
	bool Drag(const FString& FromId, const FString& ToId,
	          int32 Steps = 8,
	          const FString& InputLayer = TEXT("engine")) const;

	/**
	 * Send a key-press event to a widget.
	 * Supported keys: Enter/Return/Submit, Escape/Esc/Cancel, Tab, Shift+Tab.
	 * @param InputLayer  "engine": FSlateApplication OnKeyDown/Up;
	 *                    "os": OS-level virtual-key injection.
	 */
	bool KeyPress(const FString& NodeId, const FString& Key,
	              const FString& InputLayer = TEXT("engine")) const;

	/** Test seam: when set, FindWidget searches this subtree instead of the
	    on-screen user widgets. */
	void SetSearchRootOverride(UWidget* Root) { SearchRootOverride = Root; }

private:
	UWidget* FindWidget(const FString& NodeId) const;
	FVector2D GetWidgetCenter(UWidget* Widget) const;

	// Game-thread implementations.
	bool ClickImpl(const FString& NodeId, const FString& InputLayer,
	               const FString& Button) const;
	bool SendTextImpl(const FString& NodeId, const FString& Text) const;
	bool ScrollImpl(const FString& NodeId, float DeltaX, float DeltaY) const;
	bool DragImpl(const FString& FromId, const FString& ToId, int32 Steps,
	              const FString& InputLayer) const;
	bool KeyPressImpl(const FString& NodeId, const FString& Key,
	                  const FString& InputLayer) const;

	TSharedRef<FAutoAgentStableIdResolver> Resolver;
	UWidget* SearchRootOverride = nullptr;
};
