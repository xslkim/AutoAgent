// AutoAgent TASK-0205 — AutoAgentIdCustomization.cpp
//
// Details Panel customization for UWidget subclasses.
// Read-only: this file never writes visual properties on game objects.

#include "AutoAgentIdCustomization.h"
#include "AutoAgentStableIdResolver.h"
#include "Components/Widget.h"
#include "DetailCategoryBuilder.h"
#include "DetailLayoutBuilder.h"
#include "DetailWidgetRow.h"
#include "UObject/UObjectIterator.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Text/STextBlock.h"

#if WITH_METADATA
#include "UObject/Class.h"
#include "UObject/Field.h"
#endif

// ===========================================================================
// MakeInstance
// ===========================================================================

TSharedRef<IDetailCustomization> FAutoAgentIdCustomization::MakeInstance()
{
	return MakeShared<FAutoAgentIdCustomization>();
}

// ===========================================================================
// CustomizeDetails
// ===========================================================================

void FAutoAgentIdCustomization::CustomizeDetails(IDetailLayoutBuilder& DetailBuilder)
{
	// Only customise single-object selection to keep the UI uncluttered.
	TArray<TWeakObjectPtr<UObject>> Objects;
	DetailBuilder.GetObjectsBeingCustomized(Objects);
	if (Objects.Num() != 1)
	{
		return;
	}
	UWidget* Widget = Cast<UWidget>(Objects[0].Get());
	if (!Widget)
	{
		return;
	}

	// Resolve the stable ID for this widget.
	// Load() performs file I/O and a reflection scan; acceptable for an
	// editor-only Details panel refresh (not called on every frame).
	FAutoAgentStableIdResolver Resolver;
	Resolver.Load();
	const FAutoAgentResolvedId Resolved = Resolver.Resolve(Widget->GetName());

	// Source → human-readable label
	auto SourceLabel = [](EAutoAgentIdSource Src) -> FText
	{
		switch (Src)
		{
		case EAutoAgentIdSource::Ini:
			return FText::FromString(TEXT("Ini  (Config/AutoAgentIds.ini)"));
		case EAutoAgentIdSource::PropertyMeta:
			return FText::FromString(TEXT("PropertyMeta  (UPROPERTY meta=(AutoAgentId=...))"));
		case EAutoAgentIdSource::Runtime:
			return FText::FromString(TEXT("Runtime  (RegisterRuntime)"));
		default:
			return FText::FromString(TEXT("Auto  (unpinned — falls back to widget name)"));
		}
	};

	// Colour: green for explicitly pinned, amber for auto-fallback.
	const FSlateColor IdColor = Resolved.bPinned
									? FSlateColor(FLinearColor(0.2f, 0.9f, 0.3f))
									: FSlateColor(FLinearColor(0.9f, 0.7f, 0.1f));

	IDetailCategoryBuilder& Category = DetailBuilder.EditCategory(
		"AutoAgent",
		FText::FromString(TEXT("AutoAgent Stable ID")),
		ECategoryPriority::Uncommon);

	// ---- Row: Stable ID ------------------------------------------------
	Category.AddCustomRow(FText::FromString(TEXT("Stable ID")))
		.NameContent()
			[SNew(STextBlock)
				 .Text(FText::FromString(TEXT("Stable ID")))
				 .Font(DetailBuilder.GetDetailFont())]
		.ValueContent()
		.MinDesiredWidth(200.0f)
			[SNew(STextBlock)
				 .Text(FText::FromString(Resolved.PinnedId))
				 .ColorAndOpacity(IdColor)
				 .Font(DetailBuilder.GetDetailFont())];

	// ---- Row: Source ---------------------------------------------------
	Category.AddCustomRow(FText::FromString(TEXT("ID Source")))
		.NameContent()
			[SNew(STextBlock)
				 .Text(FText::FromString(TEXT("Source")))
				 .Font(DetailBuilder.GetDetailFont())]
		.ValueContent()
		.MinDesiredWidth(200.0f)
			[SNew(STextBlock)
				 .Text(SourceLabel(Resolved.Source))
				 .Font(DetailBuilder.GetDetailFont())];

	// ---- Row: Logical Role (only shown when non-empty) -----------------
	if (!Resolved.LogicalRole.IsEmpty())
	{
		Category.AddCustomRow(FText::FromString(TEXT("Logical Role")))
			.NameContent()
				[SNew(STextBlock)
					 .Text(FText::FromString(TEXT("Logical Role")))
					 .Font(DetailBuilder.GetDetailFont())]
			.ValueContent()
				[SNew(STextBlock)
					 .Text(FText::FromString(Resolved.LogicalRole))
					 .Font(DetailBuilder.GetDetailFont())];
	}

	// ---- Row: Scan button ----------------------------------------------
	Category.AddCustomRow(FText::FromString(TEXT("Scan Unpinned")))
		.WholeRowContent()
			[SNew(SButton)
				 .Text(FText::FromString(TEXT("Scan Unpinned Widget Properties")))
				 .ToolTipText(FText::FromString(
					 TEXT("Scans all loaded UWidget-derived classes for BindWidget UPROPERTY "
						  "entries that have no pinned AutoAgent stable ID and writes the "
						  "results to the Output Log.")))
				 .OnClicked(FOnClicked::CreateStatic(
					 &FAutoAgentIdCustomization::OnScanUnpinnedClicked))];
}

// ===========================================================================
// OnScanUnpinnedClicked
// ===========================================================================

FReply FAutoAgentIdCustomization::OnScanUnpinnedClicked()
{
	FAutoAgentStableIdResolver Resolver;
	Resolver.Load();

	TArray<FString> Unpinned;

#if WITH_METADATA
	for (TObjectIterator<UClass> ClassIt; ClassIt; ++ClassIt)
	{
		UClass* Class = *ClassIt;
		if (!Class || !Class->IsChildOf(UWidget::StaticClass()))
		{
			continue;
		}
		if (Class->HasAnyClassFlags(CLASS_Abstract))
		{
			continue;
		}

		for (TFieldIterator<FProperty> PropIt(Class, EFieldIteratorFlags::ExcludeSuper);
			 PropIt;
			 ++PropIt)
		{
			// Only report BindWidget / BindWidgetOptional properties — these are
			// the ones the AI accesses by stable ID at runtime.
			if (!PropIt->HasMetaData(TEXT("BindWidget")) &&
				!PropIt->HasMetaData(TEXT("BindWidgetOptional")))
			{
				continue;
			}

			const FString PropName = PropIt->GetName();
			const FAutoAgentResolvedId Resolved = Resolver.Resolve(PropName);
			if (!Resolved.bPinned)
			{
				Unpinned.Add(
					FString::Printf(TEXT("%s::%s"), *Class->GetName(), *PropName));
			}
		}
	}
#endif // WITH_METADATA

	if (Unpinned.IsEmpty())
	{
		UE_LOG(LogTemp, Log, TEXT("[AutoAgent] Scan complete — all BindWidget properties have pinned IDs."));
	}
	else
	{
		UE_LOG(LogTemp, Warning, TEXT("[AutoAgent] Scan complete — %d unpinned BindWidget properties:"), Unpinned.Num());
		for (const FString& Entry : Unpinned)
		{
			UE_LOG(LogTemp, Warning, TEXT("  [UNPINNED]  %s"), *Entry);
		}
		UE_LOG(LogTemp, Warning, TEXT("[AutoAgent] Fix: add +Id=(...) to Config/AutoAgentIds.ini  OR  "
									  "use UPROPERTY(meta=(AutoAgentId=\"...\"))"));
	}

	return FReply::Handled();
}
