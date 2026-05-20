using System.Collections;
using System.IO;
using UnityEngine;

namespace AutoAgent
{
    /// <summary>
    /// Capture a screenshot in one of three modes:
    ///   • <see cref="CaptureFullscreen"/> — the whole rendered frame
    ///   • <see cref="CaptureNode"/>       — crop to a RectTransform's world bounds
    ///   • <see cref="CaptureRect"/>       — crop to an arbitrary screen-space rect
    ///
    /// Output format (PNG / JPG) is picked from the file extension. Each entry
    /// is a coroutine that yields one <see cref="WaitForEndOfFrame"/> so the
    /// captured texture comes from a finished render. Driven by
    /// <see cref="AutoAgentBootstrap"/>.
    /// </summary>
    internal static class ScreenshotCapturer
    {
        public enum Format { Png, Jpg }

        public static Format DetectFormat(string path)
        {
            if (string.IsNullOrEmpty(path)) return Format.Png;
            string ext = Path.GetExtension(path).ToLowerInvariant();
            return (ext == ".jpg" || ext == ".jpeg") ? Format.Jpg : Format.Png;
        }

        // ---- mode: fullscreen ---------------------------------------------

        public static IEnumerator CaptureFullscreen(string path)
        {
            yield return new WaitForEndOfFrame();
            Texture2D tex = null;
            try
            {
                tex = ScreenCapture.CaptureScreenshotAsTexture();
                WriteToFile(tex, path);
            }
            finally
            {
                if (tex != null) Object.Destroy(tex);
            }
        }

        // ---- mode: node ----------------------------------------------------

        public static IEnumerator CaptureNode(GameObject go, string path)
        {
            yield return new WaitForEndOfFrame();
            var rect = ComputeNodeScreenRect(go);
            yield return CaptureRect(rect, path);
        }

        // ---- mode: rect ----------------------------------------------------

        public static IEnumerator CaptureRect(RectInt rect, string path)
        {
            yield return new WaitForEndOfFrame();
            Texture2D full = null, cropped = null;
            try
            {
                full = ScreenCapture.CaptureScreenshotAsTexture();
                cropped = CropTexture(full, ClampToScreen(rect));
                WriteToFile(cropped, path);
            }
            finally
            {
                if (full != null) Object.Destroy(full);
                if (cropped != null) Object.Destroy(cropped);
            }
        }

        // ---- bounds math ---------------------------------------------------

        /// <summary>
        /// Axis-aligned screen-space rect for a UI node's RectTransform.
        /// Walks the four world corners through the appropriate camera (or
        /// straight to screen for an Overlay canvas).
        /// </summary>
        public static RectInt ComputeNodeScreenRect(GameObject go)
        {
            if (go == null)
                throw new WireException(WireError.WidgetNotFound, "node is null");
            var rt = go.GetComponent<RectTransform>();
            if (rt == null)
                throw new WireException(WireError.WidgetNotInteractable,
                    $"node has no RectTransform: {go.name}");

            var canvas = rt.GetComponentInParent<Canvas>();
            Camera cam = null;
            if (canvas != null && canvas.renderMode != RenderMode.ScreenSpaceOverlay)
                cam = canvas.worldCamera;

            var corners = new Vector3[4];
            rt.GetWorldCorners(corners);

            float xMin = float.MaxValue, yMin = float.MaxValue;
            float xMax = float.MinValue, yMax = float.MinValue;
            for (int i = 0; i < 4; i++)
            {
                Vector2 sp = cam != null
                    ? (Vector2)RectTransformUtility.WorldToScreenPoint(cam, corners[i])
                    : (Vector2)corners[i];
                if (sp.x < xMin) xMin = sp.x;
                if (sp.x > xMax) xMax = sp.x;
                if (sp.y < yMin) yMin = sp.y;
                if (sp.y > yMax) yMax = sp.y;
            }

            int x = Mathf.RoundToInt(xMin);
            int y = Mathf.RoundToInt(yMin);
            int w = Mathf.Max(1, Mathf.RoundToInt(xMax - xMin));
            int h = Mathf.Max(1, Mathf.RoundToInt(yMax - yMin));
            return new RectInt(x, y, w, h);
        }

        // Keep the rect inside [0, Screen.size] and at least 1×1.
        static RectInt ClampToScreen(RectInt r)
        {
            int sw = Screen.width;
            int sh = Screen.height;
            int x = Mathf.Clamp(r.x, 0, Mathf.Max(0, sw - 1));
            int y = Mathf.Clamp(r.y, 0, Mathf.Max(0, sh - 1));
            int w = Mathf.Clamp(r.width, 1, Mathf.Max(1, sw - x));
            int h = Mathf.Clamp(r.height, 1, Mathf.Max(1, sh - y));
            return new RectInt(x, y, w, h);
        }

        // ---- helpers -------------------------------------------------------

        static Texture2D CropTexture(Texture2D source, RectInt r)
        {
            var pixels = source.GetPixels(r.x, r.y, r.width, r.height);
            var tex = new Texture2D(r.width, r.height, TextureFormat.RGBA32, false);
            tex.SetPixels(pixels);
            tex.Apply();
            return tex;
        }

        static void WriteToFile(Texture2D tex, string path)
        {
            if (string.IsNullOrEmpty(path))
                throw new WireException(WireError.InvalidParams, "screenshot path is empty");
            var dir = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            byte[] bytes = DetectFormat(path) == Format.Jpg
                ? tex.EncodeToJPG()
                : tex.EncodeToPNG();
            File.WriteAllBytes(path, bytes);
        }
    }
}
