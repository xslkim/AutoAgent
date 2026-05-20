using System;
using System.Collections;
using System.Collections.Generic;
using System.Threading;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace AutoAgent.Tests
{
    /// <summary>
    /// PlayMode tests for MainThreadDispatcher and the complete
    /// WireErrorCode table (TASK-0113).
    ///
    /// Threading model:
    ///   Post() is called from a real background Thread; FlushOnMainThread()
    ///   is called on the test (main) thread. This verifies the core
    ///   guarantee: engine API calls always execute on the Unity main thread.
    /// </summary>
    public class ThreadMarshallingTests
    {
        // ===================================================================
        // MainThreadDispatcher — IsMainThread
        // ===================================================================

        [Test]
        public void IsMainThreadReturnsTrueOnOwnerThread()
        {
            var d = new MainThreadDispatcher();
            Assert.IsTrue(d.IsMainThread,
                "dispatcher created on test thread; IsMainThread should be true here");
        }

        [Test]
        public void IsMainThreadReturnsFalseOnBackgroundThread()
        {
            var d = new MainThreadDispatcher();
            bool? bgResult = null;
            var t = new Thread(() => bgResult = d.IsMainThread);
            t.Start();
            t.Join();
            Assert.IsFalse(bgResult, "IsMainThread should be false on a background thread");
        }

        // ===================================================================
        // MainThreadDispatcher — Post / FlushOnMainThread
        // ===================================================================

        [Test]
        public void PostedActionRunsOnFlushThread()
        {
            var d   = new MainThreadDispatcher();
            int ran = 0;

            // Post from this (main) thread — typical test setup
            d.Post(() => ran++);
            Assert.AreEqual(0, ran, "action must not run before Flush");

            d.FlushOnMainThread();
            Assert.AreEqual(1, ran, "action must run after Flush");
        }

        [Test]
        public void ActionPostedFromBgThreadExecutesOnFlushThread()
        {
            var d          = new MainThreadDispatcher();
            int? capturedId = null;
            int mainId      = Thread.CurrentThread.ManagedThreadId;

            // Simulate the WebSocket background thread posting work
            var bgThread = new Thread(() =>
                d.Post(() => capturedId = Thread.CurrentThread.ManagedThreadId));
            bgThread.Start();
            bgThread.Join();

            // The action is in the queue but not yet run
            Assert.IsNull(capturedId, "action must not run before Flush");

            // Flush on the main (test) thread
            d.FlushOnMainThread();

            Assert.IsNotNull(capturedId, "action should have run after Flush");
            Assert.AreEqual(mainId, capturedId.Value,
                "action should execute on the thread that calls FlushOnMainThread");
        }

        [Test]
        public void MultipleActionsPostedFromBgThreadRunInOrder()
        {
            var d      = new MainThreadDispatcher();
            var order  = new List<int>();

            var bgThread = new Thread(() =>
            {
                d.Post(() => order.Add(1));
                d.Post(() => order.Add(2));
                d.Post(() => order.Add(3));
            });
            bgThread.Start();
            bgThread.Join();

            d.FlushOnMainThread();
            Assert.AreEqual(new[] { 1, 2, 3 }, order.ToArray(),
                "actions must execute in FIFO order");
        }

        [Test]
        public void ThrowingActionDoesNotStallQueue()
        {
            var d   = new MainThreadDispatcher();
            int ran = 0;

            // Enqueue: throw, then a healthy action
            d.Post(() => throw new InvalidOperationException("boom"));
            d.Post(() => ran++);

            // Flush should not propagate the exception to the caller
            Assert.DoesNotThrow(() => d.FlushOnMainThread(),
                "Flush must swallow action exceptions");
            Assert.AreEqual(1, ran, "second action must still run after the first throws");
        }

        [Test]
        public void PostNullThrows()
        {
            var d = new MainThreadDispatcher();
            Assert.Throws<ArgumentNullException>(() => d.Post(null));
        }

        // ===================================================================
        // ProtocolHandler — replies execute on the main thread
        // ===================================================================

        [Test]
        public void ProtocolHandlerEnqueuedReplyRunsOnFlushThread()
        {
            // Use a fresh MainThreadDispatcher so we don't depend on bootstrap.
            var dispatcher = new MainThreadDispatcher();
            var handler    = new ProtocolHandler(dispatcher);

            int mainId         = Thread.CurrentThread.ManagedThreadId;
            int? replyThreadId = null;

            string json = "{\"jsonrpc\":\"2.0\",\"id\":1," +
                          "\"method\":\"negotiate_version\"," +
                          "\"params\":{\"client_version\":\"0.1\"}}";

            // Simulate a background WebSocket thread calling Enqueue
            var bgThread = new Thread(() =>
                handler.Enqueue(json, _ => replyThreadId = Thread.CurrentThread.ManagedThreadId));
            bgThread.Start();
            bgThread.Join();

            Assert.IsNull(replyThreadId, "reply must not fire before Flush");

            // Flush on the main thread
            handler.DrainOnMainThread();

            Assert.IsNotNull(replyThreadId, "reply should have fired after Flush");
            Assert.AreEqual(mainId, replyThreadId.Value,
                "reply callback must execute on the flushing (main) thread");
        }

        [Test]
        public void ProtocolHandlerEnqueuedReplyContainsResult()
        {
            var dispatcher = new MainThreadDispatcher();
            var handler    = new ProtocolHandler(dispatcher);

            string response = null;
            string json = "{\"jsonrpc\":\"2.0\",\"id\":42," +
                          "\"method\":\"negotiate_version\"," +
                          "\"params\":{\"client_version\":\"0.1\"}}";

            handler.Enqueue(json, r => response = r);
            handler.DrainOnMainThread();

            Assert.IsNotNull(response, "response must be set after flush");
            Assert.IsTrue(response.Contains("\"result\":"),
                $"response should contain 'result': {response}");
            Assert.IsTrue(response.Contains("\"id\":42"),
                $"response should echo id: {response}");
        }

        // ===================================================================
        // WireErrorCode — completeness and uniqueness
        // ===================================================================

        [Test]
        public void AllErrorCodesHaveDistinctValues()
        {
            var values = new HashSet<int>();
            foreach (WireErrorCode code in Enum.GetValues(typeof(WireErrorCode)))
            {
                int v = (int)code;
                Assert.IsTrue(values.Add(v),
                    $"Duplicate error code value {v} for {code}");
            }
        }

        [Test]
        public void AllExpectedErrorCodesPresent()
        {
            // Spot-check the codes from the protocol spec table.
            var codes = new HashSet<int>(
                Array.ConvertAll((WireErrorCode[])Enum.GetValues(typeof(WireErrorCode)),
                    c => (int)c));

            foreach (var (value, name) in new (int, string)[]
            {
                (-32700, "ParseError"),
                (-32600, "InvalidRequest"),
                (-32601, "MethodNotFound"),
                (-32602, "InvalidParams"),
                (-32603, "InternalError"),
                (-32001, "WidgetNotFound"),
                (-32002, "WidgetNotInteractable"),
                (-32003, "VisualPropertyWrite"),
                (-32004, "StructuralChange"),
                (-32005, "TimeoutError"),
                (-32006, "InputInjectionFailed"),
                (-32007, "EngineThreadViolation"),
                (-32008, "ScreenshotFailed"),
                (-32010, "VersionMismatch"),
                (-32011, "NegotiationTimeout"),
                (-32012, "SubprotocolMismatch"),
                (-32013, "NotNegotiated"),
                (-32030, "PathViolation"),
            })
            {
                Assert.IsTrue(codes.Contains(value),
                    $"WireErrorCode missing {name} ({value})");
            }
        }

        [Test]
        public void WireErrorAliasesMatchEnum()
        {
            Assert.AreEqual((int)WireErrorCode.WidgetNotFound,
                WireError.WidgetNotFound);
            Assert.AreEqual((int)WireErrorCode.WidgetNotInteractable,
                WireError.WidgetNotInteractable);
            Assert.AreEqual((int)WireErrorCode.TimeoutError,
                WireError.Timeout);
            Assert.AreEqual((int)WireErrorCode.InvalidParams,
                WireError.InvalidParams);
            Assert.AreEqual((int)WireErrorCode.InternalError,
                WireError.InternalError);
            Assert.AreEqual((int)WireErrorCode.ParseError,
                WireError.ParseError);
            Assert.AreEqual((int)WireErrorCode.MethodNotFound,
                WireError.MethodNotFound);
        }
    }
}
