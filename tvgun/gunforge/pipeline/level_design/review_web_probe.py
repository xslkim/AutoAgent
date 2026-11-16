"""Local LD17 comparison prototype. All frames and review operations run in Godot."""
import argparse
import base64
import json
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from paths import CACHE, GODOT, ROOT
from review_revision import preview, review_context


PAGE = """<!doctype html>
<html lang="zh"><meta charset="utf-8"><title>Godot 审阅桥接对照</title>
<style>
body{font:16px system-ui;background:#111b2b;color:#edf3fc;margin:2rem auto;max-width:960px;padding:0 1rem}
button,input,select{font:inherit;margin:.25rem;padding:.4rem}
img{display:block;width:100%;margin:1rem 0} pre{white-space:pre-wrap;background:#203044;padding:1rem}
</style>
<h1>Godot 审阅桥接对照</h1>
<form id="seek"><label>跳到帧 <input id="tick" type="number" min="0" required></label><button>跳转</button></form>
<button id="swap">切换上一版本</button><output id="status"></output>
<img id="frame" alt="Godot 同帧画面">
<label>事件 <select id="events"></select></label><button id="inspect">查看源属性</button>
<pre id="details"></pre>
<form id="note"><label>隔离批注 <input id="message" maxlength="800" required></label><button>保存</button></form>
<script>
const byId = id => document.getElementById(id);
const token = "__TOKEN__";
let busy = false;
async function command(op, fields = {}) {
  if (busy) return;
  busy = true;
  try {
    const response = await fetch("/command", {
      method:"POST", headers:{"Content-Type":"application/json", "X-Review-Token":token},
      body:JSON.stringify({op, ...fields})
    });
    const data = await response.json();
    if (!response.ok || data.error) throw Error(data.error || response.statusText);
    byId("status").textContent = `第 ${data.tick} 帧 · ${data.build_id.slice(0,12)}` + (data.saved ? " · 已保存隔离批注" : "");
    if (data.frame) {
      byId("tick").value = data.tick;
      byId("frame").src = "data:image/png;base64," + data.frame;
      byId("events").replaceChildren(...data.event_ids.map(id => new Option(id,id)));
      byId("details").textContent = JSON.stringify(data.state,null,2);
    } else if (data.details) byId("details").textContent = JSON.stringify(data.details,null,2);
    else if (data.saved) byId("message").value = "";
  } catch (error) {
    byId("status").textContent = error.message;
  } finally { busy = false; }
}
byId("seek").onsubmit = event => { event.preventDefault(); command("seek",{tick:Number(byId("tick").value)}); };
byId("swap").onclick = () => command("switch");
byId("inspect").onclick = () => command("inspect",{id:byId("events").value});
byId("note").onsubmit = event => { event.preventDefault(); command("note",{text:byId("message").value}); };
command("seek",{tick:__TICK__});
</script>"""


def serve(process, directory, tick, port, token):
    frame = directory / "bridge-frame" / "player.png"
    pending = directory / "request.pending"
    request = directory / "request.json"

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, payload, content_type="application/json; charset=utf-8"):
            data = payload.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path != "/":
                self.reply(404, "{}")
                return
            self.reply(200, PAGE.replace("__TOKEN__", token).replace("__TICK__", str(tick)), "text/html; charset=utf-8")

        def do_POST(self):
            if self.path != "/command" or self.headers.get("X-Review-Token") != token:
                self.reply(403, '{"error":"Unknown command origin"}')
                return
            try:
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 8192:
                    raise ValueError("Invalid request size")
                command = json.loads(self.rfile.read(size))
                operation = command.get("op")
                if operation == "seek" and type(command.get("tick")) is int and 0 <= command["tick"] <= 2**31 - 1:
                    pass
                elif operation == "inspect" and isinstance(command.get("id"), str) and 0 < len(command["id"]) <= 256:
                    pass
                elif operation == "note" and isinstance(command.get("text"), str) and 0 < len(command["text"].strip()) <= 800:
                    pass
                elif operation != "switch":
                    raise ValueError("Invalid review operation")
                if request.exists():
                    raise RuntimeError("A previous command is still queued")
                command["request_id"] = secrets.token_hex(8)
                response = directory / f"response-{command['request_id']}.json"
                pending.write_text(json.dumps(command), encoding="utf-8")
                pending.replace(request)
                for _ in range(600):
                    if response.exists():
                        break
                    if process.poll() is not None:
                        raise RuntimeError("Godot stopped. See godot.log.")
                    time.sleep(0.025)
                else:
                    raise RuntimeError("Godot did not respond in time")
                result = json.loads(response.read_bytes())
                response.unlink()
                if "frame_sha256" in result:
                    result["frame"] = base64.b64encode(frame.read_bytes()).decode("ascii")
                self.reply(200, json.dumps(result))
            except (ValueError, AttributeError) as error:
                self.reply(400, json.dumps({"error": str(error)}))
            except (OSError, RuntimeError) as error:
                self.reply(503, json.dumps({"error": str(error)}))

    return HTTPServer(("127.0.0.1", port), Handler)


def verify(url, token, tick, later_tick, anchor, directory):
    timings = {}

    def invoke(op, **fields):
        request = Request(url + "command", json.dumps({"op": op, **fields}).encode(),
                          {"X-Review-Token": token, "Content-Type": "application/json"})
        start = time.monotonic()
        with urlopen(request, timeout=20) as response:
            result = json.load(response)
        timings.setdefault(op, []).append(round((time.monotonic() - start) * 1000, 1))
        if "error" in result:
            raise RuntimeError(result["error"])
        return result

    candidate = invoke("seek", tick=tick)
    alternate = invoke("seek", tick=later_tick)
    restored = invoke("seek", tick=tick)
    inspected = invoke("inspect", id=anchor)
    noted = invoke("note", text="LD17 isolated bridge test")
    base = invoke("switch")
    assert alternate["tick"] > tick
    assert candidate == restored
    assert inspected["tick"] == noted["tick"] == base["tick"] == tick
    assert inspected["details"]["event_id"] == anchor
    assert inspected["details"]["source"]["pointer"]
    assert noted["saved"] and candidate["build_id"] != base["build_id"]
    assert candidate["frame_sha256"] != base["frame_sha256"]
    annotation = next((directory / "comments").glob("note-*.json"))
    context = review_context(annotation)
    assert context["tick"] == tick and context["anchor"] == anchor
    assert context["build_id"] == candidate["build_id"]
    assert context["evidence"][0]["sha256"] == candidate["frame_sha256"]
    return {"passed": True, "tick": tick, "event": anchor, "same_pose": candidate["pose_sha256"] == base["pose_sha256"],
            "later_tick": alternate["tick"], "later_pose_changed": candidate["pose_sha256"] != alternate["pose_sha256"],
            "candidate": candidate["build_id"], "base": base["build_id"], "response_ms": timings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposal", type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--later-tick", type=int, help="second comparison frame for the automated check")
    args = parser.parse_args()
    proposal = json.loads(args.proposal.read_bytes())
    comparison = preview(args.proposal)
    tick = comparison["tick"]
    directory = CACHE / "runs" / f"review-bridge-{time.time_ns()}"
    directory.mkdir(parents=True)
    token = secrets.token_hex(16)
    command = [GODOT, "--path", ROOT / "gunforge/framework", "--script",
               "res://tests/review_bridge_probe.gd", "--", "--review-smoke",
               f"--build={comparison['candidate']}", f"--compare={comparison['base']}",
               f"--assets={ROOT}", f"--at-tick={tick}", f"--evidence={directory}",
               f"--reviews={directory / 'comments'}"]
    with (directory / "godot.log").open("wb") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            with serve(process, directory, tick, args.port, token) as server:
                url = f"http://127.0.0.1:{server.server_port}/"
                print(url, flush=True)
                if not args.verify:
                    server.serve_forever()
                    return
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    later_tick = args.later_tick if args.later_tick is not None else tick + 60
                    result = verify(url, token, tick, later_tick, proposal["review"]["anchor"], directory)
                    (directory / "comparison.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
                    print(json.dumps({"directory": str(directory), **result}))
                finally:
                    server.shutdown()
                    thread.join()
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
