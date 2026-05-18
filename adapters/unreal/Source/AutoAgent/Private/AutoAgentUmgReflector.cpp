#include "AutoAgentUmgReflector.h"
#include "AutoAgentStableIdResolver.h"
#include "Blueprint/UserWidget.h"
#include "Components/PanelWidget.h"
#include "Components/Widget.h"
#include "UObject/UObjectIterator.h"
#include "Dom/JsonObject.h"

FAutoAgentUmgReflector::FAutoAgentUmgReflector(
	const TSharedRef<FAutoAgentStableIdResolver>& InResolver)
	: Resolver(InResolver)
{
}

TArray<TSharedPtr<FJsonValue>> FAutoAgentUmgReflector::DumpTree() const
{
	TArray<TSharedPtr<FJsonValue>> Nodes;
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
		WalkWidget(UserWidget, FString(), Nodes);
	}
	return Nodes;
}

static TSharedPtr<FJsonValue> MakeNum(double V)
{
	return MakeShared<FJsonValueNumber>(V);
}

FString FAutoAgentUmgReflector::WalkWidget(UWidget* Widget, const FString& ParentId,
	TArray<TSharedPtr<FJsonValue>>& Out) const
{
	if (!Widget)
	{
		return FString();
	}

	const FString Name = Widget->GetName();
	const FAutoAgentResolvedId Resolved = Resolver->Resolve(Name);
	const FString NodeId = Resolved.PinnedId;

	TSharedPtr<FJsonObject> Node = MakeShared<FJsonObject>();
	Node->SetStringField(TEXT("id"), NodeId);
	Node->SetStringField(TEXT("type"), Widget->GetClass()->GetName());
	Node->SetStringField(TEXT("engine_type"), Widget->GetClass()->GetName());
	if (ParentId.IsEmpty())
	{
		Node->SetField(TEXT("parent_id"), MakeShared<FJsonValueNull>());
	}
	else
	{
		Node->SetStringField(TEXT("parent_id"), ParentId);
	}
	Node->SetStringField(TEXT("stable_id_source"),
		Resolved.bPinned ? TEXT("pinned") : TEXT("auto"));

	// --- visual ---
	const FGeometry& Geo = Widget->GetCachedGeometry();
	const FVector2D Size = Geo.GetLocalSize();
	const FVector2D Pos = Geo.GetAbsolutePosition();

	TSharedPtr<FJsonObject> Visual = MakeShared<FJsonObject>();
	Visual->SetArrayField(TEXT("position"), { MakeNum(Pos.X), MakeNum(Pos.Y) });
	Visual->SetArrayField(TEXT("size"), { MakeNum(Size.X), MakeNum(Size.Y) });
	Visual->SetBoolField(TEXT("visible"), Widget->IsVisible());
	Visual->SetArrayField(TEXT("world_bounds"),
		{ MakeNum(Pos.X), MakeNum(Pos.Y), MakeNum(Pos.X + Size.X), MakeNum(Pos.Y + Size.Y) });
	Node->SetObjectField(TEXT("visual"), Visual);

	// --- meta ---
	const TMap<FString, FString> Sprites = Resolver->GetStateSprites(Name);
	if (!Resolved.LogicalRole.IsEmpty() || Sprites.Num() > 0)
	{
		TSharedPtr<FJsonObject> Meta = MakeShared<FJsonObject>();
		if (!Resolved.LogicalRole.IsEmpty())
		{
			Meta->SetStringField(TEXT("logical_role"), Resolved.LogicalRole);
		}
		if (Sprites.Num() > 0)
		{
			TSharedPtr<FJsonObject> SpritesObj = MakeShared<FJsonObject>();
			for (const TPair<FString, FString>& KV : Sprites)
			{
				SpritesObj->SetStringField(KV.Key, KV.Value);
			}
			Meta->SetObjectField(TEXT("state_sprites"), SpritesObj);
		}
		Node->SetObjectField(TEXT("meta"), Meta);
	}

	// Append parent before children so the flat list is breadth-friendly.
	Out.Add(MakeShared<FJsonValueObject>(Node));

	// --- children ---
	TArray<TSharedPtr<FJsonValue>> ChildIds;
	if (UUserWidget* AsUserWidget = Cast<UUserWidget>(Widget))
	{
		if (UWidget* Root = AsUserWidget->GetRootWidget())
		{
			const FString ChildId = WalkWidget(Root, NodeId, Out);
			if (!ChildId.IsEmpty())
			{
				ChildIds.Add(MakeShared<FJsonValueString>(ChildId));
			}
		}
	}
	else if (UPanelWidget* Panel = Cast<UPanelWidget>(Widget))
	{
		for (int32 i = 0; i < Panel->GetChildrenCount(); ++i)
		{
			const FString ChildId = WalkWidget(Panel->GetChildAt(i), NodeId, Out);
			if (!ChildId.IsEmpty())
			{
				ChildIds.Add(MakeShared<FJsonValueString>(ChildId));
			}
		}
	}
	Node->SetArrayField(TEXT("children_ids"), ChildIds);

	return NodeId;
}
