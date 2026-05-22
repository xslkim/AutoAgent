using NUnit.Framework;
using UnityEngine;

namespace AutoAgent.Tests
{
    /// <summary>
    /// Edit-mode tests for Win32InputDriver (TASK-0400).
    ///
    /// Tests that do not require actual OS input injection (coordinate
    /// math, key mapping) run on all platforms.
    /// Tests that call SendInput are guarded by Assume.That and skip on
    /// non-Windows platforms.
    /// </summary>
    [TestFixture]
    public class Win32InputDriverTests
    {
        // ------------------------------------------------------------------ VK constants

        [Test]
        public void VkConstantsHaveExpectedValues()
        {
            Assert.AreEqual(0x0D, Win32InputDriver.VK_RETURN);
            Assert.AreEqual(0x1B, Win32InputDriver.VK_ESCAPE);
            Assert.AreEqual(0x09, Win32InputDriver.VK_TAB);
            Assert.AreEqual(0x10, Win32InputDriver.VK_SHIFT);
        }

        // ------------------------------------------------------------------ MapKey

        [TestCase("enter",     (ushort)0x0D)]
        [TestCase("return",    (ushort)0x0D)]
        [TestCase("submit",    (ushort)0x0D)]
        [TestCase("Enter",     (ushort)0x0D)]  // case-insensitive
        [TestCase("escape",    (ushort)0x1B)]
        [TestCase("esc",       (ushort)0x1B)]
        [TestCase("cancel",    (ushort)0x1B)]
        [TestCase("tab",       (ushort)0x09)]
        [TestCase("Tab",       (ushort)0x09)]  // case-insensitive
        public void MapKey_KnownKey_ReturnsVkCode(string key, ushort expectedVk)
        {
            Assert.AreEqual(expectedVk, Win32InputDriver.MapKey(key));
        }

        [Test]
        public void MapKey_UnknownKey_ThrowsWireException()
        {
            var ex = Assert.Throws<WireException>(() => Win32InputDriver.MapKey("F1"));
            Assert.AreEqual((int)WireError.InvalidParams, ex.Code);
        }

        [Test]
        public void MapKey_NullKey_ThrowsWireException()
        {
            Assert.Throws<WireException>(() => Win32InputDriver.MapKey(null));
        }

        // ------------------------------------------------------------------ Platform guard

        [Test]
        public void NonWindowsPlatform_Click_ThrowsWireException()
        {
            // This test only verifies the stub on non-Windows platforms.
            // On Windows the real implementation runs instead, so skip there.
            Assume.That(Application.platform != RuntimePlatform.WindowsEditor &&
                        Application.platform != RuntimePlatform.WindowsPlayer,
                        "skip: running on Windows (real SendInput available)");

            Assert.Throws<WireException>(() =>
                Win32InputDriver.Click(Vector2.zero));
        }

        [Test]
        public void NonWindowsPlatform_KeyPress_ThrowsWireException()
        {
            Assume.That(Application.platform != RuntimePlatform.WindowsEditor &&
                        Application.platform != RuntimePlatform.WindowsPlayer,
                        "skip: running on Windows");

            Assert.Throws<WireException>(() =>
                Win32InputDriver.KeyPress(Win32InputDriver.VK_RETURN));
        }

        // ------------------------------------------------------------------ Windows-only: ToAbsolute range

        [Test]
        public void ToAbsolute_OriginPosition_ReturnsValueInRange()
        {
            Assume.That(Application.platform == RuntimePlatform.WindowsEditor ||
                        Application.platform == RuntimePlatform.WindowsPlayer,
                        "skip: SendInput only available on Windows");

            var (ax, ay) = Win32InputDriver.ToAbsolute(Vector2.zero);
            // Absolute coords must be in 0–65535; allow some slack for window chrome.
            Assert.IsTrue(ax >= -1000 && ax <= 65535 + 1000,
                $"ax={ax} outside expected range");
            Assert.IsTrue(ay >= -1000 && ay <= 65535 + 1000,
                $"ay={ay} outside expected range");
        }

        [Test]
        public void ToAbsolute_CentrePosition_XGreaterThanOrigin()
        {
            Assume.That(Application.platform == RuntimePlatform.WindowsEditor ||
                        Application.platform == RuntimePlatform.WindowsPlayer,
                        "skip: SendInput only available on Windows");

            var (ax0, _) = Win32InputDriver.ToAbsolute(Vector2.zero);
            var (ax1, _) = Win32InputDriver.ToAbsolute(new Vector2(100, 0));
            // Moving right in Unity screen space should increase the absolute X.
            Assert.Greater(ax1, ax0);
        }

        [Test]
        public void ToAbsolute_HigherY_DecreasesAbsoluteY()
        {
            Assume.That(Application.platform == RuntimePlatform.WindowsEditor ||
                        Application.platform == RuntimePlatform.WindowsPlayer,
                        "skip: SendInput only available on Windows");

            // Unity Y increases upward; Windows Y increases downward.
            var (_, ay0) = Win32InputDriver.ToAbsolute(new Vector2(0, 0));
            var (_, ay1) = Win32InputDriver.ToAbsolute(new Vector2(0, 100));
            Assert.Less(ay1, ay0, "Higher Unity Y should map to lower Windows ay");
        }
    }
}
