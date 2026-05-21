// AutoAgent TASK-0201 — AutoAgentStableIdResolver.cpp
//
// Three-source stable-id resolver for UMG widgets:
//   Priority (high → low): Ini > PropertyMeta > Runtime > Auto-hash
//
// Ini      — Config/AutoAgentIds.ini  (LoadFromIniRegistry)
// PropMeta — UPROPERTY(meta=(AutoAgentId=...))  (LoadFromPropertyMeta)
// Runtime  — RegisterRuntime()  called from AI-written NativeConstruct code
// Auto     — raw widget name used as fallback id (bPinned=false)

#include "AutoAgentStableIdResolver.h"
#include "Misc/CRC.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"

#if WITH_METADATA
#include "Components/Widget.h"
#include "UObject/Class.h"
#include "UObject/UObjectIterator.h"
#endif

// ===========================================================================
// Public — Load / reload
// ===========================================================================

void FAutoAgentStableIdResolver::Load()
{
	IdsByName.Empty();
	SpritesByOwner.Empty();

	// Step 1: scan UPROPERTY meta (lower priority — filled first so Ini can
	// override).
	LoadFromPropertyMeta();

	// Step 2: parse AutoAgentIds.ini (higher priority — overrides meta).
	LoadFromIniRegistry();
}

// ===========================================================================
// Public — Runtime registration
// ===========================================================================

void FAutoAgentStableIdResolver::RegisterRuntime(const FString& WidgetName,
												 const FString& PinnedId,
												 const FString& LogicalRole)
{
	// Only add if not already covered by Ini or PropertyMeta.
	if (IdsByName.Contains(WidgetName))
	{
		return;
	}
	FAutoAgentResolvedId Entry;
	Entry.PinnedId = PinnedId;
	Entry.LogicalRole = LogicalRole;
	Entry.bPinned = !PinnedId.IsEmpty();
	Entry.Source = EAutoAgentIdSource::Runtime;
	IdsByName.Add(WidgetName, Entry);
}

// ===========================================================================
// Public — Query
// ===========================================================================

FAutoAgentResolvedId FAutoAgentStableIdResolver::Resolve(const FString& WidgetName) const
{
	if (const FAutoAgentResolvedId* Found = IdsByName.Find(WidgetName))
	{
		return *Found;
	}

	// Auto fallback: widget name is stable enough within a single session.
	// bPinned=false signals "not explicitly registered".
	FAutoAgentResolvedId Auto;
	Auto.PinnedId = WidgetName;
	Auto.bPinned = false;
	Auto.Source = EAutoAgentIdSource::Auto;
	return Auto;
}

TMap<FString, FString> FAutoAgentStableIdResolver::GetStateSprites(
	const FString& WidgetName) const
{
	if (const TMap<FString, FString>* Found = SpritesByOwner.Find(WidgetName))
	{
		return *Found;
	}
	return TMap<FString, FString>();
}

// ===========================================================================
// Public — Diagnostics
// ===========================================================================

FString FAutoAgentStableIdResolver::ComputeHashId(const FString& WidgetName)
{
	// CRC32 over the UTF-16 code units (stable within a binary; good enough
	// for diagnostic / tooling use).
	const uint32 Hash = FCrc::StrCrc32(*WidgetName);
	return FString::Printf(TEXT("auto_%08x"), Hash);
}

// ===========================================================================
// Private — LoadFromIniRegistry
// ===========================================================================

void FAutoAgentStableIdResolver::LoadFromIniRegistry()
{
	const FString IniPath = FPaths::ProjectConfigDir() / TEXT("AutoAgentIds.ini");
	FString Contents;
	if (!FFileHelper::LoadFileToString(Contents, *IniPath))
	{
		UE_LOG(LogTemp, Warning, TEXT("[AutoAgent] AutoAgentIds.ini not found at %s"), *IniPath);
		return;
	}

	int32 IniCount = 0;
	TArray<FString> Lines;
	Contents.ParseIntoArrayLines(Lines);
	for (const FString& Raw : Lines)
	{
		const FString Line = Raw.TrimStartAndEnd();

		// +Id=(C="LoginPanel",Pin="login_panel",Role="image_only")
		if (Line.StartsWith(TEXT("+Id=")))
		{
			FString C, Pin, Role;
			FParse::Value(*Line, TEXT("C="), C);
			FParse::Value(*Line, TEXT("Pin="), Pin);
			FParse::Value(*Line, TEXT("Role="), Role);
			if (!C.IsEmpty())
			{
				FAutoAgentResolvedId Entry;
				Entry.PinnedId = Pin;
				Entry.LogicalRole = Role;
				Entry.bPinned = !Pin.IsEmpty();
				Entry.Source = EAutoAgentIdSource::Ini;
				// Ini always wins — unconditional Add (overrides PropertyMeta).
				IdsByName.Add(C, Entry);
				++IniCount;
			}
		}
		// +Sprite=(Owner="LoginButtonBg",State="normal",Path="/Game/UI/...")
		else if (Line.StartsWith(TEXT("+Sprite=")))
		{
			FString Owner, State, Path;
			FParse::Value(*Line, TEXT("Owner="), Owner);
			FParse::Value(*Line, TEXT("State="), State);
			FParse::Value(*Line, TEXT("Path="), Path);
			if (!Owner.IsEmpty() && !State.IsEmpty())
			{
				SpritesByOwner.FindOrAdd(Owner).Add(State, Path);
			}
		}
	}

	UE_LOG(LogTemp, Log, TEXT("[AutoAgent] loaded %d ids (%d ini), %d sprite owners"), IdsByName.Num(), IniCount, SpritesByOwner.Num());
}

// ===========================================================================
// Private — LoadFromPropertyMeta
// ===========================================================================

void FAutoAgentStableIdResolver::LoadFromPropertyMeta()
{
#if WITH_METADATA
	// Iterate every loaded UClass that derives from UWidget and inspect its
	// own UPROPERTY declarations for AutoAgentId / AutoAgentLogicalRole meta.
	//
	// ExcludeSuper: each class only processes its own (non-inherited)
	// properties — parent properties are visited when TObjectIterator reaches
	// the parent UClass itself, preventing duplicate entries.

	int32 MetaCount = 0;
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
			FProperty* Prop = *PropIt;
			if (!Prop->HasMetaData(TEXT("AutoAgentId")))
			{
				continue;
			}

			const FString AutoAgentId = Prop->GetMetaData(TEXT("AutoAgentId"));
			const FString LogicalRole = Prop->GetMetaData(TEXT("AutoAgentLogicalRole"));
			const FString PropName = Prop->GetName();

			if (PropName.IsEmpty() || AutoAgentId.IsEmpty())
			{
				continue;
			}

			// Only add if NOT already populated by a previous LoadFromPropertyMeta
			// call for the same name (shouldn't happen normally, but guard it).
			// Ini entries added later will unconditionally override these.
			if (!IdsByName.Contains(PropName))
			{
				FAutoAgentResolvedId Entry;
				Entry.PinnedId = AutoAgentId;
				Entry.LogicalRole = LogicalRole;
				Entry.bPinned = true;
				Entry.Source = EAutoAgentIdSource::PropertyMeta;
				IdsByName.Add(PropName, Entry);
				++MetaCount;
			}
		}
	}

	if (MetaCount > 0)
	{
		UE_LOG(LogTemp, Log, TEXT("[AutoAgent] found %d ids from UPROPERTY meta"), MetaCount);
	}
#endif // WITH_METADATA
}
