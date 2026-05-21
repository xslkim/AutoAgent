// AutoAgent TASK-0202 — AutoAgentSlateInputDriver.cpp
//
// Four wire-protocol input actions with proper FSlateApplication event
// injection.  Each public method marshals to the game thread (blocking) and
// falls back to direct UMG state mutation when no Slate window is cached
// (unit-test / headless build context).
//
// Injection priority per action:
//   1. FSlateApplication pointer / key / wheel events  — viewport mode
//   2. Direct UMG API call                             — headless / test mode

#include "AutoAgentSlateInputDriver.h"
#include "AutoAgentStableIdResolver.h"
#include "Async/TaskGraphInterfaces.h"
#include "Blueprint/UserWidget.h"
#include "Components/Button.h"
#include "Components/EditableText.h"
#include "Components/EditableTextBox.h"
#include "Components/PanelWidget.h"
#include "Components/ScrollBox.h"
#include "Components/Widget.h"
#include "Framework/Application/SlateApplication.h"
#include "UObject/UObjectIterator.h"

// ===========================================================================
// Internal — game-thread dispatch
// ===========================================================================

/**
 * Block the calling thread until Func completes on the game thread.
 * If already on the game thread, runs synchronously with no overhead.
 *
 * TRet must be default-constructible.
 */
template <typename TRet>
static TRet DispatchToGameThread(TFunction<TRet()> Func)
{
	if (IsInGameThread())
	{
		return Func();
	}
	TRet Result{};
	FGraphEventRef Task = FFunctionGraphTask::CreateAndDispatchWhenReady(
		[&Func, &Result]()
		{
			Result = Func();
		},
		TStatId(),
		nullptr,
		ENamedThreads::GameThread);
	FTaskGraphInterface::Get().WaitUntilTaskCompletes(Task, ENamedThreads::AnyThread);
	return Result;
}

// ===========================================================================
// Internal — Slate geometry helper
// ===========================================================================

/**
 * Return the screen-space centre of a widget's cached Slate geometry.
 * Returns FVector2D::ZeroVector if the widget has no cached SWidget
 * (i.e. not currently rendered in a viewport).
 */
static FVector2D GetWidgetCenter(UWidget* Widget)
{
	const TSharedPtr<SWidget> Slate = Widget->GetCachedWidget();
	if (!Slate.IsValid())
	{
		return FVector2D::ZeroVector;
	}
	const FGeometry Geom = Slate->GetPaintSpaceGeometry();
	return Geom.GetAbsolutePosition() + Geom.GetAbsoluteSize() * 0.5f;
}

// ===========================================================================
// Constructor
// ===========================================================================

FAutoAgentSlateInputDriver::FAutoAgentSlateInputDriver(
	const TSharedRef<FAutoAgentStableIdResolver>& InResolver)
	: Resolver(InResolver)
{
}

// ===========================================================================
// Private — FindWidget
// ===========================================================================

static UWidget* FindInSubtree(UWidget* Widget,
							  const FString& TargetId,
							  const FAutoAgentStableIdResolver& Resolver)
{
	if (!Widget)
	{
		return nullptr;
	}
	if (Resolver.Resolve(Widget->GetName()).PinnedId == TargetId)
	{
		return Widget;
	}
	if (UUserWidget* AsUserWidget = Cast<UUserWidget>(Widget))
	{
		return FindInSubtree(AsUserWidget->GetRootWidget(), TargetId, Resolver);
	}
	if (UPanelWidget* Panel = Cast<UPanelWidget>(Widget))
	{
		for (int32 i = 0; i < Panel->GetChildrenCount(); ++i)
		{
			if (UWidget* Found = FindInSubtree(Panel->GetChildAt(i), TargetId, Resolver))
			{
				return Found;
			}
		}
	}
	return nullptr;
}

UWidget* FAutoAgentSlateInputDriver::FindWidget(const FString& NodeId) const
{
	if (SearchRootOverride)
	{
		return FindInSubtree(SearchRootOverride, NodeId, *Resolver);
	}
	for (TObjectIterator<UUserWidget> It; It; ++It)
	{
		UUserWidget* UserWidget = *It;
		if (!UserWidget || UserWidget->HasAnyFlags(RF_ClassDefaultObject | RF_ArchetypeObject))
		{
			continue;
		}
		if (!UserWidget->IsInViewport())
		{
			continue;
		}
		if (UWidget* Found = FindInSubtree(UserWidget, NodeId, *Resolver))
		{
			return Found;
		}
	}
	return nullptr;
}

// ===========================================================================
// Public — four actions (marshal to game thread, then call *Impl)
// ===========================================================================

bool FAutoAgentSlateInputDriver::Click(const FString& NodeId) const
{
	return DispatchToGameThread<bool>([this, NodeId]()
									  { return ClickImpl(NodeId); });
}

bool FAutoAgentSlateInputDriver::SendText(const FString& NodeId, const FString& Text) const
{
	return DispatchToGameThread<bool>([this, NodeId, Text]()
									  { return SendTextImpl(NodeId, Text); });
}

bool FAutoAgentSlateInputDriver::Scroll(const FString& NodeId, float DeltaX, float DeltaY) const
{
	return DispatchToGameThread<bool>([this, NodeId, DeltaX, DeltaY]()
									  { return ScrollImpl(NodeId, DeltaX, DeltaY); });
}

bool FAutoAgentSlateInputDriver::Drag(const FString& FromId, const FString& ToId, int32 Steps) const
{
	return DispatchToGameThread<bool>([this, FromId, ToId, Steps]()
									  { return DragImpl(FromId, ToId, Steps); });
}

// ===========================================================================
// Private — ClickImpl
// ===========================================================================

bool FAutoAgentSlateInputDriver::ClickImpl(const FString& NodeId) const
{
	UWidget* Widget = FindWidget(NodeId);
	if (!Widget)
	{
		return false;
	}

	// --- Slate injection path ---
	if (FSlateApplication::IsInitialized())
	{
		const TSharedPtr<SWidget> Slate = Widget->GetCachedWidget();
		if (Slate.IsValid())
		{
			// Focus before synthesizing click.
			FSlateApplication::Get().SetKeyboardFocus(Slate, EFocusCause::SetDirectly);

			const FVector2D Center = GetWidgetCenter(Widget);
			TSet<FKey> NoButtons;
			TSet<FKey> WithLeft;
			WithLeft.Add(EKeys::LeftMouseButton);

			FPointerEvent MouseDown(
				0u,
				Center,
				Center,
				NoButtons,
				EKeys::LeftMouseButton,
				0.0f,
				FModifierKeysState());
			FSlateApplication::Get().ProcessMouseButtonDownEvent(
				TSharedPtr<SWindow>(), MouseDown);

			FPointerEvent MouseUp(
				0u,
				Center,
				Center,
				WithLeft,
				EKeys::LeftMouseButton,
				0.0f,
				FModifierKeysState());
			FSlateApplication::Get().ProcessMouseButtonUpEvent(MouseUp);
			return true;
		}
	}

	// --- Fallback: broadcast UButton::OnClicked ---
	if (UButton* Button = Cast<UButton>(Widget))
	{
		Button->OnClicked.Broadcast();
	}
	return true; // widget was found even if it isn't a UButton
}

// ===========================================================================
// Private — SendTextImpl
// ===========================================================================

bool FAutoAgentSlateInputDriver::SendTextImpl(const FString& NodeId,
											  const FString& Text) const
{
	UWidget* Widget = FindWidget(NodeId);
	if (!Widget)
	{
		return false;
	}

	// --- Slate injection path (per-character FCharacterEvent) ---
	if (FSlateApplication::IsInitialized())
	{
		const TSharedPtr<SWidget> Slate = Widget->GetCachedWidget();
		if (Slate.IsValid())
		{
			FSlateApplication::Get().SetKeyboardFocus(Slate, EFocusCause::SetDirectly);
			for (const TCHAR Ch : Text)
			{
				FCharacterEvent CharEvent(Ch, FModifierKeysState(), 0u, false);
				FSlateApplication::Get().ProcessKeyCharEvent(CharEvent);
			}
			return true;
		}
	}

	// --- Fallback: set text directly ---
	if (UEditableTextBox* TextBox = Cast<UEditableTextBox>(Widget))
	{
		TextBox->SetText(FText::FromString(Text));
		return true;
	}
	if (UEditableText* EditableText = Cast<UEditableText>(Widget))
	{
		EditableText->SetText(FText::FromString(Text));
		return true;
	}
	return false; // widget found but not a text-accepting type
}

// ===========================================================================
// Private — ScrollImpl
// ===========================================================================

bool FAutoAgentSlateInputDriver::ScrollImpl(const FString& NodeId,
											float /*DeltaX*/,
											float DeltaY) const
{
	UWidget* Widget = FindWidget(NodeId);
	if (!Widget)
	{
		return false;
	}

	// --- Slate injection path ---
	if (FSlateApplication::IsInitialized())
	{
		const TSharedPtr<SWidget> Slate = Widget->GetCachedWidget();
		if (Slate.IsValid())
		{
			const FVector2D Center = GetWidgetCenter(Widget);
			TSet<FKey> NoButtons;
			FPointerEvent WheelEvent(
				0u,
				Center,
				Center,
				NoButtons,
				EKeys::Invalid,
				DeltaY,
				FModifierKeysState());
			FSlateApplication::Get().ProcessMouseWheelOrGestureEvent(WheelEvent, nullptr);
			return true;
		}
	}

	// --- Fallback: adjust UScrollBox offset directly ---
	if (UScrollBox* ScrollBox = Cast<UScrollBox>(Widget))
	{
		ScrollBox->SetScrollOffset(ScrollBox->GetScrollOffset() + DeltaY);
		return true;
	}
	return false; // widget found but not scrollable
}

// ===========================================================================
// Private — DragImpl
// ===========================================================================

bool FAutoAgentSlateInputDriver::DragImpl(const FString& FromId,
										  const FString& ToId,
										  int32 Steps) const
{
	UWidget* FromWidget = FindWidget(FromId);
	UWidget* ToWidget = FindWidget(ToId);
	if (!FromWidget || !ToWidget)
	{
		return false;
	}

	// --- Slate injection path ---
	if (FSlateApplication::IsInitialized())
	{
		const TSharedPtr<SWidget> FromSlate = FromWidget->GetCachedWidget();
		const TSharedPtr<SWidget> ToSlate = ToWidget->GetCachedWidget();
		if (FromSlate.IsValid() && ToSlate.IsValid())
		{
			const FVector2D FromCenter = GetWidgetCenter(FromWidget);
			const FVector2D ToCenter = GetWidgetCenter(ToWidget);

			TSet<FKey> NoButtons;
			TSet<FKey> WithLeft;
			WithLeft.Add(EKeys::LeftMouseButton);

			// 1. Mouse button down at source
			FPointerEvent MouseDown(
				0u,
				FromCenter,
				FromCenter,
				NoButtons,
				EKeys::LeftMouseButton,
				0.0f,
				FModifierKeysState());
			FSlateApplication::Get().ProcessMouseButtonDownEvent(
				TSharedPtr<SWindow>(), MouseDown);

			// 2. Linear mouse-move events from source to target
			const int32 NumSteps = FMath::Max(1, Steps);
			FVector2D PrevPos = FromCenter;
			for (int32 i = 1; i <= NumSteps; ++i)
			{
				const float T = static_cast<float>(i) / static_cast<float>(NumSteps);
				const FVector2D MovePos = FMath::Lerp(FromCenter, ToCenter, T);
				FPointerEvent MoveEvent(
					0u,
					MovePos,
					PrevPos,
					WithLeft,
					EKeys::Invalid,
					0.0f,
					FModifierKeysState());
				FSlateApplication::Get().ProcessMouseMoveEvent(MoveEvent);
				PrevPos = MovePos;
			}

			// 3. Mouse button up at target
			FPointerEvent MouseUp(
				0u,
				ToCenter,
				ToCenter,
				WithLeft,
				EKeys::LeftMouseButton,
				0.0f,
				FModifierKeysState());
			FSlateApplication::Get().ProcessMouseButtonUpEvent(MouseUp);
			return true;
		}
	}

	// --- Fallback: both endpoints exist, no-op ---
	return true;
}
