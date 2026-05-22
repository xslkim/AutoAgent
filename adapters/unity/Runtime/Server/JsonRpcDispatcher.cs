using System.Text.RegularExpressions;

namespace AutoAgent
{
    /// <summary>
    /// Stateless JSON-RPC 2.0 plumbing helpers — parsing, response
    /// formatting, ID serialization. Shared between <see cref="ProtocolHandler"/>
    /// and any deferred-reply coroutine that needs to send a response later
    /// (e.g. <c>wait_for</c> via <see cref="AutoAgentBootstrap.RunWaitFor"/>).
    ///
    /// All methods are pure functions; nothing here touches Unity APIs.
    /// </summary>
    internal static class JsonRpcDispatcher
    {
        // ------------------------------------------------------------------ response builders

        internal static string OkResponse(object id, string resultJson) =>
            $"{{\"jsonrpc\":\"2.0\",\"id\":{IdJson(id)},\"result\":{resultJson}}}";

        internal static string ErrorResponse(object id, int code, string message) =>
            $"{{\"jsonrpc\":\"2.0\",\"id\":{IdJson(id)},\"error\":{{\"code\":{code},\"message\":\"{NodeSerializer.Esc(message)}\"}}}}";

        internal static string IdJson(object id)
        {
            if (id == null) return "null";
            if (id is string s) return $"\"{NodeSerializer.Esc(s)}\"";
            if (id is long l)
                return l.ToString(System.Globalization.CultureInfo.InvariantCulture);
            if (id is double d)
                return d.ToString(System.Globalization.CultureInfo.InvariantCulture);
            return id.ToString();
        }

        // ------------------------------------------------------------------ request parser

        /// <summary>
        /// Extracts <c>method</c>, <c>id</c>, and <c>params</c> from a
        /// JSON-RPC 2.0 request string. Returns false if <c>method</c> is
        /// absent (malformed / not a request).
        /// </summary>
        internal static bool TryParseRequest(string json,
            out string method, out object id, out string paramsJson)
        {
            method     = ExtractStringValue(json, "method");
            id         = ExtractId(json);
            paramsJson = ExtractObject(json, "params");
            return method != null;
        }

        // ------------------------------------------------------------------ param extractors

        internal static string ExtractStringParam(string paramsJson, string key) =>
            paramsJson == null ? null : ExtractStringValue(paramsJson, key);

        internal static float ExtractFloatParam(string paramsJson, string key)
        {
            if (paramsJson == null) return 0f;
            var m = Regex.Match(paramsJson,
                $"\"{Regex.Escape(key)}\"\\s*:\\s*(-?\\d+(?:\\.\\d+)?)");
            return m.Success && float.TryParse(m.Groups[1].Value,
                System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture,
                out float v) ? v : 0f;
        }

        internal static bool ExtractBoolParam(string paramsJson, string key, bool fallback)
        {
            if (paramsJson == null) return fallback;
            var m = Regex.Match(paramsJson,
                $"\"{Regex.Escape(key)}\"\\s*:\\s*(true|false)");
            return m.Success ? m.Groups[1].Value == "true" : fallback;
        }

        /// <summary>
        /// Extracts the raw JSON token (string, number, bool, null, object, array)
        /// for <paramref name="key"/> in <paramref name="json"/>.
        /// Returns <c>null</c> if the key is not present.
        /// </summary>
        internal static string ExtractRawValue(string json, string key)
        {
            if (json == null) return null;
            int ki = json.IndexOf($"\"{key}\"", System.StringComparison.Ordinal);
            if (ki < 0) return null;
            int colon = json.IndexOf(':', ki);
            if (colon < 0) return null;
            int start = colon + 1;
            while (start < json.Length && char.IsWhiteSpace(json[start])) start++;
            if (start >= json.Length) return null;
            char first = json[start];
            // object / array — delegate to balanced-bracket extractor
            if (first == '{' || first == '[') return ExtractObject(json, key);
            // quoted string
            if (first == '"')
            {
                int end = start + 1;
                while (end < json.Length)
                {
                    if (json[end] == '\\') { end += 2; continue; }
                    if (json[end] == '"')  { end++; break; }
                    end++;
                }
                return json.Substring(start, end - start);
            }
            // keyword (null / true / false) or number
            {
                int end = start;
                while (end < json.Length && json[end] != ',' &&
                       json[end] != '}' && json[end] != ']')
                    end++;
                return json.Substring(start, end - start).Trim();
            }
        }

        // ------------------------------------------------------------------ internal JSON helpers

        static string ExtractStringValue(string json, string key)
        {
            var m = Regex.Match(json,
                $"\"{Regex.Escape(key)}\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");
            return m.Success ? Unescape(m.Groups[1].Value) : null;
        }

        static object ExtractId(string json)
        {
            // string id
            var ms = Regex.Match(json, "\"id\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");
            if (ms.Success) return Unescape(ms.Groups[1].Value);
            // number id — return numeric type so IdJson emits it unquoted
            var mn = Regex.Match(json, "\"id\"\\s*:\\s*(-?\\d+(?:\\.\\d+)?)");
            if (mn.Success)
            {
                string raw = mn.Groups[1].Value;
                if (long.TryParse(raw, out long l)) return l;
                if (double.TryParse(raw,
                        System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture,
                        out double d))
                    return d;
            }
            return null;
        }

        // Extract the value of a top-level key whose value is a JSON
        // object {…} or array […], preserving the entire nested structure.
        static string ExtractObject(string json, string key)
        {
            int ki = json.IndexOf($"\"{key}\"", System.StringComparison.Ordinal);
            if (ki < 0) return null;
            int colon = json.IndexOf(':', ki);
            if (colon < 0) return null;
            int start = colon + 1;
            while (start < json.Length && char.IsWhiteSpace(json[start])) start++;
            if (start >= json.Length) return null;
            char open  = json[start];
            char close = open == '{' ? '}' : open == '[' ? ']' : '\0';
            if (close == '\0') return null;
            int depth = 0;
            for (int i = start; i < json.Length; i++)
            {
                if (json[i] == open)  depth++;
                if (json[i] == close)
                {
                    depth--;
                    if (depth == 0) return json.Substring(start, i - start + 1);
                }
            }
            return null;
        }

        internal static string Unescape(string s) =>
            s.Replace("\\\"", "\"").Replace("\\\\", "\\")
             .Replace("\\n", "\n").Replace("\\r", "\r").Replace("\\t", "\t");
    }
}
