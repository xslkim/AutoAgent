#pragma once

#include "CoreMinimal.h"

class FAutoAgentStableIdResolver;
class FAutoAgentUmgReflector;
class FAutoAgentSlateInputDriver;

/**
 * JSON-RPC 2.0 dispatcher for the AutoAgent wire protocol.
 * Dispatch() must be called on the game thread (it touches UMG).
 */
class FAutoAgentProtocolHandler
{
public:
	FAutoAgentProtocolHandler();

	/** Dispatch one JSON-RPC request; returns the JSON-RPC response string. */
	FString Dispatch(const FString& RequestJson);

private:
	TSharedRef<FAutoAgentStableIdResolver> Resolver;
	TSharedRef<FAutoAgentUmgReflector> Reflector;
	TSharedRef<FAutoAgentSlateInputDriver> InputDriver;
};
