"""Build docs/demo.gif from real CLI output (synthetic demo DB).

Usage: python scripts/make_demo_gif.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT = Path("/root/.fonts/NotoSansSC.ttf")
if not FONT.exists():
    FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")

W, H = 960, 540
TITLE_H, FOOT_H = 36, 28
BG, FG, DIM, GREEN, YELLOW = "#0d1117", "#c9d1d9", "#8b949e", "#3fb950", "#d29922"
FPS = 10
DURATION = 100


def run(args: list[str]) -> str:
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    out = subprocess.run(
        [sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True
    )
    return (out.stdout or out.stderr).strip()


def wrap_lines(text: str, max_chars: int = 74) -> list[str]:
    lines = []
    for source in text.splitlines():
        if not source:
            lines.append("")
            continue
        while len(source) > max_chars:
            lines.append(source[:max_chars])
            source = source[max_chars:]
        lines.append(source)
    return lines


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT), size)


def render(lines: list[str], intro: bool = False, outro: bool = False) -> Image.Image:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, W, TITLE_H], fill="#161b22")
    draw.text((14, 8), "MemPatrol · terminal demo  (synthetic data)", font=font(15), fill=FG)
    for i in range(3):
        draw.ellipse([W - 66 + i * 18, 12, W - 56 + i * 18, 22], fill="#30363d")
    draw.rectangle([0, H - FOOT_H, W, H], fill="#161b22")
    draw.text((14, H - 21), "github.com/yikoko01/mem-patrol  ·  mem-patrol 0.3.5", font=font(12), fill=DIM)
    body = font(17)
    y = TITLE_H + 22
    if intro:
        draw.text((40, 160), "MemPatrol", font=font(42), fill=GREEN)
        draw.text((40, 215), "memory patrol · recall · conversation gates", font=font(20), fill=FG)
        draw.text((40, 260), "for long-lived AI agents", font=font(20), fill=DIM)
        return image
    if outro:
        draw.text((40, 180), "One kernel. Two surfaces.", font=font(30), fill=FG)
        draw.text((40, 230), "CLI + read-only MCP · any SQLite schema", font=font(20), fill=DIM)
        draw.text((40, 280), "pip install mem-patrol", font=font(20), fill=GREEN)
        draw.text((40, 320), "github.com/yikoko01/mem-patrol", font=font(16), fill=YELLOW)
        return image
    for line in lines[-19:]:
        color = FG
        if line.startswith("$ "):
            color = GREEN
        elif line.startswith("[PASS]") or line.startswith("RESULT") or line.startswith("MEMORIX"):
            color = GREEN
        if line:
            draw.text((20, y), line, font=body, fill=color)
        y += 22
    return image


def main() -> int:
    demo_dir = Path("/tmp/mem-patrol-demo")
    demo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "demo_setup.py"), str(demo_dir / "demo.db")], check=True, capture_output=True)
    commands = [
        ("memorix --version", ["-m", "memorix", "--version"]),
        ("memorix diagnose --db demo.db --now 1792000100", ["-m", "memorix", "diagnose", "--db", str(demo_dir / "demo.db"), "--now", "1792000100"]),
        ("python -m memorix.retrieval.bench", ["-m", "memorix.retrieval.bench"]),
        ("memorix recall --query \"8-23 比 8-19 更难\" --user-id demo-user", ["-m", "memorix", "recall", "--db", str(demo_dir / "demo.db"), "--user-id", "demo-user", "--query", "8-23 比 8-19 更难"]),
    ]
    outputs = [(command, wrap_lines(run(args))) for command, args in commands]
    frames: list[Image.Image] = []
    screen: list[str] = []
    for _ in range(14):
        frames.append(render([], intro=True))
    screen = []
    for command, output in outputs:
        for index in range(1, len(command) + 1):
            frames.append(render(screen + ["$ " + command[:index]]))
        screen.append("$ " + command)
        for _ in range(4):
            frames.append(render(screen))
        for line in output:
            screen.append(line)
            for _ in range(2):
                frames.append(render(screen))
        for _ in range(12):
            frames.append(render(screen))
        screen.append("")
    for _ in range(26):
        frames.append(render([], outro=True))
    target = Path("docs/demo.gif")
    target.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        target,
        save_all=True,
        append_images=frames[1:],
        duration=DURATION,
        loop=0,
        optimize=True,
    )
    print("frames", len(frames), "seconds", round(len(frames) * DURATION / 1000, 1), "path", target, "bytes", target.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
