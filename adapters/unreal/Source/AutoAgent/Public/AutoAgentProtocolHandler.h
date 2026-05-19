#pragma once

#include "CoreMinimal.h"
#include "UObject/WeakObjectPtr.h"

class FAutoAgentStableIdResolver;
class FAutoAgentUmgReflector;
class FAutoAgentSlateInputDriver;
class UGameViewportClient;

/**
 * JSON-RPC 2.0 dispatcher for the AutoAgent wire protocol.
 * Dispatch() must be called on the game thread (it touches UMG).
 */
class FAutoAgentProtocolHandler
{
public:
	FAutoAgentProtocolHandler();
	~FAutoAgentProtocolHandler();

	/** Dispatch one JSON-RPC request; returns the JSON-RPC response string. */
	FString Dispatch(const FString& RequestJson);

private:
	// UGameViewportClient::OnScreenshotCaptured callback — writes the captured
	// game-viewport pixels to PendingScreenshotPath.
	void OnScreenshotCaptured(int32 Width, int32 Height, const TArray<FColor>& Bitmap);

	TSharedRef<FAutoAgentStableIdResolver> Resolver;
	TSharedRef<FAutoAgentUmgReflector> Reflector;
	TSharedRef<FAutoAgentSlateInputDriver> InputDriver;

	FString PendingScreenshotPath;
	TWeakObjectPtr<UGameViewportClient> ScreenshotViewport;
	FDelegateHandle ScreenshotHandle;
};
