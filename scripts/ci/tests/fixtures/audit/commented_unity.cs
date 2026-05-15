// Comments containing the violating patterns should NOT be flagged.
using UnityEngine;
using UnityEngine.UI;

public class CommentedController : MonoBehaviour
{
    public Image image;

    void Awake()
    {
        // image.color = Color.red;     // commented out, must NOT match
        // image.sprite = null;         // commented out, must NOT match
        var btn = image.gameObject.AddComponent<UnityEngine.UI.Button>();
        btn.interactable = true;
    }
}
