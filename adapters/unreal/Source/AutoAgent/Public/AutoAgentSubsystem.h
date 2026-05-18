#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Containers/Ticker.h"
#include "AutoAgentSubsystem.generated.h"

class FAutoAgentWebSocketServer;

/**
 * Owns the AutoAgent wire-protocol server for the lifetime of the game
 * instance. Drives the server's poll loop every frame on the game thread.
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

	TSharedPtr<FAutoAgentWebSocketServer> Server;
	FTSTicker::FDelegateHandle TickHandle;
};
