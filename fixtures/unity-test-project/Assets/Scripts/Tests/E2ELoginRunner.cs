// AutoAgent TASK-0133 — E2ELoginRunner.cs
// AUTOAGENT_ALLOW_VISUAL — e2e test harness must control panel visibility (SetActive)
// and set RectTransform dimensions to mirror the real LoginScene fixture.
//
// Unity PlayMode e2e test that drives the full login flow end-to-end:
//   send_text → click → mock API 收到 POST → welcome_text 出现
//
// The test emits log lines that scripts/e2e/unity_login.sh greps to verify
// each e2e step completed successfully:
//   [E2E] send_text 成功  — after each text input
//   [E2E] click 成功     — after button click
//   [E2E] mock API 收到 POST — after MockApi.PostReceived becomes true
//
// Run via Unity Test Runner (PlayMode) or:
//   Unity.exe -batchmode -runTests -testPlatform PlayMode \
//             -testFilter AutoAgent.Login.Tests.E2ELoginTests \
//             -testResults results.xml -logFile unity.log

using System.Collections;
using NUnit.Framework;
using TMPro;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace AutoAgent.Login.Tests
{
    /// <summary>
    /// End-to-end login flow test.
    /// Constructs a fixture matching the LoginScene layout, attaches
    /// LoginController + MockApi, and drives a complete send_text → click
    /// → API POST → welcome_text visible flow.
    /// </summary>
    [TestFixture]
    public class E2ELoginTests
    {
        // -----------------------------------------------------------------------
        // Fixture state
        // -----------------------------------------------------------------------

        GameObject      _root;
        MockApi         _api;
        TMP_InputField  _accountField;
        TMP_InputField  _passwordField;
        Button          _loginButton;
        TextMeshProUGUI _errorLabel;
        GameObject      _welcomePanel;
        TextMeshProUGUI _welcomeText;

        // -----------------------------------------------------------------------
        // Setup — mirrors AutoAgentFixtureBuilder.BuildLoginScene() layout
        // -----------------------------------------------------------------------

        [UnitySetUp]
        public IEnumerator SetUp()
        {
            _root = new GameObject("E2E_Root");

            var loginPanel   = MakeImage(_root, "login_panel");
            _welcomePanel    = MakeImage(_root, "welcome_panel");
            _welcomePanel.SetActive(false);

            var acctBg  = MakeInputBg(loginPanel, "account_input_bg",  "account_input_text",
                                      new Vector2(0, 120), new Vector2(360, 56));
            var pwdBg   = MakeInputBg(loginPanel, "password_input_bg", "password_input_text",
                                      new Vector2(0, 40),  new Vector2(360, 56));
            var btnBg   = MakeImage(loginPanel, "login_button_bg");
            MakeText(loginPanel, "login_button_label", "Login");

            _errorLabel  = MakeText(loginPanel,   "error_label",  "").GetComponent<TextMeshProUGUI>();
            _welcomeText = MakeText(_welcomePanel, "welcome_text", "Welcome!")
                               .GetComponent<TextMeshProUGUI>();

            // MockApi — instant, valid credentials: admin / password
            _api = _root.AddComponent<MockApi>();
            _api.validUsername = "admin";
            _api.validPassword = "password";
            _api.delaySeconds  = 0f;

            // LoginController — inject API via reflection
            var ctrl = _root.AddComponent<LoginController>();
            typeof(LoginController)
                .GetField("api",
                    System.Reflection.BindingFlags.NonPublic |
                    System.Reflection.BindingFlags.Instance)
                ?.SetValue(ctrl, _api);

            // Let Start() run; controller attaches TMP_InputField + Button
            yield return null;

            // Grab the components LoginController attached
            _accountField = acctBg.GetComponent<TMP_InputField>();
            _passwordField = pwdBg.GetComponent<TMP_InputField>();
            _loginButton   = btnBg.GetComponent<Button>();
        }

        [TearDown]
        public void TearDown()
        {
            if (_root != null)
                Object.DestroyImmediate(_root);
        }

        // -----------------------------------------------------------------------
        // E2E tests
        // -----------------------------------------------------------------------

        /// <summary>
        /// Full login flow: send_text → click → mock API called → welcome visible.
        /// This is the primary e2e scenario verified by unity_login.sh.
        /// </summary>
        [UnityTest]
        [Description("E2E: send_text → click → mock API 收到 POST → welcome_text 出现")]
        public IEnumerator FullLoginFlow_E2E()
        {
            // ---- Step 1: send_text (username) ----
            Assert.IsNotNull(_accountField, "account TMP_InputField must exist after Start()");
            _accountField.text = "admin";
            Debug.Log("[E2E] send_text 成功: account_input_bg <- \"admin\"");

            // ---- Step 2: send_text (password) ----
            Assert.IsNotNull(_passwordField, "password TMP_InputField must exist after Start()");
            _passwordField.text = "password";
            Debug.Log("[E2E] send_text 成功: password_input_bg <- \"password\"");

            // ---- Step 3: click login button ----
            Assert.IsNotNull(_loginButton, "login Button must exist after Start()");
            Assert.IsTrue(_loginButton.interactable, "login button must be interactable before click");
            _loginButton.onClick.Invoke();
            Debug.Log("[E2E] click 成功: login_button_bg");

            // Wait for MockApi coroutine to complete (instant delay=0 still yields one frame)
            yield return null;
            yield return null;

            // ---- Step 4: verify mock API received POST ----
            Assert.IsTrue(_api.PostReceived,
                "MockApi must record a POST after button click");
            Assert.AreEqual("admin",    _api.LastUsername, "Username forwarded to API");
            Assert.AreEqual("password", _api.LastPassword, "Password forwarded to API");
            Debug.Log($"[E2E] mock API 收到 POST: username={_api.LastUsername}");

            // ---- Step 5: verify welcome_text visible ----
            Assert.IsTrue(_welcomePanel.activeSelf,
                "welcome_panel must be active after successful login");
            Assert.IsTrue(_welcomeText.gameObject.activeInHierarchy,
                "welcome_text must be visible after successful login");
            Debug.Log("[E2E] welcome_text 出现: PASS");
        }

        /// <summary>
        /// Failure path: wrong credentials → error shown, welcome hidden.
        /// Validates the negative e2e path.
        /// </summary>
        [UnityTest]
        [Description("E2E: 错误凭据 → error_label 显示，welcome_panel 隐藏")]
        public IEnumerator FailedLoginFlow_E2E()
        {
            _accountField.text  = "wrong_user";
            _passwordField.text = "wrong_pass";
            Debug.Log("[E2E] send_text 成功: account_input_bg <- \"wrong_user\"");
            Debug.Log("[E2E] send_text 成功: password_input_bg <- \"wrong_pass\"");

            _loginButton.onClick.Invoke();
            Debug.Log("[E2E] click 成功: login_button_bg");

            yield return null;
            yield return null;

            Assert.IsTrue(_api.PostReceived, "MockApi must record a POST even on failure");
            Debug.Log($"[E2E] mock API 收到 POST: username={_api.LastUsername} (invalid)");

            Assert.IsFalse(_welcomePanel.activeSelf, "welcome_panel must stay hidden on failure");
            Assert.IsFalse(string.IsNullOrEmpty(_errorLabel.text), "error_label must show error");
            Debug.Log($"[E2E] error_label 显示: \"{_errorLabel.text}\" — PASS");
        }

        /// <summary>
        /// Verify TMP_InputField + Button exist immediately after Start() — confirms
        /// that attached_components is populated in the dump_after snapshot.
        /// </summary>
        [Test]
        [Description("attached_components check: TMP_InputField + Button present after Start()")]
        public void AttachedComponents_PresentAfterStart()
        {
            Assert.IsNotNull(_accountField,  "TMP_InputField on account_input_bg");
            Assert.IsNotNull(_passwordField, "TMP_InputField on password_input_bg");
            Assert.IsNotNull(_loginButton,   "Button on login_button_bg");
            Debug.Log("[E2E] attached_components 验证通过: TMP_InputField × 2 + Button × 1");
        }

        // -----------------------------------------------------------------------
        // Fixture builder helpers
        // -----------------------------------------------------------------------

        static GameObject MakeImage(GameObject parent, string name)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Image));
            go.transform.SetParent(parent.transform, worldPositionStays: false);
            return go;
        }

        static GameObject MakeInputBg(GameObject parent, string bgName, string textName,
                                      Vector2 pos, Vector2 size)
        {
            var bg = new GameObject(bgName, typeof(RectTransform), typeof(Image));
            bg.transform.SetParent(parent.transform, worldPositionStays: false);
            var rt = bg.GetComponent<RectTransform>();
            rt.anchoredPosition = pos;
            rt.sizeDelta        = size;

            var txt = new GameObject(textName, typeof(RectTransform), typeof(TextMeshProUGUI));
            txt.transform.SetParent(bg.transform, worldPositionStays: false);
            txt.GetComponent<TextMeshProUGUI>().text = string.Empty;
            return bg;
        }

        static GameObject MakeText(GameObject parent, string name, string content)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(TextMeshProUGUI));
            go.transform.SetParent(parent.transform, worldPositionStays: false);
            go.GetComponent<TextMeshProUGUI>().text = content;
            return go;
        }
    }
}
