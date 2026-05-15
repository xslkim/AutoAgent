// Unity: state_sprites switching via the helper. The per-line allow_if_line_contains
// rule should keep this clean despite `.sprite =` being present.
using UnityEngine;
using UnityEngine.UI;

public class ButtonStateSwitcher : MonoBehaviour
{
    public Image image;
    public AutoAgent.StableIdComponent stableId;

    public void Press()
    {
        image.sprite = stableId.GetStateSprite("pressed");
    }

    public void Release()
    {
        image.sprite = stableId.GetStateSprite("normal");
    }
}
