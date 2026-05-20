namespace AutoAgent
{
    /// <summary>
    /// An error that maps directly onto a JSON-RPC error response. Thrown by
    /// input-driver / protocol code; <see cref="ProtocolHandler"/> turns it
    /// into <c>{"error":{"code":...,"message":...}}</c>.
    ///
    /// The full error-code table is formalized in TASK-0113; for now the codes
    /// the input driver needs live in <see cref="WireError"/>.
    /// </summary>
    internal sealed class WireException : System.Exception
    {
        public readonly int Code;

        public WireException(int code, string message) : base(message)
        {
            Code = code;
        }
    }

    /// <summary>
    /// Wire-protocol error codes (subset; authoritative table in
    /// docs/01-protocol-spec.md, consolidated by TASK-0113).
    /// </summary>
    internal static class WireError
    {
        public const int WidgetNotFound        = -32001;
        public const int WidgetNotInteractable = -32002;
        // wait_for / async operation never satisfied within its budget.
        public const int Timeout               = -32005;
        // JSON-RPC 2.0 standard code: malformed params (e.g. unsupported key).
        public const int InvalidParams         = -32602;
    }
}
