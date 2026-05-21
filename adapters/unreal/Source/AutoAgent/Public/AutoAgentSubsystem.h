#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Containers/Ticker.h"
#include "AutoAgentSubsystem.generated.h"

// FAutoAgentWebSocketServer is only referenced when the adapter is active.
// In Shipping builds (AUTOAGENT_ENABLED=0) the include is skipped so the
// header has no dependency on the server or protocol code.
#if AUTOAGENT_ENABLED
class FAutoAgentWebSocketServer;
#endif

/**
 * Owns the AutoAgent wire-protocol server for the lifetime of the game
 * instance.  Drives the server's poll loop every frame on the game thread.
 *
 * Shipping builds (AUTOAGENT_ENABLED=0)
 * --------------------------------------
 * Initialize() and Deinitialize() are no-ops; the WebSocket server is never
 * created, so there is zero runtime overhead and no listening port.
 *
 * Hot-reload / re-initialize safety
 * ----------------------------------
 * Deinitialize() stops and resets the server before the subsystem is
 * destroyed; Initialize() always creates a fresh instance.  This makes the
 * subsystem safe across editor hot-reloads and PIE restarts.
 */
UCLASS()
class AUTOAGENT_API UAutoAgentSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

private:
	bool Tick(float DeltaTime);

#if AUTOAGENT_ENABLED
	TSharedPtr<FAutoAgentWebSocketServer> Server;
	FTSTicker::FDelegateHandle TickHandle;
#endif
};
