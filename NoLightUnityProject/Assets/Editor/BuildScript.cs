using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEditor.Build.Reporting;

// This editor script performs a Windows build.
// Unity is invoked in batch mode and can optionally accept a custom output path
// via the -customBuildPath command line argument.

namespace RogueLike2D.Editor
{
    public static class BuildScript
    {
        public static void PerformWindowsBuild()
        {
            // Gather enabled scenes from the Build Settings.
            var scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToArray();
            if (scenes == null || scenes.Length == 0)
            {
                Debug.LogError("No enabled scenes found in Build Settings. Aborting build.");
                return;
            }

            // Allow -customBuildPath "C:\\...\\Builds\\Windows\\NoLight.exe"
            string custom = GetArg("-customBuildPath");
            string exePath = string.IsNullOrEmpty(custom)
                ? System.IO.Path.Combine("Builds/Windows", "RogueLike2D.exe") // default
                : custom;

            System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(exePath));

            var buildOptions = new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = exePath,
                target = BuildTarget.StandaloneWindows64,
                options = BuildOptions.None
            };

            Debug.Log($"Starting build to {exePath}");
            var report = BuildPipeline.BuildPlayer(buildOptions);
            Debug.Log($"Build Finished, Result: {report.summary.result}.");
            if (report.summary.result == BuildResult.Succeeded)
                Debug.Log($"Build succeeded: {exePath} ({report.summary.totalSize} bytes)");
            else
                Debug.LogError($"Build failed with {report.summary.result}.");
        }

        // Helper to fetch a command line argument's value.
        static string GetArg(string name)
        {
            var args = System.Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++)
                if (args[i] == name) return args[i + 1];
            return null;
        }
    }
}
