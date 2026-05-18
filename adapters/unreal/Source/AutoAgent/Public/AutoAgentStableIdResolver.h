#pragma once

#include "CoreMinimal.h"

/** Resolved stable-id metadata for one widget. */
struct FAutoAgentResolvedId
{
	FString PinnedId;
	FString LogicalRole;
	bool bPinned = false;
};

/**
 * Reads Config/AutoAgentIds.ini from the running project and resolves a
 * widget's C++ binding name into its pinned id, logical role, and state
 * sprites. Works in editor and packaged builds (no editor-only metadata).
 */
class FAutoAgentStableIdResolver
{
public:
	/** Parse AutoAgentIds.ini from the project Config directory. */
	void Load();

	/** Resolve by widget name (the BindWidget C++ property name). */
	FAutoAgentResolvedId Resolve(const FString& WidgetName) const;

	/** Returns state -> sprite-path for a widget, or empty if none. */
	TMap<FString, FString> GetStateSprites(const FString& WidgetName) const;

private:
	TMap<FString, FAutoAgentResolvedId> IdsByName;
	TMap<FString, TMap<FString, FString>> SpritesByOwner;
};
