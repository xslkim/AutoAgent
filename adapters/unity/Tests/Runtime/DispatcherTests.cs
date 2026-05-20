using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;
using UnityEngine.EventSystems;

namespace AutoAgent.Tests
{
    /// <summary>
    /// PlayMode tests for the JSON-RPC dispatcher (TASK-0112).
    ///
    /// Coverage:
    ///   JsonRpcDispatcher — parse helpers, OkResponse, ErrorResponse, IdJson
    ///   ProtocolHandler   — method routing: known methods succeed or return
    ///                       well-structured error; unknown method → -32601;
    ///                       wait_for deferral; malformed JSON → -32700.
    /// </summary>
    public class DispatcherTests
    {
        readonly List<GameObject> _spawned = new List<GameObject>();

        [TearDown]
        public void TearDown()
        {
            foreach (var go in _spawned)
                if (go != null) Object.DestroyImmediate(go);
            _spawned.Clear();
        }

        GameObject Spawn(string name, params System.Type[] types)
        {
            var go = new GameObject(name, types);
            _spawned.Add(go);
            return go;
        }

        // ===================================================================
        // JsonRpcDispatcher — pure helpers
        // ===================================================================

        [Test]
        public void OkResponseContainsResultKey()
        {
            string r = JsonRpcDispatcher.OkResponse(1L, "42");
            Assert.IsTrue(r.Contains("\"result\":42"), $"expected result key in: {r}");
            Assert.IsTrue(r.Contains("\"id\":1"),      $"expected id in: {r}");
        }

        [Test]
        public void ErrorResponseContainsErrorKey()
        {
            string r = JsonRpcDispatcher.ErrorResponse(1L, -32601, "method not found");
            Assert.IsTrue(r.Contains("\"error\":"),     $"expected error key in: {r}");
            Assert.IsTrue(r.Contains("-32601"),          $"expected code in: {r}");
            Assert.IsTrue(r.Contains("method not found"), $"expected message in: {r}");
        }

        [Test]
        public void IdJsonEmitsStringId()
        {
            string r = JsonRpcDispatcher.IdJson("abc");
            Assert.AreEqual("\"abc\"", r);
        }

        [Test]
        public void IdJsonEmitsLongId()
        {
            string r = JsonRpcDispatcher.IdJson(42L);
            Assert.AreEqual("42", r);
        }

        [Test]
        public void IdJsonEmitsNullForNull()
        {
            Assert.AreEqual("null", JsonRpcDispatcher.IdJson(null));
        }

        [Test]
        public void TryParseRequestExtractsFields()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":7,\"method\":\"dump_tree\",\"params\":{}}";
            bool ok = JsonRpcDispatcher.TryParseRequest(json,
                out string method, out object id, out string paramsJson);
            Assert.IsTrue(ok, "should parse successfully");
            Assert.AreEqual("dump_tree", method);
            Assert.AreEqual(7L, id);
            Assert.IsNotNull(paramsJson);
        }

        [Test]
        public void TryParseRequestReturnsFalseForNoMethod()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":1}";
            bool ok = JsonRpcDispatcher.TryParseRequest(json,
                out string method, out object id, out string paramsJson);
            Assert.IsFalse(ok);
            Assert.IsNull(method);
        }

        [Test]
        public void ExtractStringParamReturnsValue()
        {
            string p = JsonRpcDispatcher.ExtractStringParam(
                "{\"id\":\"node1\"}", "id");
            Assert.AreEqual("node1", p);
        }

        [Test]
        public void ExtractFloatParamReturnsValue()
        {
            float v = JsonRpcDispatcher.ExtractFloatParam(
                "{\"timeout_ms\":3000}", "timeout_ms");
            Assert.AreEqual(3000f, v, 0.001f);
        }

        [Test]
        public void ExtractBoolParamReturnsValue()
        {
            bool v = JsonRpcDispatcher.ExtractBoolParam(
                "{\"clear_first\":false}", "clear_first", true);
            Assert.IsFalse(v);
        }

        [Test]
        public void UnescapeHandlesEscapeSequences()
        {
            string r = JsonRpcDispatcher.Unescape("hello\\nworld\\t!");
            Assert.AreEqual("hello\nworld\t!", r);
        }

        // ===================================================================
        // ProtocolHandler — routing via Enqueue + DrainOnMainThread
        // ===================================================================

        static (string response, ProtocolHandler handler) DispatchSync(string json)
        {
            string response = null;
            var handler = new ProtocolHandler();
            handler.Enqueue(json, r => response = r);
            handler.DrainOnMainThread();
            return (response, handler);
        }

        // ---- negotiate_version --------------------------------------------

        [Test]
        public void NegotiateVersionRoutes()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":1," +
                          "\"method\":\"negotiate_version\"," +
                          "\"params\":{\"client_version\":\"0.1\"}}";
            var (r, _) = DispatchSync(json);
            Assert.IsNotNull(r, "should return a response");
            Assert.IsTrue(r.Contains("\"result\":"), $"should contain result: {r}");
            Assert.IsTrue(r.Contains("accepted"), $"should contain accepted: {r}");
        }

        // ---- dump_tree ----------------------------------------------------

        [Test]
        public void DumpTreeRoutes()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"dump_tree\"}";
            var (r, _) = DispatchSync(json);
            Assert.IsNotNull(r);
            Assert.IsTrue(r.Contains("\"result\":"), $"should contain result: {r}");
        }

        // ---- find_widget --------------------------------------------------

        [Test]
        public void FindWidgetRoutes()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"find_widget\"," +
                          "\"params\":{}}";
            var (r, _) = DispatchSync(json);
            Assert.IsNotNull(r);
            Assert.IsTrue(r.Contains("\"result\":"), $"should contain result: {r}");
        }

        // ---- get_widget ---------------------------------------------------

        [Test]
        public void GetWidgetMissingIdReturnsInvalidParams()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":4,\"method\":\"get_widget\"," +
                          "\"params\":{}}";
            var (r, _) = DispatchSync(json);
            Assert.IsNotNull(r);
            Assert.IsTrue(r.Contains("\"error\":"), $"should contain error: {r}");
            Assert.IsTrue(r.Contains("-32602"), $"should be -32602: {r}");
        }

        // ---- click --------------------------------------------------------

        [Test]
        public void ClickMissingIdReturnsInvalidParams()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":5,\"method\":\"click\"," +
                          "\"params\":{}}";
            var (r, _) = DispatchSync(json);
            Assert.IsNotNull(r);
            Assert.IsTrue(r.Contains("-32602"), $"should be -32602: {r}");
        }

        [Test]
        public void ClickUnknownNodeReturnsWidgetNotFound()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":5,\"method\":\"click\"," +
                          "\"params\":{\"id\":\"__no_such_node__\"}}";
            var (r, _) = DispatchSync(json);
            Assert.IsNotNull(r);
            Assert.IsTrue(r.Contains("-32001"), $"should be -32001: {r}");
        }

        // ---- send_text ----------------------------------------------------

        [Test]
        public void SendTextMissingIdReturnsInvalidParams()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":6,\"method\":\"send_text\"," +
                          "\"params\":{\"text\":\"hello\"}}";
            var (r, _) = DispatchSync(json);
            Assert.IsNotNull(r);
            Assert.IsTrue(r.Contains("-32602"), $"should be -32602: {r}");
        }

        // ---- scroll -------------------------------------------------------

        [Test]
        public void ScrollMissingIdReturnsInvalidParams()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":8,\"method\":\"scroll\"," +
                          "\"params\":{\"delta_x\":0,\"delta_y\":0.1}}";
            var (r, _) = DispatchSync(json);
            Assert.IsNotNull(r);
            Assert.IsTrue(r.Contains("-32602"), $"should be -32602: {r}");
        }

        // ---- key_press ----------------------------------------------------

        [Test]
        public void KeyPressMissingIdReturnsInvalidParams()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":9,\"method\":\"key_press\"," +
                          "\"params\":{\"key\":\"Enter\"}}";
            var (r, _) = DispatchSync(json);
            Assert.IsNotNull(r);
            Assert.IsTrue(r.Contains("-32602"), $"should be -32602: {r}");
        }

        // ---- take_screenshot ----------------------------------------------

        [Test]
        public void TakeScreenshotMissingPathReturnsInvalidParams()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":10," +
                          "\"method\":\"take_screenshot\",\"params\":{}}";
            var (r, _) = DispatchSync(json);
            Assert.IsNotNull(r);
            Assert.IsTrue(r.Contains("-32602"), $"should be -32602: {r}");
        }

        [Test]
        public void TakeScreenshotUnsupportedModeReturnsInvalidParams()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":10," +
                          "\"method\":\"take_screenshot\"," +
                          "\"params\":{\"path\":\"/tmp/x.png\",\"mode\":\"panorama\"}}";
            var (r, _) = DispatchSync(json);
            Assert.IsNotNull(r);
            Assert.IsTrue(r.Contains("-32602"), $"should be -32602: {r}");
        }

        // ---- wait_for (async deferred) ------------------------------------

        [Test]
        public void WaitForMissingConditionReturnsInvalidParams()
        {
            // Omit condition → sync validation should reject immediately.
            string json = "{\"jsonrpc\":\"2.0\",\"id\":11," +
                          "\"method\":\"wait_for\",\"params\":{\"id\":\"node1\"}}";
            var (r, _) = DispatchSync(json);
            Assert.IsNotNull(r, "should get a sync error for missing condition");
            Assert.IsTrue(r.Contains("-32602"), $"should be -32602: {r}");
        }

        [Test]
        public void WaitForUnknownConditionReturnsInvalidParams()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":12," +
                          "\"method\":\"wait_for\"," +
                          "\"params\":{\"condition\":\"bogus\",\"id\":\"n\"}}";
            var (r, _) = DispatchSync(json);
            Assert.IsNotNull(r, "bogus condition should return sync error");
            Assert.IsTrue(r.Contains("-32602"), $"should be -32602: {r}");
        }

        [UnityTest]
        public IEnumerator WaitForWidgetAppearedCoroutineResolvesImmediately()
        {
            // Drive WaitConditions.WaitFor directly so we don't depend on
            // AutoAgentBootstrap._instance being alive in batchmode CI.
            // The deferred-reply wiring (Bootstrap.RunWaitFor → coroutine →
            // reply callback) is an integration concern covered by e2e tests.
            Spawn("WFAppearedTarget");

            bool succeeded = false;
            bool threw     = false;

            var coroutine = WaitConditions.WaitFor(
                "widget_appeared", "WFAppearedTarget", null, 2000);

            while (true)
            {
                bool more;
                try   { more = coroutine.MoveNext(); }
                catch { threw = true; break; }
                if (!more) { succeeded = true; break; }
                yield return null;
            }

            Assert.IsFalse(threw,     "should not throw for a visible node");
            Assert.IsTrue(succeeded,  "coroutine should finish after condition met");
        }

        // ---- unknown method -----------------------------------------------

        [Test]
        public void UnknownMethodReturnsMethodNotFound()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":99," +
                          "\"method\":\"frobnicate\",\"params\":{}}";
            var (r, _) = DispatchSync(json);
            Assert.IsNotNull(r);
            Assert.IsTrue(r.Contains("\"error\":"), $"should contain error: {r}");
            Assert.IsTrue(r.Contains("-32601"), $"should be -32601: {r}");
            Assert.IsTrue(r.Contains("frobnicate"), $"should name the method: {r}");
        }

        // ---- malformed JSON -----------------------------------------------

        [Test]
        public void MalformedJsonReturnsParseError()
        {
            string json = "this is not json at all";
            var (r, _) = DispatchSync(json);
            Assert.IsNotNull(r);
            Assert.IsTrue(r.Contains("\"error\":"), $"should contain error: {r}");
            Assert.IsTrue(r.Contains("-32700"), $"should be -32700: {r}");
        }

        // ---- response id round-trip ---------------------------------------

        [Test]
        public void ResponsePreservesStringId()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":\"req-abc\"," +
                          "\"method\":\"frobnicate\"}";
            var (r, _) = DispatchSync(json);
            Assert.IsTrue(r.Contains("\"id\":\"req-abc\""),
                $"id should echo back: {r}");
        }

        [Test]
        public void ResponsePreservesNumericId()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":42,\"method\":\"dump_tree\"}";
            var (r, _) = DispatchSync(json);
            Assert.IsTrue(r.Contains("\"id\":42"),
                $"id should echo back unquoted: {r}");
        }
    }
}
