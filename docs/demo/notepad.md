# AutoVisionTest MVP Demo Guide — Notepad

This guide walks through the complete MVP demonstration of AutoVisionTest using Windows Notepad.

## Prerequisites

### Hardware
- Windows 10/11 desktop
- GPU with >= 8GB VRAM (for local VLM inference), OR cloud API access
- 16GB+ RAM recommended

### Software
- Python 3.11+
- AutoVisionTest installed (`pip install -e .`)
- vLLM (>= 0.6) for local model serving, OR cloud API keys

### Model Services

Start the required VLM inference services:

**Option A: Local inference (recommended for development)**

```bash
# Terminal 1: Start Planner (Qwen2.5-VL-7B)
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-VL-7B-Instruct-AWQ \
    --port 8000 \
    --max-model-len 4096

# Terminal 2: Start Actor/grounding (ShowUI-2B)
python -m vllm.entrypoints.openai.api_server \
    --model showlab/ShowUI-2B \
    --port 8001 \
    --max-model-len 4096
```

**Option B: Cloud API**

Edit `config/model.yaml`:

```yaml
planner:
  backend: "claude_api"  # or "openai_api"
  model: "claude-sonnet-4-20250514"
  api_key_env: "ANTHROPIC_API_KEY"
```

Set the API key: `$env:ANTHROPIC_API_KEY = "sk-..."` (PowerShell)

## Demo Steps

### Step 1: Prepare the sandbox

```powershell
mkdir C:\TestSandbox -Force
Remove-Item C:\TestSandbox\* -Recurse -Force -ErrorAction SilentlyContinue
```

### Step 2: Run exploratory test (J.1)

```powershell
$env:AUTOVT_RUN_E2E = "1"
python -m pytest tests/e2e/test_notepad_exploration.py -v -s
```

Or use the CLI directly:

```powershell
autovisiontest run --goal "打开记事本,输入hello world,保存到C:\TestSandbox\out.txt" --app "C:\Windows\System32\notepad.exe"
```

**Expected outcome:**
- Notepad opens automatically
- AI observes the screen and plans actions
- "hello world" is typed into Notepad
- File is saved to `C:\TestSandbox\out.txt`
- Test exits with code 0 (PASS)
- A recording is auto-saved for future regression runs

### Step 3: Verify the result

```powershell
# Check output file
Get-Content C:\TestSandbox\out.txt
# Should output: hello world

# Check that a recording was created
autovisiontest list-recordings
```

### Step 4: Run regression test (J.2)

After J.1 succeeds, a recording is automatically saved. Running the same goal again uses regression mode:

```powershell
$env:AUTOVT_RUN_E2E = "1"
python -m pytest tests/e2e/test_notepad_regression.py -v -s
```

**Expected outcome:**
- Regression mode (faster, deterministic)
- Completes in < 60 seconds
- Same output file generated

### Step 5: View the report

```powershell
# List sessions
autovisiontest status --list

# View specific session report
autovisiontest report <session_id> --format json
```

## Architecture Overview

```
User (CLI/HTTP/MCP)
    │
    ▼
SessionScheduler
    ├── Planner (Qwen2.5-VL-7B / Claude)
    │   └── Analyzes screenshot + history → next action intent
    ├── Actor (ShowUI-2B)
    │   └── Locates element by description → (x, y) coordinates
    ├── Reflector (shared with Planner)
    │   └── Verifies action result, judges goal completion
    └── SafetyGuard
        └── Blocks dangerous operations
```

## The 8-Step Closed Loop

As defined in the product document §2.2:

1. **AI writes code** → code enters the project repo
2. **Build** → compilation/package install
3. **Launch app** → AutoVisionTest starts the target app
4. **Capture screenshot** → mss captures the screen
5. **AI analyzes + acts** → Planner → Actor → mouse/keyboard
6. **Verify result** → Reflector + assertions
7. **Generate report** → structured JSON with evidence
8. **AI reads report** → fixes bugs, re-runs

## Troubleshooting

### "Connection refused" on port 8000/8001
- Ensure vLLM services are running
- Check GPU memory: `nvidia-smi`

### Notepad doesn't open
- Verify `C:\Windows\System32\notepad.exe` exists
- Check that no other Notepad instances are blocking

### Test runs too long (> 5 min)
- The Planner may be stuck. Check logs for repeated actions.
- Reduce `max_steps` in `config/model.yaml`

### Low grounding accuracy
- Ensure screenshots are captured at the expected resolution
- Check that ShowUI-2B model loaded correctly

## Configuration Reference

Key settings in `config/model.yaml`:

| Setting | Default | Description |
|---------|---------|-------------|
| `planner.backend` | `vllm_local` | Planner model backend |
| `planner.model` | `Qwen/Qwen2.5-VL-7B-Instruct-AWQ` | Planner model |
| `actor.backend` | `showui_local` | Actor/grounding backend |
| `actor.model` | `showlab/ShowUI-2B` | Actor model |
| `runtime.max_steps` | 30 | Max actions per session |
| `runtime.max_session_duration_s` | 600 | Max session time (seconds) |
