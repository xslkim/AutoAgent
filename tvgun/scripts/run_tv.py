#!/usr/bin/env python3
"""PC 电视端：手机光枪"打鸭子"真机验证系统。

全屏 cv2 窗口渲染带亮白边框的游戏画面（Sinden 光枪方案），
内置 HTTP 服务器（0.0.0.0:8000）供手机网页上报规范坐标射击。

接口契约（与手机端严格一致）：
  GET /        -> webgun/index.html（不存在返回 503）
  GET /gun.js  -> webgun/gun.js（不存在返回 503）
  POST /shot   {"x": float, "y": float}（规范坐标）-> {"hit": bool, "score": int}
  POST /aim    {"x": float, "y": float}（规范坐标）-> {"ok": true}（兼容路径）
  UDP  :port   文本 "x,y"（规范坐标，~120Hz，最新覆盖，主路径——TCP 连接
               建立的 WiFi 抖动（5-30ms 尖峰）会直接变成准星卡顿，UDP 无连接）
  UDP  :port+1 局域网自动发现：收到 "TVGUN_DISCOVER" 回复 "TVGUN_HERE <port>"，
               手机端广播探测后从应答包源地址拿到 PC IP，零配置连接
  GET /state   -> {"score": int, "target": {"x": float, "y": float, "r": float}}

用法:
  python scripts/run_tv.py [--port 8000] [--size 1920x1080] [--speed 1.0]
                           [--seed 42] [--windowed]
  python scripts/run_tv.py --selftest
"""
from __future__ import annotations

import argparse
import json
import queue
import random
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WEBGUN_DIR = ROOT / "webgun"

NORM_W, NORM_H = 1920.0, 1080.0  # 规范坐标系
TARGET_R = 60.0                  # 鸭子半径（规范坐标）
BASE_SPEED = 420.0               # 鸭子速度（规范坐标/秒）
FLASH_SEC = 0.15                 # 命中/未命中闪屏时长
AIM_TIMEOUT = 0.6                # 准星超时隐藏（秒）
AIM_R = 25.0                     # 准星圆圈半径（规范坐标）
MARGIN_RATIO = 0.04              # 边框内边距（窗口短边比例）
BORDER_THICK = 24                # 边框厚度（像素）
CORNER_LEN = 3                   # L 形角标臂长 = 边框厚度倍数

DEFAULT_SIZE = (1920, 1080)


def parse_size(s: str) -> tuple[int, int]:
    w, h = s.lower().split("x")
    return int(w), int(h)


def frame_geometry(w: int, h: int) -> tuple[int, int, int, int]:
    """返回游戏区内角点 (x0, y0, x1, y1)（窗口像素，开区间边界）。"""
    m = int(round(min(w, h) * MARGIN_RATIO))
    x0 = m + BORDER_THICK
    y0 = m + BORDER_THICK
    return x0, y0, w - x0, h - y0


def norm_to_px(x: float, y: float, w: int, h: int) -> tuple[int, int]:
    """规范坐标 (1920x1080) -> 窗口像素。"""
    x0, y0, x1, y1 = frame_geometry(w, h)
    px = x0 + x / NORM_W * (x1 - x0)
    py = y0 + y / NORM_H * (y1 - y0)
    return int(round(px)), int(round(py))


def px_to_norm(px: int, py: int, w: int, h: int) -> tuple[float, float]:
    """窗口像素 -> 规范坐标 (1920x1080)。"""
    x0, y0, x1, y1 = frame_geometry(w, h)
    x = (px - x0) / (x1 - x0) * NORM_W
    y = (py - y0) / (y1 - y0) * NORM_H
    return float(x), float(y)


class GameState:
    """游戏状态，全部在规范坐标系下运算。"""

    def __init__(self, speed: float = 1.0, seed: int | None = None):
        self.rng = random.Random(seed)
        self.speed_scale = speed
        self.score = 0
        self.tx, self.ty = NORM_W / 2, NORM_H / 2
        self.vx, self.vy = 0.0, 0.0
        self.respawn()
        self.flash_kind: str | None = None   # "hit" / "miss"
        self.flash_until = 0.0
        self.shots: queue.Queue = queue.Queue()  # (x, y, done_event, result_box)
        self._aim_lock = threading.Lock()
        self._aim: tuple[float, float, float] | None = None  # (x, y, monotonic_ts)

    def respawn(self):
        m = TARGET_R + 10
        self.tx = self.rng.uniform(m, NORM_W - m)
        self.ty = self.rng.uniform(m, NORM_H - m)
        ang = self.rng.uniform(0, 2 * np.pi)
        v = BASE_SPEED * self.speed_scale
        self.vx, self.vy = float(v * np.cos(ang)), float(v * np.sin(ang))

    def update(self, dt: float):
        self.tx += self.vx * dt
        self.ty += self.vy * dt
        if self.tx < TARGET_R or self.tx > NORM_W - TARGET_R:
            self.vx = -self.vx
            self.tx = min(max(self.tx, TARGET_R), NORM_W - TARGET_R)
        if self.ty < TARGET_R or self.ty > NORM_H - TARGET_R:
            self.vy = -self.vy
            self.ty = min(max(self.ty, TARGET_R), NORM_H - TARGET_R)

    def judge(self, x: float, y: float) -> bool:
        d2 = (x - self.tx) ** 2 + (y - self.ty) ** 2
        return bool(d2 <= TARGET_R ** 2)

    def handle_shot(self, x: float, y: float) -> bool:
        hit = self.judge(x, y)
        if hit:
            self.score += 1
            self.respawn()
        self.flash_kind = "hit" if hit else "miss"
        self.flash_until = time.monotonic() + FLASH_SEC
        return hit

    def set_aim(self, x: float, y: float):
        """HTTP 线程写入准星槽位，新值覆盖旧值。"""
        with self._aim_lock:
            self._aim = (x, y, time.monotonic())

    def get_aim(self) -> tuple[float, float] | None:
        """主循环每帧读取；超时（>AIM_TIMEOUT 秒无更新）返回 None。"""
        with self._aim_lock:
            aim = self._aim
        if aim is None or time.monotonic() - aim[2] > AIM_TIMEOUT:
            return None
        return aim[0], aim[1]

    def consume_shots(self):
        """消费 HTTP 线程入队的射击请求并回写结果。"""
        while True:
            try:
                x, y, done, box = self.shots.get_nowait()
            except queue.Empty:
                return
            box["hit"] = self.handle_shot(x, y)
            done.set()

    def snapshot(self) -> dict:
        return {"score": self.score,
                "target": {"x": self.tx, "y": self.ty, "r": TARGET_R}}


def make_handler(state: GameState):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

        def _serve_webgun(self, name: str, ctype: str):
            p = WEBGUN_DIR / name
            if not p.is_file():
                msg = f"webgun/{name} not found; phone web page is provided by another component\n"
                self._send(503, msg.encode("utf-8"), "text/plain; charset=utf-8")
                return
            self._send(200, p.read_bytes(), ctype)

        def do_GET(self):
            if self.path == "/" or self.path == "/index.html":
                self._serve_webgun("index.html", "text/html; charset=utf-8")
            elif self.path == "/gun.js":
                self._serve_webgun("gun.js", "text/javascript; charset=utf-8")
            elif self.path == "/state":
                self._json(200, state.snapshot())
            else:
                self._send(404, b"not found\n", "text/plain; charset=utf-8")

        def do_POST(self):
            if self.path not in ("/shot", "/aim"):
                self._send(404, b"not found\n", "text/plain; charset=utf-8")
                return
            try:
                n = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._json(400, {"error": "missing Content-Length"})
                return
            try:
                body = json.loads(self.rfile.read(n))
                x, y = float(body["x"]), float(body["y"])
            except (ValueError, TypeError, KeyError):
                self._json(400, {"error": "invalid JSON body, expected {\"x\": float, \"y\": float}"})
                return
            if self.path == "/aim":
                state.set_aim(x, y)
                self._json(200, {"ok": True})
                return
            done, box = threading.Event(), {}
            state.shots.put((x, y, done, box))
            done.wait()
            self._json(200, {"hit": box["hit"], "score": state.score})

        def log_message(self, fmt, *args):
            pass

    return Handler


def start_server(state: GameState, port: int) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("0.0.0.0", port), make_handler(state))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


DISCOVERY_REQ = b"TVGUN_DISCOVER"
DISCOVERY_RES = b"TVGUN_HERE"


def start_udp(state: GameState, port: int) -> socket.socket:
    """UDP aim 监听（与 HTTP 同端口号；UDP/TCP 命名空间独立不冲突）。
    报文：ASCII "x,y"（规范坐标）。最新覆盖，丢包无妨（120Hz 冗余）。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    sock.settimeout(0.5)

    def loop():
        while True:
            try:
                data, _ = sock.recvfrom(128)
            except socket.timeout:
                continue
            except OSError:
                return  # socket closed on shutdown
            try:
                xs, ys = data.decode("ascii").strip().split(",")
                state.set_aim(float(xs), float(ys))
            except (ValueError, UnicodeDecodeError):
                continue

    threading.Thread(target=loop, daemon=True).start()
    return sock


def start_discovery(port: int, game_port: int) -> socket.socket:
    """局域网自动发现应答：手机广播 TVGUN_DISCOVER，这里回复
    TVGUN_HERE <game_port>；手机从应答包源地址拿到 PC IP，免手动配置。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.settimeout(0.5)
    res = DISCOVERY_RES + b" " + str(game_port).encode("ascii")

    def loop():
        while True:
            try:
                data, addr = sock.recvfrom(128)
            except socket.timeout:
                continue
            except OSError:
                return  # socket closed on shutdown
            if data.strip() == DISCOVERY_REQ:
                try:
                    sock.sendto(res, addr)
                except OSError:
                    continue

    threading.Thread(target=loop, daemon=True).start()
    return sock


def draw_frame(state: GameState, w: int, h: int) -> np.ndarray:
    img = np.zeros((h, w, 3), np.uint8)
    m = int(round(min(w, h) * MARGIN_RATIO))
    t = BORDER_THICK
    # 命中/未命中时游戏区闪绿/红
    if state.flash_kind and time.monotonic() < state.flash_until:
        color = (0, 90, 0) if state.flash_kind == "hit" else (0, 0, 90)
        x0, y0, x1, y1 = frame_geometry(w, h)
        cv2.rectangle(img, (x0, y0), (x1 - 1, y1 - 1), color, -1)
    # 亮白实心边框
    cv2.rectangle(img, (m, m), (w - m - 1, h - m - 1), (255, 255, 255), t)
    # 四角 L 形角标（便于机器检测）
    L = t * CORNER_LEN
    for cx, cy, sx, sy in ((m, m, 1, 1), (w - m - 1, m, -1, 1),
                           (m, h - m - 1, 1, -1), (w - m - 1, h - m - 1, -1, -1)):
        off = t // 2
        cv2.line(img, (cx + sx * off, cy + sy * off),
                 (cx + sx * (off + L), cy + sy * off), (255, 255, 255), t)
        cv2.line(img, (cx + sx * off, cy + sy * off),
                 (cx + sx * off, cy + sy * (off + L)), (255, 255, 255), t)
    # 鸭子（简单扑翼模拟：半径随时间脉动 + 两侧"翅膀"）
    cx, cy = norm_to_px(state.tx, state.ty, w, h)
    x0, y0, x1, y1 = frame_geometry(w, h)
    r = int(round(TARGET_R / NORM_W * (x1 - x0)))
    phase = time.monotonic() * 10.0
    cv2.circle(img, (cx, cy), r, (80, 220, 255), -1)
    wing = int(r * 0.9 * abs(np.sin(phase)))
    cv2.ellipse(img, (cx - r, cy - wing // 2), (r // 2, max(wing // 2, 1)),
                -30, 0, 360, (60, 180, 220), -1)
    cv2.ellipse(img, (cx + r, cy - wing // 2), (r // 2, max(wing // 2, 1)),
                30, 0, 360, (60, 180, 220), -1)
    cv2.circle(img, (cx + r // 3, cy - r // 3), max(r // 6, 2), (0, 0, 0), -1)
    # 分数
    cv2.putText(img, f"SCORE {state.score}", (m + t + 10, m + t + 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2, cv2.LINE_AA)
    # 手机准星（超时未更新则不画）
    aim = state.get_aim()
    if aim is not None:
        ax, ay = norm_to_px(aim[0], aim[1], w, h)
        ar = int(round(AIM_R / NORM_W * (x1 - x0)))
        cyan = (255, 255, 0)
        cv2.circle(img, (ax, ay), ar, cyan, 2, cv2.LINE_AA)
        cv2.line(img, (ax - 2 * ar, ay), (ax + 2 * ar, ay), cyan, 2, cv2.LINE_AA)
        cv2.line(img, (ax, ay - 2 * ar), (ax, ay + 2 * ar), cyan, 2, cv2.LINE_AA)
        cv2.putText(img, f"({int(round(aim[0]))}, {int(round(aim[1]))})",
                    (ax + ar + 6, ay - ar - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, cyan, 2, cv2.LINE_AA)
    return img


def run_game(args) -> int:
    state = GameState(speed=args.speed, seed=args.seed)
    srv = start_server(state, args.port)
    udp = start_udp(state, args.port)
    disco = start_discovery(args.port + 1, args.port)
    w, h = parse_size(args.size)
    win = "TVGun"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, w, h)
    if not args.windowed:
        cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    print(f"HTTP+UDP server listening on 0.0.0.0:{args.port} "
          f"(discovery on {args.port + 1}, ESC to quit)")
    try:
        prev = time.monotonic()
        while True:
            t_loop = time.monotonic()
            state.update(min(t_loop - prev, 0.1))
            prev = t_loop
            state.consume_shots()
            cv2.imshow(win, draw_frame(state, w, h))
            # 60Hz 节奏：waitKey 只补满帧周期（waitKey(16) 是在工作耗时之上
            # 再固定等 16ms，实际只有 40-50fps，准星跟随会发涩）
            spent_ms = (time.monotonic() - t_loop) * 1000
            if cv2.waitKey(max(1, int(round(16.6 - spent_ms)))) & 0xFF == 27:
                break
    finally:
        srv.shutdown()
        srv.server_close()
        udp.close()
        disco.close()
        cv2.destroyAllWindows()
    return 0


def selftest() -> int:
    import urllib.error
    import urllib.request

    def free_port() -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    port = free_port()
    state = GameState(speed=0.0, seed=0)
    state.tx, state.ty = NORM_W / 2, NORM_H / 2  # 固定目标便于断言
    srv = start_server(state, port)
    base = f"http://127.0.0.1:{port}"
    failures = []

    def check(name, cond):
        print(f"{'PASS' if cond else 'FAIL'} {name}")
        if not cond:
            failures.append(name)

    def pump_until(fut, timeout: float = 10.0):
        # selftest 无游戏主循环，由本线程持续消费射击队列直至请求完成
        deadline = time.monotonic() + timeout
        while not fut.done() and time.monotonic() < deadline:
            state.consume_shots()
            time.sleep(0.005)

    try:
        with urllib.request.urlopen(f"{base}/state") as r:
            st = json.loads(r.read())
        check("GET /state", st["score"] == 0 and st["target"]["r"] == TARGET_R
              and abs(st["target"]["x"] - NORM_W / 2) < 1e-6)

        def post_shot(body) -> tuple[int, dict]:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            req = urllib.request.Request(f"{base}/shot", data=data,
                                         headers={"Content-Type": "application/json"})
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(1) as ex:
                fut = ex.submit(urllib.request.urlopen, req)
                pump_until(fut)
                with fut.result() as r:
                    return r.status, json.loads(r.read())

        code, resp = post_shot({"x": NORM_W / 2, "y": NORM_H / 2})
        check("POST /shot center hit", code == 200 and resp["hit"] is True and resp["score"] == 1)

        state.tx, state.ty = NORM_W / 2, NORM_H / 2  # 命中后已重生，重新固定
        code, resp = post_shot({"x": 0.0, "y": 0.0})
        check("POST /shot corner miss", code == 200 and resp["hit"] is False and resp["score"] == 1)

        try:
            post_shot(b"not json")
            check("POST /shot bad JSON -> 400", False)
        except urllib.error.HTTPError as e:
            check("POST /shot bad JSON -> 400", e.code == 400)

        def post_aim(body) -> tuple[int, dict]:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            req = urllib.request.Request(f"{base}/aim", data=data,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())

        code, resp = post_aim({"x": 640.5, "y": 360.25})
        check("POST /aim valid -> 200 ok", code == 200 and resp == {"ok": True})
        aim = state.get_aim()
        check("POST /aim updates slot", aim is not None
              and abs(aim[0] - 640.5) < 1e-6 and abs(aim[1] - 360.25) < 1e-6)

        # UDP aim（主路径）
        udp = start_udp(state, port)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as c:
                c.sendto(b"111.5,222.5", ("127.0.0.1", port))
            deadline = time.monotonic() + 2.0
            aim = None
            while time.monotonic() < deadline:
                aim = state.get_aim()
                if aim is not None and abs(aim[0] - 111.5) < 1e-6:
                    break
                time.sleep(0.01)
            check("UDP aim updates slot", aim is not None
                  and abs(aim[0] - 111.5) < 1e-6 and abs(aim[1] - 222.5) < 1e-6)
        finally:
            udp.close()

        # 局域网自动发现应答（自测走单播，应答逻辑与广播相同）
        disco = start_discovery(port + 1, port)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as c:
                c.settimeout(2.0)
                c.sendto(DISCOVERY_REQ, ("127.0.0.1", port + 1))
                data, _ = c.recvfrom(128)
            check("discovery replies TVGUN_HERE <port>",
                  data == DISCOVERY_RES + b" " + str(port).encode("ascii"))
        finally:
            disco.close()

        try:
            post_aim(b"not json")
            check("POST /aim bad JSON -> 400", False)
        except urllib.error.HTTPError as e:
            check("POST /aim bad JSON -> 400", e.code == 400)
    finally:
        srv.shutdown()
        srv.server_close()

    print("SELFTEST " + ("PASS" if not failures else f"FAIL ({len(failures)})"))
    return 0 if not failures else 1


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="TVGun PC 电视端")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--size", default=f"{int(NORM_W)}x{int(NORM_H)}", help="窗口像素 WxH")
    p.add_argument("--speed", type=float, default=1.0, help="鸭子速度倍率")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--windowed", action="store_true", help="窗口模式调试（不全屏）")
    p.add_argument("--selftest", action="store_true", help="无窗口自测 HTTP 接口")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.selftest:
        return selftest()
    return run_game(args)


if __name__ == "__main__":
    sys.exit(main())
