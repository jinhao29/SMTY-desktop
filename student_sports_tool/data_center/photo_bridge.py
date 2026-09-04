# -*- coding: utf-8 -*-
"""数据层：Android 端签到照片桥接器。

职责：
- 定义 PhotoBridge 抽象接口（解密/拷贝/列表）
- 提供 DefaultPhotoBridge 默认实现：原样拷贝加密照片，保持目录结构
- 在备份恢复时被 backup_coordinator 调用，将 Android 端加密照片迁移到桌面端

设计说明：
- Android 端使用 PhotoCrypto（基于固定种子 + 用户私钥派生密钥）加密签到照片
- 桌面端无对应解密能力时，原样拷贝到 photos/ 目录，保留文件名以便后续解密
- 接口预留 decrypt 方法，后续可由子类实现真实解密逻辑
"""
import os
import shutil
import zipfile
from abc import ABC, abstractmethod
from typing import Callable, List, Optional

# 照片在桌面端档案目录下的子目录
PHOTO_SUBDIR = 'photos'


class PhotoBridge(ABC):
    """Android 端签到照片桥接抽象接口。"""

    @abstractmethod
    def restore_from_zip(self, zip_path: str, target_dir: str,
                         progress_cb: Optional[Callable[[str], None]] = None) -> int:
        """从备份 zip 中提取照片到目标目录。

        参数:
            zip_path: 备份 zip 路径
            target_dir: 桌面端档案目录（照片将拷贝到 {target_dir}/photos/ 下）
            progress_cb: 进度回调 (message: str) -> None

        返回: 拷贝成功的照片数
        """
        raise NotImplementedError

    @abstractmethod
    def decrypt(self, encrypted_path: str, output_path: str) -> bool:
        """解密单张照片（默认实现不解密，直接拷贝）。

        参数:
            encrypted_path: 加密照片路径
            output_path: 解密后输出路径

        返回: True 成功，False 失败
        """
        raise NotImplementedError

    @abstractmethod
    def list_photos(self, target_dir: str, student_name: Optional[str] = None) -> List[str]:
        """列出已拷贝的照片路径。student_name 指定时仅返回该学员的照片。"""
        raise NotImplementedError


class DefaultPhotoBridge(PhotoBridge):
    """默认照片桥接实现：原样拷贝加密照片，保持目录结构。

    不进行解密，仅将加密照片按 {target_dir}/photos/{相对路径} 拷贝。
    后续如需解密，可继承此类并重写 decrypt 方法。
    """

    # 支持的照片扩展名（含加密后缀）
    PHOTO_EXTS = ('.jpg', '.jpeg', '.png', '.jpg.enc', '.png.enc', '.dat')

    def restore_from_zip(self, zip_path: str, target_dir: str,
                         progress_cb: Optional[Callable[[str], None]] = None) -> int:
        if not os.path.exists(zip_path):
            return 0
        photo_dir = os.path.join(target_dir, PHOTO_SUBDIR)
        os.makedirs(photo_dir, exist_ok=True)
        count = 0
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                # 跨平台路径归一化（zip 内部使用 /，Windows 上需 normpath）
                norm_name = os.path.normpath(name)
                base = os.path.basename(norm_name)
                if not base:
                    continue
                if not self._is_photo(base):
                    continue
                # 保持 zip 内的相对目录结构
                rel_dir = os.path.dirname(norm_name)
                # 去掉前导 photos/ 前缀避免重复嵌套
                if rel_dir.lower().startswith('photos') :
                    rel_dir = rel_dir[len('photos'):].lstrip(os.sep)
                out_dir = os.path.join(photo_dir, rel_dir) if rel_dir else photo_dir
                os.makedirs(out_dir, exist_ok=True)
                out_path = os.path.join(out_dir, base)
                try:
                    with zf.open(name) as src, open(out_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    count += 1
                    if progress_cb and count % 20 == 0:
                        progress_cb(f'已迁移 {count} 张签到照片...')
                except OSError:
                    continue
        if progress_cb:
            progress_cb(f'签到照片迁移完成：共 {count} 张')
        return count

    def decrypt(self, encrypted_path: str, output_path: str) -> bool:
        """默认实现：不解密，直接拷贝。

        后续可继承此类并实现真实解密逻辑（参考 Android 端 PhotoCrypto）。
        """
        if not os.path.exists(encrypted_path):
            return False
        try:
            shutil.copy2(encrypted_path, output_path)
            return True
        except OSError:
            return False

    def list_photos(self, target_dir: str, student_name: Optional[str] = None) -> List[str]:
        photo_dir = os.path.join(target_dir, PHOTO_SUBDIR)
        if not os.path.isdir(photo_dir):
            return []
        result = []
        for root, _dirs, files in os.walk(photo_dir):
            for f in files:
                if not self._is_photo(f):
                    continue
                full = os.path.join(root, f)
                if student_name:
                    # 按学员名筛选（路径中包含学员名）
                    if student_name in full:
                        result.append(full)
                else:
                    result.append(full)
        return sorted(result)

    @classmethod
    def _is_photo(cls, filename: str) -> bool:
        """判断文件是否为照片（按扩展名）。"""
        lower = filename.lower()
        return any(lower.endswith(ext) for ext in cls.PHOTO_EXTS)


# 单例：默认桥接实例
_default_bridge: Optional[PhotoBridge] = None


def get_default_bridge() -> PhotoBridge:
    """获取默认 PhotoBridge 实例（单例）。"""
    global _default_bridge
    if _default_bridge is None:
        _default_bridge = DefaultPhotoBridge()
    return _default_bridge


def set_default_bridge(bridge: PhotoBridge) -> None:
    """注入自定义 PhotoBridge（用于测试或后续替换为解密实现）。"""
    global _default_bridge
    _default_bridge = bridge
