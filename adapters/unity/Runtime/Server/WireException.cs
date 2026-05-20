namespace AutoAgent
{
    /// <summary>
    /// An error that maps directly onto a JSON-RPC error response. Thrown by
    /// input-driver / protocol code; <see cref="ProtocolHandler"/> turns it
    /// into <c>{"error":{"code":...,"message":...}}</c>.
    ///
    /// Use <see cref="WireError"/> constants (or cast <see cref="WireErrorCode"/>
    /// to <c>int</c>) for the <paramref name="code"/> argument.
    /// </summary>
    internal sealed class WireException : System.Exception
    {
        public readonly int Code;

        public WireException(int code, string message) : base(message)
        {
            Code = code;
        }

        public WireException(WireErrorCode code, string message)
            : this((int)code, message) { }
    }

    /// <summary>
    /// Convenience int aliases for the most-used <see cref="WireErrorCode"/>
    /// values. Kept as <c>int</c> so call-sites that pass them directly to
    /// <see cref="WireException"/> or <see cref="JsonRpcDispatcher"/> don't
    /// need a cast.
    /// </summary>
    internal static class WireError
    {
        public const int WidgetNotFound        = (int)WireErrorCode.WidgetNotFound;
        public const int WidgetNotInteractable = (int)WireErrorCode.WidgetNotInteractable;
        public const int VisualPropertyWrite   = (int)WireErrorCode.VisualPropertyWrite;
        public const int StructuralChange      = (int)WireErrorCode.StructuralChange;
        public const int Timeout               = (int)WireErrorCode.TimeoutError;
        public const int InputInjectionFailed  = (int)WireErrorCode.InputInjectionFailed;
        public const int EngineThreadViolation = (int)WireErrorCode.EngineThreadViolation;
        public const int ScreenshotFailed      = (int)WireErrorCode.ScreenshotFailed;
        public const int VersionMismatch       = (int)WireErrorCode.VersionMismatch;
        public const int NegotiationTimeout    = (int)WireErrorCode.NegotiationTimeout;
        public const int SubprotocolMismatch   = (int)WireErrorCode.SubprotocolMismatch;
        public const int NotNegotiated         = (int)WireErrorCode.NotNegotiated;
        public const int PathViolation         = (int)WireErrorCode.PathViolation;

        // JSON-RPC 2.0 standard codes
        public const int ParseError     = (int)WireErrorCode.ParseError;
        public const int InvalidRequest = (int)WireErrorCode.InvalidRequest;
        public const int MethodNotFound = (int)WireErrorCode.MethodNotFound;
        public const int InvalidParams  = (int)WireErrorCode.InvalidParams;
        public const int InternalError  = (int)WireErrorCode.InternalError;
    }
}
