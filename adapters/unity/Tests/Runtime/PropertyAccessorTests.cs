using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace AutoAgent.Tests
{
    /// <summary>
    /// PlayMode tests for ScriptInvoker and PropertyAccessor (TASK-0115).
    ///
    /// Coverage:
    ///   ScriptInvoker.Invoke     — happy path, missing script, missing method, arg passing
    ///   PropertyAccessor.Get     — field, C# property, missing member
    ///   PropertyAccessor.Set     — behavior category OK, visual category → -32003
    ///   ProtocolHandler routing  — invoke_method / get_property / set_property wire paths
    ///   JsonRpcDispatcher.ExtractRawValue — string, number, bool, null, array tokens
    /// </summary>
    public class PropertyAccessorTests
    {
        readonly List<GameObject> _spawned = new List<GameObject>();

        [TearDown]
        public void TearDown()
        {
            foreach (var go in _spawned)
                if (go != null) Object.DestroyImmediate(go);
            _spawned.Clear();
        }

        // ------------------------------------------------------------------ helpers

        GameObject SpawnWith<T>(string name) where T : Component
        {
            var go = new GameObject(name, typeof(T));
            _spawned.Add(go);
            return go;
        }

        static (string response, ProtocolHandler handler) DispatchSync(string json)
        {
            string response = null;
            var handler     = new ProtocolHandler();
            handler.Enqueue(json, r => response = r);
            handler.DrainOnMainThread();
            return (response, handler);
        }

        // ================================================================== ScriptInvoker

        [Test]
        public void InvokeMethod_PublicVoidNoArgs_Succeeds()
        {
            var go = SpawnWith<FakeScript>("InvokeTarget");
            var script = go.GetComponent<FakeScript>();
            Assert.AreEqual(0, script.CallCount);

            string result = ScriptInvoker.Invoke(go, nameof(FakeScript), "DoWork", "[]");

            Assert.AreEqual("null", result);
            Assert.AreEqual(1, script.CallCount);
        }

        [Test]
        public void InvokeMethod_WithStringArg_PassesValue()
        {
            var go = SpawnWith<FakeScript>("InvokeArg");
            string result = ScriptInvoker.Invoke(go, nameof(FakeScript), "Echo",
                "[\"hello world\"]");

            Assert.AreEqual("\"hello world\"", result);
        }

        [Test]
        public void InvokeMethod_WithIntArg_PassesValue()
        {
            var go = SpawnWith<FakeScript>("InvokeInt");
            string result = ScriptInvoker.Invoke(go, nameof(FakeScript), "Double", "[7]");

            Assert.AreEqual("14", result);
        }

        [Test]
        public void InvokeMethod_ReturnsBool_SerializesCorrectly()
        {
            var go = SpawnWith<FakeScript>("InvokeBool");
            string result = ScriptInvoker.Invoke(go, nameof(FakeScript), "AlwaysTrue", "[]");

            Assert.AreEqual("true", result);
        }

        [Test]
        public void InvokeMethod_MissingScript_ThrowsWidgetNotFound()
        {
            var go = SpawnWith<FakeScript>("NoScript");
            var ex = Assert.Throws<WireException>(() =>
                ScriptInvoker.Invoke(go, "NonExistentScript", "DoWork", "[]"));

            Assert.AreEqual(WireError.WidgetNotFound, ex.Code);
        }

        [Test]
        public void InvokeMethod_MissingMethod_ThrowsWidgetNotInteractable()
        {
            var go = SpawnWith<FakeScript>("NoMethod");
            var ex = Assert.Throws<WireException>(() =>
                ScriptInvoker.Invoke(go, nameof(FakeScript), "NonExistentMethod", "[]"));

            Assert.AreEqual(WireError.WidgetNotInteractable, ex.Code);
        }

        // ================================================================== PropertyAccessor — Get

        [Test]
        public void GetProperty_PublicField_ReturnsSerializedValue()
        {
            var go = SpawnWith<FakeScript>("GetField");
            go.GetComponent<FakeScript>().publicField = "test_value";

            string result = PropertyAccessor.GetProperty(go, nameof(FakeScript), "publicField");

            Assert.AreEqual("\"test_value\"", result);
        }

        [Test]
        public void GetProperty_CSharpProperty_ReturnsValue()
        {
            var go = SpawnWith<FakeScript>("GetProp");
            go.GetComponent<FakeScript>().BehaviorProp = 42;

            string result = PropertyAccessor.GetProperty(go, nameof(FakeScript), "BehaviorProp");

            Assert.AreEqual("42", result);
        }

        [Test]
        public void GetProperty_MissingMember_ThrowsWidgetNotInteractable()
        {
            var go = SpawnWith<FakeScript>("GetMissing");
            var ex = Assert.Throws<WireException>(() =>
                PropertyAccessor.GetProperty(go, nameof(FakeScript), "doesNotExist"));

            Assert.AreEqual(WireError.WidgetNotInteractable, ex.Code);
        }

        [Test]
        public void GetProperty_MissingScript_ThrowsWidgetNotFound()
        {
            var go = SpawnWith<FakeScript>("GetScriptMissing");
            var ex = Assert.Throws<WireException>(() =>
                PropertyAccessor.GetProperty(go, "NoSuchScript", "publicField"));

            Assert.AreEqual(WireError.WidgetNotFound, ex.Code);
        }

        // ================================================================== PropertyAccessor — Set

        [Test]
        public void SetProperty_BehaviorCategory_WritesField()
        {
            var go = SpawnWith<FakeScript>("SetBehavior");

            PropertyAccessor.SetProperty(go, nameof(FakeScript), "publicField",
                "\"new_value\"", "behavior");

            Assert.AreEqual("new_value", go.GetComponent<FakeScript>().publicField);
        }

        [Test]
        public void SetProperty_MetaCategory_WritesField()
        {
            var go = SpawnWith<FakeScript>("SetMeta");

            PropertyAccessor.SetProperty(go, nameof(FakeScript), "publicField",
                "\"meta_value\"", "meta");

            Assert.AreEqual("meta_value", go.GetComponent<FakeScript>().publicField);
        }

        [Test]
        public void SetProperty_VisualCategory_ThrowsVisualPropertyWrite()
        {
            var go = SpawnWith<FakeScript>("SetVisual");
            var ex = Assert.Throws<WireException>(() =>
                PropertyAccessor.SetProperty(go, nameof(FakeScript), "publicField",
                    "\"blocked\"", "visual"));

            Assert.AreEqual(WireError.VisualPropertyWrite, ex.Code);
            Assert.AreEqual("test_default",               // unchanged
                go.GetComponent<FakeScript>().publicField, "field must not be modified");
        }

        [Test]
        public void SetProperty_IntField_CoercesFromJsonNumber()
        {
            var go = SpawnWith<FakeScript>("SetInt");

            PropertyAccessor.SetProperty(go, nameof(FakeScript), "intField", "99", "behavior");

            Assert.AreEqual(99, go.GetComponent<FakeScript>().intField);
        }

        [Test]
        public void SetProperty_CSharpProperty_WritesValue()
        {
            var go = SpawnWith<FakeScript>("SetProp");

            PropertyAccessor.SetProperty(go, nameof(FakeScript), "BehaviorProp", "77", "behavior");

            Assert.AreEqual(77, go.GetComponent<FakeScript>().BehaviorProp);
        }

        // ================================================================== ProtocolHandler routing

        [Test]
        public void InvokeMethodRoute_MissingIdReturnsInvalidParams()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"invoke_method\"," +
                          "\"params\":{\"script\":\"FakeScript\",\"method_name\":\"DoWork\"}}";
            var (r, _) = DispatchSync(json);
            Assert.IsTrue(r.Contains("-32602"), $"expected -32602: {r}");
        }

        [Test]
        public void InvokeMethodRoute_UnknownNodeReturnsWidgetNotFound()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"invoke_method\"," +
                          "\"params\":{\"id\":\"__no_node__\",\"script\":\"FakeScript\"," +
                          "\"method_name\":\"DoWork\",\"args\":[]}}";
            var (r, _) = DispatchSync(json);
            Assert.IsTrue(r.Contains("-32001"), $"expected -32001: {r}");
        }

        [Test]
        public void GetPropertyRoute_MissingScriptReturnsInvalidParams()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"get_property\"," +
                          "\"params\":{\"id\":\"n\",\"property\":\"x\"}}";
            var (r, _) = DispatchSync(json);
            Assert.IsTrue(r.Contains("-32602"), $"expected -32602: {r}");
        }

        [Test]
        public void SetPropertyRoute_VisualCategoryReturnsMinus32003()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":4,\"method\":\"set_property\"," +
                          "\"params\":{\"id\":\"n\",\"script\":\"FakeScript\"," +
                          "\"property\":\"position\",\"value\":\"0\",\"category\":\"visual\"}}";
            var (r, _) = DispatchSync(json);
            Assert.IsTrue(r.Contains("-32003"), $"expected -32003: {r}");
        }

        [Test]
        public void SetPropertyRoute_MissingIdReturnsInvalidParams()
        {
            string json = "{\"jsonrpc\":\"2.0\",\"id\":5,\"method\":\"set_property\"," +
                          "\"params\":{\"script\":\"FakeScript\",\"property\":\"x\"," +
                          "\"value\":\"1\",\"category\":\"behavior\"}}";
            var (r, _) = DispatchSync(json);
            Assert.IsTrue(r.Contains("-32602"), $"expected -32602: {r}");
        }

        // ================================================================== ExtractRawValue

        [Test]
        public void ExtractRawValue_StringToken()
        {
            string r = JsonRpcDispatcher.ExtractRawValue("{\"value\":\"hello\"}", "value");
            Assert.AreEqual("\"hello\"", r);
        }

        [Test]
        public void ExtractRawValue_NumberToken()
        {
            string r = JsonRpcDispatcher.ExtractRawValue("{\"value\":42}", "value");
            Assert.AreEqual("42", r);
        }

        [Test]
        public void ExtractRawValue_BoolToken()
        {
            string r = JsonRpcDispatcher.ExtractRawValue("{\"value\":true}", "value");
            Assert.AreEqual("true", r);
        }

        [Test]
        public void ExtractRawValue_NullToken()
        {
            string r = JsonRpcDispatcher.ExtractRawValue("{\"value\":null}", "value");
            Assert.AreEqual("null", r);
        }

        [Test]
        public void ExtractRawValue_ArrayToken()
        {
            string r = JsonRpcDispatcher.ExtractRawValue("{\"args\":[1,2,3]}", "args");
            Assert.AreEqual("[1,2,3]", r);
        }

        [Test]
        public void ExtractRawValue_MissingKey_ReturnsNull()
        {
            string r = JsonRpcDispatcher.ExtractRawValue("{\"other\":1}", "value");
            Assert.IsNull(r);
        }
    }

    // ====================================================================== helpers

    /// <summary>Minimal MonoBehaviour used only in PropertyAccessorTests.</summary>
    internal sealed class FakeScript : MonoBehaviour
    {
        public string publicField = "test_default";
        public int    intField    = 0;

        public int BehaviorProp { get; set; }

        public int CallCount { get; private set; }

        public void DoWork()  => CallCount++;
        public string Echo(string s) => s;
        public int    Double(int n)  => n * 2;
        public bool   AlwaysTrue()   => true;
    }
}
