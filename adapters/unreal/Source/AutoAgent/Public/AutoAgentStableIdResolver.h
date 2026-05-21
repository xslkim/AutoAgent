#pragma once

#include "CoreMinimal.h"

// ---------------------------------------------------------------------------
// Source precedence (highest wins):
//   Ini > PropertyMeta > Runtime > Auto (hash)
// ---------------------------------------------------------------------------
enum class EAutoAgentIdSource : uint8
{
	Auto,		  // fallback — widget name used as-is; bPinned = false
	Runtime,	  // RegisterRuntime() call in NativeConstruct / Begin Play
	PropertyMeta, // UPROPERTY(meta=(AutoAgentId=...)) reflection
	Ini,		  // Config/AutoAgentIds.ini
};

/** Resolved stable-id metadata for one widget. */
struct FAutoAgentResolvedId
{
	FString PinnedId;
	FString LogicalRole;
	bool bPinned = false;
	EAutoAgentIdSource Source = EAutoAgentIdSource::Auto;
};

/**
 * Resolves a UWidget's C++ binding name into its pinned stable-id, logical
 * role, and optional state-sprite map.  Three explicit sources are supported
 * (highest-priority first):
 *
 *  1. Config/AutoAgentIds.ini  (LoadFromIniRegistry, called by Load())
 *  2. UPROPERTY meta=(AutoAgentId=...)  (LoadFromPropertyMeta, called by Load())
 *  3. RegisterRuntime()  — AI-written code in NativeConstruct() can register
 *     widgets it creates dynamically at runtime.
 *
 * Unregistered widgets fall back to their raw UObject name as an auto-id
 * (bPinned=false, Source=Auto).  ComputeHashId() provides a CRC32-based
 * diagnostic identifier for tooling.
 *
 * Works in Editor, Development, and Shipping builds.  UPROPERTY meta
 * reflection is guarded by WITH_METADATA and gracefully skipped in
 * Shipping (where metadata is stripped by the linker).
 */
class FAutoAgentStableIdResolver
{
public:
	// -----------------------------------------------------------------------
	// Load / reload
	// -----------------------------------------------------------------------

	/**
	 * (Re)loads all static registrations.
	 * Call once at startup (e.g., from AutoAgentSubsystem::Initialize).
	 * Thread-safety: call only on the game thread.
	 *
	 * Load order (later calls override earlier for the same key):
	 *   1. LoadFromPropertyMeta()  — lowest static priority
	 *   2. LoadFromIniRegistry()   — highest static priority
	 */
	void Load();

	// -----------------------------------------------------------------------
	// Runtime registration
	// -----------------------------------------------------------------------

	/**
	 * Register a stable id at runtime (e.g., for a widget created
	 * programmatically in NativeConstruct).
	 *
	 * A runtime entry is added only if the widget name is NOT already known
	 * from Ini or PropertyMeta (lower priority than static sources).
	 *
	 * @param WidgetName   Widget->GetName() value at runtime.
	 * @param PinnedId     Stable ID to assign (e.g. "login_button_bg").
	 * @param LogicalRole  Optional semantic role (e.g. "button").
	 */
	void RegisterRuntime(const FString& WidgetName, const FString& PinnedId, const FString& LogicalRole = TEXT(""));

	// -----------------------------------------------------------------------
	// Query
	// -----------------------------------------------------------------------

	/** Resolve a widget's name to its stable-id metadata. */
	FAutoAgentResolvedId Resolve(const FString& WidgetName) const;

	/** Returns state -> sprite-path for a widget, or empty map if none. */
	TMap<FString, FString> GetStateSprites(const FString& WidgetName) const;

	// -----------------------------------------------------------------------
	// Diagnostics
	// -----------------------------------------------------------------------

	/**
	 * Compute a stable CRC32-based diagnostic ID for a widget name.
	 * Used by tooling to generate reproducible identifiers when no pinned id
	 * exists; NOT used in the hot Resolve() path.
	 *
	 * Format: "auto_XXXXXXXX" (8 hex digits).
	 */
	static FString ComputeHashId(const FString& WidgetName);

private:
	/** Parse Config/AutoAgentIds.ini and add/override entries (source=Ini). */
	void LoadFromIniRegistry();

	/**
	 * Scan all UClass objects derived from UWidget for properties that carry
	 * AutoAgentId / AutoAgentLogicalRole metadata, and populate entries with
	 * source=PropertyMeta (does NOT override existing Ini entries).
	 *
	 * No-op in Shipping builds (WITH_METADATA is false).
	 */
	void LoadFromPropertyMeta();

	// -----------------------------------------------------------------------
	// State
	// -----------------------------------------------------------------------

	/** Primary id map: widget C++ name → resolved entry. */
	TMap<FString, FAutoAgentResolvedId> IdsByName;

	/** Sprite map: widget C++ name → (state → asset path). */
	TMap<FString, TMap<FString, FString>> SpritesByOwner;
};
