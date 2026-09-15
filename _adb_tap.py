# -*- coding: utf-8 -*-
"""真机驱动小工具（vivo V2426A / 任意 adb 设备）：uiautomator dump → 按文本定位 → 点击/输入/截图。

用法：
  python _adb_tap.py list                     # 列出当前页面所有带 text/content-desc 的节点（文本,中心坐标,类）
  python _adb_tap.py region 1300              # 列出 y2<1300 的所有节点（含无文本容器）→ 量顶部间距用
  python _adb_tap.py tap 文本 [文本2 ...]      # 依次查找并点击（取第一个匹配的中心点）
  python _adb_tap.py taplast 文本              # 同上但取最后一个匹配（弹窗按钮与列表按钮同文本时用）
  python _adb_tap.py type 文本                 # 输入文本（adb input text，仅 ASCII 稳妥）
  python _adb_tap.py key back                  # 发送按键（back/home/4/29 等）
  python _adb_tap.py shot 文件名.png           # 截图到 _ui_coach/

注意：
- 本机 PowerShell 下 stdout 不回传 → 调用方请把输出重定向到文件再读。
- vivo 全系屏蔽第三方 App logcat，UI 层证据只能靠截图 + dump（本脚本）。
- Compose 的 Text 会出现在 uiautomator 的 text 属性里；空输入框/无文本容器只在 region 模式可见。
- 脚本内**不存任何屏幕坐标**：坐标每次从 dump 现算，因此与「当前设备 + 当前 UI」强绑定。
  换设备（尤其分辨率/dpi 不同）、或 App 改了布局 → 必须重新 dump 定位，
  **勿沿用旧坐标、也勿沿用旧截图得出的间距结论**。
- 不指定 `-s` 序列号，依赖「当前唯一在线设备」；多设备同连时 adb 会歧义（more than one device）。
  本脚本刻意不持有任何设备标识（型号/序列号都不写死）。
- ADB 走 %LOCALAPPDATA% 的 SDK 路径；输出目录见 OUT_DIR（本机工作区约定）。
"""
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ADB = os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe")
# ponytail: 输出目录写死本机工作区路径（截图只在本机看，跨机无意义）；
#   换工作区改这一行即可，不值得为此加一层配置层。
OUT_DIR = r"G:\shangmentiyu\_ui_coach"
UI_XML = os.path.join(OUT_DIR, "ui.xml")


def adb(*args):
    return subprocess.run([ADB, *args], capture_output=True, text=True, errors="replace")


def dump():
    os.makedirs(OUT_DIR, exist_ok=True)
    adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
    adb("pull", "/sdcard/ui.xml", UI_XML)
    return ET.parse(UI_XML).getroot()


def collect(root):
    """带 text/content-desc 的节点 → (label, cx, cy, class)"""
    rows = []
    for n in root.iter():
        label = (n.get("text") or "").strip() or (n.get("content-desc") or "").strip()
        bounds = n.get("bounds") or ""
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
        if label and m:
            x1, y1, x2, y2 = map(int, m.groups())
            rows.append((label, (x1 + x2) // 2, (y1 + y2) // 2, n.get("class") or ""))
    return rows


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    if cmd == "type":
        adb("shell", "input", "text", sys.argv[2])
        print("typed:", sys.argv[2])
        return 0
    if cmd == "key":
        adb("shell", "input", "keyevent", sys.argv[2])
        print("key:", sys.argv[2])
        return 0
    if cmd == "shot":
        name = sys.argv[2]
        adb("shell", "screencap", "-p", "/sdcard/shot.png")
        adb("pull", "/sdcard/shot.png", os.path.join(OUT_DIR, name))
        print("saved:", os.path.join(OUT_DIR, name))
        return 0

    rows = collect(dump())

    if cmd == "region":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 1200
        out = []
        for n in ET.parse(UI_XML).getroot().iter():
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.get("bounds") or "")
            if not m:
                continue
            x1, y1, x2, y2 = map(int, m.groups())
            if y1 < limit:
                label = ((n.get("text") or "") + "|" + (n.get("content-desc") or "")).strip("|")
                out.append((y1, y2, x1, x2, n.get("class") or "", label))
        for y1, y2, x1, x2, cls, label in sorted(out):
            print(f"y {y1:>5}-{y2:<5} x {x1:>5}-{x2:<5} h={y2 - y1:<5} "
                  f"{cls.split('.')[-1]:<14} {label[:36]}")
        return 0

    if cmd == "list":
        for label, x, y, cls in rows:
            print(f"{label}\t({x},{y})\t{cls.split('.')[-1]}")
        return 0

    if cmd in ("tap", "taplast"):
        for kw in sys.argv[2:]:
            hit = [r for r in rows if kw in r[0]]
            if not hit:
                print(f"MISS: {kw}")
                continue
            label, x, y, cls = hit[-1] if cmd == "taplast" else hit[0]
            adb("shell", "input", "tap", str(x), str(y))
            print(f"TAP[{cmd}]: {kw} -> '{label}' ({x},{y}) {cls.split('.')[-1]}")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
