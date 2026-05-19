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

        /// <summary>
        /// Fire-and-forget screenshot. Captures the rendered frame and writes a
        /// PNG to <paramref name="path"/>. Called from the protocol handler.
        /// </summary>
        public static void RequestScreenshot(string path)
        {
            if (_instance != null)
                _instance.StartCoroutine(_instance.CaptureRoutine(path));
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

        System.Collections.IEnumerator CaptureRoutine(string path)
        {
            yield return new WaitForEndOfFrame();
            Texture2D tex = null;
            try
            {
                tex = ScreenCapture.CaptureScreenshotAsTexture();
                System.IO.File.WriteAllBytes(path, tex.EncodeToPNG());
                Debug.Log($"[AutoAgent] screenshot written: {path}");
            }
            catch (System.Exception ex)
            {
                Debug.LogWarning($"[AutoAgent] screenshot failed: {ex.Message}");
            }
            finally
            {
                if (tex != null) Destroy(tex);
            }
        }

        void OnDestroy()
        {
            _server?.Stop();
            if (_instance == this) _instance = null;
        }

        void OnApplicationQuit() => _server?.Stop();
    }
}
