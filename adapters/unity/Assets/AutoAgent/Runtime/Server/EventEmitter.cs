using System;
using System.Globalization;

namespace AutoAgent
{
    /// <summary>
    /// Formats and broadcasts JSON-RPC 2.0 notification frames (no <c>id</c>)
    /// from the adapter to the connected MCP-server client. Each <c>Emit*</c>
    /// call is fire-and-forget: thread-safe as long as the underlying
    /// <paramref name="broadcast"/> callback is.
    ///
    /// Supported notification methods:
    ///   <c>event.scene_changed</c>      — active scene replaced
    ///   <c>event.widget_appeared</c>    — node became active in hierarchy
    ///   <c>event.widget_disappeared</c> — node deactivated or destroyed
    ///   <c>event.text_changed</c>       — text content of a node changed
    ///
    /// In tests, supply a capturing <c>Action&lt;string&gt;</c> instead of a
    /// real <see cref="WebSocketServer.Broadcast"/> for deterministic asserts.
    /// </summary>
    internal sealed class EventEmitter
    {
        readonly Action<string> _broadcast;

        /// <param name="broadcast">
        /// Callback that sends one text frame to the connected client.
        /// Must be thread-safe. Pass <see cref="WebSocketServer.Broadcast"/> in
        /// production; a collecting lambda in tests.
        /// </param>
        internal EventEmitter(Action<string> broadcast)
        {
            _broadcast = broadcast ?? (_ => { });
        }

        // ---- notification emitters ----------------------------------------

        internal void EmitSceneChanged(string sceneName) =>
            Emit("event.scene_changed",
                $"{{\"scene_name\":\"{Esc(sceneName)}\",\"timestamp\":{Ts()}}}");

        internal void EmitWidgetAppeared(string nodeId) =>
            Emit("event.widget_appeared",
                $"{{\"id\":\"{Esc(nodeId)}\",\"timestamp\":{Ts()}}}");

        internal void EmitWidgetDisappeared(string nodeId) =>
            Emit("event.widget_disappeared",
                $"{{\"id\":\"{Esc(nodeId)}\",\"timestamp\":{Ts()}}}");

        internal void EmitTextChanged(string nodeId, string newText) =>
            Emit("event.text_changed",
                $"{{\"id\":\"{Esc(nodeId)}\",\"text\":\"{Esc(newText ?? "")}\",\"timestamp\":{Ts()}}}");

        // ---- helpers ------------------------------------------------------

        void Emit(string method, string paramsJson) =>
            _broadcast(
                $"{{\"jsonrpc\":\"2.0\",\"method\":\"{method}\",\"params\":{paramsJson}}}");

        // JSON-escape a string value (re-uses NodeSerializer's escaper).
        static string Esc(string s) => NodeSerializer.Esc(s ?? "");

        // Unix timestamp with millisecond precision, formatted as a JSON number.
        static string Ts() =>
            (DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0)
                .ToString("F3", CultureInfo.InvariantCulture);
    }
}
