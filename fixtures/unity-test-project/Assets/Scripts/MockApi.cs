// AutoAgent TASK-0132 — MockApi.cs
//
// Simulates an HTTP POST /api/login endpoint for testing purposes.
// Attach to any GameObject in the scene (LoginController holds a reference).
//
// Usage in tests:
//   api.SetCredentials("admin", "secret");
//   StartCoroutine(api.Login("admin", "secret", result => Assert.IsTrue(result.success)));

using System;
using System.Collections;
using UnityEngine;

namespace AutoAgent.Login
{
    /// <summary>Result returned by <see cref="MockApi.Login"/>.</summary>
    [Serializable]
    public class LoginResult
    {
        public bool   success;
        public string error;   // populated on failure
    }

    /// <summary>
    /// Lightweight mock that stands in for a real HTTP login endpoint.
    /// Records whether a POST was received so tests can assert the call happened.
    /// </summary>
    public class MockApi : MonoBehaviour
    {
        // -----------------------------------------------------------------------
        // Config (set from tests or Inspector)
        // -----------------------------------------------------------------------

        [Tooltip("Username accepted as valid credentials.")]
        public string validUsername = "admin";

        [Tooltip("Password accepted as valid credentials.")]
        public string validPassword = "password";

        [Tooltip("Simulated network round-trip delay in seconds.")]
        public float delaySeconds = 0.05f;

        // -----------------------------------------------------------------------
        // State (inspectable in tests)
        // -----------------------------------------------------------------------

        /// <summary>True after the first <see cref="Login"/> call has been issued.</summary>
        public bool PostReceived { get; private set; }

        /// <summary>Last username passed to <see cref="Login"/>.</summary>
        public string LastUsername { get; private set; }

        /// <summary>Last password passed to <see cref="Login"/>.</summary>
        public string LastPassword { get; private set; }

        /// <summary>Number of times <see cref="Login"/> has been called.</summary>
        public int CallCount { get; private set; }

        // -----------------------------------------------------------------------
        // Public API
        // -----------------------------------------------------------------------

        /// <summary>Set valid credentials (convenience helper for tests).</summary>
        public void SetCredentials(string username, string password)
        {
            validUsername = username;
            validPassword = password;
        }

        /// <summary>Reset all tracking state between tests.</summary>
        public void Reset()
        {
            PostReceived = false;
            LastUsername = null;
            LastPassword = null;
            CallCount    = 0;
        }

        /// <summary>
        /// Simulate a POST /api/login with <paramref name="username"/> and
        /// <paramref name="password"/>. Calls <paramref name="callback"/> with the
        /// result after a simulated round-trip delay.
        /// </summary>
        public IEnumerator Login(string username, string password, Action<LoginResult> callback)
        {
            // Record the call
            PostReceived  = true;
            LastUsername  = username;
            LastPassword  = password;
            CallCount    += 1;

            // Simulate network latency
            if (delaySeconds > 0f)
                yield return new WaitForSeconds(delaySeconds);

            bool ok = string.Equals(username, validUsername, StringComparison.Ordinal)
                   && string.Equals(password, validPassword, StringComparison.Ordinal);

            callback(new LoginResult
            {
                success = ok,
                error   = ok ? null : "Invalid username or password.",
            });
        }
    }
}
