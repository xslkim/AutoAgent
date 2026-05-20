using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using TMPro;

namespace AutoAgent
{
    /// <summary>
    /// Polls the active scene every <see cref="PollIntervalFrames"/> frames and
    /// fires <see cref="EventEmitter"/> notifications when widget state changes:
    ///
    ///   <c>event.widget_appeared</c>    — node transitions to active-in-hierarchy
    ///   <c>event.widget_disappeared</c> — node transitions to inactive or is removed
    ///   <c>event.text_changed</c>       — text content of a node changed since last poll
    ///
    /// Polling is throttled to avoid per-frame reflection cost. Call
    /// <see cref="PollNow"/> directly in tests for deterministic results.
    ///
    /// Attach via <see cref="AutoAgentBootstrap"/> alongside
    /// <see cref="SceneChangeWatcher"/>.
    /// </summary>
    internal sealed class WidgetLifecycleWatcher : MonoBehaviour
    {
        // One poll per N frames. Default ~2 per second at 60 fps.
        internal int PollIntervalFrames = 30;

        EventEmitter _emitter;
        int          _frameCounter;

        // Per-node state: id → (visible, text-or-null).
        // "text" is null for nodes that have no text component.
        readonly Dictionary<string, bool>   _lastVisible = new Dictionary<string, bool>();
        readonly Dictionary<string, string> _lastText    = new Dictionary<string, string>();

        internal void Init(EventEmitter emitter, int pollIntervalFrames = 30)
        {
            _emitter           = emitter;
            PollIntervalFrames = pollIntervalFrames;
        }

        void Update()
        {
            if (++_frameCounter < PollIntervalFrames) return;
            _frameCounter = 0;
            PollNow();
        }

        /// <summary>
        /// Run one poll cycle. May emit any number of notifications.
        /// Exposed as <c>internal</c> so tests can drive it synchronously.
        /// </summary>
        internal void PollNow()
        {
            var nodes    = UGuiReflector.DumpActiveScene();
            var seen     = new HashSet<string>(nodes.Count);

            foreach (var node in nodes)
            {
                string id      = node.Id;
                bool   visible = node.Visual?.Visible ?? false;
                seen.Add(id);

                // --- visibility change ---
                if (_lastVisible.TryGetValue(id, out bool wasVisible))
                {
                    if (visible && !wasVisible)
                        _emitter?.EmitWidgetAppeared(id);
                    else if (!visible && wasVisible)
                        _emitter?.EmitWidgetDisappeared(id);
                }
                else
                {
                    // First time we see this node: emit appeared if active.
                    if (visible)
                        _emitter?.EmitWidgetAppeared(id);
                }
                _lastVisible[id] = visible;

                // --- text change ---
                var go = EngineInputDriver.FindById(id);
                if (go != null)
                {
                    string text = ReadText(go);
                    if (text != null) // node has a text component
                    {
                        if (_lastText.TryGetValue(id, out string prev))
                        {
                            if (text != prev)
                                _emitter?.EmitTextChanged(id, text);
                        }
                        // First observation: record but don't emit.
                        _lastText[id] = text;
                    }
                }
            }

            // --- nodes removed from scene ---
            var toRemove = new List<string>();
            foreach (var kvp in _lastVisible)
            {
                if (!seen.Contains(kvp.Key))
                {
                    if (kvp.Value) // was visible before it vanished
                        _emitter?.EmitWidgetDisappeared(kvp.Key);
                    toRemove.Add(kvp.Key);
                }
            }
            foreach (var id in toRemove)
            {
                _lastVisible.Remove(id);
                _lastText.Remove(id);
            }
        }

        // ---- helpers --------------------------------------------------------

        static string ReadText(GameObject go)
        {
            var tmp = go.GetComponent<TMP_Text>();
            if (tmp != null) return tmp.text;
            var tmpIf = go.GetComponent<TMP_InputField>();
            if (tmpIf != null) return tmpIf.text;
            var leg = go.GetComponent<Text>();
            if (leg != null) return leg.text;
            var legIf = go.GetComponent<InputField>();
            if (legIf != null) return legIf.text;
            return null; // no text component
        }
    }
}
