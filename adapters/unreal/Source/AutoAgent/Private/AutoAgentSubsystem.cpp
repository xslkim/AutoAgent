// AutoAgent TASK-0204 — AutoAgentSubsystem.cpp
//
// AUTOAGENT_ENABLED guards all active adapter code so the WebSocket server
// and its transitive dependencies (protocol handler, reflector, input driver)
// are never instantiated in Shipping builds.

#include "AutoAgentSubsystem.h"

#if AUTOAGENT_ENABLED
#include "AutoAgentWebSocketServer.h"
#endif

void UAutoAgentSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

#if AUTOAGENT_ENABLED
	Server = MakeShared<FAutoAgentWebSocketServer>();
	Server->Start();

	TickHandle = FTSTicker::GetCoreTicker().AddTicker(
		FTickerDelegate::CreateUObject(this, &UAutoAgentSubsystem::Tick));

	UE_LOG(LogTemp, Log, TEXT("[AutoAgent] subsystem initialized (AUTOAGENT_ENABLED=1)"));
#else
	UE_LOG(LogTemp, Verbose, TEXT("[AutoAgent] subsystem disabled in Shipping build (AUTOAGENT_ENABLED=0)"));
#endif
}

void UAutoAgentSubsystem::Deinitialize()
{
#if AUTOAGENT_ENABLED
	if (TickHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(TickHandle);
		TickHandle.Reset();
	}
	if (Server.IsValid())
	{
		Server->Stop();
		Server.Reset();
	}
#endif

	Super::Deinitialize();
}

bool UAutoAgentSubsystem::Tick(float /*DeltaTime*/)
{
#if AUTOAGENT_ENABLED
	if (Server.IsValid())
	{
		Server->Poll();
	}
#endif
	return true; // keep ticking
}
