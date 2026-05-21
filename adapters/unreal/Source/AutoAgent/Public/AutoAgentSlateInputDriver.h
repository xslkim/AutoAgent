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
	 * Synthesize a left-click at the widget's screen-space centre.
	 * Injects FPointerEvent(MouseButtonDown) + FPointerEvent(MouseButtonUp)
	 * via FSlateApplication::ProcessMouseButtonDownEvent / UpEvent.
	 * Falls back to UButton::OnClicked.Broadcast() when no Slate SWidget is
	 * cached.
	 *
	 * @return false if the widget was not found; true otherwise.
	 */
	bool Click(const FString& NodeId) const;

	/**
	 * Focus the target widget and inject each character of Text via
	 * FSlateApplication::ProcessKeyCharEvent (one FCharacterEvent per TCHAR).
	 * Falls back to UEditableText(Box)::SetText() in headless / unit-test mode.
	 *
	 * @return false if the widget was not found or is not a text widget.
	 */
	bool SendText(const FString& NodeId, const FString& Text) const;

	/**
	 * Inject a mouse-wheel event at the widget's screen-space centre via
	 * FSlateApplication::ProcessMouseWheelOrGestureEvent.
	 * Falls back to UScrollBox::SetScrollOffset() when no SWidget is cached.
	 *
	 * @param DeltaX  Horizontal scroll (positive = right).
	 * @param DeltaY  Vertical scroll   (positive = up / scroll-back in UE).
	 * @return false if the widget was not found.
	 */
	bool Scroll(const FString& NodeId, float DeltaX, float DeltaY) const;

	/**
	 * Synthesize a drag gesture: mouse-down at FromId's screen centre, a
	 * linear sequence of mouse-move events, then mouse-up at ToId's centre.
	 * Falls back to a no-op (returns true) when widgets have no cached SWidget.
	 *
	 * @param Steps  Number of intermediate FPointerEvent move events along
	 *               the straight-line path (minimum 1; default 8).
	 * @return false if either widget was not found.
	 */
	bool Drag(const FString& FromId, const FString& ToId, int32 Steps = 8) const;

	/** Test seam: when set, FindWidget searches this subtree instead of the
	    on-screen user widgets. */
	void SetSearchRootOverride(UWidget* Root) { SearchRootOverride = Root; }

private:
	UWidget* FindWidget(const FString& NodeId) const;

	// Game-thread implementations — called after thread dispatch.
	bool ClickImpl(const FString& NodeId) const;
	bool SendTextImpl(const FString& NodeId, const FString& Text) const;
	bool ScrollImpl(const FString& NodeId, float DeltaX, float DeltaY) const;
	bool DragImpl(const FString& FromId, const FString& ToId, int32 Steps) const;

	TSharedRef<FAutoAgentStableIdResolver> Resolver;
	UWidget* SearchRootOverride = nullptr;
};
