using UnityEngine;
using UnityEngine.SceneManagement;

namespace AutoAgent
{
    /// <summary>
    /// Subscribes to <see cref="SceneManager.sceneLoaded"/> and emits an
    /// <c>event.scene_changed</c> JSON-RPC notification whenever the active
    /// scene changes (additive loads are also reported).
    ///
    /// Attach via <see cref="AutoAgentBootstrap"/> so it lives on the
    /// DontDestroyOnLoad object and survives scene transitions.
    /// </summary>
    internal sealed class SceneChangeWatcher : MonoBehaviour
    {
        EventEmitter _emitter;

        internal void Init(EventEmitter emitter) => _emitter = emitter;

        void OnEnable()  => SceneManager.sceneLoaded   += OnSceneLoaded;
        void OnDisable() => SceneManager.sceneLoaded   -= OnSceneLoaded;

        void OnSceneLoaded(Scene scene, LoadSceneMode mode) =>
            _emitter?.EmitSceneChanged(scene.name);

        /// <summary>
        /// Test hook — fires the same notification as a real scene load.
        /// Avoids requiring the scene to be in build settings during CI.
        /// </summary>
        internal void SimulateSceneLoaded(string sceneName) =>
            _emitter?.EmitSceneChanged(sceneName);
    }
}
