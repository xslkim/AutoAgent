using System;
using System.Collections.Concurrent;
using UnityEngine;

namespace AutoAgent
{
    /// <summary>
    /// Thread-safe FIFO queue of <see cref="Action"/> delegates that must
    /// execute on the Unity main thread. Background threads (e.g. the
    /// WebSocket receive loop) call <see cref="Post"/> to enqueue work;
    /// the Unity main thread calls <see cref="FlushOnMainThread"/> once per
    /// frame (from <see cref="AutoAgentBootstrap.Update"/>).
    ///
    /// Design notes:
    /// • Every public method except <see cref="FlushOnMainThread"/> is safe
    ///   to call from any thread.
    /// • <see cref="IsMainThread"/> compares against the thread that created
    ///   this instance — which must always be the Unity main thread.
    /// • Exceptions thrown by queued actions are caught, logged, and
    ///   swallowed so one bad action cannot stall the queue.
    /// </summary>
    internal sealed class MainThreadDispatcher
    {
        readonly ConcurrentQueue<Action> _queue  = new ConcurrentQueue<Action>();
        readonly int                     _ownerId;

        /// <summary>
        /// Creates a dispatcher. <b>Must be called from the Unity main
        /// thread</b> so that <see cref="IsMainThread"/> is accurate.
        /// </summary>
        public MainThreadDispatcher()
        {
            _ownerId = System.Threading.Thread.CurrentThread.ManagedThreadId;
        }

        // ---- public API ---------------------------------------------------

        /// <summary>
        /// Enqueue <paramref name="action"/> for execution on the main
        /// thread. Thread-safe; may be called from any thread.
        /// </summary>
        public void Post(Action action)
        {
            if (action == null) throw new ArgumentNullException(nameof(action));
            _queue.Enqueue(action);
        }

        /// <summary>
        /// Drain the queue, executing every pending action on the calling
        /// thread. <b>Must be called from the Unity main thread.</b>
        /// </summary>
        public void FlushOnMainThread()
        {
            while (_queue.TryDequeue(out var action))
            {
                try   { action(); }
                catch (Exception ex) { Debug.LogException(ex); }
            }
        }

        /// <summary>
        /// Returns <c>true</c> when called from the thread that created
        /// this dispatcher (i.e. the Unity main thread).
        /// </summary>
        public bool IsMainThread =>
            System.Threading.Thread.CurrentThread.ManagedThreadId == _ownerId;

        /// <summary>Owner thread id captured at construction time.</summary>
        internal int OwnerThreadId => _ownerId;
    }
}
