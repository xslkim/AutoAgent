using System;
using System.Reflection;
using UnityEngine;

namespace AutoAgent
{
    /// <summary>
    /// Runtime C# reflection helper for <c>get_property</c> / <c>set_property</c>.
    ///
    /// Category rules (enforced server-side):
    ///   "behavior" or "meta" → allowed
    ///   "visual"             → always rejected with -32003 VisualPropertyWrite
    ///
    /// Fields and auto-properties are resolved in declaration order; the first
    /// match wins. Both public and non-public members are searched so that
    /// private/protected serialized fields (common in Unity) can be reached.
    /// </summary>
    internal static class PropertyAccessor
    {
        static readonly BindingFlags AnyInstance =
            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;

        // ------------------------------------------------------------------ public API

        internal static string GetProperty(GameObject go, string scriptName, string propertyName)
        {
            var mb = FindScript(go, scriptName);
            if (mb == null)
                throw new WireException(WireErrorCode.WidgetNotFound,
                    $"script not found: {scriptName}");

            var type = mb.GetType();

            var field = type.GetField(propertyName, AnyInstance);
            if (field != null) return ScriptInvoker.SerializeValue(field.GetValue(mb));

            var prop = type.GetProperty(propertyName, AnyInstance);
            if (prop != null && prop.CanRead)
                return ScriptInvoker.SerializeValue(prop.GetValue(mb));

            throw new WireException(WireErrorCode.WidgetNotInteractable,
                $"property not found: {propertyName}");
        }

        internal static void SetProperty(GameObject go, string scriptName,
            string propertyName, string valueJson, string category)
        {
            if (string.Equals(category, "visual", StringComparison.OrdinalIgnoreCase))
                throw new WireException(WireErrorCode.VisualPropertyWrite,
                    $"visual property writes are not allowed: {propertyName}");

            var mb = FindScript(go, scriptName);
            if (mb == null)
                throw new WireException(WireErrorCode.WidgetNotFound,
                    $"script not found: {scriptName}");

            var type = mb.GetType();

            var field = type.GetField(propertyName, AnyInstance);
            if (field != null)
            {
                field.SetValue(mb, ScriptInvoker.Coerce(valueJson, field.FieldType));
                return;
            }

            var prop = type.GetProperty(propertyName, AnyInstance);
            if (prop != null && prop.CanWrite)
            {
                prop.SetValue(mb, ScriptInvoker.Coerce(valueJson, prop.PropertyType));
                return;
            }

            throw new WireException(WireErrorCode.WidgetNotInteractable,
                $"property not found: {propertyName}");
        }

        // ------------------------------------------------------------------ internal

        internal static MonoBehaviour FindScript(GameObject go, string scriptName)
            => ScriptInvoker.FindScript(go, scriptName);
    }
}
