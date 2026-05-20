using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace AutoAgent.Editor
{
    /// <summary>
    /// CI helper — builds the open project as a Win64 standalone player with
    /// the IL2CPP scripting backend. Used to verify the adapter survives
    /// IL2CPP managed-code stripping (see AutoAgent.link.xml).
    ///
    /// Invoked headless from unity-pr.yml:
    ///   Unity.exe -batchmode -nographics -projectPath &lt;fixture&gt; \
    ///     -executeMethod AutoAgent.Editor.CIBuild.BuildIl2cppPlayer
    ///
    /// The method calls EditorApplication.Exit itself: 0 on a successful
    /// build, 1 otherwise.
    /// </summary>
    public static class CIBuild
    {
        public static void BuildIl2cppPlayer()
        {
            // Prefer the project's configured build scenes; fall back to every
            // scene in the project so the build is never empty.
            var scenes = EditorBuildSettings.scenes
                .Where(s => s.enabled)
                .Select(s => s.path)
                .ToArray();
            if (scenes.Length == 0)
            {
                scenes = AssetDatabase.FindAssets("t:Scene")
                    .Select(AssetDatabase.GUIDToAssetPath)
                    .Where(p => p.StartsWith("Assets/"))
                    .ToArray();
            }

            // Output under <project>/Build/il2cpp/ — a stable, project-relative
            // path the workflow can locate regardless of Unity's working dir.
            var projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            var outDir = Path.Combine(projectRoot, "Build", "il2cpp");
            Directory.CreateDirectory(outDir);
            var outExe = Path.Combine(outDir, "AutoAgentTest.exe");

            PlayerSettings.SetScriptingBackend(
                NamedBuildTarget.Standalone, ScriptingImplementation.IL2CPP);

            var options = new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = outExe,
                target = BuildTarget.StandaloneWindows64,
                targetGroup = BuildTargetGroup.Standalone,
                options = BuildOptions.None,
            };

            Debug.Log($"[CIBuild] IL2CPP build starting — {scenes.Length} scene(s) -> {outExe}");
            BuildReport report = BuildPipeline.BuildPlayer(options);
            BuildSummary summary = report.summary;
            Debug.Log($"[CIBuild] IL2CPP build result={summary.result} " +
                      $"totalSize={summary.totalSize} bytes " +
                      $"totalErrors={summary.totalErrors}");

            EditorApplication.Exit(summary.result == BuildResult.Succeeded ? 0 : 1);
        }
    }
}
