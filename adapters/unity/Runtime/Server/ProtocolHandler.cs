using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Text;
using System.Text.RegularExpressions;
using UnityEngine;

namespace AutoAgent
{
    /// <summary>
    /// JSON-RPC 2.0 dispatcher. Thread-safe: background WS thread enqueues work;
    /// Unity main thread (AutoAgentBootstrap.Update) drains the queue.
    /// </summary>
    internal class ProtocolHandler
    {
        internal struct MainThreadJob
        {
            public string RequestJson;
            public Action<string> Reply;
        }

        readonly ConcurrentQueue<MainThreadJob> _queue = new ConcurrentQueue<MainThreadJob>();

        // Called by WebSocketServer on its background thread.
        public void Enqueue(string requestJson, Action<string> reply) =>
            _queue.Enqueue(new MainThreadJob { RequestJson = requestJson, Reply = reply });

        // Called by AutoAgentBootstrap.Update() on the Unity main thread.
        public void DrainOnMainThread()
        {
            while (_queue.TryDequeue(out var job))
            {
                string response;
                try { response = Dispatch(job.RequestJson); }
                catch (Exception ex) { response = ErrorResponse(null, -32603, ex.Message); }
                job.Reply(response);
            }
        }

        // ------------------------------------------------------------------ dispatch

        string Dispatch(string json)
        {
            if (!TryParseRequest(json, out string method, out object id, out string paramsJson))
                return ErrorResponse(null, -32700, "parse error");

            try
            {
                return method switch
                {
                    "negotiate_version" => HandleNegotiateVersion(id, paramsJson),
                    "dump_tree"         => HandleDumpTree(id),
                    "find_widget"       => HandleFindWidget(id, paramsJson),
                    "get_widget"        => HandleGetWidget(id, paramsJson),
                    "click"             => HandleClick(id, paramsJson),
                    "send_text"         => HandleSendText(id, paramsJson),
                    "drag"              => HandleDrag(id, paramsJson),
                    "scroll"            => HandleScroll(id, paramsJson),
                    "take_screenshot"   => HandleTakeScreenshot(id, paramsJson),
                    _                   => ErrorResponse(id, -32601, $"method not found: {method}"),
                };
            }
            catch (WireException we)
            {
                // A typed wire error (e.g. -32002 WidgetNotInteractable) —
                // surface its own code rather than a generic internal error.
                return ErrorResponse(id, we.Code, we.Message);
            }
            catch (Exception ex)
            {
                return ErrorResponse(id, -32603, ex.Message);
            }
        }

        // ------------------------------------------------------------------ handlers

        static string HandleNegotiateVersion(object id, string paramsJson)
        {
            // params: { "client_version": "0.1" }
            // result: { "server_version": "0.1", "accepted": true }
            return OkResponse(id, "{\"server_version\":\"0.1\",\"accepted\":true}");
        }

        static string HandleDumpTree(object id)
        {
            var nodes = UGuiReflector.DumpActiveScene();
            var json = NodeSerializer.SerializeTree(nodes);
            return OkResponse(id, json);
        }

        static string HandleFindWidget(object id, string paramsJson)
        {
            string role = ExtractStringParam(paramsJson, "logical_role");
            string text = ExtractStringParam(paramsJson, "text");

            var nodes = UGuiReflector.DumpActiveScene();
            var matches = new List<string>();
            foreach (var n in nodes)
            {
                if (role != null && (n.Meta == null || n.Meta.LogicalRole != role)) continue;
                if (text != null)
                {
                    var go = EngineInputDriver.FindById(n.Id);
                    string nodeText = go != null ? GetTextContent(go) : null;
                    if (nodeText == null || !nodeText.Contains(text)) continue;
                }
                matches.Add(n.Id);
            }

            var sb = new StringBuilder("[");
            for (int i = 0; i < matches.Count; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append('"').Append(NodeSerializer.Esc(matches[i])).Append('"');
            }
            sb.Append(']');
            return OkResponse(id, sb.ToString());
        }

        static string HandleGetWidget(object id, string paramsJson)
        {
            string nodeId = ExtractStringParam(paramsJson, "id");
            if (string.IsNullOrEmpty(nodeId))
                return ErrorResponse(id, -32602, "missing param: id");

            var nodes = UGuiReflector.DumpActiveScene();
            foreach (var n in nodes)
                if (n.Id == nodeId)
                    return OkResponse(id, NodeSerializer.SerializeTree(new List<NodeData> { n })
                                                        .TrimStart('[').TrimEnd(']'));
            return ErrorResponse(id, -32001, $"widget not found: {nodeId}");
        }

        static string HandleClick(object id, string paramsJson)
        {
            string nodeId = ExtractStringParam(paramsJson, "id");
            if (string.IsNullOrEmpty(nodeId))
                return ErrorResponse(id, -32602, "missing param: id");
            // Click throws WireException on failure (widget not found /
            // not interactable); Dispatch's catch turns it into an error.
            EngineInputDriver.Click(nodeId);
            return OkResponse(id, "null");
        }

        static string HandleSendText(object id, string paramsJson)
        {
            string nodeId = ExtractStringParam(paramsJson, "id");
            string text   = ExtractStringParam(paramsJson, "text") ?? "";
            if (string.IsNullOrEmpty(nodeId))
                return ErrorResponse(id, -32602, "missing param: id");
            // clear_first defaults to true (replace the field's old value).
            bool clearFirst = ExtractBoolParam(paramsJson, "clear_first", true);
            // SendText throws WireException on failure; Dispatch's catch maps it.
            EngineInputDriver.SendText(nodeId, text, clearFirst);
            return OkResponse(id, "null");
        }

        static string HandleDrag(object id, string paramsJson)
        {
            string fromId = ExtractStringParam(paramsJson, "from_id");
            string toId   = ExtractStringParam(paramsJson, "to_id");
            if (string.IsNullOrEmpty(fromId) || string.IsNullOrEmpty(toId))
                return ErrorResponse(id, -32602, "missing params: from_id / to_id");
            bool ok = EngineInputDriver.Drag(fromId, toId);
            return ok ? OkResponse(id, "null")
                      : ErrorResponse(id, -32001, "source or destination widget not found");
        }

        static string HandleScroll(object id, string paramsJson)
        {
            string nodeId = ExtractStringParam(paramsJson, "id");
            if (string.IsNullOrEmpty(nodeId))
                return ErrorResponse(id, -32602, "missing param: id");

            float dx = ExtractFloatParam(paramsJson, "delta_x");
            float dy = ExtractFloatParam(paramsJson, "delta_y");
            bool ok = EngineInputDriver.Scroll(nodeId, dx, dy);
            return ok ? OkResponse(id, "null")
                      : ErrorResponse(id, -32001, $"widget not found: {nodeId}");
        }

        static string HandleTakeScreenshot(object id, string paramsJson)
        {
            string path = ExtractStringParam(paramsJson, "path");
            if (string.IsNullOrEmpty(path))
                return ErrorResponse(id, -32602, "missing param: path");
            // Fire-and-forget: a coroutine captures the frame and writes the PNG.
            AutoAgentBootstrap.RequestScreenshot(path);
            return OkResponse(id, $"{{\"path\":\"{NodeSerializer.Esc(path)}\"}}");
        }

        // ------------------------------------------------------------------ JSON-RPC helpers

        static string OkResponse(object id, string resultJson) =>
            $"{{\"jsonrpc\":\"2.0\",\"id\":{IdJson(id)},\"result\":{resultJson}}}";

        static string ErrorResponse(object id, int code, string message) =>
            $"{{\"jsonrpc\":\"2.0\",\"id\":{IdJson(id)},\"error\":{{\"code\":{code},\"message\":\"{NodeSerializer.Esc(message)}\"}}}}";

        static string IdJson(object id)
        {
            if (id == null) return "null";
            if (id is string s) return $"\"{NodeSerializer.Esc(s)}\"";
            if (id is long l)
                return l.ToString(System.Globalization.CultureInfo.InvariantCulture);
            if (id is double d)
                return d.ToString(System.Globalization.CultureInfo.InvariantCulture);
            return id.ToString();
        }

        // ------------------------------------------------------------------ minimal JSON parser

        static bool TryParseRequest(string json, out string method, out object id, out string paramsJson)
        {
            method = ExtractStringValue(json, "method");
            id = ExtractId(json);
            paramsJson = ExtractObject(json, "params");
            return method != null;
        }

        static string ExtractStringValue(string json, string key)
        {
            var m = Regex.Match(json, $"\"{Regex.Escape(key)}\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");
            return m.Success ? Unescape(m.Groups[1].Value) : null;
        }

        static object ExtractId(string json)
        {
            // string id
            var ms = Regex.Match(json, "\"id\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");
            if (ms.Success) return Unescape(ms.Groups[1].Value);
            // number id — return a numeric type so IdJson emits it unquoted
            var mn = Regex.Match(json, "\"id\"\\s*:\\s*(-?\\d+(?:\\.\\d+)?)");
            if (mn.Success)
            {
                string raw = mn.Groups[1].Value;
                if (long.TryParse(raw, out long l)) return l;
                if (double.TryParse(raw, System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture, out double d))
                    return d;
            }
            return null;
        }

        // Extract the value of a top-level key whose value is a JSON object {…} or array […].
        static string ExtractObject(string json, string key)
        {
            int ki = json.IndexOf($"\"{key}\"", StringComparison.Ordinal);
            if (ki < 0) return null;
            int colon = json.IndexOf(':', ki);
            if (colon < 0) return null;
            int start = colon + 1;
            while (start < json.Length && char.IsWhiteSpace(json[start])) start++;
            if (start >= json.Length) return null;
            char open = json[start];
            char close = open == '{' ? '}' : open == '[' ? ']' : '\0';
            if (close == '\0') return null;
            int depth = 0;
            for (int i = start; i < json.Length; i++)
            {
                if (json[i] == open)  depth++;
                if (json[i] == close) { depth--; if (depth == 0) return json.Substring(start, i - start + 1); }
            }
            return null;
        }

        static string ExtractStringParam(string paramsJson, string key) =>
            paramsJson == null ? null : ExtractStringValue(paramsJson, key);

        static float ExtractFloatParam(string paramsJson, string key)
        {
            if (paramsJson == null) return 0f;
            var m = Regex.Match(paramsJson, $"\"{Regex.Escape(key)}\"\\s*:\\s*(-?\\d+(?:\\.\\d+)?)");
            return m.Success && float.TryParse(m.Groups[1].Value,
                System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out float v) ? v : 0f;
        }

        static bool ExtractBoolParam(string paramsJson, string key, bool fallback)
        {
            if (paramsJson == null) return fallback;
            var m = Regex.Match(paramsJson, $"\"{Regex.Escape(key)}\"\\s*:\\s*(true|false)");
            return m.Success ? m.Groups[1].Value == "true" : fallback;
        }

        static string Unescape(string s) =>
            s.Replace("\\\"", "\"").Replace("\\\\", "\\")
             .Replace("\\n", "\n").Replace("\\r", "\r").Replace("\\t", "\t");

        static string GetTextContent(UnityEngine.GameObject go)
        {
            var tmp = go.GetComponent<TMPro.TMP_Text>();
            if (tmp != null) return tmp.text;
            var leg = go.GetComponent<UnityEngine.UI.Text>();
            if (leg != null) return leg.text;
            return null;
        }
    }
}
