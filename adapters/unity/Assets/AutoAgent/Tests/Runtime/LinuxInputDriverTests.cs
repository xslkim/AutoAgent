using NUnit.Framework;
using UnityEngine;

namespace AutoAgent.Tests
{
    [TestFixture]
    public class LinuxInputDriverTests
    {
        // ---- X11 keycode constants ----

        [Test]
        public void X11KeyConstants_HaveExpectedValues()
        {
            Assert.AreEqual(36u, LinuxInputDriver.XK_RETURN);
            Assert.AreEqual(9u,  LinuxInputDriver.XK_ESCAPE);
            Assert.AreEqual(23u, LinuxInputDriver.XK_TAB);
            Assert.AreEqual(50u, LinuxInputDriver.XK_LSHIFT);
        }

        // ---- MapKey ----

        [TestCase("enter",  36u)]
        [TestCase("return", 36u)]
        [TestCase("submit", 36u)]
        [TestCase("Enter",  36u)]
        [TestCase("escape", 9u)]
        [TestCase("esc",    9u)]
        [TestCase("cancel", 9u)]
        [TestCase("tab",   23u)]
        public void MapKey_KnownKey_ReturnsX11Keycode(string key, uint expected)
        {
            Assert.AreEqual(expected, LinuxInputDriver.MapKey(key));
        }

        [Test]
        public void MapKey_UnknownKey_ThrowsWireException()
        {
            var ex = Assert.Throws<WireException>(
                () => LinuxInputDriver.MapKey("F1"));
            Assert.AreEqual((int)WireError.InvalidParams, ex.Code);
        }

        [Test]
        public void MapKey_NullKey_ThrowsWireException()
        {
            Assert.Throws<WireException>(
                () => LinuxInputDriver.MapKey(null));
        }

        // ---- Platform guard ----

        [Test]
        public void NonLinuxPlatform_Click_ThrowsWireException()
        {
            if (Application.platform == RuntimePlatform.LinuxEditor ||
                Application.platform == RuntimePlatform.LinuxPlayer)
            {
                Assert.Pass("skip: running on Linux (real XTest available)");
                return;
            }
            Assert.Throws<WireException>(
                () => LinuxInputDriver.Click(Vector2.zero));
        }

        [Test]
        public void NonLinuxPlatform_KeyPress_ThrowsWireException()
        {
            if (Application.platform == RuntimePlatform.LinuxEditor ||
                Application.platform == RuntimePlatform.LinuxPlayer)
            {
                Assert.Pass("skip: running on Linux (real XTest available)");
                return;
            }
            Assert.Throws<WireException>(
                () => LinuxInputDriver.KeyPress(LinuxInputDriver.XK_RETURN));
        }

        // ---- Linux-only: ToX11Coords ----

        [Test]
        public void ToX11Coords_Origin_ReturnsNonNegativeValues()
        {
            Assume.That(
                Application.platform == RuntimePlatform.LinuxEditor ||
                Application.platform == RuntimePlatform.LinuxPlayer,
                "skip: XTest only available on Linux");
            var (x, y) = LinuxInputDriver.ToX11Coords(Vector2.zero);
            Assert.GreaterOrEqual(x, 0);
            Assert.GreaterOrEqual(y, 0);
        }

        [Test]
        public void ToX11Coords_HigherUnityY_DecreasesX11Y()
        {
            Assume.That(
                Application.platform == RuntimePlatform.LinuxEditor ||
                Application.platform == RuntimePlatform.LinuxPlayer,
                "skip: XTest only available on Linux");
            var (_, y0)   = LinuxInputDriver.ToX11Coords(new Vector2(0, 0));
            var (_, y100) = LinuxInputDriver.ToX11Coords(new Vector2(0, 100));
            Assert.Less(y100, y0,
                "Higher Unity Y should map to lower X11 Y (Y-flip)");
        }

        [Test]
        public void ToX11Coords_RightwardUnityX_IncreasesX11X()
        {
            Assume.That(
                Application.platform == RuntimePlatform.LinuxEditor ||
                Application.platform == RuntimePlatform.LinuxPlayer,
                "skip: XTest only available on Linux");
            var (x0, _)   = LinuxInputDriver.ToX11Coords(new Vector2(0, 0));
            var (x100, _) = LinuxInputDriver.ToX11Coords(new Vector2(100, 0));
            Assert.Greater(x100, x0,
                "Higher Unity X should map to higher X11 X");
        }
    }
}
