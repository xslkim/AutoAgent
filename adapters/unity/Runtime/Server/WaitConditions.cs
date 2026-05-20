using System;
using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace AutoAgent
{
    /// <summary>
    /// Polls a wire-protocol <c>wait_for</c> condition until it holds or the
    /// timeout expires. Conditions:
    ///   <c>widget_appeared</c>    — node exists and is active in hierarchy
    ///   <c>widget_disappeared</c> — node no longer exists, or is inactive
    ///   <c>visible</c>            — node is active AND effective alpha &gt; 0
    ///   <c>text_changed</c>       — node's text content differs from the
    ///                               supplied baseline
    /// </summary>
    internal static class WaitConditions
    {
        public const int DefaultTimeoutMs = 5000;

        /// <summary>Default coroutine entry — clocked by Time.realtimeSinceStartup.</summary>
        public static IEnumerator WaitFor(string condition, string nodeId,
                                          string baselineText, int timeoutMs)
            => WaitFor(condition, nodeId, baselineText, timeoutMs,
                       () => Time.realtimeSinceStartup);

        /// <summary>Test-friendly entry: accepts a custom clock for deterministic
        /// timeout exercises.</summary>
        internal static IEnumerator WaitFor(string condition, string nodeId,
                                            string baselineText, int timeoutMs,
                                            Func<float> clock)
        {
            if (timeoutMs <= 0) timeoutMs = DefaultTimeoutMs;
            float deadline = clock() + (timeoutMs / 1000f);

            while (true)
            {
                if (CheckCondition(condition, nodeId, baselineText))
                    yield break;
                if (clock() >= deadline)
                    throw new WireException(WireError.Timeout,
                        $"wait_for '{condition}' (id={nodeId}) timed out after {timeoutMs}ms");
                yield return null;
            }
        }

        /// <summary>One-shot evaluation of a condition. Exposed for tests.</summary>
        public static bool CheckCondition(string condition, string nodeId, string baselineText)
        {
            if (string.IsNullOrEmpty(condition))
                throw new WireException(WireError.InvalidParams,
                    "wait_for condition is required");

            var go = string.IsNullOrEmpty(nodeId)
                ? null
                : EngineInputDriver.FindById(nodeId);

            switch (condition.Trim().ToLowerInvariant())
            {
                case "widget_appeared":
                    return go != null && go.activeInHierarchy;

                case "widget_disappeared":
                    return go == null || !go.activeInHierarchy;

                case "visible":
                    return go != null && IsVisible(go);

                case "text_changed":
                    // Need the node to exist so the comparison is meaningful;
                    // a vanished node is "disappeared", not "text changed".
                    if (go == null) return false;
                    return !string.Equals(ReadText(go), baselineText, StringComparison.Ordinal);

                default:
                    throw new WireException(WireError.InvalidParams,
                        $"unknown wait_for condition: {condition}");
            }
        }

        // ---- helpers -------------------------------------------------------

        // "Visible" = drawn on screen. We approximate with: GameObject active,
        // CanvasGroup alpha > 0 if present, and any Graphic's color alpha > 0.
        static bool IsVisible(GameObject go)
        {
            if (!go.activeInHierarchy) return false;

            var cg = go.GetComponent<CanvasGroup>();
            if (cg != null && cg.alpha <= 0f) return false;

            var graphic = go.GetComponent<Graphic>();
            if (graphic != null && graphic.color.a <= 0f) return false;

            return true;
        }

        // Read text from any of the common Unity text components.
        static string ReadText(GameObject go)
        {
            var tmp = go.GetComponent<TMP_Text>();
            if (tmp != null) return tmp.text;
            var tmpInput = go.GetComponent<TMP_InputField>();
            if (tmpInput != null) return tmpInput.text;
            var legacy = go.GetComponent<Text>();
            if (legacy != null) return legacy.text;
            var legacyInput = go.GetComponent<InputField>();
            if (legacyInput != null) return legacyInput.text;
            return null;
        }
    }
}
