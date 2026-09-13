# -*- coding: utf-8 -*-
"""同步通道 TLS 测试（docs/sync_tls_design.md §6 PC 项）。

覆盖：
- 自签证书生成 / 复用（ensure_cert 幂等）
- 指纹计算稳定（SHA-256 → Base64，与 Android 端 SyncTlsTrust 算法对齐的锚定值）
- HTTPS server 启停 + urllib 带 ssl 上下文访问 /health（跨线程握手真链路）
- 明文 HTTP 客户端连 TLS 端口 → 握手失败且服务不崩（手机旧版探测回退前提）
"""
import base64
import hashlib
import os
import ssl
import sys
import tempfile
import threading
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_center'))

from data_center import sync_server
from data_center.tls_cert import ensure_cert, cert_fingerprint, build_ssl_context


@pytest.fixture()
def archive_dir(tmp_path):
    d = tmp_path / 'archive'
    d.mkdir()
    return str(d)


def _start_server(tls_context, tmp_dir):
    sync_server.SyncRequestHandler.status_cb = None
    server = sync_server.create_server(
        host='127.0.0.1', port=0, save_dir=str(tmp_dir / 'backups'),
        token='t', archive_dir='', log_cb=None, tls_context=tls_context)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, server.server_address[1]


def test_ensure_cert_generate_and_reuse(archive_dir):
    cert_path, key_path = ensure_cert(archive_dir)
    assert os.path.exists(cert_path) and os.path.exists(key_path)
    mtime = os.path.getmtime(cert_path)
    # 复用：第二次调用不重新生成
    cert2, key2 = ensure_cert(archive_dir)
    assert cert2 == cert_path and os.path.getmtime(cert2) == mtime


def test_fingerprint_matches_der_sha256(archive_dir):
    """指纹 = SHA-256(DER) 的 Base64 —— Android 端同算法锚定。"""
    cert_path, _ = ensure_cert(archive_dir)
    fp = cert_fingerprint(cert_path)
    with open(cert_path, 'rb') as f:
        der = ssl.PEM_cert_to_DER_cert(f.read().decode('ascii'))
    expected = base64.b64encode(hashlib.sha256(der).digest()).decode('ascii')
    assert fp == expected and len(base64.b64decode(fp)) == 32


def test_https_server_health_roundtrip(archive_dir, tmp_path):
    ensure_cert(archive_dir)
    ctx = build_ssl_context(archive_dir)
    server, port = _start_server(ctx, tmp_path)
    try:
        # 客户端关闭校验（等价于手机端 TOFU 场景：只验指纹不验链）
        cctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        cctx.check_hostname = False
        cctx.verify_mode = ssl.CERT_NONE
        cctx.minimum_version = ssl.TLSVersion.TLSv1_2
        url = 'https://127.0.0.1:%d/health' % port
        with urllib.request.urlopen(url, context=cctx, timeout=5) as resp:
            assert resp.status == 200 and resp.read() == b'OK'
    finally:
        server.shutdown()


def test_plaintext_client_fails_server_survives(archive_dir, tmp_path):
    """明文客户端打到 TLS 端口：握手失败，服务继续可用（§5 回退矩阵）。"""
    ensure_cert(archive_dir)
    ctx = build_ssl_context(archive_dir)
    server, port = _start_server(ctx, tmp_path)
    try:
        with pytest.raises(Exception):
            urllib.request.urlopen(
                'http://127.0.0.1:%d/health' % port, timeout=5).read()
        # TLS 客户端随后仍正常（服务未被明文探活搞挂）
        cctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        cctx.check_hostname = False
        cctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(
                'https://127.0.0.1:%d/health' % port, context=cctx,
                timeout=5) as resp:
            assert resp.status == 200
    finally:
        server.shutdown()
