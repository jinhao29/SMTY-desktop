# -*- coding: utf-8 -*-
"""数据层：同步通道 TLS 自签证书（设计见 docs/sync_tls_design.md）。

职责：
- ensure_cert(archive_dir)：不存在则生成自签证书（RSA 2048 / 10 年），
  存 <档案目录>/.sync/tls_cert.pem + tls_key.pem；存在则复用
- cert_fingerprint(cert_path)：SHA-256(DER) → Base64，供手机端 TOFU 比对
- build_ssl_context(archive_dir)：server 端 SSLContext（TLS 1.2+）

安全边界（与 Android 端 SyncTlsTrust.kt 成对，勿单端改动指纹算法）：
自签证书无可信 CA，手机端关闭 hostname 校验，以「首连固定指纹」替代——
指纹更换 = 服务端证书更换，需用户重新信任。

依赖：cryptography（生成证书）；指纹计算仅标准库。
"""
import base64
import datetime
import hashlib
import ipaddress
import logging
import os
import socket
import ssl

_logger = logging.getLogger(__name__)

CERT_REL_DIR = os.path.join('.sync')
CERT_FILE = 'tls_cert.pem'
KEY_FILE = 'tls_key.pem'

# 指纹展示前缀长度（面板人工核对用）
FINGERPRINT_DISPLAY_LEN = 16


def _cert_paths(archive_dir: str):
    d = os.path.join(archive_dir, CERT_REL_DIR)
    return (os.path.join(d, CERT_FILE), os.path.join(d, KEY_FILE))


def _local_ips():
    """收集本机 IPv4（含回环），失败容忍。"""
    ips = {'127.0.0.1'}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        # 连外网地址族探测出口 IP（UDP connect 不发包）
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            ips.add(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    return sorted(ips)


def ensure_cert(archive_dir: str):
    """确保证书存在，返回 (cert_path, key_path)；生成失败抛异常由调用方处理。"""
    cert_path, key_path = _cert_paths(archive_dir)
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path
    os.makedirs(os.path.dirname(cert_path), exist_ok=True)

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u'shangmentiyu-sync')])
    now = datetime.datetime.now(datetime.timezone.utc)
    san = [x509.IPAddress(ipaddress.ip_address(ip)) for ip in _local_ips()]
    try:
        san.append(x509.DNSName(socket.gethostname()))
    except (OSError, UnicodeDecodeError):
        pass
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)  # 自签：签发者=主体
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .sign(key, hashes.SHA256())
    )
    with open(key_path, 'wb') as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()))
    with open(cert_path, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    _logger.info('同步 TLS 证书已生成：%s', cert_path)
    return cert_path, key_path


def cert_fingerprint(cert_path: str) -> str:
    """证书 SHA-256 指纹（DER 摘 → Base64），与 Android 端 SyncTlsTrust 算法对齐。"""
    with open(cert_path, 'rb') as f:
        pem = f.read()
    # 标准库 ssl.PEM_cert_to_DER_cert：无第三方依赖
    der = ssl.PEM_cert_to_DER_cert(pem.decode('ascii'))
    return base64.b64encode(hashlib.sha256(der).digest()).decode('ascii')


def build_ssl_context(archive_dir: str) -> ssl.SSLContext:
    """构造 server 端 SSLContext（TLS 1.2+，仅服务端持证书）。"""
    cert_path, key_path = ensure_cert(archive_dir)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert_path, key_path)
    return ctx
