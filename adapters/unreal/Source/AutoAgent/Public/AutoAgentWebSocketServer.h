#pragma once

#include "CoreMinimal.h"
#include "Containers/Queue.h"

class FTcpListener;
class FSocket;
struct FIPv4Endpoint;
class FAutoAgentProtocolHandler;

/**
 * Minimal multi-client WebSocket server for the AutoAgent wire protocol.
 *
 * FTcpListener accepts connections on its own thread; everything else
 * (handshake, frame I/O, dispatch) runs on the game thread inside Poll(),
 * so UMG/Slate access needs no cross-thread marshalling.
 */
class FAutoAgentWebSocketServer
{
public:
	FAutoAgentWebSocketServer();
	~FAutoAgentWebSocketServer();

	void Start();
	void Stop();
	void Poll();   // called every frame on the game thread

private:
	struct FClientConn
	{
		FSocket* Socket = nullptr;
		TArray<uint8> RxBuffer;
		bool bHandshakeDone = false;
	};

	bool HandleConnectionAccepted(FSocket* Socket, const FIPv4Endpoint& Endpoint);
	bool ReadAvailable(FClientConn& Client);
	bool TryHandshake(FClientConn& Client, bool& bOutShouldClose);
	bool TryExtractFrame(FClientConn& Client, FString& OutMessage, bool& bOutClosed);
	void DestroyClientSocket(FSocket* Socket);

	FTcpListener* Listener = nullptr;
	TQueue<FSocket*, EQueueMode::Mpsc> Incoming;
	TArray<TSharedPtr<FClientConn>> Clients;
	TSharedPtr<FAutoAgentProtocolHandler> Handler;
};
