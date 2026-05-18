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

        void OnDestroy()
        {
            _server?.Stop();
            if (_instance == this) _instance = null;
        }

        void OnApplicationQuit() => _server?.Stop();
    }
}
