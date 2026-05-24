// AUTOAGENT_ALLOW_VISUAL: highlight toggle modifies Image.color for selected-state feedback.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using TMPro;

/// <summary>
/// Interactive card-panel controller for the poc_playground scene.
/// Wires interactivity onto the static visual skeleton (Images + Labels)
/// added by AutoAgentFixtureBuilder.
///
/// AI-written by Claude Code during autonomous loop (TASK POC-PLAYGROUND-001).
/// </summary>
public class PocPlaygroundController : MonoBehaviour
{
    [Header("Buttons")]
    [SerializeField] private List<Image> _clickTargets = new();

    [Header("Text Input")]
    [SerializeField] private Image       _textTargetBg;
    [SerializeField] private TMP_Text    _textTargetLabel;
    private TMP_InputField               _inputField;

    [Header("State")]
    private int   _selectedIndex = -1;
    private Color _defaultColor  = Color.white;
    private Color _highlightColor = new(1f, 0.85f, 0.3f, 1f);

    // ------------------------------------------------------------------ lifecycle

    void Start()
    {
        FindClickTargets();
        AttachButtons();
        AttachInputField();
    }

    // ------------------------------------------------------------------ click targets

    void FindClickTargets()
    {
        // Node names match pinned IDs set in the Unity scene.
        string[] ids =
        {
            "click_target",
            "click_target_variant_1", "click_target_variant_2",
            "click_target_variant_3", "click_target_variant_4",
            "click_target_variant_5",
        };
        foreach (var id in ids)
        {
            var go = GameObject.Find(id);
            if (go == null) continue;
            var img = go.GetComponent<Image>();
            if (img != null)
            {
                _clickTargets.Add(img);
                _defaultColor = img.color;
            }
        }
    }

    void AttachButtons()
    {
        for (int i = 0; i < _clickTargets.Count; i++)
        {
            var img = _clickTargets[i];
            var go  = img.gameObject;

            // Add Button using the existing Image as target graphic.
            var btn = go.GetComponent<Button>() ?? go.AddComponent<Button>();
            btn.targetGraphic = img;
            img.raycastTarget = true; // enable input on the visual skeleton

            int idx = i; // capture for closure
            btn.onClick.AddListener(() => OnClickTarget(idx));
        }
    }

    void OnClickTarget(int index)
    {
        // Remove highlight from previous selection.
        if (_selectedIndex >= 0 && _selectedIndex < _clickTargets.Count)
            _clickTargets[_selectedIndex].color = _defaultColor;

        _selectedIndex = index;
        if (index >= 0 && index < _clickTargets.Count)
            _clickTargets[index].color = _highlightColor;
    }

    // ------------------------------------------------------------------ text input + filter

    void AttachInputField()
    {
        if (_textTargetBg == null)
        {
            var go = GameObject.Find("text_target");
            if (go != null) _textTargetBg = go.GetComponent<Image>();
        }
        if (_textTargetLabel == null)
        {
            var go = GameObject.Find("text_target_text");
            if (go != null) _textTargetLabel = go.GetComponent<TMP_Text>();
        }

        if (_textTargetBg == null) return;

        var go2 = _textTargetBg.gameObject;
        _inputField = go2.GetComponent<TMP_InputField>() ?? go2.AddComponent<TMP_InputField>();
        _inputField.targetGraphic = _textTargetBg;
        if (_textTargetLabel != null)
            _inputField.textComponent = _textTargetLabel;

        _inputField.onValueChanged.AddListener(OnFilterTextChanged);
    }

    void OnFilterTextChanged(string text)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            foreach (var img in _clickTargets)
                img.gameObject.SetActive(true);
            return;
        }

        var lower = text.ToLowerInvariant();
        foreach (var img in _clickTargets)
        {
            bool match = img.name.ToLowerInvariant().Contains(lower);
            img.gameObject.SetActive(match);
        }
    }

    // ------------------------------------------------------------------ drag handler

    // IBeginDragHandler / IDragHandler / IDropHandler are added by the
    // framework's input driver when drag/drop is tested.  For a simple
    // implementation the Button on-click serves as the primary verification.
}
