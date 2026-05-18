#include "AutoAgentSlateInputDriver.h"
#include "AutoAgentStableIdResolver.h"
#include "Blueprint/UserWidget.h"
#include "Components/PanelWidget.h"
#include "Components/Widget.h"
#include "Components/Button.h"
#include "Components/EditableText.h"
#include "Components/EditableTextBox.h"
#include "Components/ScrollBox.h"
#include "UObject/UObjectIterator.h"

FAutoAgentSlateInputDriver::FAutoAgentSlateInputDriver(
	const TSharedRef<FAutoAgentStableIdResolver>& InResolver)
	: Resolver(InResolver)
{
}

// Recursively searches a widget subtree for one whose resolved id matches.
static UWidget* FindInSubtree(UWidget* Widget, const FString& TargetId,
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

bool FAutoAgentSlateInputDriver::Click(const FString& NodeId) const
{
	UWidget* Widget = FindWidget(NodeId);
	if (!Widget)
	{
		return false;
	}
	if (UButton* Button = Cast<UButton>(Widget))
	{
		Button->OnClicked.Broadcast();
	}
	return true;
}

bool FAutoAgentSlateInputDriver::SendText(const FString& NodeId, const FString& Text) const
{
	UWidget* Widget = FindWidget(NodeId);
	if (!Widget)
	{
		return false;
	}
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
	return false;
}

bool FAutoAgentSlateInputDriver::Scroll(const FString& NodeId, float /*DeltaX*/, float DeltaY) const
{
	UWidget* Widget = FindWidget(NodeId);
	if (!Widget)
	{
		return false;
	}
	if (UScrollBox* ScrollBox = Cast<UScrollBox>(Widget))
	{
		ScrollBox->SetScrollOffset(ScrollBox->GetScrollOffset() + DeltaY);
		return true;
	}
	return false;
}

bool FAutoAgentSlateInputDriver::Drag(const FString& FromId, const FString& ToId) const
{
	// PoC: confirm both endpoints resolve. Native drag-and-drop simulation
	// is deferred to Phase 1.
	return FindWidget(FromId) != nullptr && FindWidget(ToId) != nullptr;
}
