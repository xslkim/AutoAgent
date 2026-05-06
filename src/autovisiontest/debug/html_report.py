"""HTML report generator for DebugTracer.

Produces a self-contained single-file HTML with all images inlined as base64.
No external dependencies — opens in any modern browser.
"""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autovisiontest.debug.tracer import DebugTracer, StepTrace

_CSS = """
:root {
  --bg:      #16181d;
  --surface: #1f2128;
  --card:    #272a33;
  --border:  #363a45;
  --text:    #c9cbd0;
  --dim:     #666b77;
  --accent:  #4dabf7;
  --pass:    #51cf66;
  --fail:    #ff6b6b;
  --warn:    #ffd43b;
  --action:  #74c0fc;
  --tag-bg:  #2c3040;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,sans-serif;font-size:13px;line-height:1.5}
a{color:var(--accent);text-decoration:none}

/* ── Layout ── */
.page{max-width:1600px;margin:0 auto;padding:16px}

/* ── Header ── */
.header{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px 24px;margin-bottom:20px}
.header h1{font-size:20px;font-weight:600;color:#fff;margin-bottom:10px}
.meta-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:8px 24px}
.meta-item{display:flex;gap:6px}
.meta-label{color:var(--dim);min-width:60px;flex-shrink:0}
.meta-value{color:var(--text);word-break:break-all}
.badge{display:inline-block;padding:2px 10px;border-radius:4px;font-size:12px;font-weight:600}
.badge-pass{background:#1a3a25;color:var(--pass)}
.badge-fail{background:#3a1a1a;color:var(--fail)}
.badge-other{background:#2a2a1a;color:var(--warn)}

/* ── Steps nav ── */
.steps-nav{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px}
.nav-pill{padding:4px 10px;border-radius:20px;border:1px solid var(--border);cursor:pointer;font-size:12px;background:var(--card)}
.nav-pill:hover{border-color:var(--accent);color:var(--accent)}

/* ── Step card ── */
.step{background:var(--card);border:1px solid var(--border);border-radius:8px;margin-bottom:16px;overflow:hidden}
.step-header{display:flex;align-items:center;gap:10px;padding:12px 16px;background:var(--surface);border-bottom:1px solid var(--border);cursor:pointer;user-select:none}
.step-header:hover{background:#252830}
.step-num{font-size:13px;font-weight:700;color:var(--accent);min-width:52px}
.step-action-badge{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:var(--tag-bg);color:var(--action)}
.step-thought-preview{color:var(--dim);font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.step-ts{color:var(--dim);font-size:11px;flex-shrink:0}
.step-body{padding:16px;display:grid;grid-template-columns:1fr 1fr;gap:16px}

/* ── Screenshots ── */
.screenshots{display:flex;flex-direction:column;gap:10px}
.screenshot-group{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.img-card{background:var(--surface);border:1px solid var(--border);border-radius:6px;overflow:hidden}
.img-label{padding:5px 8px;font-size:11px;color:var(--dim);background:var(--bg);border-bottom:1px solid var(--border)}
.img-card img{display:block;width:100%;height:auto;cursor:zoom-in}

/* ── Right panel ── */
.right-panel{display:flex;flex-direction:column;gap:12px;overflow:hidden}

/* ── Section ── */
.section-label{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--dim);margin-bottom:5px}

/* ── Thought box ── */
.thought-box{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--warn);border-radius:4px;padding:10px 12px;font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-word;max-height:180px;overflow-y:auto}

/* ── Action box ── */
.action-box{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--action);border-radius:4px;padding:10px 12px;font-size:12px;font-family:monospace}
.action-type{font-weight:700;color:var(--action)}
.action-coords{color:var(--warn)}
.action-params{color:var(--dim)}

/* ── Model image section ── */
.sent-img-section details summary{cursor:pointer;color:var(--accent);font-size:12px;padding:4px 0}
.sent-img-section img{max-width:100%;margin-top:6px;border:1px solid var(--border);border-radius:4px}
.sent-img-meta{font-size:11px;color:var(--dim);margin-top:4px}

/* ── Prompt section ── */
.prompt-section details summary{cursor:pointer;color:var(--accent);font-size:12px;padding:4px 0}
.prompt-box{background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:10px;font-size:11px;font-family:monospace;white-space:pre-wrap;word-break:break-word;max-height:220px;overflow-y:auto;margin-top:6px}
.prompt-history{font-size:11px;color:var(--dim);margin-top:4px}

/* ── Raw response ── */
.raw-section details summary{cursor:pointer;color:var(--accent);font-size:12px;padding:4px 0}
.raw-box{background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:10px;font-size:11px;font-family:monospace;white-space:pre-wrap;word-break:break-word;max-height:200px;overflow-y:auto;margin-top:6px}

/* ── Lightbox ── */
#lightbox{display:none;position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:9999;align-items:center;justify-content:center;cursor:zoom-out}
#lightbox.open{display:flex}
#lightbox img{max-width:92vw;max-height:92vh;border-radius:4px;border:1px solid var(--border)}

/* ── Responsive ── */
@media(max-width:900px){
  .step-body{grid-template-columns:1fr}
  .screenshot-group{grid-template-columns:1fr}
}
"""

_JS = """
// Collapse / expand step bodies
document.querySelectorAll('.step-header').forEach(h => {
  h.addEventListener('click', () => {
    const body = h.nextElementSibling;
    body.style.display = body.style.display === 'none' ? '' : 'none';
  });
});

// Lightbox
const lb = document.getElementById('lightbox');
const lbImg = document.getElementById('lb-img');
document.querySelectorAll('.img-card img').forEach(img => {
  img.addEventListener('click', e => {
    e.stopPropagation();
    lbImg.src = img.src;
    lb.classList.add('open');
  });
});
lb.addEventListener('click', () => lb.classList.remove('open'));
document.addEventListener('keydown', e => { if(e.key==='Escape') lb.classList.remove('open'); });

// Nav pills scroll
document.querySelectorAll('.nav-pill').forEach(p => {
  p.addEventListener('click', () => {
    const target = document.getElementById(p.dataset.target);
    if(target) target.scrollIntoView({behavior:'smooth', block:'start'});
  });
});
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _h(text: str) -> str:
    return html.escape(str(text))


def _status_badge(status: str) -> str:
    s = status.upper()
    if "PASS" in s or "COMPLETED" in s:
        css = "badge-pass"
    elif "FAIL" in s or "CRASH" in s or "ERROR" in s:
        css = "badge-fail"
    else:
        css = "badge-other"
    return f'<span class="badge {css}">{_h(status)}</span>'


def _action_display(step: "StepTrace") -> str:
    atype = _h(step.action_type)
    coords = f" @ ({step.coords[0]}, {step.coords[1]})" if step.coords else ""
    params = ""
    if step.action_params:
        skip = {"x", "y", "to_x", "to_y"}
        extra = {k: v for k, v in step.action_params.items() if k not in skip}
        if extra:
            params = "  " + _h(json.dumps(extra, ensure_ascii=False))
    return (
        f'<span class="action-type">{atype}</span>'
        f'<span class="action-coords">{_h(coords)}</span>'
        f'<span class="action-params">{params}</span>'
    )


def _img_tag(b64: str, mime: str = "image/png") -> str:
    return f'<img src="data:{mime};base64,{b64}" loading="lazy">'


def _render_step(step: "StepTrace", idx: int) -> str:
    from autovisiontest.debug.tracer import jpeg_to_b64, png_to_b64

    before_b64 = png_to_b64(step.before_png)
    after_b64 = png_to_b64(step.after_png) if step.after_png else before_b64

    # Thought preview (first line, max 100 chars)
    thought_first = step.thought.splitlines()[0][:100] if step.thought else "(no thought)"

    bc = step.backend_call

    # ── Left: screenshots ──
    screenshot_html = f"""
<div class="screenshots">
  <div class="section-label">截图</div>
  <div class="screenshot-group">
    <div class="img-card">
      <div class="img-label">动作前</div>
      {_img_tag(before_b64)}
    </div>
    <div class="img-card">
      <div class="img-label">动作后</div>
      {_img_tag(after_b64)}
    </div>
  </div>
"""
    if bc is not None:
        sent_b64 = jpeg_to_b64(bc.sent_jpeg)
        orig_w, orig_h = bc.orig_size
        sent_w, sent_h = bc.sent_size
        scale_note = (
            f"原始 {orig_w}×{orig_h} → 发送 {sent_w}×{sent_h}"
            if (orig_w, orig_h) != (sent_w, sent_h)
            else f"{orig_w}×{orig_h}（无缩放）"
        )
        screenshot_html += f"""
  <div class="sent-img-section">
    <details>
      <summary>发送给模型的图像（缩放后 JPEG）</summary>
      {_img_tag(sent_b64, "image/jpeg")}
      <div class="sent-img-meta">{_h(scale_note)}</div>
    </details>
  </div>
"""
    screenshot_html += "</div>"

    # ── Right: prompt + response ──
    right_html = '<div class="right-panel">'

    # Thought
    right_html += f"""
<div>
  <div class="section-label">模型思考（Thought）</div>
  <div class="thought-box">{_h(step.thought or "(empty)")}</div>
</div>
"""

    # Action
    right_html += f"""
<div>
  <div class="section-label">执行动作</div>
  <div class="action-box">{_action_display(step)}</div>
</div>
"""

    # Prompt (collapsible)
    if bc is not None:
        right_html += f"""
<div class="prompt-section">
  <details>
    <summary>发送给模型的 Prompt（点击展开）</summary>
    <pre class="prompt-box">{_h(bc.prompt_text)}</pre>
    <div class="prompt-history">历史步骤数：{bc.history_count}</div>
  </details>
</div>
"""

    # Raw response (collapsible)
    if bc is not None:
        right_html += f"""
<div class="raw-section">
  <details>
    <summary>模型原始输出（Raw Response）</summary>
    <pre class="raw-box">{_h(bc.raw_response or "(empty)")}</pre>
  </details>
</div>
"""

    right_html += "</div>"

    return f"""
<div class="step" id="step-{idx}">
  <div class="step-header">
    <span class="step-num">Step {step.step_idx + 1}</span>
    <span class="step-action-badge">{_h(step.action_type)}</span>
    <span class="step-thought-preview">{_h(thought_first)}</span>
    <span class="step-ts">{_h(step.timestamp)}</span>
  </div>
  <div class="step-body">
    {screenshot_html}
    {right_html}
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_html(tracer: "DebugTracer") -> str:
    """Render a self-contained HTML string from a completed DebugTracer."""

    total = len(tracer.steps)
    status_badge = _status_badge(tracer.final_status or "UNKNOWN")

    # Navigation pills
    nav_pills = "".join(
        f'<span class="nav-pill" data-target="step-{i}">Step {s.step_idx + 1}: {_h(s.action_type)}</span>'
        for i, s in enumerate(tracer.steps)
    )

    # Step cards
    step_cards = "".join(_render_step(s, i) for i, s in enumerate(tracer.steps))

    header = f"""
<div class="header">
  <h1>AutoVisionTest 调试报告</h1>
  <div class="meta-grid">
    <div class="meta-item"><span class="meta-label">会话 ID</span><span class="meta-value">{_h(tracer.session_id)}</span></div>
    <div class="meta-item"><span class="meta-label">目标</span><span class="meta-value">{_h(tracer.session_goal)}</span></div>
    <div class="meta-item"><span class="meta-label">应用</span><span class="meta-value">{_h(tracer.app_path)}</span></div>
    <div class="meta-item"><span class="meta-label">开始时间</span><span class="meta-value">{_h(tracer.started_at)}</span></div>
    <div class="meta-item"><span class="meta-label">结束时间</span><span class="meta-value">{_h(tracer.finished_at)}</span></div>
    <div class="meta-item"><span class="meta-label">总步数</span><span class="meta-value">{total}</span></div>
    <div class="meta-item"><span class="meta-label">结果</span><span class="meta-value">{status_badge}</span></div>
  </div>
</div>
"""

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AutoVisionTest Debug — {_h(tracer.session_id)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page">
{header}
<div class="steps-nav">{nav_pills}</div>
{step_cards}
</div>

<!-- Lightbox -->
<div id="lightbox"><img id="lb-img" src=""></div>

<script>{_JS}</script>
</body>
</html>
"""
