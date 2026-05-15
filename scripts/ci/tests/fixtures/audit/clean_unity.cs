// Unity sample that only touches behavior — should pass clean.
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;

public class LoginController : MonoBehaviour
{
    public Image loginButtonBg;
    public TMPro.TMP_InputField accountInput;

    void Awake()
    {
        // Implement logical_role = button by attaching a Button component.
        var btn = loginButtonBg.gameObject.AddComponent<Button>();
        btn.onClick.AddListener(OnLogin);
        loginButtonBg.raycastTarget = true;   // behavior, allowed

        // Implement logical_role = input.
        accountInput.interactable = true;
    }

    void OnLogin() { /* business logic */ }
}
