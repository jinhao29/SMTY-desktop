# -*- coding: utf-8 -*-
"""发版打包脚本：PyInstaller → zip → sha256 侧车 → 打印 gh release 命令。

用法：
    python make_release.py            # 全流程：打包 + 产出 release 资产
    python make_release.py --skip-build  # 跳过 PyInstaller，仅对现有 dist/app 重打 zip

产物（release/ 目录）：
    上门体育教学管理工具.zip            # zip 根即 exe（updater._locate_app_root 兼容嵌套）
    上门体育教学管理工具.zip.sha256     # "<hash>  <文件名>" 标准格式侧车

发版（需网络与 gh 登录，push 动作由维护者手动执行）：
    git add VERSION && git commit -m "release v<X.Y.Z>"
    git tag v<X.Y.Z> && git push origin main --tags   # 主仓无远端发布流程，推 tag 仅作归档
    gh release create v<X.Y.Z> release/上门体育教学管理工具.zip release/上门体育教学管理工具.zip.sha256 \
        --title "v<X.Y.Z>" --notes "sha256: <hash>"
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = '上门体育教学管理工具.spec'
RELEASE_DIR = os.path.join(HERE, 'release')


def zip_name_for(version: str) -> str:
    """Release 资产名用 ASCII（带版本号）。

    GitHub 对中文 asset 名的 gh 上传/PATCH 处理不稳定（实测中文名被清洗成
    default.zip）。updater 精确匹配失败后会模糊匹配 *.zip，侧车名按
    <asset>.sha256 动态拼接，故 ASCII 命名对更新链路完全透明。
    """
    return f'shangmen-tool-{version}.zip'


def fail(msg):
    print(f'[make_release] FAIL: {msg}')
    sys.exit(1)


def read_version():
    path = os.path.join(HERE, 'VERSION')
    if not os.path.exists(path):
        fail('VERSION 文件不存在（版本真源必须先建）')
    v = open(path, encoding='utf-8').read().strip()
    if not re.fullmatch(r'v\d+\.\d+\.\d+', v):
        fail(f'VERSION 内容 "{v}" 不是 vMAJOR.MINOR.PATCH 格式')
    return v


def run_build():
    print('[make_release] PyInstaller 打包中（3-8 分钟）...')
    r = subprocess.run([sys.executable, '-m', 'PyInstaller', SPEC, '--noconfirm', '--clean'],
                       cwd=HERE)
    if r.returncode != 0:
        fail('PyInstaller 打包失败')
    if not os.path.exists(os.path.join(DIST_APP, '上门体育教学管理工具.exe')):
        fail(f'{DIST_APP} 中未见主 exe')


def make_zip(zip_name):
    os.makedirs(RELEASE_DIR, exist_ok=True)
    zip_path = os.path.join(RELEASE_DIR, zip_name)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    import zipfile
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, _dirs, files in os.walk(DIST_APP):
            for f in files:
                full = os.path.join(root, f)
                arc = os.path.relpath(full, DIST_APP)
                zf.write(full, arc)
    return zip_path


def make_sha256(zip_path):
    h = hashlib.sha256()
    with open(zip_path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    digest = h.hexdigest()
    sidecar = zip_path + '.sha256'
    with open(sidecar, 'w', encoding='utf-8', newline='\n') as f:
        f.write(f'{digest}  {os.path.basename(zip_path)}\n')
    return digest


def main():
    skip = '--skip-build' in sys.argv
    version = read_version()
    print(f'[make_release] 版本: {version}')
    if not skip:
        run_build()
    elif not os.path.isdir(DIST_APP):
        fail('dist/app 不存在，无法 --skip-build')
    # PyInstaller onedir 的 datas 落点不稳定（应进 _internal 但实测未打入），
    # 不赌打包器行为：直接把 VERSION 复制到 exe 旁，zip 后即随包分发
    version_src = os.path.join(HERE, 'VERSION')
    if os.path.exists(version_src):
        shutil.copy2(version_src, os.path.join(DIST_APP, 'VERSION'))
    # 确认包内带上了 VERSION（运行时版本号来源）
    if not os.path.exists(os.path.join(DIST_APP, 'VERSION')):
        fail('dist/app/VERSION 复制失败，zip 将缺少版本真源')
    zip_path = make_zip(zip_name_for(version))
    digest = make_sha256(zip_path)
    size_mb = os.path.getsize(zip_path) / 1048576
    print(f'[make_release] DONE {version}')
    print(f'  zip:     {zip_path} ({size_mb:.1f} MB)')
    print(f'  sha256:  {digest}')
    print()
    print(f'发布命令（确认后手动执行）:')
    print(f'  gh release create {version} "{zip_path}" "{zip_path}.sha256" '
          f'--repo jinhao29/SMTY-desktop --title "{version}" --notes "sha256: {digest}"')


if __name__ == '__main__':
    main()
