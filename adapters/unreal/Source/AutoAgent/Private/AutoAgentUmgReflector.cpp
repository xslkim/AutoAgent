// AutoAgent TASK-0200 — AutoAgentUmgReflector.cpp
// AUTOAGENT_ALLOW_VISUAL — reflector reads visual properties (color, alpha,
// position, visibility) from the live widget tree; no writes occur here.
//
// Produces a flat JSON array (AutoAgent protocol dump_tree) for every
// on-screen UUserWidget.  One node per UWidget; parent_id linkage forms the
// logical tree.
//
// Visual fields:  position, size, visible, world_bounds, color, alpha, sprite_ref
// Behavior fields: interactable, attached_components
// Meta fields:    logical_role, state_sprites (from AutoAgentIds.ini)
//
// Traversal order: depth-first from each top-level UUserWidget's root widget.
// Duplicate detection via TSet<FString> Visited prevents double-emitting nodes
// that appear as both a UUserWidget entry-point AND a child in a parent walk.

#include "AutoAgentUmgReflector.h"
#include "AutoAgentStableIdResolver.h"

#include "Blueprint/UserWidget.h"
#include "Blueprint/WidgetBlueprintLibrary.h"
#include "Components/PanelWidget.h"
#include "Components/ContentWidget.h"
#include "Components/NamedSlot.h"
#include "Components/Widget.h"
#include "Components/Image.h"

#include "Dom/JsonObject.h"
#include "Engine/Engine.h"

// ---------------------------------------------------------------------------
// Constructor
// ---------------------------------------------------------------------------

FAutoAgentUmgReflector::FAutoAgentUmgReflector(
	const TSharedRef<FAutoAgentStableIdResolver>& InResolver)
	: Resolver(InResolver)
{
}

// ---------------------------------------------------------------------------
// DumpTree — entry point
// ---------------------------------------------------------------------------

TArray<TSharedPtr<FJsonValue>> FAutoAgentUmgReflector::DumpTree() const
{
	TArray<TSharedPtr<FJsonValue>> Nodes;
	TSet<FString> Visited;

	// Prefer UWidgetBlueprintLibrary when a game world is available; fall back
	// to TObjectIterator (works in unit-test contexts without a full world).
	UWorld* World = (GEngine && GEngine->GameViewport) ? GEngine->GameViewport->GetWorld() : nullptr;
	if (World)
	{
		TArray<UUserWidget*> Widgets;
		UWidgetBlueprintLibrary::GetAllWidgetsOfClass(
			World, Widgets, UUserWidget::StaticClass(), /*bTopLevelOnly=*/true);

		for (UUserWidget* UserWidget : Widgets)
		{
			if (!UserWidget || !UserWidget->IsInViewport())
			{
				continue;
			}
			WalkWidget(UserWidget, FString(), Nodes, Visited);
		}
	}
	else
	{
		// Unit-test / editor fallback: TObjectIterator
		for (TObjectIterator<UUserWidget> It; It; ++It)
		{
			UUserWidget* UserWidget = *It;
			if (!UserWidget ||
				UserWidget->HasAnyFlags(RF_ClassDefaultObject | RF_ArchetypeObject) ||
				!UserWidget->IsInViewport())
			{
				continue;
			}
			WalkWidget(UserWidget, FString(), Nodes, Visited);
		}
	}

	return Nodes;
}

// ---------------------------------------------------------------------------
// JSON helpers
// ---------------------------------------------------------------------------

static TSharedPtr<FJsonValue> MakeNum(double V)
{
	return MakeShared<FJsonValueNumber>(V);
}

static TSharedPtr<FJsonValue> MakeStr(const FString& S)
{
	return MakeShared<FJsonValueString>(S);
}

// ---------------------------------------------------------------------------
// WalkWidget — recursive core
// ---------------------------------------------------------------------------

FString FAutoAgentUmgReflector::WalkWidget(UWidget* Widget, const FString& ParentId, TArray<TSharedPtr<FJsonValue>>& Out, TSet<FString>& Visited) const
{
	if (!Widget)
	{
		return FString();
	}

	const FString Name = Widget->GetName();
	const FAutoAgentResolvedId Resolved = Resolver->Resolve(Name);
	const FString NodeId = Resolved.PinnedId;

	// --- Duplicate guard -------------------------------------------------------
	// A nested UUserWidget can appear both as a top-level entry point AND as
	// a child during a parent walk; emit only the first occurrence.
	if (Visited.Contains(NodeId))
	{
		return NodeId; // still return the ID so children_ids linkage is correct
	}
	Visited.Add(NodeId);

	// --- Base node object -------------------------------------------------------
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

	// --- visual ----------------------------------------------------------------
	const FGeometry& Geo = Widget->GetCachedGeometry();
	const FVector2D Size = Geo.GetLocalSize();
	const FVector2D AbsPos = Geo.GetAbsolutePosition();

	TSharedPtr<FJsonObject> Visual = MakeShared<FJsonObject>();
	Visual->SetArrayField(TEXT("position"), {MakeNum(AbsPos.X), MakeNum(AbsPos.Y)});
	Visual->SetArrayField(TEXT("size"), {MakeNum(Size.X), MakeNum(Size.Y)});
	Visual->SetBoolField(TEXT("visible"), Widget->IsVisible());
	Visual->SetArrayField(TEXT("world_bounds"),
						  {MakeNum(AbsPos.X), MakeNum(AbsPos.Y), MakeNum(AbsPos.X + Size.X), MakeNum(AbsPos.Y + Size.Y)});

	// color + alpha: read from UImage if widget is a UImage;
	// fall back to the widget's own render opacity.
	if (const UImage* Img = Cast<UImage>(Widget))
	{
		const FLinearColor& C = Img->GetColorAndOpacity();
		Visual->SetArrayField(TEXT("color"),
							  {MakeNum(C.R), MakeNum(C.G), MakeNum(C.B), MakeNum(C.A)});
		Visual->SetNumberField(TEXT("alpha"), static_cast<double>(C.A));

		// sprite_ref: the texture asset path (empty if no texture)
		const FSlateBrush& Brush = Img->GetBrush();
		if (const UObject* Resource = Brush.GetResourceObject())
		{
			Visual->SetStringField(TEXT("sprite_ref"), Resource->GetPathName());
		}
		else
		{
			Visual->SetField(TEXT("sprite_ref"), MakeShared<FJsonValueNull>());
		}
	}
	else
	{
		// Non-image widget: no color/sprite_ref; alpha from render opacity
		const float Opacity = Widget->GetRenderOpacity();
		Visual->SetArrayField(TEXT("color"),
							  {MakeNum(1.0), MakeNum(1.0), MakeNum(1.0), MakeNum(Opacity)});
		Visual->SetNumberField(TEXT("alpha"), static_cast<double>(Opacity));
		Visual->SetField(TEXT("sprite_ref"), MakeShared<FJsonValueNull>());
	}

	Node->SetObjectField(TEXT("visual"), Visual);

	// --- behavior --------------------------------------------------------------
	TSharedPtr<FJsonObject> Behavior = MakeShared<FJsonObject>();
	// interactable: widget is enabled (user-interaction enabled) and visible
	Behavior->SetBoolField(TEXT("interactable"),
						   Widget->GetIsEnabled() && Widget->IsVisible());
	// attached_components: AI-added child widgets of "behavior" types
	// (e.g. UButton, UEditableTextBox) are listed by their class names.
	// We collect direct children that are interactive widget types.
	TArray<TSharedPtr<FJsonValue>> AttachedComponents;
	{
		static const TArray<FName> BehaviorClasses = {
			TEXT("Button"),
			TEXT("EditableTextBox"),
			TEXT("EditableText"),
			TEXT("CheckBox"),
			TEXT("Slider"),
			TEXT("ComboBoxString"),
			TEXT("ScrollBox"),
			TEXT("ListView"),
			TEXT("SpinBox"),
		};
		auto IsInteractiveClass = [&](UWidget* Child) -> bool
		{
			if (!Child)
				return false;
			const FName ClassName = Child->GetClass()->GetFName();
			for (const FName& BName : BehaviorClasses)
			{
				if (ClassName == BName)
					return true;
			}
			return false;
		};
		// Check direct children via PanelWidget or ContentWidget
		if (UPanelWidget* Panel = Cast<UPanelWidget>(Widget))
		{
			for (int32 i = 0; i < Panel->GetChildrenCount(); ++i)
			{
				UWidget* Child = Panel->GetChildAt(i);
				if (IsInteractiveClass(Child))
				{
					AttachedComponents.Add(MakeStr(Child->GetClass()->GetName()));
				}
			}
		}
		else if (UContentWidget* Content = Cast<UContentWidget>(Widget))
		{
			if (UWidget* Child = Content->GetContent())
			{
				if (IsInteractiveClass(Child))
				{
					AttachedComponents.Add(MakeStr(Child->GetClass()->GetName()));
				}
			}
		}
	}
	Behavior->SetArrayField(TEXT("attached_components"), AttachedComponents);
	Node->SetObjectField(TEXT("behavior"), Behavior);

	// --- meta ------------------------------------------------------------------
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

	// Emit this node before its children so the flat list is breadth-friendly.
	Out.Add(MakeShared<FJsonValueObject>(Node));

	// --- children --------------------------------------------------------------
	TArray<TSharedPtr<FJsonValue>> ChildIds;

	auto RecordChild = [&](UWidget* Child)
	{
		const FString ChildId = WalkWidget(Child, NodeId, Out, Visited);
		if (!ChildId.IsEmpty())
		{
			ChildIds.Add(MakeStr(ChildId));
		}
	};

	if (UUserWidget* AsUserWidget = Cast<UUserWidget>(Widget))
	{
		// UserWidget: descend into its WidgetTree root
		if (UWidget* Root = AsUserWidget->GetRootWidget())
		{
			RecordChild(Root);
		}
	}
	else if (UNamedSlot* NamedSlot = Cast<UNamedSlot>(Widget))
	{
		// NamedSlot: single content child (UContentWidget subclass)
		if (UWidget* Content = NamedSlot->GetContent())
		{
			RecordChild(Content);
		}
	}
	else if (UPanelWidget* Panel = Cast<UPanelWidget>(Widget))
	{
		// PanelWidget: zero or more children (VerticalBox, CanvasPanel, etc.)
		for (int32 i = 0; i < Panel->GetChildrenCount(); ++i)
		{
			RecordChild(Panel->GetChildAt(i));
		}
	}
	else if (UContentWidget* Content = Cast<UContentWidget>(Widget))
	{
		// Generic single-child ContentWidget (e.g. ScaleBox, SizeBox)
		if (UWidget* Child = Content->GetContent())
		{
			RecordChild(Child);
		}
	}

	Node->SetArrayField(TEXT("children_ids"), ChildIds);
	return NodeId;
}
