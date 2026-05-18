#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonValue.h"

class UWidget;
class UUserWidget;
class FAutoAgentStableIdResolver;

/**
 * Walks the UMG widget tree of every on-screen UUserWidget and produces a flat
 * array of AutoAgent protocol nodes (as JSON values).
 *
 * Must be called on the game thread.
 */
class FAutoAgentUmgReflector
{
public:
	explicit FAutoAgentUmgReflector(const TSharedRef<FAutoAgentStableIdResolver>& InResolver);

	/** Returns the dump_tree result: a JSON array of node objects. */
	TArray<TSharedPtr<FJsonValue>> DumpTree() const;

private:
	// Returns this widget's resolved id; appends it and its descendants to Out.
	FString WalkWidget(UWidget* Widget, const FString& ParentId,
		TArray<TSharedPtr<FJsonValue>>& Out) const;

	TSharedRef<FAutoAgentStableIdResolver> Resolver;
};
