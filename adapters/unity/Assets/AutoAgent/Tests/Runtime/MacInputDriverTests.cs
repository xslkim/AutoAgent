using NUnit.Framework;
using UnityEngine;

namespace AutoAgent.Tests
{
    [TestFixture]
    public class MacInputDriverTests
    {
        // ---- CGKeyCode constants ----

        [Test]
        public void CgKeyConstants_HaveExpectedValues()
        {
            Assert.AreEqual((ushort)0x24, MacInputDriver.CGKEY_RETURN);  // 36
            Assert.AreEqual((ushort)0x35, MacInputDriver.CGKEY_ESCAPE);   // 53
            Assert.AreEqual((ushort)0x30, MacInputDriver.CGKEY_TAB);      // 48
            Assert.AreEqual((ushort)0x38, MacInputDriver.CGKEY_LSHIFT);   // 56
        }

        // ---- MapKey ----

        [TestCase("enter",  (ushort)0x24)]
        [TestCase("return", (ushort)0x24)]
        [TestCase("submit", (ushort)0x24)]
        [TestCase("Enter",  (ushort)0x24)]
        [TestCase("escape", (ushort)0x35)]
        [TestCase("esc",    (ushort)0x35)]
        [TestCase("cancel", (ushort)0x35)]
        [TestCase("tab",    (ushort)0x30)]
        public void MapKey_KnownKey_ReturnsCgKeyCode(string key, ushort expected)
        {
            Assert.AreEqual(expected, MacInputDriver.MapKey(key));
        }

        [Test]
        public void MapKey_UnknownKey_ThrowsWireException()
        {
            var ex = Assert.Throws<WireException>(
                () => MacInputDriver.MapKey("F1"));
            Assert.AreEqual((int)WireError.InvalidParams, ex.Code);
        }

        [Test]
        public void MapKey_NullKey_ThrowsWireException()
        {
            Assert.Throws<WireException>(
                () => MacInputDriver.MapKey(null));
        }

        // ---- Platform guard ----

        [Test]
        public void NonMacOSPlatform_Click_ThrowsWireException()
        {
            if (Application.platform == RuntimePlatform.OSXEditor ||
                Application.platform == RuntimePlatform.OSXPlayer)
            {
                Assert.Pass("skip: running on macOS (real CGEvent available)");
                return;
            }
            Assert.Throws<WireException>(
                () => MacInputDriver.Click(Vector2.zero));
        }

        [Test]
        public void NonMacOSPlatform_KeyPress_ThrowsWireException()
        {
            if (Application.platform == RuntimePlatform.OSXEditor ||
                Application.platform == RuntimePlatform.OSXPlayer)
            {
                Assert.Pass("skip: running on macOS (real CGEvent available)");
                return;
            }
            Assert.Throws<WireException>(
                () => MacInputDriver.KeyPress(MacInputDriver.CGKEY_RETURN));
        }

        // ---- macOS-only: ToScreenPoint ----

        [Test]
        public void ToScreenPoint_Origin_ReturnsNonNegativeValues()
        {
            if (Application.platform != RuntimePlatform.OSXEditor &&
                Application.platform != RuntimePlatform.OSXPlayer)
            {
                Assert.Ignore("CGEvent only available on macOS");
            }
            var (mx, my) = MacInputDriver.ToScreenPoint(Vector2.zero);
            Assert.GreaterOrEqual(mx, 0);
            Assert.GreaterOrEqual(my, 0);
        }

        [Test]
        public void ToScreenPoint_HigherUnityY_DecreasesMacY()
        {
            if (Application.platform != RuntimePlatform.OSXEditor &&
                Application.platform != RuntimePlatform.OSXPlayer)
            {
                Assert.Ignore("CGEvent only available on macOS");
            }
            var (_, my0)   = MacInputDriver.ToScreenPoint(new Vector2(0, 0));
            var (_, my100) = MacInputDriver.ToScreenPoint(new Vector2(0, 100));
            Assert.Less(my100, my0,
                "Higher Unity Y should map to lower macOS Y (Y-flip)");
        }

        [Test]
        public void ToScreenPoint_RightwardUnityX_IncreasesMacX()
        {
            if (Application.platform != RuntimePlatform.OSXEditor &&
                Application.platform != RuntimePlatform.OSXPlayer)
            {
                Assert.Ignore("CGEvent only available on macOS");
            }
            var (mx0, _)   = MacInputDriver.ToScreenPoint(new Vector2(0, 0));
            var (mx100, _) = MacInputDriver.ToScreenPoint(new Vector2(100, 0));
            Assert.Greater(mx100, mx0,
                "Higher Unity X should map to higher macOS X");
        }
    }
}
