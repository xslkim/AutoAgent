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
 * Protocol fields emitted per node:
 *   id, type, engine_type, parent_id, stable_id_source
 *   visual  : position, size, visible, world_bounds, color, alpha, sprite_ref
 *   behavior: interactable, attached_components
 *   meta    : logical_role, state_sprites (when non-empty)
 *   children_ids
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
	/**
	 * Recursively walks Widget and its descendants.
	 * Visited tracks IDs already emitted — callers must pass a mutable reference.
	 * Returns this widget's resolved id (empty string on skip/null).
	 */
	FString WalkWidget(UWidget* Widget, const FString& ParentId,
		TArray<TSharedPtr<FJsonValue>>& Out,
		TSet<FString>& Visited) const;

	TSharedRef<FAutoAgentStableIdResolver> Resolver;
};
