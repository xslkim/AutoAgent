// Unity sample with several visual-write violations.
using UnityEngine;
using UnityEngine.UI;

public class LoginController : MonoBehaviour
{
    public Image background;
    public Image buttonImage;
    public Transform iconRoot;

    void Awake()
    {
        background.color = Color.red;                       // violation: color_write
        buttonImage.sprite = Resources.Load<Sprite>("foo"); // violation: sprite_write (no GetStateSprite)
        iconRoot.transform.localScale = Vector3.one;        // violation: transform_visual
        gameObject.SetActive(false);                        // violation: set_active
        background.enabled = false;                         // violation: enabled_write
    }
}
