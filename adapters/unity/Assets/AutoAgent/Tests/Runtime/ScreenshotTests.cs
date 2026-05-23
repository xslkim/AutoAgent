// AUTOAGENT_ALLOW_VISUAL: test fixtures set RectTransform size/position for test setup.
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

        // ---- WriteToFile / CropTexture (sync, no WaitForEndOfFrame) -------
        //
        // The capture COROUTINES (CaptureFullscreen / CaptureNode / CaptureRect)
        // can't be tested in -batchmode CI: they yield WaitForEndOfFrame, which
        // doesn't return reliably without the editor's render loop. We instead
        // test the pure pixel + IO logic — build a Texture2D in-memory, call
        // CropTexture / WriteToFile directly, assert dimensions + headers.

        [Test]
        public void WriteToFileEmitsPngWithMatchingDimensions()
        {
            var tex = MakeSolidTexture(20, 15, Color.white);
            try
            {
                var path = TempPath(".png");
                ScreenshotCapturer.WriteToFile(tex, path);

                Assert.IsTrue(File.Exists(path), "PNG file must be written");
                AssertPngHeader(path);
                Assert.AreEqual(20, ReadPngWidth(path),
                    "PNG width must match the source texture");
            }
            finally { UnityEngine.Object.DestroyImmediate(tex); }
        }

        [Test]
        public void WriteToFileEmitsJpgWhenExtensionIsJpg()
        {
            var tex = MakeSolidTexture(16, 16, Color.red);
            try
            {
                var path = TempPath(".jpg");
                ScreenshotCapturer.WriteToFile(tex, path);

                Assert.IsTrue(File.Exists(path), "JPG file must be written");
                AssertJpegHeader(path);
            }
            finally { UnityEngine.Object.DestroyImmediate(tex); }
        }

        [Test]
        public void WriteToFileWithEmptyPathThrowsInvalidParams()
        {
            var tex = MakeSolidTexture(4, 4, Color.green);
            try
            {
                var ex = Assert.Throws<WireException>(
                    () => ScreenshotCapturer.WriteToFile(tex, ""));
                Assert.AreEqual(WireError.InvalidParams, ex.Code);
            }
            finally { UnityEngine.Object.DestroyImmediate(tex); }
        }

        [Test]
        public void CropTextureProducesRequestedDimensions()
        {
            // 40×30 source, crop a known interior rect.
            var src = MakeSolidTexture(40, 30, Color.gray);
            Texture2D cropped = null;
            try
            {
                cropped = ScreenshotCapturer.CropTexture(src, new RectInt(5, 5, 10, 8));
                Assert.AreEqual(10, cropped.width, "crop width");
                Assert.AreEqual(8, cropped.height, "crop height");
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(src);
                if (cropped != null) UnityEngine.Object.DestroyImmediate(cropped);
            }
        }

        [Test]
        public void CropPipelineWritesFileWithCroppedDimensions()
        {
            // End-to-end synchronous path: crop a source texture then write
            // it — mirrors what CaptureRect would do once the frame is ready.
            var src = MakeSolidTexture(40, 30, Color.white);
            Texture2D cropped = null;
            try
            {
                cropped = ScreenshotCapturer.CropTexture(src, new RectInt(0, 0, 24, 16));
                var path = TempPath(".png");
                ScreenshotCapturer.WriteToFile(cropped, path);

                Assert.IsTrue(File.Exists(path));
                AssertPngHeader(path);
                Assert.AreEqual(24, ReadPngWidth(path));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(src);
                if (cropped != null) UnityEngine.Object.DestroyImmediate(cropped);
            }
        }

        // ---- helpers -------------------------------------------------------

        static Texture2D MakeSolidTexture(int w, int h, Color c)
        {
            var tex = new Texture2D(w, h, TextureFormat.RGBA32, false);
            var pixels = new Color[w * h];
            for (int i = 0; i < pixels.Length; i++) pixels[i] = c;
            tex.SetPixels(pixels);
            tex.Apply();
            return tex;
        }


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
