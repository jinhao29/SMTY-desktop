# -*- coding: utf-8 -*-
"""EVOLVE 进化体育 - 黑白 logo 生成器（概念1破环 / 概念2上升 / 概念3徽章）
输出: generated-logos/*.svg + preview.html + png_wrappers/*.html
"""
import os

OUT = os.path.dirname(os.path.abspath(__file__))
WRAP = os.path.join(OUT, "png_wrappers")
os.makedirs(WRAP, exist_ok=True)

T = 22      # 笔画粗
H = 100     # 大写字高

# ---------- 字母（局部坐标，原点=字母左上角） ----------
def e_paths(x, w=56):
    """科技感 E：横臂端部 45° 斜切，竖笔带两个缺口"""
    return [
        f"M{x},0 L{x+w},0 L{x+w},10 L{x+w-10},22 L{x},22 Z",            # 上臂
        f"M{x},22 L{x+22},22 L{x+22},39 L{x},39 Z",                     # 竖笔上段
        f"M{x},39 L{x+48},39 L{x+48},61 L{x},61 Z",                     # 中臂
        f"M{x},61 L{x+22},61 L{x+22},78 L{x},78 Z",                     # 竖笔下段
        f"M{x},78 L{x+w-10},78 L{x+w},90 L{x+w},100 L{x},100 Z",        # 下臂
    ]

def v_path(x, w=64):
    return [f"M{x},0 L{x+22},0 L{x+32},60 L{x+42},0 L{x+w},0 L{x+w-21},100 L{x+21},100 Z"]

def l_path(x, w=50):
    return [f"M{x},0 L{x+22},0 L{x+22},78 L{x+w-12},78 L{x+w},90 L{x+w},100 L{x},100 Z"]

# 概念2 用简洁 E（无缺口，仅端部斜切）
def e_plain_paths(x, w=56):
    return [
        f"M{x},0 L{x+w},0 L{x+w},10 L{x+w-10},22 L{x},22 Z",
        f"M{x},0 L{x+22},0 L{x+22},100 L{x},100 Z",
        f"M{x},39 L{x+48},39 L{x+48},61 L{x},61 Z",
        f"M{x},78 L{x+w-10},78 L{x+w},90 L{x+w},100 L{x},100 Z",
    ]

def o_ring(cx, cy, ink):
    """普通圆环 O（概念2 用）"""
    return (f'<ellipse cx="{cx}" cy="{cy}" rx="21" ry="39" fill="none" '
            f'stroke="{ink}" stroke-width="{T}"/>')

# ---------- 概念1：破环 ----------
# 字距: E0=0(w56) V=70(w64) O=148(w96,环心148+48) L=258(w50) V=322(w64) E=400(w56) 总宽456
import math
COS45 = math.cos(math.radians(45))

def concept1(ink, bg=None):
    W, HT = 520, 232
    ox, oy = 40, 52                      # 字标组偏移（skew 后底部左移~11，左缘≥0）
    cx, cy = 196, 50                     # 环心（局部坐标，O 格 148..244 的中心）
    COS45 = math.cos(math.radians(45))
    shaft_len = 78
    ex = cx + shaft_len * COS45          # 箭杆末端
    ey = cy - shaft_len * COS45
    tipx, tipy = ex + 24 * COS45, ey - 24 * COS45          # 箭尖
    b1x, b1y = ex + 26 * COS45, ey + 26 * COS45            # 倒钩（垂直方向 ±）
    b2x, b2y = ex - 26 * COS45, ey - 26 * COS45

    p = []
    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {HT}">')
    if bg:
        p.append(f'<rect width="{W}" height="{HT}" fill="{bg}"/>')
    p.append('<defs><mask id="gap">')
    p.append('<rect x="-40" y="-60" width="620" height="340" fill="#fff"/>')
    # 缺口带：预旋转时沿 +x 从环心向外，绕环心转 -45° 后正好压在箭杆路径上
    p.append(f'<rect x="{cx}" y="{cy-15}" width="150" height="30" fill="#000" '
             f'transform="rotate(-45 {cx} {cy})"/>')
    p.append('</mask></defs>')
    # 字标组：先 skew（局部原点）再平移，字母/环/箭共用局部坐标（y 0..100）
    g = f'<g transform="translate({ox},{oy}) skewX(-6)">'
    g += f'<g mask="url(#gap)"><ellipse cx="{cx}" cy="{cy}" rx="21" ry="39" fill="none" stroke="{ink}" stroke-width="{T}"/></g>'
    paths = []
    paths += e_paths(0)
    paths += v_path(70)
    paths += l_path(258)
    paths += v_path(322)
    paths += e_paths(400)
    for d in paths:
        g += f'<path d="{d}" fill="{ink}"/>'
    # 箭杆（只在环上开口处穿过，无需遮罩）+ 实心箭头
    g += (f'<line x1="{cx}" y1="{cy}" x2="{ex}" y2="{ey}" stroke="{ink}" '
          f'stroke-width="{T}"/>')
    g += f'<polygon points="{b1x},{b1y} {tipx},{tipy} {b2x},{b2y}" fill="{ink}"/>'
    g += '</g>'
    # 中文副标（正常排版，不倾斜）
    g += (f'<text x="{W/2}" y="208" text-anchor="middle" fill="{ink}" '
          f'font-family="Microsoft YaHei, PingFang SC, sans-serif" font-weight="700" '
          f'font-size="44" letter-spacing="26">进化体育</text>')
    g += (f'<line x1="60" y1="192" x2="112" y2="192" stroke="{ink}" stroke-width="3"/>'
          f'<line x1="408" y1="192" x2="460" y2="192" stroke="{ink}" stroke-width="3"/>')
    p.append(g)
    p.append('</svg>')
    return "\n".join(p)

# ---------- 概念2：上升（三道递宽折线 + 简洁字标） ----------
def concept2(ink, bg=None):
    W, HT = 520, 560
    cx = W / 2
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {HT}">']
    if bg:
        p.append(f'<rect width="{W}" height="{HT}" fill="{bg}"/>')
    # 三道折线：底宽110 → 顶宽150，居中
    rows = [(320, 110), (256, 130), (192, 150)]
    for base, w in rows:
        p.append(f'<path d="M{cx-w/2},{base} L{cx},{base-40} L{cx+w/2},{base}" '
                 f'fill="none" stroke="{ink}" stroke-width="24"/>')
    # 字标（简洁字母，縮放0.82居中）
    s = 0.82
    tw = 456 * s
    tx = (W - tw) / 2
    ty = 386
    p.append(f'<g transform="translate({tx},{ty}) scale({s})">')
    for d in e_plain_paths(0) + v_path(70) + [None] + l_path(258) + v_path(322) + e_plain_paths(400):
        if d is None:
            continue
        p.append(f'<path d="{d}" fill="{ink}"/>')
    # O 位置: x=148, 环心 148+48
    p.append(o_ring(196, 50, ink))
    p.append('</g>')
    p.append(f'<text x="{cx}" y="{ty + 100*s + 62}" text-anchor="middle" fill="{ink}" '
             f'font-family="Microsoft YaHei, PingFang SC, sans-serif" font-weight="700" '
             f'font-size="40" letter-spacing="24">进化体育</text>')
    p.append('</svg>')
    return "\n".join(p)

# ---------- 概念2M：仅图形（独立标志） ----------
def concept2_mark(ink, bg=None):
    W = 240
    cx = W / 2
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} 200">']
    if bg:
        p.append(f'<rect width="{W}" height="200" fill="{bg}"/>')
    rows = [(158, 110), (106, 130), (54, 150)]
    for base, w in rows:
        p.append(f'<path d="M{cx-w/2},{base} L{cx},{base-40} L{cx+w/2},{base}" '
                 f'fill="none" stroke="{ink}" stroke-width="24"/>')
    p.append('</svg>')
    return "\n".join(p)

# ---------- 概念3：圆形徽章 ----------
def concept3(ink, bg=None):
    W = 420
    c = W / 2
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {W}">']
    if bg:
        p.append(f'<rect width="{W}" height="{W}" fill="{bg}"/>')
    p.append(f'<circle cx="{c}" cy="{c}" r="198" fill="none" stroke="{ink}" stroke-width="7"/>')
    p.append(f'<circle cx="{c}" cy="{c}" r="150" fill="none" stroke="{ink}" stroke-width="3"/>')
    p.append(f'<defs><path id="arcTop" d="M{c-172},{c} A172,172 0 0 1 {c+172},{c}" fill="none"/></defs>')
    p.append(f'<text fill="{ink}" font-family="Arial, sans-serif" font-weight="bold" '
             f'font-size="32" letter-spacing="7">'
             f'<textPath href="#arcTop" startOffset="50%" text-anchor="middle">EVOLVE SPORTS CLUB</textPath></text>')
    # 左右分隔圆点
    p.append(f'<circle cx="42" cy="{c}" r="7" fill="{ink}"/>')
    p.append(f'<circle cx="{W-42}" cy="{c}" r="7" fill="{ink}"/>')
    # 中心三道折线
    rows = [(212, 92), (176, 110), (140, 128)]
    for base, w in rows:
        p.append(f'<path d="M{c-w/2},{base} L{c},{base-30} L{c+w/2},{base}" '
                 f'fill="none" stroke="{ink}" stroke-width="18"/>')
    # 中心中文名 + 小字
    p.append(f'<text x="{c}" y="292" text-anchor="middle" fill="{ink}" '
             f'font-family="Microsoft YaHei, PingFang SC, sans-serif" font-weight="700" '
             f'font-size="50" letter-spacing="12">进化体育</text>')
    p.append(f'<text x="{c}" y="332" text-anchor="middle" fill="{ink}" '
             f'font-family="Microsoft YaHei, PingFang SC, sans-serif" font-weight="400" '
             f'font-size="20" letter-spacing="16">俱乐部</text>')
    p.append('</svg>')
    return "\n".join(p)

# ---------- 输出 ----------
def write(name, content):
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("written:", path)

INKS = {"black": "#000", "white": "#fff"}
for cname, fn in [("concept1-破环", concept1), ("concept2-上升", concept2),
                  ("concept2M-上升图形", concept2_mark), ("concept3-徽章", concept3)]:
    for iname, ink in INKS.items():
        write(f"{cname}-{iname}.svg", fn(ink))

# PNG 导出用 wrapper
wrappers = []
for cname, fn, aspect in [("concept1-破环", concept1, (520, 232)),
                          ("concept2-上升", concept2, (520, 560)),
                          ("concept2M-上升图形", concept2_mark, (240, 200)),
                          ("concept3-徽章", concept3, (420, 420))]:
    for iname, ink in INKS.items():
        bg = "#000" if ink == "#fff" else "#fff"
        w, h = aspect
        html = (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
                f'<style>*{{margin:0;padding:0}}body{{background:{bg};'
                f'display:flex;align-items:center;justify-content:center;'
                f'width:{w*2}px;height:{h*2}px}}'
                f'img{{width:{w*2}px;height:{h*2}px;display:block}}'
                f'</style></head><body>'
                f'<img src="../{cname}-{iname}.svg"></body></html>')
        wpath = os.path.join(WRAP, f"{cname}-{iname}.html")
        with open(wpath, "w", encoding="utf-8") as f:
            f.write(html)
        wrappers.append((f"{cname}-{iname}", (w * 2, h * 2)))
        print("wrapper:", wpath)

with open(os.path.join(OUT, "_wrappers.tsv"), "w", encoding="utf-8") as f:
    for name, (w, h) in wrappers:
        f.write(f"{name}\t{w}\t{h}\n")

# ---------- 预览页 ----------
def svg_body(svg):
    return svg.split("\n", 1)[1] if svg.startswith("<?") else svg

c1w = concept1("#fff", "#0a0a0a")
c1b = concept1("#000", "#ffffff")
c2w = concept2("#fff", "#0a0a0a")
c2b = concept2("#000", "#ffffff")
c2mw = concept2_mark("#fff", "#0a0a0a")
c2mb = concept2_mark("#000", "#ffffff")
c3w = concept3("#fff", "#0a0a0a")
c3b = concept3("#000", "#ffffff")

def strip_bg(svg):
    return svg

preview = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>EVOLVE 进化体育 · Logo 方案</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#0a0a0a; color:#eee; font-family:"Microsoft YaHei",sans-serif; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:48px 32px 96px; }}
  h1 {{ font-size:22px; font-weight:700; letter-spacing:2px; margin-bottom:6px; }}
  .sub {{ color:#888; font-size:13px; margin-bottom:48px; }}
  .concept {{ margin-bottom:72px; }}
  .concept h2 {{ font-size:15px; color:#fff; letter-spacing:1px; margin-bottom:4px; }}
  .concept .desc {{ font-size:13px; color:#777; margin-bottom:16px; line-height:1.7; }}
  .panel {{ border:1px solid #222; border-radius:10px; overflow:hidden; }}
  .dark {{ background:#0a0a0a; display:flex; justify-content:center; padding:36px; }}
  .light {{ background:#fff; display:flex; justify-content:center; padding:36px; }}
  .row2 {{ display:flex; }}
  .row2 > div {{ flex:1; }}
  .row2 > div:first-child {{ border-right:1px solid #222; }}
  svg {{ display:block; }}
  .c1 svg {{ width:560px; height:auto; }}
  .c2 svg {{ width:340px; height:auto; }}
  .c2m svg {{ width:150px; height:auto; }}
  .markline {{ display:flex; align-items:center; gap:40px; }}
  .markline .box {{ border:1px solid #222; border-radius:8px; padding:18px 26px; }}
  .smallnote {{ font-size:12px; color:#666; margin-top:10px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>EVOLVE 进化体育 · 黑白 LOGO 三方案</h1>
  <div class="sub">矢量手绘 · 黑白双版本 · 上：深底效果 / 下：浅底效果 —— 每张图都是独立 .svg 文件，可无限放大</div>

  <div class="concept c1">
    <h2>方案一 · 破环 BREAKTHROUGH</h2>
    <div class="desc">O 被一支向右上方冲刺的箭冲破——「进化 = 突破自我」。字母端部 45° 斜切 + 6° 前倾，速度感；箭头可单独截出做辅助图形。中文保持端正清晰。</div>
    <div class="panel">
      <div class="dark">{c1w}</div>
      <div class="light">{c1b}</div>
    </div>
  </div>

  <div class="concept c2">
    <h2>方案二 · 上升 ASCENT</h2>
    <div class="desc">三道逐级加宽的上升折线：每一步都更开阔，向上进化。图形可独立使用（App 图标 / 印花），字标干净利落。</div>
    <div class="panel">
      <div class="row2">
        <div class="dark">{c2w}</div>
        <div class="light">{c2b}</div>
      </div>
    </div>
    <div class="markline" style="margin-top:16px">
      <div class="box dark" style="padding:18px 26px">{c2mw}</div>
      <div class="box light" style="padding:18px 26px">{c2mb}</div>
      <div class="smallnote">↑ 独立图形（深/浅底）· 缩到 32px 依然清晰</div>
    </div>
  </div>

  <div class="concept c3" style="max-width:520px">
    <h2>方案三 · 徽章 CREST</h2>
    <div class="desc">俱乐部经典圆形队徽：环排英文 + 中文，中心三道上升线。适合队服、奖牌、社交头像。</div>
    <div class="panel">
      <div class="row2">
        <div class="dark">{c3w}</div>
        <div class="light">{c3b}</div>
      </div>
    </div>
  </div>
</div>
</body>
</html>"""

ppath = os.path.join(OUT, "preview.html")
with open(ppath, "w", encoding="utf-8") as f:
    f.write(preview)
print("written:", ppath)
