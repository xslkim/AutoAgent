using System.Collections.Generic;
using System.Text;

namespace AutoAgent
{
    /// <summary>
    /// Handlers for the <c>pin_id</c> and <c>list_orphan_ids</c> wire methods
    /// (TASK-0116).
    ///
    /// <c>pin_id</c> attaches (or updates) a <see cref="StableIdComponent"/> on
    /// the target widget so that the next <c>dump_tree</c> call returns the
    /// node with <c>stable_id_source = "pinned"</c> and the caller-chosen id.
    ///
    /// <c>list_orphan_ids</c> reads the id set that was persisted by the last
    /// <c>dump_tree</c> call (<see cref="OrphanTracker"/>) and returns the
    /// subset that is absent from the current scene — i.e. nodes that have
    /// been removed or whose hierarchy path changed since the last dump.
    /// </summary>
    internal static class PinIdHandler
    {
        // ------------------------------------------------------------------ pin_id

        /// <summary>
        /// Wire handler for <c>pin_id</c>.
        /// Params: <c>{ "id": "&lt;current wire id&gt;", "pinned_id": "&lt;new pin&gt;" }</c>.
        /// Result: <c>null</c> (no payload on success).
        /// Errors: -32602 on missing params, -32001 if the widget is not found.
        /// </summary>
        internal static string HandlePinId(object rpcId, string paramsJson)
        {
            string nodeId   = JsonRpcDispatcher.ExtractStringParam(paramsJson, "id");
            string pinnedId = JsonRpcDispatcher.ExtractStringParam(paramsJson, "pinned_id");

            if (string.IsNullOrEmpty(nodeId))
                return JsonRpcDispatcher.ErrorResponse(rpcId, WireError.InvalidParams,
                    "missing param: id");
            if (string.IsNullOrEmpty(pinnedId))
                return JsonRpcDispatcher.ErrorResponse(rpcId, WireError.InvalidParams,
                    "missing param: pinned_id");

            var go = EngineInputDriver.FindById(nodeId);
            if (go == null)
                return JsonRpcDispatcher.ErrorResponse(rpcId, WireError.WidgetNotFound,
                    $"widget not found: {nodeId}");

            // Add the component if absent, then write the pinned id.
            var sid = go.GetComponent<StableIdComponent>();
            if (sid == null) sid = go.AddComponent<StableIdComponent>();
            sid.pinnedId = pinnedId;

            return JsonRpcDispatcher.OkResponse(rpcId, "null");
        }

        // ------------------------------------------------------------------ list_orphan_ids

        /// <summary>
        /// Wire handler for <c>list_orphan_ids</c>.
        /// Returns the ids that were present in the last <c>dump_tree</c> scan
        /// but are no longer present in the current scene (i.e. potential orphans).
        /// Returns <c>[]</c> when <paramref name="tracker"/> is <c>null</c> or
        /// no previous scan exists.
        /// </summary>
        internal static string HandleListOrphanIds(object rpcId, OrphanTracker tracker)
        {
            if (tracker == null)
                return JsonRpcDispatcher.OkResponse(rpcId, "[]");

            var previous   = tracker.LoadLastScan();
            var nodes      = UGuiReflector.DumpActiveScene();
            var currentIds = new HashSet<string>(nodes.ConvertAll(n => n.Id));

            var orphans = new List<string>();
            foreach (var id in previous)
                if (!currentIds.Contains(id))
                    orphans.Add(id);

            var sb = new StringBuilder("[");
            for (int i = 0; i < orphans.Count; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append('"').Append(NodeSerializer.Esc(orphans[i])).Append('"');
            }
            sb.Append(']');
            return JsonRpcDispatcher.OkResponse(rpcId, sb.ToString());
        }
    }
}
