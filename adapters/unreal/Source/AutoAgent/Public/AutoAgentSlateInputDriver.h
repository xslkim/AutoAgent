#pragma once

#include "CoreMinimal.h"

class UWidget;
class FAutoAgentStableIdResolver;

/**
 * Executes the four wire-protocol input actions on UMG widgets located by
 * their stable id. Must be called on the game thread.
 *
 * PoC scope: send_text / scroll manipulate widget state directly; click
 * broadcasts a button's OnClicked; drag verifies both endpoints exist.
 * Deep input-path simulation is covered by the automation test.
 */
class FAutoAgentSlateInputDriver
{
public:
	explicit FAutoAgentSlateInputDriver(
		const TSharedRef<FAutoAgentStableIdResolver>& InResolver);

	bool Click(const FString& NodeId) const;
	bool SendText(const FString& NodeId, const FString& Text) const;
	bool Scroll(const FString& NodeId, float DeltaX, float DeltaY) const;
	bool Drag(const FString& FromId, const FString& ToId) const;

private:
	UWidget* FindWidget(const FString& NodeId) const;

	TSharedRef<FAutoAgentStableIdResolver> Resolver;
};
