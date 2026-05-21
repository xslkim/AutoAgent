// AutoAgent TASK-0203 — AutoAgentWebSocketServer.cpp
//
// Production-quality WebSocket server over FTcpListener.
//
// Key additions vs PoC:
//   - MaxConnections enforcement (new connections rejected when at cap)
//   - negotiate_version notification sent immediately after handshake
//   - bNegotiateSent guard (one-time per connection)
//   - ParseWebSocketFrame refactored as a static free-function (shared by
//     TryExtractFrame and the test-only ParseFrameForTest)

#include "AutoAgentWebSocketServer.h"
#include "AutoAgentProtocolHandler.h"
#include "Common/TcpListener.h"
#include "Containers/StringConv.h"
#include "Interfaces/IPv4/IPv4Address.h"
#include "Interfaces/IPv4/IPv4Endpoint.h"
#include "Misc/Base64.h"
#include "Misc/SecureHash.h"
#include "Sockets.h"
#include "SocketSubsystem.h"

namespace
{
const int32 AutoAgentPort = 27842;
const TCHAR* AutoAgentSubprotocol = TEXT("autoagent.v1");
const TCHAR* AutoAgentVersion = TEXT("1.0.0");
const TCHAR* WebSocketGuid = TEXT("258EAFA5-E914-47DA-95CA-C5AB0DC85B11");

/** negotiate_version JSON-RPC notification sent to new clients. */
const TCHAR* NegotiateVersionJson =
	TEXT("{\"jsonrpc\":\"2.0\",\"method\":\"negotiate_version\",")
		TEXT("\"params\":{\"protocol\":\"autoagent.v1\",\"version\":\"1.0.0\"}}");

// ---------------------------------------------------------------------------
// Socket send helpers
// ---------------------------------------------------------------------------

void SendRaw(FSocket* Socket, const TArray<uint8>& Bytes)
{
	if (!Socket || Bytes.Num() == 0)
	{
		return;
	}
	int32 Sent = 0;
	Socket->Send(Bytes.GetData(), Bytes.Num(), Sent);
}

void SendRawString(FSocket* Socket, const FString& Text)
{
	FTCHARToUTF8 Utf8(*Text);
	TArray<uint8> Bytes;
	Bytes.Append(reinterpret_cast<const uint8*>(Utf8.Get()), Utf8.Length());
	SendRaw(Socket, Bytes);
}

void SendTextFrame(FSocket* Socket, const FString& Text)
{
	FTCHARToUTF8 Utf8(*Text);
	const int32 Len = Utf8.Length();
	TArray<uint8> Frame;
	Frame.Add(0x81); // FIN + text opcode
	if (Len <= 125)
	{
		Frame.Add(static_cast<uint8>(Len));
	}
	else if (Len <= 65535)
	{
		Frame.Add(126);
		Frame.Add(static_cast<uint8>((Len >> 8) & 0xFF));
		Frame.Add(static_cast<uint8>(Len & 0xFF));
	}
	else
	{
		Frame.Add(127);
		for (int32 i = 7; i >= 0; --i)
		{
			Frame.Add(static_cast<uint8>((static_cast<uint64>(Len) >> (i * 8)) & 0xFF));
		}
	}
	Frame.Append(reinterpret_cast<const uint8*>(Utf8.Get()), Len);
	SendRaw(Socket, Frame);
}

void SendControlFrame(FSocket* Socket, uint8 Opcode, const TArray<uint8>& Payload)
{
	const int32 Len = FMath::Min(Payload.Num(), 125);
	TArray<uint8> Frame;
	Frame.Add(0x80 | Opcode);
	Frame.Add(static_cast<uint8>(Len));
	if (Len > 0)
	{
		Frame.Append(Payload.GetData(), Len);
	}
	SendRaw(Socket, Frame);
}

FString PayloadToString(const TArray<uint8>& Bytes)
{
	FUTF8ToTCHAR Conv(reinterpret_cast<const ANSICHAR*>(Bytes.GetData()), Bytes.Num());
	return FString(Conv.Length(), Conv.Get());
}

int32 FindHeaderEnd(const TArray<uint8>& Buf)
{
	for (int32 i = 0; i + 3 < Buf.Num(); ++i)
	{
		if (Buf[i] == 13 && Buf[i + 1] == 10 && Buf[i + 2] == 13 && Buf[i + 3] == 10)
		{
			return i;
		}
	}
	return INDEX_NONE;
}

// ---------------------------------------------------------------------------
// Frame parser — shared by TryExtractFrame and ParseFrameForTest
// ---------------------------------------------------------------------------

/**
 * Parse one WebSocket frame from Buf, consuming its bytes on success.
 *
 * Handles all opcodes (text, binary, continuation, ping, pong, close).
 * Ping frames trigger an immediate pong via Socket; pass nullptr when testing
 * without a real socket (pong send is silently skipped).
 *
 * @return true if a complete frame was found and consumed; false if Buf
 *         contains fewer bytes than the frame header requires.
 */
bool ParseWebSocketFrame(TArray<uint8>& Buf,
						 FString& OutMessage,
						 bool& bOutClosed,
						 FSocket* Socket)
{
	OutMessage.Empty();
	bOutClosed = false;

	if (Buf.Num() < 2)
	{
		return false;
	}

	const uint8 Byte0 = Buf[0];
	const uint8 Byte1 = Buf[1];
	const int32 Opcode = Byte0 & 0x0F;
	const bool bMasked = (Byte1 & 0x80) != 0;
	uint64 PayloadLen = Byte1 & 0x7F;
	int32 Offset = 2;

	if (PayloadLen == 126)
	{
		if (Buf.Num() < 4)
		{
			return false;
		}
		PayloadLen = (static_cast<uint64>(Buf[2]) << 8) | static_cast<uint64>(Buf[3]);
		Offset = 4;
	}
	else if (PayloadLen == 127)
	{
		if (Buf.Num() < 10)
		{
			return false;
		}
		PayloadLen = 0;
		for (int32 i = 0; i < 8; ++i)
		{
			PayloadLen = (PayloadLen << 8) | static_cast<uint64>(Buf[2 + i]);
		}
		Offset = 10;
	}

	uint8 Mask[4] = {0, 0, 0, 0};
	if (bMasked)
	{
		if (Buf.Num() < Offset + 4)
		{
			return false;
		}
		for (int32 i = 0; i < 4; ++i)
		{
			Mask[i] = Buf[Offset + i];
		}
		Offset += 4;
	}

	if (static_cast<uint64>(Buf.Num()) < static_cast<uint64>(Offset) + PayloadLen)
	{
		return false; // frame not yet fully received
	}

	TArray<uint8> Payload;
	Payload.SetNumUninitialized(static_cast<int32>(PayloadLen));
	for (uint64 i = 0; i < PayloadLen; ++i)
	{
		const uint8 Raw = Buf[Offset + static_cast<int32>(i)];
		Payload[static_cast<int32>(i)] = bMasked ? (Raw ^ Mask[i % 4]) : Raw;
	}
	Buf.RemoveAt(0, Offset + static_cast<int32>(PayloadLen));

	switch (Opcode)
	{
	case 0x8: // close
		bOutClosed = true;
		return true;
	case 0x9: // ping → reply pong
		if (Socket)
		{
			SendControlFrame(Socket, 0xA, Payload);
		}
		return true;
	case 0xA: // pong → ignore
		return true;
	case 0x0: // continuation
	case 0x1: // text
	case 0x2: // binary
		OutMessage = PayloadToString(Payload);
		return true;
	default:
		return true; // unknown opcode — skip
	}
}

} // namespace

// ===========================================================================
// Constructor / destructor
// ===========================================================================

FAutoAgentWebSocketServer::FAutoAgentWebSocketServer()
{
}

FAutoAgentWebSocketServer::~FAutoAgentWebSocketServer()
{
	Stop();
}

// ===========================================================================
// Start / Stop
// ===========================================================================

void FAutoAgentWebSocketServer::Start()
{
	Handler = MakeShared<FAutoAgentProtocolHandler>();

	const FIPv4Endpoint Endpoint(FIPv4Address(127, 0, 0, 1), AutoAgentPort);
	Listener = new FTcpListener(Endpoint);
	Listener->OnConnectionAccepted().BindRaw(
		this, &FAutoAgentWebSocketServer::HandleConnectionAccepted);

	UE_LOG(LogTemp, Log, TEXT("[AutoAgent] WebSocket server listening on ws://127.0.0.1:%d (max %d clients)"), AutoAgentPort, MaxConnections);
}

void FAutoAgentWebSocketServer::Stop()
{
	if (Listener)
	{
		Listener->Stop();
		delete Listener;
		Listener = nullptr;
	}

	FSocket* Pending = nullptr;
	while (Incoming.Dequeue(Pending))
	{
		DestroyClientSocket(Pending);
	}
	for (const TSharedPtr<FClientConn>& Client : Clients)
	{
		if (Client.IsValid())
		{
			DestroyClientSocket(Client->Socket);
		}
	}
	Clients.Empty();
	Handler.Reset();
}

// ===========================================================================
// Connection acceptance (runs on FTcpListener thread)
// ===========================================================================

bool FAutoAgentWebSocketServer::HandleConnectionAccepted(FSocket* Socket,
														 const FIPv4Endpoint& /*Endpoint*/)
{
	// Runs on the FTcpListener thread — hand the socket to the game thread.
	if (Socket)
	{
		Socket->SetNonBlocking(true);
		Incoming.Enqueue(Socket);
	}
	return true;
}

// ===========================================================================
// Poll — game thread, called every frame
// ===========================================================================

void FAutoAgentWebSocketServer::Poll()
{
	// Adopt newly accepted connections (or reject if at capacity).
	FSocket* NewSocket = nullptr;
	while (Incoming.Dequeue(NewSocket))
	{
		if (Clients.Num() >= MaxConnections)
		{
			UE_LOG(LogTemp, Warning, TEXT("[AutoAgent] connection limit reached (%d); rejecting new client"), MaxConnections);
			DestroyClientSocket(NewSocket);
			continue;
		}
		TSharedPtr<FClientConn> Client = MakeShared<FClientConn>();
		Client->Socket = NewSocket;
		Clients.Add(Client);
	}

	// Service each active client (iterate backwards so removal is safe).
	for (int32 i = Clients.Num() - 1; i >= 0; --i)
	{
		FClientConn& Client = *Clients[i];
		bool bRemove = false;

		if (!ReadAvailable(Client))
		{
			bRemove = true;
		}

		if (!bRemove && !Client.bHandshakeDone)
		{
			bool bShouldClose = false;
			if (TryHandshake(Client, bShouldClose) && bShouldClose)
			{
				bRemove = true;
			}
		}

		// Send negotiate_version once, immediately after handshake completes.
		if (!bRemove && Client.bHandshakeDone && !Client.bNegotiateSent)
		{
			SendTextFrame(Client.Socket, NegotiateVersionJson);
			Client.bNegotiateSent = true;
		}

		if (!bRemove && Client.bHandshakeDone)
		{
			FString Message;
			bool bClosed = false;
			while (TryExtractFrame(Client, Message, bClosed))
			{
				if (bClosed)
				{
					bRemove = true;
					break;
				}
				if (!Message.IsEmpty() && Handler.IsValid())
				{
					SendTextFrame(Client.Socket, Handler->Dispatch(Message));
				}
			}
		}

		if (bRemove)
		{
			DestroyClientSocket(Client.Socket);
			Clients.RemoveAt(i);
		}
	}
}

// ===========================================================================
// Private helpers
// ===========================================================================

void FAutoAgentWebSocketServer::DestroyClientSocket(FSocket* Socket)
{
	if (!Socket)
	{
		return;
	}
	Socket->Close();
	if (ISocketSubsystem* SocketSub = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM))
	{
		SocketSub->DestroySocket(Socket);
	}
}

bool FAutoAgentWebSocketServer::ReadAvailable(FClientConn& Client)
{
	if (!Client.Socket)
	{
		return false;
	}
	uint32 PendingSize = 0;
	while (Client.Socket->HasPendingData(PendingSize) && PendingSize > 0)
	{
		TArray<uint8> Chunk;
		Chunk.SetNumUninitialized(static_cast<int32>(FMath::Min<uint32>(PendingSize, 65536u)));
		int32 BytesRead = 0;
		if (!Client.Socket->Recv(
				Chunk.GetData(), Chunk.Num(), BytesRead, ESocketReceiveFlags::None))
		{
			return false; // socket error / peer closed
		}
		if (BytesRead <= 0)
		{
			break;
		}
		Client.RxBuffer.Append(Chunk.GetData(), BytesRead);
	}
	return true;
}

bool FAutoAgentWebSocketServer::TryHandshake(FClientConn& Client, bool& bOutShouldClose)
{
	bOutShouldClose = false;

	const int32 HeaderEnd = FindHeaderEnd(Client.RxBuffer);
	if (HeaderEnd == INDEX_NONE)
	{
		return false; // need more bytes
	}

	// HTTP headers are ASCII — copy into an FString line-by-line.
	FString HeaderStr;
	HeaderStr.Reserve(HeaderEnd + 4);
	for (int32 i = 0; i < HeaderEnd + 4; ++i)
	{
		HeaderStr.AppendChar(static_cast<TCHAR>(Client.RxBuffer[i]));
	}
	Client.RxBuffer.RemoveAt(0, HeaderEnd + 4);

	FString Key;
	FString Protocols;
	TArray<FString> Lines;
	HeaderStr.ParseIntoArray(Lines, TEXT("\r\n"));
	for (const FString& Line : Lines)
	{
		if (Line.StartsWith(TEXT("Sec-WebSocket-Key:"), ESearchCase::IgnoreCase))
		{
			Key = Line.RightChop(18).TrimStartAndEnd();
		}
		else if (Line.StartsWith(TEXT("Sec-WebSocket-Protocol:"), ESearchCase::IgnoreCase))
		{
			Protocols = Line.RightChop(23).TrimStartAndEnd();
		}
	}

	if (Key.IsEmpty() || !Protocols.Contains(AutoAgentSubprotocol))
	{
		SendRawString(Client.Socket,
					  TEXT("HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n"));
		bOutShouldClose = true;
		return true;
	}

	// Compute Sec-WebSocket-Accept.
	const FString Magic = Key + WebSocketGuid;
	FTCHARToUTF8 MagicUtf8(*Magic);
	uint8 Hash[20];
	FSHA1::HashBuffer(MagicUtf8.Get(), MagicUtf8.Length(), Hash);
	const FString Accept = FBase64::Encode(Hash, 20);

	const FString Response =
		TEXT("HTTP/1.1 101 Switching Protocols\r\n")
			TEXT("Upgrade: websocket\r\n")
				TEXT("Connection: Upgrade\r\n") +
		FString::Printf(TEXT("Sec-WebSocket-Accept: %s\r\n"), *Accept) +
		FString::Printf(
			TEXT("Sec-WebSocket-Protocol: %s\r\n\r\n"), AutoAgentSubprotocol);
	SendRawString(Client.Socket, Response);

	Client.bHandshakeDone = true;
	return true;
}

bool FAutoAgentWebSocketServer::TryExtractFrame(FClientConn& Client,
												FString& OutMessage,
												bool& bOutClosed)
{
	return ParseWebSocketFrame(Client.RxBuffer, OutMessage, bOutClosed, Client.Socket);
}

// ===========================================================================
// Test seam — ParseFrameForTest
// ===========================================================================

#if WITH_DEV_AUTOMATION_TESTS
bool FAutoAgentWebSocketServer::ParseFrameForTest(TArray<uint8>& Buf,
												  FString& OutMessage,
												  bool& bOutClosed)
{
	// nullptr socket → pong sends are silently skipped (correct for unit tests).
	return ParseWebSocketFrame(Buf, OutMessage, bOutClosed, nullptr);
}
#endif // WITH_DEV_AUTOMATION_TESTS
