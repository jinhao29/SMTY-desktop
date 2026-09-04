# -*- coding: utf-8 -*-
"""CRLF 保留版转换 v2：在 close-paren 所在行【之前】插入 shape/colors 行。"""
import io, os

BASE = r"C:\Users\LeeNiuBi\Desktop\shangmentiyu\android_app\app\src\main\java\com\shangmentiyu\sportscoach\ui"
FILES = ["home/LessonManageTab.kt", "tools/BmiCalculatorScreen.kt"]
NEED_IMPORTS = [
    "import com.shangmentiyu.sportscoach.ui.theme.AppTextFieldShape",
    "import com.shangmentiyu.sportscoach.ui.theme.appTextFieldColors",
]


def scan_blocks(src):
    results = []
    n = len(src)
    i = 0
    while i < n:
        if src.startswith('//', i):
            nl = src.find('\n', i)
            i = nl if nl != -1 else n
            continue
        if src.startswith('/*', i):
            end = src.find('*/', i)
            i = (end + 2) if end != -1 else n
            continue
        if src.startswith('OutlinedTextField', i):
            j = i + len('OutlinedTextField')
            if j < n and src[j] == '(':
                depth = 0
                k = j
                while k < n:
                    c = src[k]
                    if c in ('"', "'"):
                        q = c
                        k += 1
                        while k < n:
                            if src[k] == '\\':
                                k += 2
                                continue
                            if src[k] == q:
                                k += 1
                                break
                            k += 1
                        continue
                    if c == '(':
                        depth += 1
                    elif c == ')':
                        depth -= 1
                        if depth == 0:
                            results.append((i, k))
                            break
                    k += 1
                i = k + 1
                continue
        i += 1
    return results


def process(path):
    with io.open(path, 'r', encoding='utf-8', newline='') as f:
        data = f.read()
    src = data.replace('\r\n', '\n')

    segs = data.split('\n')
    endings = ['\r\n' if s.endswith('\r') else '\n' for s in segs[:-1]]
    main_ending = '\r\n' if endings.count('\r\n') >= (len(endings) - endings.count('\r\n')) else '\n'

    src_lines = src.split('\n')
    n_src = len(src_lines)

    insert_before = {}   # line_index -> [new line contents]

    blocks = scan_blocks(src)
    inserted = 0
    for (start, end) in blocks:
        block = src[start:end + 1]
        if 'appTextFieldColors' in block:
            continue
        if 'focusedBorderColor = Color.Transparent' in block or \
           'unfocusedBorderColor = Color.Transparent' in block or \
           'focusedBorderColor = androidx.compose.ui.graphics.Color.Transparent' in block or \
           'unfocusedBorderColor = androidx.compose.ui.graphics.Color.Transparent' in block:
            continue
        line_start = src.rfind('\n', 0, start) + 1
        indent = src[line_start:start]
        indent = indent[:len(indent) - len(indent.lstrip())]
        li = src[:end].count('\n')            # close-paren 所在行号
        insert_before.setdefault(li, []).append("%sshape = AppTextFieldShape," % indent)
        insert_before.setdefault(li, []).append("%scolors = appTextFieldColors()," % indent)
        inserted += 1

    has_wild = any('import com.shangmentiyu.sportscoach.ui.theme.*' in l for l in src_lines)
    if not has_wild and not any('appTextFieldColors' in l and l.startswith('import ') for l in src_lines):
        last_import_li = -1
        for li in range(n_src):
            if src_lines[li].startswith('import '):
                last_import_li = li
        if last_import_li != -1:
            insert_after_imports = NEED_IMPORTS
        else:
            insert_after_imports = []
    else:
        insert_after_imports = []

    out = []
    for li in range(n_src):
        # 在 close-paren 行之前插入
        if li in insert_before:
            for new_line in insert_before[li]:
                out.append(new_line)
                out.append(main_ending)
        out.append(src_lines[li])
        ending = endings[li] if li < len(endings) else main_ending
        out.append(ending)
        # import 插在最后一个 import 行之后
        if li == last_import_li and insert_after_imports:
            for imp in insert_after_imports:
                out.append(imp)
                out.append(main_ending)

    new_text = ''.join(out)
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(new_text)
    return inserted


for rel in FILES:
    p = os.path.join(BASE, rel)
    ins = process(p)
    print("%-40s insert=%d" % (rel, ins))
