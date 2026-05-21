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
 * Architecture
 * ------------
 * FTcpListener accepts connections on its own thread and hands new sockets to
 * the game thread via Incoming (Mpsc queue).  All protocol work — handshake,
 * frame I/O, JSON-RPC dispatch, negotiate_version — runs inside Poll(), which
 * is called every frame on the game thread.  This keeps UMG/Slate access
 * free of cross-thread marshalling.
 *
 * Connection limit
 * ----------------
 * At most MaxConnections simultaneous clients are accepted.  Connections
 * beyond the limit are immediately destroyed in Poll().
 *
 * negotiate_version
 * -----------------
 * Immediately after the WebSocket handshake the server sends a JSON-RPC
 * notification:
 *   {"jsonrpc":"2.0","method":"negotiate_version",
 *    "params":{"protocol":"autoagent.v1","version":"1.0.0"}}
 * Clients should reject any server that omits this notification or reports
 * an incompatible protocol/version.
 */
class FAutoAgentWebSocketServer
{
public:
	/** Maximum simultaneous WebSocket client connections. */
	static constexpr int32 MaxConnections = 16;

	FAutoAgentWebSocketServer();
	~FAutoAgentWebSocketServer();

	void Start();
	void Stop();

	/** Called every frame on the game thread to drive the server. */
	void Poll();

	/** Returns the current number of active WebSocket connections. */
	int32 GetConnectionCount() const
	{
		return Clients.Num();
	}

#if WITH_DEV_AUTOMATION_TESTS
	/**
	 * Test-only — parse one WebSocket frame from Buf (modified in-place).
	 * Mirrors the production frame-extraction logic so tests can exercise the
	 * parser without a real TCP socket.
	 *
	 * @param Buf        Mutable byte buffer (consumed on success).
	 * @param OutMessage Decoded text payload (valid when returns true and
	 *                   bOutClosed is false).
	 * @param bOutClosed Set to true when a Close frame was received.
	 * @return true if a complete frame was extracted; false if more bytes
	 *         are needed.
	 */
	static bool ParseFrameForTest(TArray<uint8>& Buf,
								  FString& OutMessage,
								  bool& bOutClosed);
#endif // WITH_DEV_AUTOMATION_TESTS

private:
	struct FClientConn
	{
		FSocket* Socket = nullptr;
		TArray<uint8> RxBuffer;
		bool bHandshakeDone = false;
		bool bNegotiateSent = false; // negotiate_version sent after handshake
	};

	bool HandleConnectionAccepted(FSocket* Socket, const FIPv4Endpoint& Endpoint);
	bool ReadAvailable(FClientConn& Client);
	bool TryHandshake(FClientConn& Client, bool& bOutShouldClose);
	bool TryExtractFrame(FClientConn& Client,
						 FString& OutMessage,
						 bool& bOutClosed);
	void DestroyClientSocket(FSocket* Socket);

	FTcpListener* Listener = nullptr;
	TQueue<FSocket*, EQueueMode::Mpsc> Incoming;
	TArray<TSharedPtr<FClientConn>> Clients;
	TSharedPtr<FAutoAgentProtocolHandler> Handler;
};
