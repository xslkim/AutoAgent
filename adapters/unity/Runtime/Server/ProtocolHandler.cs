using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Text;
using UnityEngine;

namespace AutoAgent
{
    /// <summary>
    /// JSON-RPC 2.0 dispatcher. Thread-safe: background WS thread enqueues work
    /// via <see cref="Enqueue"/>; Unity main thread (<see cref="AutoAgentBootstrap.Update"/>)
    /// drains the queue via <see cref="DrainOnMainThread"/>.
    ///
    /// Internally uses <see cref="MainThreadDispatcher"/> to marshal every
    /// request action to the Unity main thread before execution.
    ///
    /// Most handlers are synchronous and call <c>reply</c> immediately.
    /// <c>wait_for</c> is the exception: it starts a coroutine via
    /// <see cref="AutoAgentBootstrap.RunWaitFor"/> and defers the reply until
    /// the condition is met or the timeout expires.
    ///
    /// Pure JSON-RPC plumbing lives in <see cref="JsonRpcDispatcher"/>;
    /// error codes are defined in <see cref="WireErrorCode"/>.
    /// </summary>
    internal class ProtocolHandler
    {
        readonly MainThreadDispatcher _dispatcher;
        readonly OrphanTracker _orphanTracker;

        public ProtocolHandler() : this(new MainThreadDispatcher(), OrphanTracker.ForProject()) { }

        /// <summary>Injection constructor for tests. Pass <c>null</c> for tracker to disable
        /// orphan tracking (list_orphan_ids will return []).</summary>
        internal ProtocolHandler(MainThreadDispatcher dispatcher, OrphanTracker tracker = null)
        {
            _dispatcher    = dispatcher;
            _orphanTracker = tracker;
        }

        // Called by WebSocketServer on its background thread.
        // The work is wrapped in an action and posted to the main-thread queue.
        public void Enqueue(string requestJson, Action<string> reply)
        {
            _dispatcher.Post(() =>
            {
                string response;
                try { response = Dispatch(requestJson, reply); }
                catch (Exception ex)
                {
                    response = JsonRpcDispatcher.ErrorResponse(
                        null, WireError.InternalError, ex.Message);
                }
                // null → deferred (wait_for coroutine will call reply later)
                if (response != null) reply(response);
            });
        }

        // Called by AutoAgentBootstrap.Update() on the Unity main thread.
        public void DrainOnMainThread() => _dispatcher.FlushOnMainThread();

        // ------------------------------------------------------------------ dispatch

        // Returns null for async methods (wait_for) that send their reply
        // via a coroutine; returns a non-null string for all sync methods.
        string Dispatch(string json, Action<string> reply)
        {
            if (!JsonRpcDispatcher.TryParseRequest(json,
                    out string method, out object id, out string paramsJson))
                return JsonRpcDispatcher.ErrorResponse(null, WireError.ParseError, "parse error");

            try
            {
                return method switch
                {
                    "negotiate_version" => HandleNegotiateVersion(id, paramsJson),
                    "dump_tree"         => HandleDumpTree(id, _orphanTracker),
                    "pin_id"            => PinIdHandler.HandlePinId(id, paramsJson),
                    "list_orphan_ids"   => PinIdHandler.HandleListOrphanIds(id, _orphanTracker),
                    "find_widget"       => HandleFindWidget(id, paramsJson),
                    "get_widget"        => HandleGetWidget(id, paramsJson),
                    "click"             => HandleClick(id, paramsJson),
                    "send_text"         => HandleSendText(id, paramsJson),
                    "drag"              => HandleDrag(id, paramsJson),
                    "scroll"            => HandleScroll(id, paramsJson),
                    "key_press"         => HandleKeyPress(id, paramsJson),
                    "take_screenshot"   => HandleTakeScreenshot(id, paramsJson),
                    "invoke_method"     => HandleInvokeMethod(id, paramsJson),
                    "get_property"      => HandleGetProperty(id, paramsJson),
                    "set_property"      => HandleSetProperty(id, paramsJson),
                    // Async: starts a coroutine, reply is sent by the coroutine.
                    "wait_for"          => HandleWaitFor(id, paramsJson, reply),
                    _                   => JsonRpcDispatcher.ErrorResponse(
                                              id, WireError.MethodNotFound,
                                              $"method not found: {method}"),
                };
            }
            catch (WireException we)
            {
                // A typed wire error (e.g. -32002 WidgetNotInteractable) —
                // surface its own code rather than a generic internal error.
                return JsonRpcDispatcher.ErrorResponse(id, we.Code, we.Message);
            }
            catch (Exception ex)
            {
                return JsonRpcDispatcher.ErrorResponse(id, WireError.InternalError, ex.Message);
            }
        }

        // ------------------------------------------------------------------ handlers

        static string HandleNegotiateVersion(object id, string paramsJson)
        {
            // params: { "client_version": "0.1" }
            // result: { "server_version": "0.1", "accepted": true }
            return JsonRpcDispatcher.OkResponse(id,
                "{\"server_version\":\"0.1\",\"accepted\":true}");
        }

        static string HandleDumpTree(object id, OrphanTracker tracker = null)
        {
            var nodes = UGuiReflector.DumpActiveScene();
            // Persist the current id set so that list_orphan_ids can diff against it.
            tracker?.Save(nodes.ConvertAll(n => n.Id));
            var json  = NodeSerializer.SerializeTree(nodes);
            return JsonRpcDispatcher.OkResponse(id, json);
        }

        static string HandleFindWidget(object id, string paramsJson)
        {
            string role = JsonRpcDispatcher.ExtractStringParam(paramsJson, "logical_role");
            string text = JsonRpcDispatcher.ExtractStringParam(paramsJson, "text");

            var nodes   = UGuiReflector.DumpActiveScene();
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
            return JsonRpcDispatcher.OkResponse(id, sb.ToString());
        }

        static string HandleGetWidget(object id, string paramsJson)
        {
            string nodeId = JsonRpcDispatcher.ExtractStringParam(paramsJson, "id");
            if (string.IsNullOrEmpty(nodeId))
                return JsonRpcDispatcher.ErrorResponse(id, WireError.InvalidParams, "missing param: id");

            var nodes = UGuiReflector.DumpActiveScene();
            foreach (var n in nodes)
                if (n.Id == nodeId)
                    return JsonRpcDispatcher.OkResponse(id,
                        NodeSerializer.SerializeTree(new List<NodeData> { n })
                                       .TrimStart('[').TrimEnd(']'));
            return JsonRpcDispatcher.ErrorResponse(id, WireError.WidgetNotFound, $"widget not found: {nodeId}");
        }

        static string HandleClick(object id, string paramsJson)
        {
            string nodeId = JsonRpcDispatcher.ExtractStringParam(paramsJson, "id");
            if (string.IsNullOrEmpty(nodeId))
                return JsonRpcDispatcher.ErrorResponse(id, WireError.InvalidParams, "missing param: id");
            // Click throws WireException on failure; Dispatch's catch maps it.
            EngineInputDriver.Click(nodeId);
            return JsonRpcDispatcher.OkResponse(id, "null");
        }

        static string HandleSendText(object id, string paramsJson)
        {
            string nodeId = JsonRpcDispatcher.ExtractStringParam(paramsJson, "id");
            string text   = JsonRpcDispatcher.ExtractStringParam(paramsJson, "text") ?? "";
            if (string.IsNullOrEmpty(nodeId))
                return JsonRpcDispatcher.ErrorResponse(id, WireError.InvalidParams, "missing param: id");
            bool clearFirst = JsonRpcDispatcher.ExtractBoolParam(paramsJson, "clear_first", true);
            EngineInputDriver.SendText(nodeId, text, clearFirst);
            return JsonRpcDispatcher.OkResponse(id, "null");
        }

        static string HandleDrag(object id, string paramsJson)
        {
            string fromId = JsonRpcDispatcher.ExtractStringParam(paramsJson, "from_id");
            string toId   = JsonRpcDispatcher.ExtractStringParam(paramsJson, "to_id");
            if (string.IsNullOrEmpty(fromId) || string.IsNullOrEmpty(toId))
                return JsonRpcDispatcher.ErrorResponse(id, WireError.InvalidParams,
                    "missing params: from_id / to_id");
            int durationMs = (int)JsonRpcDispatcher.ExtractFloatParam(paramsJson, "duration_ms");
            AutoAgentBootstrap.RunDrag(fromId, toId, durationMs);
            return JsonRpcDispatcher.OkResponse(id, "null");
        }

        static string HandleScroll(object id, string paramsJson)
        {
            string nodeId = JsonRpcDispatcher.ExtractStringParam(paramsJson, "id");
            if (string.IsNullOrEmpty(nodeId))
                return JsonRpcDispatcher.ErrorResponse(id, WireError.InvalidParams, "missing param: id");
            float dx = JsonRpcDispatcher.ExtractFloatParam(paramsJson, "delta_x");
            float dy = JsonRpcDispatcher.ExtractFloatParam(paramsJson, "delta_y");
            EngineInputDriver.Scroll(nodeId, dx, dy);
            return JsonRpcDispatcher.OkResponse(id, "null");
        }

        static string HandleKeyPress(object id, string paramsJson)
        {
            string nodeId = JsonRpcDispatcher.ExtractStringParam(paramsJson, "id");
            string key    = JsonRpcDispatcher.ExtractStringParam(paramsJson, "key");
            if (string.IsNullOrEmpty(nodeId))
                return JsonRpcDispatcher.ErrorResponse(id, WireError.InvalidParams, "missing param: id");
            if (string.IsNullOrEmpty(key))
                return JsonRpcDispatcher.ErrorResponse(id, WireError.InvalidParams, "missing param: key");
            EngineInputDriver.KeyPress(nodeId, key);
            return JsonRpcDispatcher.OkResponse(id, "null");
        }

        static string HandleTakeScreenshot(object id, string paramsJson)
        {
            string path = JsonRpcDispatcher.ExtractStringParam(paramsJson, "path");
            if (string.IsNullOrEmpty(path))
                return JsonRpcDispatcher.ErrorResponse(id, WireError.InvalidParams, "missing param: path");
            string mode = (JsonRpcDispatcher.ExtractStringParam(paramsJson, "mode") ?? "fullscreen")
                .Trim().ToLowerInvariant();
            switch (mode)
            {
                case "fullscreen":
                    AutoAgentBootstrap.RequestScreenshot(path);
                    break;
                case "node":
                    string nodeId = JsonRpcDispatcher.ExtractStringParam(paramsJson, "id");
                    if (string.IsNullOrEmpty(nodeId))
                        return JsonRpcDispatcher.ErrorResponse(id, WireError.InvalidParams,
                            "missing param: id (node mode)");
                    AutoAgentBootstrap.RequestScreenshotNode(nodeId, path);
                    break;
                case "rect":
                    int rx = (int)JsonRpcDispatcher.ExtractFloatParam(paramsJson, "x");
                    int ry = (int)JsonRpcDispatcher.ExtractFloatParam(paramsJson, "y");
                    int rw = (int)JsonRpcDispatcher.ExtractFloatParam(paramsJson, "w");
                    int rh = (int)JsonRpcDispatcher.ExtractFloatParam(paramsJson, "h");
                    AutoAgentBootstrap.RequestScreenshotRect(rx, ry, rw, rh, path);
                    break;
                default:
                    return JsonRpcDispatcher.ErrorResponse(id, WireError.InvalidParams,
                        $"unsupported mode: {mode}");
            }
            return JsonRpcDispatcher.OkResponse(id,
                $"{{\"path\":\"{NodeSerializer.Esc(path)}\"}}");
        }

        /// <summary>
        /// Starts a <see cref="WaitConditions.WaitFor"/> coroutine via
        /// <see cref="AutoAgentBootstrap.RunWaitFor"/> and returns <c>null</c>
        /// to signal a deferred reply. The coroutine sends the reply when the
        /// condition is met (<c>{"success":true,"elapsed_ms":N}</c>) or on
        /// timeout (<c>{"code":-32005,...}</c>).
        /// </summary>
        static string HandleWaitFor(object id, string paramsJson, Action<string> reply)
        {
            string condition = JsonRpcDispatcher.ExtractStringParam(paramsJson, "condition");
            if (string.IsNullOrEmpty(condition))
                return JsonRpcDispatcher.ErrorResponse(id, WireError.InvalidParams,
                    "missing param: condition");

            string nodeId   = JsonRpcDispatcher.ExtractStringParam(paramsJson, "id");
            string baseline = JsonRpcDispatcher.ExtractStringParam(paramsJson, "expected_value");
            int timeoutMs   = (int)JsonRpcDispatcher.ExtractFloatParam(paramsJson, "timeout_ms");

            // Validate condition name synchronously so bad values surface as
            // -32602 right away rather than as a silent coroutine failure.
            try { WaitConditions.CheckCondition(condition, nodeId, baseline); }
            catch (WireException we) when (we.Code == WireError.InvalidParams)
            {
                return JsonRpcDispatcher.ErrorResponse(id, we.Code, we.Message);
            }
            catch
            {
                // Other exceptions (e.g. widget not found) are expected during
                // the wait loop — don't short-circuit here.
            }

            AutoAgentBootstrap.RunWaitFor(condition, nodeId, baseline,
                timeoutMs == 0 ? WaitConditions.DefaultTimeoutMs : timeoutMs,
                id, reply);
            return null; // deferred — coroutine will call reply
        }

        // ------------------------------------------------------------------ reflection handlers

        static string HandleInvokeMethod(object id, string paramsJson)
        {
            string nodeId     = JsonRpcDispatcher.ExtractStringParam(paramsJson, "id");
            string script     = JsonRpcDispatcher.ExtractStringParam(paramsJson, "script");
            string methodName = JsonRpcDispatcher.ExtractStringParam(paramsJson, "method_name");
            if (string.IsNullOrEmpty(nodeId) || string.IsNullOrEmpty(script) ||
                string.IsNullOrEmpty(methodName))
                return JsonRpcDispatcher.ErrorResponse(id, WireError.InvalidParams,
                    "missing param: id / script / method_name");

            var go = EngineInputDriver.FindById(nodeId);
            if (go == null)
                return JsonRpcDispatcher.ErrorResponse(id, WireError.WidgetNotFound,
                    $"widget not found: {nodeId}");

            string argsJson   = JsonRpcDispatcher.ExtractRawValue(paramsJson, "args") ?? "[]";
            string returnJson = ScriptInvoker.Invoke(go, script, methodName, argsJson);
            return JsonRpcDispatcher.OkResponse(id, $"{{\"return_value\":{returnJson}}}");
        }

        static string HandleGetProperty(object id, string paramsJson)
        {
            string nodeId    = JsonRpcDispatcher.ExtractStringParam(paramsJson, "id");
            string script    = JsonRpcDispatcher.ExtractStringParam(paramsJson, "script");
            string property  = JsonRpcDispatcher.ExtractStringParam(paramsJson, "property");
            if (string.IsNullOrEmpty(nodeId) || string.IsNullOrEmpty(script) ||
                string.IsNullOrEmpty(property))
                return JsonRpcDispatcher.ErrorResponse(id, WireError.InvalidParams,
                    "missing param: id / script / property");

            var go = EngineInputDriver.FindById(nodeId);
            if (go == null)
                return JsonRpcDispatcher.ErrorResponse(id, WireError.WidgetNotFound,
                    $"widget not found: {nodeId}");

            string valueJson = PropertyAccessor.GetProperty(go, script, property);
            return JsonRpcDispatcher.OkResponse(id, $"{{\"value\":{valueJson}}}");
        }

        static string HandleSetProperty(object id, string paramsJson)
        {
            string nodeId   = JsonRpcDispatcher.ExtractStringParam(paramsJson, "id");
            string script   = JsonRpcDispatcher.ExtractStringParam(paramsJson, "script");
            string property = JsonRpcDispatcher.ExtractStringParam(paramsJson, "property");
            string category = JsonRpcDispatcher.ExtractStringParam(paramsJson, "category") ?? "behavior";
            if (string.IsNullOrEmpty(nodeId) || string.IsNullOrEmpty(script) ||
                string.IsNullOrEmpty(property))
                return JsonRpcDispatcher.ErrorResponse(id, WireError.InvalidParams,
                    "missing param: id / script / property");

            // Visual-category gate — checked before FindById so "visual" always fails fast.
            if (string.Equals(category, "visual", StringComparison.OrdinalIgnoreCase))
                return JsonRpcDispatcher.ErrorResponse(id, WireError.VisualPropertyWrite,
                    $"visual property writes are not allowed: {property}");

            var go = EngineInputDriver.FindById(nodeId);
            if (go == null)
                return JsonRpcDispatcher.ErrorResponse(id, WireError.WidgetNotFound,
                    $"widget not found: {nodeId}");

            string valueJson = JsonRpcDispatcher.ExtractRawValue(paramsJson, "value") ?? "null";
            PropertyAccessor.SetProperty(go, script, property, valueJson, category);
            return JsonRpcDispatcher.OkResponse(id, "{\"success\":true}");
        }

        // ------------------------------------------------------------------ misc

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
