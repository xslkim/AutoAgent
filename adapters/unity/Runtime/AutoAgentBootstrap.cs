using System;
using System.Collections;
using UnityEngine;

namespace AutoAgent
{
    /// <summary>
    /// Entry point for the AutoAgent runtime. Created automatically at application
    /// start (RuntimeInitializeOnLoadMethod). Survives scene loads (DontDestroyOnLoad)
    /// and drains the ProtocolHandler main-thread queue every frame.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class AutoAgentBootstrap : MonoBehaviour
    {
        static AutoAgentBootstrap _instance;

        ProtocolHandler _handler;
        WebSocketServer _server;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        static void AutoStart()
        {
            if (_instance != null) return;
            var go = new GameObject("[AutoAgent]");
            DontDestroyOnLoad(go);
            _instance = go.AddComponent<AutoAgentBootstrap>();
        }

        void Awake()
        {
            if (_instance != null && _instance != this)
            {
                Destroy(gameObject);
                return;
            }
            _instance = this;
            // Keep the game loop (and thus the main-thread request queue) running
            // even when the editor / player window loses focus — required for
            // automation while a remote client drives the adapter.
            Application.runInBackground = true;
            _handler = new ProtocolHandler();
            _server  = new WebSocketServer(_handler);
            _server.Start();
        }

        void Update() => _handler?.DrainOnMainThread();

        // ---- fire-and-forget screenshot ------------------------------------

        /// <summary>
        /// Fullscreen screenshot. Writes the file at <paramref name="path"/>;
        /// format inferred from the extension (.png / .jpg).
        /// </summary>
        public static void RequestScreenshot(string path)
        {
            if (_instance != null)
                _instance.StartCoroutine(ScreenshotCapturer.CaptureFullscreen(path));
        }

        /// <summary>
        /// Node screenshot — crops the frame to a single RectTransform's
        /// world bounds. Resolves the node synchronously so a bad id surfaces
        /// as a WireException immediately.
        /// </summary>
        public static void RequestScreenshotNode(string nodeId, string path)
        {
            var go = EngineInputDriver.FindById(nodeId);
            if (go == null)
                throw new WireException(WireError.WidgetNotFound,
                    $"widget not found: {nodeId}");
            if (go.GetComponent<RectTransform>() == null)
                throw new WireException(WireError.WidgetNotInteractable,
                    $"node has no RectTransform: {nodeId}");
            if (_instance != null)
                _instance.StartCoroutine(ScreenshotCapturer.CaptureNode(go, path));
        }

        /// <summary>
        /// Rect screenshot — crops to an explicit screen-space rect.
        /// </summary>
        public static void RequestScreenshotRect(int x, int y, int w, int h, string path)
        {
            if (w <= 0 || h <= 0)
                throw new WireException(WireError.InvalidParams,
                    $"rect width / height must be positive (got {w}x{h})");
            if (_instance != null)
                _instance.StartCoroutine(
                    ScreenshotCapturer.CaptureRect(new RectInt(x, y, w, h), path));
        }

        /// <summary>
        /// Fire-and-forget drag. Resolves the endpoints synchronously (so a bad
        /// id surfaces as a WireException now) then plays the multi-frame drag
        /// coroutine. Called from the protocol handler.
        /// </summary>
        public static void RunDrag(string fromId, string toId, int durationMs)
        {
            // Synchronous validation — throws WireException on a bad id, which
            // the protocol handler turns into an error response.
            EngineInputDriver.ResolveDrag(fromId, toId);
            if (_instance != null)
                _instance.StartCoroutine(EngineInputDriver.Drag(fromId, toId, durationMs));
        }

        /// <summary>
        /// Start a <see cref="WaitConditions.WaitFor"/> coroutine. When the
        /// condition is satisfied the coroutine calls <paramref name="reply"/>
        /// with <c>{"success":true,"elapsed_ms":N}</c>; on timeout it calls
        /// <paramref name="reply"/> with a JSON-RPC error (-32005 Timeout).
        /// </summary>
        public static void RunWaitFor(string condition, string nodeId,
            string baseline, int timeoutMs, object rpcId, Action<string> reply)
        {
            if (_instance != null)
                _instance.StartCoroutine(
                    WaitForCoroutine(condition, nodeId, baseline, timeoutMs, rpcId, reply));
        }

        static IEnumerator WaitForCoroutine(string condition, string nodeId,
            string baseline, int timeoutMs, object rpcId, Action<string> reply)
        {
            float start     = Time.realtimeSinceStartup;
            var   waitEnum  = WaitConditions.WaitFor(condition, nodeId, baseline, timeoutMs);

            while (true)
            {
                bool more;
                try { more = waitEnum.MoveNext(); }
                catch (WireException we)
                {
                    reply(JsonRpcDispatcher.ErrorResponse(rpcId, we.Code, we.Message));
                    yield break;
                }
                catch (Exception ex)
                {
                    reply(JsonRpcDispatcher.ErrorResponse(rpcId, WireError.InternalError, ex.Message));
                    yield break;
                }

                if (!more) break;
                yield return waitEnum.Current;
            }

            int elapsedMs = Mathf.RoundToInt(
                (Time.realtimeSinceStartup - start) * 1000f);
            reply(JsonRpcDispatcher.OkResponse(rpcId,
                $"{{\"success\":true,\"elapsed_ms\":{elapsedMs}}}"));
        }

        void OnDestroy()
        {
            _server?.Stop();
            if (_instance == this) _instance = null;
        }

        void OnApplicationQuit() => _server?.Stop();
    }
}
