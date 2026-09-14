# -*- coding: utf-8 -*-
"""给指定 GitHub 仓生成 deploy key（若不存在）→ 注册 → SSH 推送 → 校验远端 sha。

用法：python _gh_push.py <owner/repo> <workdir> <reponame>
原因：本机 HTTPS 通道走 127.0.0.1:12516 代理，对 github.com 的 CONNECT 稳定 502；
     SSH(22) 直连可用，故改用 deploy key + ssh 通道。
"""
import os
import subprocess
import sys

repo = sys.argv[1]
workdir = sys.argv[2]
name = sys.argv[3]
key = os.path.expanduser(rf"~\.ssh\{name}")

# 1) 生成无 passphrase key（不存在时）
if not os.path.exists(key):
    g = subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", key, "-N", "", "-C", f"wb-deploy-{name}"],
        capture_output=True, text=True,
    )
    print("gen rc:", g.returncode)
pub = open(key + ".pub", encoding="utf-8").read().strip()

# 2) 注册 deploy key 到该仓库（写权限，仅此仓库）
r = subprocess.run(
    ["gh", "api", "-X", "POST", f"repos/{repo}/keys",
     "-f", f"title=wb-deploy-{name}", "-f", f"key={pub}", "-F", "read_only=false"],
    capture_output=True, text=True,
)
print("register rc:", r.returncode)
print("register out:", (r.stdout or "").strip()[:160])
print("register err:", (r.stderr or "").strip()[:200])

# 3) SSH 推送
os.chdir(workdir)
ssh_cmd = "ssh -i " + key.replace("\\", "/") + " -o StrictHostKeyChecking=no -o IdentitiesOnly=yes"
env = dict(os.environ, GIT_SSH_COMMAND=ssh_cmd)
p = subprocess.run(["git", "push", f"git@github.com:{repo}.git", "main"],
                   capture_output=True, text=True, env=env)
print("push rc:", p.returncode)
print("push out:", (p.stdout or "").strip()[:200])
print("push err:", (p.stderr or "").strip()[:300])

# 4) 校验远端 sha 与本地一致
q = subprocess.run(["gh", "api", f"repos/{repo}/git/refs/heads/main", "--jq", ".object.sha"],
                   capture_output=True, text=True)
h = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
remote = (q.stdout or "").strip()
local = (h.stdout or "").strip()
print("remote:", remote)
print("local :", local)
print("MATCH :", remote == local)
