# AutoAgent Canonical Task DSL — Schema Reference

Canonical task files describe a complete UI automation task as a structured YAML
document.  They serve as both the **prompt** given to the AI agent and the
**acceptance criteria** checked after the task runs.

## File naming

```
docs/canonical-tasks/<task-id>.yaml
```

Example: `docs/canonical-tasks/login.yaml`

---

## Top-level fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | string | ✅ | DSL schema version, currently `"1.0"` |
| `task_id` | string | ✅ | Unique task identifier (e.g. `TASK-0132`) |
| `title` | string | ✅ | One-line human description |
| `engine` | string | ✅ | Target engine: `unity` \| `unreal` \| `godot` |
| `scene` | string | ✅ | Scene / level name the task runs in |
| `preconditions` | list | ❌ | State requirements before execution |
| `steps` | list | ✅ | Ordered list of automation steps |
| `expected_outcome` | object | ✅ | Post-run verification spec |
| `constraints` | object | ❌ | Guard-rails (cost, iterations, SSIM) |

---

## `preconditions`

Each entry must have a `fixture` or `controller` key:

```yaml
preconditions:
  - fixture: LoginScene
    state: initial        # named state from fixture spec
  - controller: LoginController
    status: ready         # "ready" means Start() completed without error
```

---

## `steps`

Each step is an object with the following fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✅ | Unique step identifier within the task |
| `action` | string | ✅ | Action verb (see table below) |
| `target` | string | ✅ | `pinnedId` of the target node |
| `value` | string | ❌ | Input value for `send_text` |
| `timeout_ms` | int | ❌ | Timeout for async assertions (default: 2000 ms) |
| `description` | string | ❌ | Human-readable step description |
| `verify` | object | ❌ | Inline assertion run immediately after the action |

### Supported actions

| Action | Description |
|--------|-------------|
| `send_text` | Type text into an input field (`target` must have `TMP_InputField`) |
| `clear_text` | Clear an input field's content |
| `click` | Click a button (`target` must have `Button`) |
| `assert_visible` | Assert node is active and visible in hierarchy |
| `assert_hidden` | Assert node is inactive or not visible |
| `assert_mock_called` | Assert `MockApi.PostReceived == true` and check forwarded credentials |
| `assert_text` | Assert `TextMeshProUGUI.text` equals a specific value |
| `screenshot` | Capture a screenshot (stored in `baselines/`) |
| `wait_ms` | Pause execution for N milliseconds |

### `verify` sub-fields

| Key | Used with | Description |
|-----|-----------|-------------|
| `field_value` | `send_text` | Assert the input field contains this exact value after typing |
| `post_received` | `assert_mock_called` | Assert `MockApi.PostReceived` equals this boolean |
| `username` | `assert_mock_called` | Assert `MockApi.LastUsername` equals this string |
| `password` | `assert_mock_called` | Assert `MockApi.LastPassword` equals this string |

---

## `expected_outcome`

```yaml
expected_outcome:
  visual_fields_unchanged: true          # dump_before == dump_after for all visual fields
  attached_components_added:             # components that must appear in dump_after
    - node: <pinnedId>
      component: <type-name>
  nodes_visible:
    - <pinnedId>                         # must be activeInHierarchy after task
  nodes_hidden:
    - <pinnedId>                         # must NOT be activeInHierarchy after task
```

`visual_fields_unchanged: true` is enforced by comparing `dump_tree` snapshots
taken before and after the controller's `Start()` runs.  Fields compared:

- `RectTransform.anchoredPosition`
- `RectTransform.sizeDelta`
- `Image.sprite`
- `TextMeshProUGUI.text`
- `TextMeshProUGUI.color`

---

## `constraints`

```yaml
constraints:
  max_iterations: 5        # AI agent must complete within N loop iterations
  cost_limit_usd: 5.0      # single-task cost cap (maps to budget.json limits.single_task_usd)
  visual_diff_ssim_min: 0.95  # minimum SSIM for visual regression comparison
```

---

## Parser behaviour

1. The parser validates `schema_version` before processing any other field.
2. Steps are executed **in order**; a step failure stops execution and reports
   the failing step's `id` and `action`.
3. `timeout_ms` applies only to assertion steps; action steps are synchronous
   by default.
4. Unknown action verbs raise a `ParseError` (strict mode) or emit a warning
   and skip the step (lenient mode, default).
5. `preconditions` are checked before the first step; failure aborts the task
   immediately with exit code 2.
6. `expected_outcome` is evaluated after the last step completes (or after the
   last coroutine frame settles).

---

## Example

See [`login.yaml`](login.yaml) for a complete worked example.
