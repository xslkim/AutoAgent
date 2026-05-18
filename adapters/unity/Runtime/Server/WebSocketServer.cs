using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using UnityEngine;

namespace AutoAgent
{
    /// <summary>
    /// Minimal single-client WebSocket server on ws://127.0.0.1:27842.
    /// Validates subprotocol "autoagent.v1" and routes text frames to ProtocolHandler.
    /// Runs accept-loop + per-client read-loop on background threads.
    /// </summary>
    internal class WebSocketServer
    {
        const int Port = 27842;
        const string Subprotocol = "autoagent.v1";
        const string WsGuid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

        readonly ProtocolHandler _handler;
        TcpListener _listener;
        Thread _acceptThread;
        volatile bool _running;

        public WebSocketServer(ProtocolHandler handler) => _handler = handler;

        public void Start()
        {
            _listener = new TcpListener(IPAddress.Loopback, Port);
            _listener.Start();
            _running = true;
            _acceptThread = new Thread(AcceptLoop) { IsBackground = true, Name = "AutoAgent-WS-Accept" };
            _acceptThread.Start();
            Debug.Log($"[AutoAgent] WebSocket server listening on ws://127.0.0.1:{Port}");
        }

        public void Stop()
        {
            _running = false;
            try { _listener?.Stop(); } catch { }
        }

        // ------------------------------------------------------------------ accept loop

        void AcceptLoop()
        {
            while (_running)
            {
                try
                {
                    var client = _listener.AcceptTcpClient();
                    var t = new Thread(() => ServeClient(client))
                    { IsBackground = true, Name = "AutoAgent-WS-Client" };
                    t.Start();
                }
                catch (SocketException) when (!_running) { break; }
                catch (Exception ex) { Debug.LogWarning($"[AutoAgent] Accept error: {ex.Message}"); }
            }
        }

        // ------------------------------------------------------------------ per-client loop

        void ServeClient(TcpClient client)
        {
            using (client)
            using (var stream = client.GetStream())
            {
                try
                {
                    if (!Handshake(stream)) return;
                    ReadLoop(stream);
                }
                catch (Exception ex) when (ex is IOException || ex is SocketException)
                {
                    // client disconnected — normal
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"[AutoAgent] Client error: {ex.Message}");
                }
            }
        }

        // ------------------------------------------------------------------ WS handshake

        bool Handshake(NetworkStream stream)
        {
            // Read HTTP request headers
            var sb = new StringBuilder();
            var buf = new byte[4096];
            int total = 0;
            while (true)
            {
                int n = stream.Read(buf, total, buf.Length - total);
                if (n == 0) return false;
                total += n;
                string partial = Encoding.UTF8.GetString(buf, 0, total);
                if (partial.Contains("\r\n\r\n")) { sb.Append(partial); break; }
                if (total >= buf.Length) return false; // header too large
            }
            string headers = sb.ToString();

            // Extract Sec-WebSocket-Key
            var keyMatch = Regex.Match(headers, @"Sec-WebSocket-Key:\s*(.+)\r\n");
            if (!keyMatch.Success) return false;
            string key = keyMatch.Groups[1].Value.Trim();

            // Validate subprotocol
            var protoMatch = Regex.Match(headers, @"Sec-WebSocket-Protocol:\s*(.+)\r\n");
            bool hasCorrectProto = protoMatch.Success &&
                protoMatch.Groups[1].Value.Contains(Subprotocol);

            // Compute accept token
            string accept;
            using (var sha = SHA1.Create())
                accept = Convert.ToBase64String(sha.ComputeHash(Encoding.UTF8.GetBytes(key + WsGuid)));

            if (!hasCorrectProto)
            {
                // Reject with 400 — wrong subprotocol
                byte[] reject = Encoding.UTF8.GetBytes(
                    "HTTP/1.1 400 Bad Request\r\n" +
                    "Content-Length: 0\r\n\r\n");
                stream.Write(reject, 0, reject.Length);
                return false;
            }

            // Send 101 Switching Protocols
            string response =
                "HTTP/1.1 101 Switching Protocols\r\n" +
                "Upgrade: websocket\r\n" +
                "Connection: Upgrade\r\n" +
                $"Sec-WebSocket-Accept: {accept}\r\n" +
                $"Sec-WebSocket-Protocol: {Subprotocol}\r\n" +
                "\r\n";
            byte[] respBytes = Encoding.UTF8.GetBytes(response);
            stream.Write(respBytes, 0, respBytes.Length);
            return true;
        }

        // ------------------------------------------------------------------ frame read loop

        void ReadLoop(NetworkStream stream)
        {
            while (_running)
            {
                string msg = ReadFrame(stream);
                if (msg == null) break; // connection closed

                // Dispatch: enqueue on main thread, send reply back on this thread.
                string reply = null;
                var ev = new ManualResetEventSlim(false);
                _handler.Enqueue(msg, r => { reply = r; ev.Set(); });
                ev.Wait(); // block until main thread has processed
                if (reply != null) SendFrame(stream, reply);
            }
        }

        // ------------------------------------------------------------------ frame codec

        // Reads frames until a text/binary message arrives. Control frames
        // (ping/pong) are handled inline. Returns null on close / error.
        static string ReadFrame(NetworkStream stream)
        {
            while (true)
            {
                byte[] header = ReadExact(stream, 2);
                if (header == null) return null;

                byte b0 = header[0], b1 = header[1];
                int opcode = b0 & 0x0F;
                bool masked = (b1 & 0x80) != 0;
                long payloadLen = b1 & 0x7F;

                if (payloadLen == 126)
                {
                    byte[] ext = ReadExact(stream, 2);
                    if (ext == null) return null;
                    payloadLen = (ext[0] << 8) | ext[1];
                }
                else if (payloadLen == 127)
                {
                    byte[] ext = ReadExact(stream, 8);
                    if (ext == null) return null;
                    payloadLen = 0;
                    for (int i = 0; i < 8; i++) payloadLen = (payloadLen << 8) | ext[i];
                }

                byte[] mask = null;
                if (masked)
                {
                    mask = ReadExact(stream, 4);
                    if (mask == null) return null;
                }

                byte[] payload = ReadExact(stream, (int)payloadLen);
                if (payload == null) return null;

                if (masked)
                    for (int i = 0; i < payload.Length; i++)
                        payload[i] ^= mask[i % 4];

                switch (opcode)
                {
                    case 0x8: // close
                        return null;
                    case 0x9: // ping → reply with pong, keep reading
                        SendControlFrame(stream, 0xA, payload);
                        continue;
                    case 0xA: // pong → ignore, keep reading
                        continue;
                    case 0x0: // continuation
                    case 0x1: // text
                    case 0x2: // binary
                        return Encoding.UTF8.GetString(payload);
                    default:  // unknown opcode
                        return null;
                }
            }
        }

        // Sends a control frame (ping/pong). Control payloads are <= 125 bytes.
        static void SendControlFrame(NetworkStream stream, int opcode, byte[] payload)
        {
            int len = payload.Length > 125 ? 125 : payload.Length;
            byte[] header = { (byte)(0x80 | opcode), (byte)len };
            lock (stream)
            {
                stream.Write(header, 0, header.Length);
                if (len > 0) stream.Write(payload, 0, len);
            }
        }

        static void SendFrame(NetworkStream stream, string text)
        {
            byte[] payload = Encoding.UTF8.GetBytes(text);
            int len = payload.Length;
            byte[] header;

            if (len <= 125)
            {
                header = new byte[] { 0x81, (byte)len };
            }
            else if (len <= 65535)
            {
                header = new byte[] { 0x81, 126, (byte)(len >> 8), (byte)(len & 0xFF) };
            }
            else
            {
                header = new byte[10];
                header[0] = 0x81; header[1] = 127;
                for (int i = 9; i >= 2; i--) { header[i] = (byte)(len & 0xFF); len >>= 8; }
            }

            lock (stream) // serialise concurrent sends
            {
                stream.Write(header, 0, header.Length);
                stream.Write(payload, 0, payload.Length);
            }
        }

        static byte[] ReadExact(NetworkStream stream, int count)
        {
            if (count == 0) return Array.Empty<byte>();
            var buf = new byte[count];
            int read = 0;
            while (read < count)
            {
                int n = stream.Read(buf, read, count - read);
                if (n == 0) return null;
                read += n;
            }
            return buf;
        }
    }
}
