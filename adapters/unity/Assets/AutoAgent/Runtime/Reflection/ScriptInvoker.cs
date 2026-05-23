using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace AutoAgent
{
    /// <summary>
    /// Runtime C# reflection helper for <c>invoke_method</c>.
    /// Locates a MonoBehaviour by script name on a GameObject and invokes a
    /// named public (or non-public) method with JSON-decoded positional args.
    /// </summary>
    internal static class ScriptInvoker
    {
        internal static string Invoke(GameObject go, string scriptName,
            string methodName, string argsJson)
        {
            var mb = FindScript(go, scriptName);
            if (mb == null)
                throw new WireException(WireErrorCode.WidgetNotFound,
                    $"script not found: {scriptName}");

            var type   = mb.GetType();
            var method = type.GetMethod(methodName,
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            if (method == null)
                throw new WireException(WireErrorCode.WidgetNotInteractable,
                    $"method not found: {methodName}");

            var parameters = method.GetParameters();
            object[] args;
            try   { args = ParseArgs(argsJson, parameters); }
            catch { args = new object[parameters.Length]; }

            object result;
            try   { result = method.Invoke(mb, args); }
            catch (TargetInvocationException tie)
            {
                throw new WireException(WireErrorCode.InternalError,
                    tie.InnerException?.Message ?? tie.Message);
            }

            return SerializeValue(result);
        }

        // ------------------------------------------------------------------ helpers

        internal static MonoBehaviour FindScript(GameObject go, string scriptName)
        {
            foreach (var mb in go.GetComponents<MonoBehaviour>())
                if (mb.GetType().Name == scriptName) return mb;
            return null;
        }

        /// <summary>Serialize a CLR value to a JSON token.</summary>
        internal static string SerializeValue(object v)
        {
            if (v == null)      return "null";
            if (v is bool b)    return b ? "true" : "false";
            if (v is string s)  return $"\"{NodeSerializer.Esc(s)}\"";
            if (v is int i)     return i.ToString(Inv);
            if (v is long l)    return l.ToString(Inv);
            if (v is float f)   return f.ToString("0.##", Inv);
            if (v is double d)  return d.ToString("0.##", Inv);
            return $"\"{NodeSerializer.Esc(v.ToString())}\"";
        }

        // ------------------------------------------------------------------ arg parsing

        static object[] ParseArgs(string argsJson, ParameterInfo[] parameters)
        {
            var result = new object[parameters.Length];
            if (parameters.Length == 0) return result;

            argsJson = argsJson?.Trim();
            if (string.IsNullOrEmpty(argsJson) || argsJson == "[]") return result;

            // Strip outer brackets
            string inner = argsJson.Substring(1, argsJson.Length - 2).Trim();
            var tokens   = SplitJsonArray(inner);

            for (int i = 0; i < Math.Min(tokens.Count, parameters.Length); i++)
                result[i] = Coerce(tokens[i].Trim(), parameters[i].ParameterType);
            return result;
        }

        // Split a flat JSON array body (no outer brackets) on top-level commas.
        static List<string> SplitJsonArray(string json)
        {
            var tokens    = new List<string>();
            int depth     = 0;
            int start     = 0;
            bool inString = false;
            for (int i = 0; i < json.Length; i++)
            {
                char c = json[i];
                if (inString) { if (c == '\\') i++; else if (c == '"') inString = false; continue; }
                if (c == '"')       { inString = true; continue; }
                if (c == '{' || c == '[') depth++;
                if (c == '}' || c == ']') depth--;
                if (c == ',' && depth == 0) { tokens.Add(json.Substring(start, i - start)); start = i + 1; }
            }
            if (start < json.Length) tokens.Add(json.Substring(start));
            return tokens;
        }

        internal static object Coerce(string token, Type targetType)
        {
            token = token?.Trim();
            if (string.IsNullOrEmpty(token) || token == "null") return null;
            if (token == "true")  return Convert.ChangeType(true,  targetType);
            if (token == "false") return Convert.ChangeType(false, targetType);
            if (token.StartsWith("\"") && token.EndsWith("\""))
            {
                string s = JsonRpcDispatcher.Unescape(token.Substring(1, token.Length - 2));
                return Convert.ChangeType(s, targetType, Inv);
            }
            if (targetType == typeof(int)    && int.TryParse(token, out int   iv)) return iv;
            if (targetType == typeof(long)   && long.TryParse(token, out long  lv)) return lv;
            if (targetType == typeof(float)  && float.TryParse(token,
                    System.Globalization.NumberStyles.Float, Inv, out float fv)) return fv;
            if (targetType == typeof(double) && double.TryParse(token,
                    System.Globalization.NumberStyles.Float, Inv, out double dv)) return dv;
            return Convert.ChangeType(token, targetType, Inv);
        }

        static readonly System.Globalization.CultureInfo Inv =
            System.Globalization.CultureInfo.InvariantCulture;
    }
}
