// AutoAgent TASK-0132 — LoginControllerTests.cs
// AUTOAGENT_ALLOW_VISUAL — test fixture setup must write RectTransform dimensions
// and SetActive state to mirror the real LoginScene fixture precisely; these are
// controlled test-harness writes, not unreviewed production visual mutations.
//
// Unity PlayMode tests for LoginController.
// Run via: Window > General > Test Runner > PlayMode > Run All
//
// Coverage:
//   - Interactive components (TMP_InputField, Button) added to correct nodes
//   - Visual fields unchanged after LoginController.Start() (dump_before ≈ dump_after)
//   - Successful login: welcome_panel shown, login_panel hidden
//   - Failed login: error_label shows error message, welcome_panel hidden
//   - MockApi.PostReceived true after submit; credentials forwarded correctly
//   - e2e flow: send_text → click → mock receives POST → welcome_text visible

using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using TMPro;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace AutoAgent.Login.Tests
{
    /// <summary>PlayMode tests for LoginController + MockApi integration.</summary>
    public class LoginControllerTests
    {
        // -----------------------------------------------------------------------
        // Scene setup / teardown
        // -----------------------------------------------------------------------

        GameObject      _root;
        MockApi         _api;
        LoginController _ctrl;

        // Fixture nodes (mirror AutoAgentFixtureBuilder output)
        GameObject _loginPanel;
        GameObject _welcomePanel;
        GameObject _accountInputBg;
        GameObject _passwordInputBg;
        GameObject _loginButtonBg;
        TextMeshProUGUI _errorLabel;
        TextMeshProUGUI _welcomeText;

        [UnitySetUp]
        public IEnumerator SetUp()
        {
            // Build a minimal fixture that mirrors LoginScene structure
            _root = new GameObject("TestRoot");

            _loginPanel   = MakeImage(_root, "login_panel");
            _welcomePanel = MakeImage(_root, "welcome_panel");

            _accountInputBg  = MakeInputBg(_loginPanel, "account_input_bg",  "account_input_text");
            _passwordInputBg = MakeInputBg(_loginPanel, "password_input_bg",  "password_input_text");
            _loginButtonBg   = MakeImage(_loginPanel, "login_button_bg");
            MakeText(_loginPanel, "login_button_label", "Login");

            _errorLabel  = MakeText(_loginPanel, "error_label", "").GetComponent<TextMeshProUGUI>();
            _welcomeText = MakeText(_welcomePanel, "welcome_text", "Welcome!").GetComponent<TextMeshProUGUI>();

            // API mock
            _api = _root.AddComponent<MockApi>();
            _api.validUsername = "admin";
            _api.validPassword = "secret";
            _api.delaySeconds  = 0f;   // instant for tests

            // Controller (wired to API)
            _ctrl = _root.AddComponent<LoginController>();
            // Inject API via reflection (field is SerializeField private)
            typeof(LoginController)
                .GetField("api", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)
                ?.SetValue(_ctrl, _api);

            // Let Start() run
            yield return null;
        }

        [TearDown]
        public void TearDown()
        {
            if (_root != null)
                Object.DestroyImmediate(_root);
        }

        // -----------------------------------------------------------------------
        // 1. Attached components
        // -----------------------------------------------------------------------

        [Test]
        [Description("account_input_bg must have TMP_InputField after Start")]
        public void AccountInputBg_HasTMPInputField()
        {
            Assert.IsNotNull(_accountInputBg.GetComponent<TMP_InputField>(),
                "TMP_InputField expected on account_input_bg");
        }

        [Test]
        [Description("password_input_bg must have TMP_InputField after Start")]
        public void PasswordInputBg_HasTMPInputField()
        {
            Assert.IsNotNull(_passwordInputBg.GetComponent<TMP_InputField>(),
                "TMP_InputField expected on password_input_bg");
        }

        [Test]
        [Description("login_button_bg must have Button after Start")]
        public void LoginButtonBg_HasButton()
        {
            Assert.IsNotNull(_loginButtonBg.GetComponent<Button>(),
                "Button expected on login_button_bg");
        }

        // -----------------------------------------------------------------------
        // 2. Visual fields unchanged (dump_before ≈ dump_after)
        // -----------------------------------------------------------------------

        [Test]
        [Description("RectTransform values on account_input_bg must not change")]
        public void AccountInputBg_RectTransformUnchanged()
        {
            var rt = _accountInputBg.GetComponent<RectTransform>();
            Assert.AreEqual(new Vector2(360, 56), rt.sizeDelta,
                "sizeDelta must equal fixture value (360×56)");
            Assert.AreEqual(new Vector2(0, 120), rt.anchoredPosition,
                "anchoredPosition must equal fixture value (0, 120)");
        }

        [Test]
        [Description("error_label text must be empty after Start (visual unchanged)")]
        public void ErrorLabel_EmptyAfterStart()
        {
            Assert.AreEqual(string.Empty, _errorLabel.text);
        }

        [Test]
        [Description("welcome_panel must be inactive after Start")]
        public void WelcomePanel_InactiveAfterStart()
        {
            Assert.IsFalse(_welcomePanel.activeSelf,
                "welcome_panel must start hidden");
        }

        // -----------------------------------------------------------------------
        // 3. Successful login flow
        // -----------------------------------------------------------------------

        [UnityTest]
        [Description("e2e: enter valid credentials → click → welcome_panel shown")]
        public IEnumerator SuccessfulLogin_ShowsWelcomePanel()
        {
            // Simulate send_text
            var acctField = _accountInputBg.GetComponent<TMP_InputField>();
            var pwdField  = _passwordInputBg.GetComponent<TMP_InputField>();
            acctField.text = "admin";
            pwdField.text  = "secret";

            // Simulate click
            _loginButtonBg.GetComponent<Button>().onClick.Invoke();

            // Wait for coroutine (2 frames for instant MockApi)
            yield return null;
            yield return null;

            Assert.IsTrue(_welcomePanel.activeSelf, "welcome_panel must be active after success");
            Assert.IsFalse(_loginPanel.activeSelf,  "login_panel must be hidden after success");
        }

        [UnityTest]
        [Description("mock API receives POST with correct credentials on login")]
        public IEnumerator SuccessfulLogin_MockApiReceivesPost()
        {
            var acctField = _accountInputBg.GetComponent<TMP_InputField>();
            var pwdField  = _passwordInputBg.GetComponent<TMP_InputField>();
            acctField.text = "admin";
            pwdField.text  = "secret";

            _loginButtonBg.GetComponent<Button>().onClick.Invoke();
            yield return null;
            yield return null;

            Assert.IsTrue(_api.PostReceived,            "MockApi.PostReceived must be true");
            Assert.AreEqual("admin",  _api.LastUsername, "Username forwarded to API");
            Assert.AreEqual("secret", _api.LastPassword, "Password forwarded to API");
        }

        [UnityTest]
        [Description("welcome_text node is visible after successful login")]
        public IEnumerator SuccessfulLogin_WelcomeTextVisible()
        {
            _accountInputBg.GetComponent<TMP_InputField>().text = "admin";
            _passwordInputBg.GetComponent<TMP_InputField>().text = "secret";
            _loginButtonBg.GetComponent<Button>().onClick.Invoke();

            yield return null;
            yield return null;

            // welcome_text is a child of welcome_panel; it becomes visible when panel activates
            Assert.IsTrue(_welcomeText.gameObject.activeInHierarchy,
                "welcome_text must be visible after login");
        }

        // -----------------------------------------------------------------------
        // 4. Failed login flow
        // -----------------------------------------------------------------------

        [UnityTest]
        [Description("wrong credentials → error_label shows message, welcome_panel hidden")]
        public IEnumerator FailedLogin_ShowsErrorLabel()
        {
            _accountInputBg.GetComponent<TMP_InputField>().text  = "wrong";
            _passwordInputBg.GetComponent<TMP_InputField>().text = "bad";
            _loginButtonBg.GetComponent<Button>().onClick.Invoke();

            yield return null;
            yield return null;

            Assert.IsFalse(string.IsNullOrEmpty(_errorLabel.text),
                "error_label must show a non-empty error message");
            Assert.IsFalse(_welcomePanel.activeSelf,
                "welcome_panel must remain hidden after failed login");
        }

        [UnityTest]
        [Description("login button re-enabled after failed login attempt")]
        public IEnumerator FailedLogin_ButtonReenabled()
        {
            _accountInputBg.GetComponent<TMP_InputField>().text  = "wrong";
            _passwordInputBg.GetComponent<TMP_InputField>().text = "bad";
            var btn = _loginButtonBg.GetComponent<Button>();
            btn.onClick.Invoke();

            yield return null;
            yield return null;

            Assert.IsTrue(btn.interactable, "Button must be interactable again after failure");
        }

        // -----------------------------------------------------------------------
        // 5. MockApi state
        // -----------------------------------------------------------------------

        [UnityTest]
        [Description("MockApi.CallCount increments on each login attempt")]
        public IEnumerator MockApi_CallCountIncrements()
        {
            _accountInputBg.GetComponent<TMP_InputField>().text  = "admin";
            _passwordInputBg.GetComponent<TMP_InputField>().text = "secret";
            var btn = _loginButtonBg.GetComponent<Button>();

            btn.onClick.Invoke();
            yield return null; yield return null;

            // Re-enable and click again
            btn.interactable = true;
            _loginPanel.SetActive(true);
            _welcomePanel.SetActive(false);
            btn.onClick.Invoke();
            yield return null; yield return null;

            Assert.AreEqual(2, _api.CallCount, "CallCount should be 2 after two login attempts");
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

        // Builds the account/password input_bg with a child input_text, matching the
        // LoginScene fixture layout (anchoredPosition / sizeDelta match fixture values).
        static GameObject MakeInputBg(GameObject parent, string bgName, string textName)
        {
            var bg = new GameObject(bgName, typeof(RectTransform), typeof(Image));
            bg.transform.SetParent(parent.transform, worldPositionStays: false);
            var rt = bg.GetComponent<RectTransform>();
            rt.sizeDelta        = new Vector2(360, 56);
            rt.anchoredPosition = bgName == "account_input_bg"
                ? new Vector2(0, 120) : new Vector2(0, 40);

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
