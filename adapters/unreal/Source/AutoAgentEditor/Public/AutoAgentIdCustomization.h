#pragma once

#include "CoreMinimal.h"
#include "IDetailCustomization.h"
#include "Input/Reply.h"

class IDetailLayoutBuilder;

/**
 * Details Panel customization for UWidget subclasses.
 *
 * Registered at editor startup for all classes derived from UWidget.
 * Adds an "AutoAgent Stable ID" category that shows:
 *
 *  • Stable ID  — the resolved stable identifier (green if pinned, amber if auto)
 *  • Source     — Ini / PropertyMeta / Runtime / Auto
 *  • Logical Role — if present in the registration
 *  • [Scan Unpinned] button — logs all BindWidget properties that lack a
 *    pinned AutoAgent ID across every currently loaded widget class
 *
 * All data is read-only; no visual properties are mutated.
 */
class FAutoAgentIdCustomization : public IDetailCustomization
{
public:
	static TSharedRef<IDetailCustomization> MakeInstance();

	virtual void CustomizeDetails(IDetailLayoutBuilder& DetailBuilder) override;

private:
	/**
	 * Scan every loaded UWidget-derived class for BindWidget UPROPERTY entries
	 * that have no pinned AutoAgent stable ID, and write the results to the
	 * Output Log.
	 *
	 * Uses WITH_METADATA guard so the scan is a no-op in Shipping builds where
	 * property metadata is stripped.
	 */
	static FReply OnScanUnpinnedClicked();
};
