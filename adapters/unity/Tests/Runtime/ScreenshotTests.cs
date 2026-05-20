using System;
using System.Collections;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace AutoAgent.Tests
{
    /// <summary>
    /// PlayMode tests for ScreenshotCapturer (TASK-0110).
    /// Covers format detection, node-bounds math, and the three capture
    /// modes' file output (PNG / JPG headers, sensible dimensions).
    /// In headless / batch CI the rendered frame may be empty, so tests
    /// assert file structure rather than pixel content.
    /// </summary>
    public class ScreenshotTests
    {
        readonly System.Collections.Generic.List<string> _tempFiles =
            new System.Collections.Generic.List<string>();
        readonly System.Collections.Generic.List<GameObject> _spawned =
            new System.Collections.Generic.List<GameObject>();

        [TearDown]
        public void TearDown()
        {
            foreach (var f in _tempFiles)
            {
                try { if (File.Exists(f)) File.Delete(f); } catch { /* best-effort */ }
            }
            _tempFiles.Clear();
            foreach (var go in _spawned)
                if (go != null) UnityEngine.Object.DestroyImmediate(go);
            _spawned.Clear();
        }

        string TempPath(string ext)
        {
            var p = Path.Combine(
                Path.GetTempPath(),
                $"autoagent_shot_{Guid.NewGuid():N}{ext}");
            _tempFiles.Add(p);
            return p;
        }

        GameObject Spawn(string name, params Type[] components)
        {
            var go = new GameObject(name, components);
            _spawned.Add(go);
            return go;
        }

        // ---- format detection ----------------------------------------------

        [Test]
        public void DetectFormatRecognizesPng()
        {
            Assert.AreEqual(ScreenshotCapturer.Format.Png,
                ScreenshotCapturer.DetectFormat("/x/y.png"));
            Assert.AreEqual(ScreenshotCapturer.Format.Png,
                ScreenshotCapturer.DetectFormat("X.PNG"));
        }

        [Test]
        public void DetectFormatRecognizesJpg()
        {
            Assert.AreEqual(ScreenshotCapturer.Format.Jpg,
                ScreenshotCapturer.DetectFormat("/x/y.jpg"));
            Assert.AreEqual(ScreenshotCapturer.Format.Jpg,
                ScreenshotCapturer.DetectFormat("/x/y.JPEG"));
        }

        [Test]
        public void DetectFormatDefaultsToPng()
        {
            Assert.AreEqual(ScreenshotCapturer.Format.Png,
                ScreenshotCapturer.DetectFormat("noext"));
            Assert.AreEqual(ScreenshotCapturer.Format.Png,
                ScreenshotCapturer.DetectFormat(""));
        }

        // ---- node bounds ---------------------------------------------------

        [Test]
        public void ComputeNodeScreenRectThrowsForMissingRectTransform()
        {
            var go = Spawn("NoRT"); // bare GameObject — only Transform
            var ex = Assert.Throws<WireException>(
                () => ScreenshotCapturer.ComputeNodeScreenRect(go));
            Assert.AreEqual(WireError.WidgetNotInteractable, ex.Code);
        }

        [UnityTest]
        public IEnumerator ComputeNodeScreenRectMatchesRectTransformSize()
        {
            var canvasGO = Spawn("C", typeof(Canvas), typeof(GraphicRaycaster));
            var canvas = canvasGO.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;

            var nodeGO = new GameObject("N", typeof(RectTransform));
            _spawned.Add(nodeGO);
            nodeGO.transform.SetParent(canvasGO.transform, false);
            var rt = nodeGO.GetComponent<RectTransform>();
            rt.anchorMin = rt.anchorMax = Vector2.zero;
            rt.pivot = Vector2.zero;
            rt.anchoredPosition = new Vector2(50, 30);
            rt.sizeDelta = new Vector2(100, 40);

            yield return null;
            Canvas.ForceUpdateCanvases();
            yield return null;

            var r = ScreenshotCapturer.ComputeNodeScreenRect(nodeGO);
            Assert.AreEqual(100, r.width, "width should match sizeDelta.x");
            Assert.AreEqual(40, r.height, "height should match sizeDelta.y");
        }

        // ---- capture (fullscreen) -----------------------------------------

        [UnityTest]
        public IEnumerator FullscreenCaptureWritesPngFile()
        {
            var path = TempPath(".png");
            yield return ScreenshotCapturer.CaptureFullscreen(path);

            Assert.IsTrue(File.Exists(path), "PNG file must be written");
            AssertPngHeader(path);
        }

        [UnityTest]
        public IEnumerator FullscreenCaptureWritesJpgWhenExtensionIsJpg()
        {
            var path = TempPath(".jpg");
            yield return ScreenshotCapturer.CaptureFullscreen(path);

            Assert.IsTrue(File.Exists(path), "JPG file must be written");
            AssertJpegHeader(path);
        }

        // ---- capture (rect) -----------------------------------------------

        [UnityTest]
        public IEnumerator RectCaptureWritesPngFile()
        {
            if (Screen.width < 4 || Screen.height < 4)
                Assert.Ignore($"Screen too small in this environment ({Screen.width}x{Screen.height})");

            var path = TempPath(".png");
            int w = Mathf.Min(32, Screen.width);
            int h = Mathf.Min(32, Screen.height);
            yield return ScreenshotCapturer.CaptureRect(new RectInt(0, 0, w, h), path);

            Assert.IsTrue(File.Exists(path));
            AssertPngHeader(path);
            int pw = ReadPngWidth(path);
            Assert.AreEqual(w, pw, "PNG width must match the requested crop width");
        }

        // ---- capture (node) -----------------------------------------------

        [UnityTest]
        public IEnumerator NodeCaptureWritesFileWithExpectedDimensions()
        {
            if (Screen.width < 4 || Screen.height < 4)
                Assert.Ignore($"Screen too small in this environment ({Screen.width}x{Screen.height})");

            var canvasGO = Spawn("C", typeof(Canvas), typeof(GraphicRaycaster));
            var canvas = canvasGO.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;

            var nodeGO = new GameObject("ScreenshotTarget", typeof(RectTransform));
            _spawned.Add(nodeGO);
            nodeGO.transform.SetParent(canvasGO.transform, false);
            var rt = nodeGO.GetComponent<RectTransform>();
            rt.anchorMin = rt.anchorMax = Vector2.zero;
            rt.pivot = Vector2.zero;
            rt.anchoredPosition = new Vector2(10, 10);
            rt.sizeDelta = new Vector2(Mathf.Min(40, Screen.width - 12),
                                       Mathf.Min(30, Screen.height - 12));
            yield return null;
            Canvas.ForceUpdateCanvases();
            yield return null;

            var expected = ScreenshotCapturer.ComputeNodeScreenRect(nodeGO);
            var path = TempPath(".png");
            yield return ScreenshotCapturer.CaptureNode(nodeGO, path);

            Assert.IsTrue(File.Exists(path));
            AssertPngHeader(path);
            int pw = ReadPngWidth(path);
            Assert.AreEqual(expected.width, pw,
                "PNG width must match ComputeNodeScreenRect's width");
        }

        // ---- helpers -------------------------------------------------------

        static void AssertPngHeader(string path)
        {
            var bytes = File.ReadAllBytes(path);
            Assert.GreaterOrEqual(bytes.Length, 8, "file too small to be a PNG");
            // PNG signature: 89 50 4E 47 0D 0A 1A 0A
            Assert.AreEqual(0x89, bytes[0], "byte 0 must be PNG signature start");
            Assert.AreEqual(0x50, bytes[1]);
            Assert.AreEqual(0x4E, bytes[2]);
            Assert.AreEqual(0x47, bytes[3]);
        }

        static void AssertJpegHeader(string path)
        {
            var bytes = File.ReadAllBytes(path);
            Assert.GreaterOrEqual(bytes.Length, 3, "file too small to be a JPEG");
            // JPEG SOI marker: FF D8 FF
            Assert.AreEqual(0xFF, bytes[0]);
            Assert.AreEqual(0xD8, bytes[1]);
            Assert.AreEqual(0xFF, bytes[2]);
        }

        static int ReadPngWidth(string path)
        {
            var b = File.ReadAllBytes(path);
            // PNG width: big-endian uint32 at offset 16
            return (b[16] << 24) | (b[17] << 16) | (b[18] << 8) | b[19];
        }
    }
}
