namespace AutoAgent
{
    /// <summary>
    /// Complete wire-protocol error code table.
    /// Authoritative source: <c>docs/01-protocol-spec.md §六</c>.
    ///
    /// Standard JSON-RPC 2.0 codes (-327xx / -326xx) are negative integers
    /// in the reserved range; AutoAgent custom codes occupy -320xx.
    /// </summary>
    internal enum WireErrorCode
    {
        // ---- JSON-RPC 2.0 standard -----------------------------------------
        ParseError      = -32700,   // Malformed JSON
        InvalidRequest  = -32600,   // Not a valid JSON-RPC 2.0 request
        MethodNotFound  = -32601,   // Unknown method name
        InvalidParams   = -32602,   // Missing or invalid parameter
        InternalError   = -32603,   // Unhandled exception inside adapter

        // ---- AutoAgent adapter custom codes --------------------------------
        WidgetNotFound        = -32001, // No node with the requested stable ID
        WidgetNotInteractable = -32002, // Node exists but has no suitable handler
        VisualPropertyWrite   = -32003, // Attempt to mutate a visual field (blocked)
        StructuralChange      = -32004, // Attempt to modify hierarchy (blocked)
        TimeoutError          = -32005, // wait_for deadline exceeded
        InputInjectionFailed  = -32006, // Input event could not be dispatched
        EngineThreadViolation = -32007, // Engine API called from wrong thread
        ScreenshotFailed      = -32008, // Capture pipeline error
        // -32009 reserved
        VersionMismatch       = -32010, // Incompatible protocol versions
        NegotiationTimeout    = -32011, // Handshake not completed within 5 s
        SubprotocolMismatch   = -32012, // WebSocket subprotocol ≠ autoagent.v1
        NotNegotiated         = -32013, // Method called before negotiate_version
        // -32014 … -32029 reserved
        PathViolation         = -32030, // AI tried to write outside path whitelist
    }
}
