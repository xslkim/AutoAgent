#include "AutoAgentSubsystem.h"
#include "AutoAgentWebSocketServer.h"

void UAutoAgentSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	Server = MakeShared<FAutoAgentWebSocketServer>();
	Server->Start();

	TickHandle = FTSTicker::GetCoreTicker().AddTicker(
		FTickerDelegate::CreateUObject(this, &UAutoAgentSubsystem::Tick));
}

void UAutoAgentSubsystem::Deinitialize()
{
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
	Super::Deinitialize();
}

bool UAutoAgentSubsystem::Tick(float /*DeltaTime*/)
{
	if (Server.IsValid())
	{
		Server->Poll();
	}
	return true; // keep ticking
}
