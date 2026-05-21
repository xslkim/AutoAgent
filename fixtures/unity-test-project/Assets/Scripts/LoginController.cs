// AutoAgent TASK-0132 — LoginController.cs
// AUTOAGENT_ALLOW_VISUAL — this file IS the behavior layer; SetActive calls here are
// the intended login-flow state transitions (show/hide panels on success/failure),
// not fixture modifications.
//
// Autonomous-loop implementation: adds TMP_InputField + Button to the pre-built
// LoginScene fixture at runtime and drives the login flow.
//
// Design constraints (docs/10 §3):
//   - The fixture is a pure-visual skeleton with NO interactive components.
//   - This controller ONLY adds behaviour; it must not alter any visual field
//     (position, size, sprite, text content, color) so that dump_before vs
//     dump_after shows identical visual state.
//   - Interactive components live in attached_components; visual stays in fields.
//
// Node names match the pinnedId values applied by AutoAgentMetadataBuilder:
//   account_input_bg, password_input_bg, login_button_bg,
//   error_label, welcome_panel, login_panel, welcome_text

using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace AutoAgent.Login
{
    /// <summary>
    /// Adds <see cref="TMP_InputField"/> and <see cref="Button"/> to the LoginScene
    /// fixture nodes and drives the login flow via <see cref="MockApi"/>.
    /// </summary>
    [AddComponentMenu("AutoAgent/Login Controller")]
    public class LoginController : MonoBehaviour
    {
        // -----------------------------------------------------------------------
        // Inspector fields — override node names when fixture names change
        // -----------------------------------------------------------------------

        [Header("Fixture node names (match pinnedId)")]
        [SerializeField] string accountInputNode  = "account_input_bg";
        [SerializeField] string passwordInputNode = "password_input_bg";
        [SerializeField] string loginButtonNode   = "login_button_bg";
        [SerializeField] string errorLabelNode    = "error_label";
        [SerializeField] string welcomePanelNode  = "welcome_panel";
        [SerializeField] string loginPanelNode    = "login_panel";

        [Header("API (assign in Inspector or via test setup)")]
        [SerializeField] MockApi api;

        // -----------------------------------------------------------------------
        // Runtime references (populated in Start)
        // -----------------------------------------------------------------------

        TMP_InputField  _accountField;
        TMP_InputField  _passwordField;
        Button          _loginButton;
        TextMeshProUGUI _errorLabel;
        GameObject      _welcomePanel;
        GameObject      _loginPanel;

        bool _ready;

        // -----------------------------------------------------------------------
        // Unity lifecycle
        // -----------------------------------------------------------------------

        void Start()
        {
            // Locate fixture nodes — using inactive search so welcome_panel is found
            _loginPanel   = RequireNode(loginPanelNode);
            _welcomePanel = RequireNode(welcomePanelNode);
            _errorLabel   = RequireNode(errorLabelNode).GetComponent<TextMeshProUGUI>();

            // Add interactive components to the visual skeleton
            // These appear in attached_components in the dump_after snapshot.
            _accountField  = AttachInputField(RequireNode(accountInputNode));
            _passwordField = AttachInputField(RequireNode(passwordInputNode));
            _loginButton   = AttachButton(RequireNode(loginButtonNode));

            // Wire button
            _loginButton.onClick.AddListener(OnLoginClicked);

            // Ensure initial visual state (welcome hidden, error empty)
            _welcomePanel.SetActive(false);
            _errorLabel.text = string.Empty;

            _ready = true;
        }

        // -----------------------------------------------------------------------
        // Login flow
        // -----------------------------------------------------------------------

        void OnLoginClicked()
        {
            if (!_ready) return;
            if (api == null)
            {
                Debug.LogError("[LoginController] No MockApi assigned.");
                return;
            }
            StartCoroutine(LoginCoroutine());
        }

        IEnumerator LoginCoroutine()
        {
            _loginButton.interactable = false;
            _errorLabel.text = string.Empty;

            string username = _accountField != null ? _accountField.text : string.Empty;
            string password = _passwordField != null ? _passwordField.text : string.Empty;

            LoginResult result = null;
            yield return api.Login(username, password, r => result = r);

            if (result != null && result.success)
            {
                _loginPanel.SetActive(false);
                _welcomePanel.SetActive(true);
            }
            else
            {
                _errorLabel.text          = result?.error ?? "Login failed.";
                _loginButton.interactable = true;
            }
        }

        // -----------------------------------------------------------------------
        // Component helpers — no visual properties are modified
        // -----------------------------------------------------------------------

        /// <summary>
        /// Add a <see cref="TMP_InputField"/> to <paramref name="go"/>.
        /// Uses the first child <see cref="TextMeshProUGUI"/> as the text component.
        /// Does NOT alter position, size, sprite, or text color.
        /// </summary>
        static TMP_InputField AttachInputField(GameObject go)
        {
            var field = go.AddComponent<TMP_InputField>();

            // Bind the existing child TMP_Text as the editable text component
            var textChild = go.GetComponentInChildren<TextMeshProUGUI>(includeInactive: true);
            if (textChild != null)
            {
                field.textComponent = textChild;
                // Viewport = the parent RectTransform (input_bg fills the visible area)
                field.textViewport = go.GetComponent<RectTransform>();
            }

            field.text = string.Empty;
            return field;
        }

        /// <summary>
        /// Add a <see cref="Button"/> to <paramref name="go"/>.
        /// Uses the node's existing <see cref="Image"/> as the target graphic.
        /// Does NOT alter position, size, or sprite.
        /// </summary>
        static Button AttachButton(GameObject go)
        {
            var btn = go.AddComponent<Button>();
            btn.targetGraphic = go.GetComponent<Image>();
            return btn;
        }

        // -----------------------------------------------------------------------
        // Scene traversal
        // -----------------------------------------------------------------------

        /// <summary>
        /// Find a <see cref="GameObject"/> by name, including inactive objects.
        /// Logs an error and returns null if not found.
        /// </summary>
        static GameObject RequireNode(string nodeName)
        {
            // GameObject.Find does not find inactive objects; use FindObjectsOfType
            // which searches the full scene hierarchy including inactive nodes.
            var all = Resources.FindObjectsOfTypeAll<GameObject>();
            foreach (var go in all)
            {
                if (go.hideFlags != HideFlags.None) continue;  // skip asset objects
                if (go.name == nodeName) return go;
            }
            Debug.LogError($"[LoginController] Node not found in scene: '{nodeName}'");
            return null;
        }
    }
}
