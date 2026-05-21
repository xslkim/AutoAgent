#include "AutoAgentStableIdResolver.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"

void FAutoAgentStableIdResolver::Load()
{
	IdsByName.Empty();
	SpritesByOwner.Empty();

	const FString IniPath = FPaths::ProjectConfigDir() / TEXT("AutoAgentIds.ini");
	FString Contents;
	if (!FFileHelper::LoadFileToString(Contents, *IniPath))
	{
		UE_LOG(LogTemp, Warning, TEXT("[AutoAgent] AutoAgentIds.ini not found at %s"), *IniPath);
		return;
	}

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
				IdsByName.Add(C, Entry);
			}
		}
		// +Sprite=(Owner="LoginButtonBg",State="normal",Path="/Game/UI/Sprites/btn_login_normal")
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

	UE_LOG(LogTemp, Log, TEXT("[AutoAgent] loaded %d ids, %d sprite owners from AutoAgentIds.ini"), IdsByName.Num(), SpritesByOwner.Num());
}

FAutoAgentResolvedId FAutoAgentStableIdResolver::Resolve(const FString& WidgetName) const
{
	if (const FAutoAgentResolvedId* Found = IdsByName.Find(WidgetName))
	{
		return *Found;
	}
	// Unregistered widget — fall back to its raw name as an auto id.
	FAutoAgentResolvedId Auto;
	Auto.PinnedId = WidgetName;
	Auto.bPinned = false;
	return Auto;
}

TMap<FString, FString> FAutoAgentStableIdResolver::GetStateSprites(const FString& WidgetName) const
{
	if (const TMap<FString, FString>* Found = SpritesByOwner.Find(WidgetName))
	{
		return *Found;
	}
	return TMap<FString, FString>();
}
