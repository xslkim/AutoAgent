// AUTOAGENT_ALLOW_VISUAL: button-press-feedback (animation tween)
// Reason: this controller drives a small color flash on click; reviewed manually.
using UnityEngine;
using UnityEngine.UI;

public class ButtonFeedback : MonoBehaviour
{
    public Image image;

    public void OnPress()
    {
        // Would normally trip color_write, but the file-level marker exempts it.
        image.color = Color.gray;
    }

    public void OnRelease()
    {
        image.color = Color.white;
    }
}
