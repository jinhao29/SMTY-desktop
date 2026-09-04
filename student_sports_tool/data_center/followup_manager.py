# -*- coding: utf-8 -*-
"""管理层：续费跟进状态读写。

职责：
- 记录教练对学员的跟进状态（已联系 + 备注）
- 7天免打扰：标记后7天内不再出现在预警列表
- 状态存储为 JSON，位于档案目录下 _followup.json
"""
import os
import json
from datetime import datetime, timedelta

FOLLOWUP_FILE = '_followup.json'
MUTE_DAYS = 7  # 免打扰天数


def _followup_path(dir_path):
    """返回跟进状态文件的完整路径。"""
    return os.path.join(dir_path, FOLLOWUP_FILE)


def load_followup(dir_path):
    """读取跟进状态。返回 {学员名: {last_contact, note, expire}}。"""
    fpath = _followup_path(dir_path)
    if not os.path.exists(fpath):
        return {}
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_followup(dir_path, data):
    """保存跟进状态到 JSON。"""
    if not dir_path:
        return
    os.makedirs(dir_path, exist_ok=True)
    fpath = _followup_path(dir_path)
    try:
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def mark_contacted(dir_path, name, note=''):
    """标记学员为已联系，设置7天免打扰。

    参数:
        name: 学员名
        note: 跟进备注
    """
    data = load_followup(dir_path)
    today = datetime.now()
    expire = today + timedelta(days=MUTE_DAYS)
    data[name] = {
        'last_contact': today.strftime('%Y-%m-%d'),
        'note': note,
        'expire': expire.strftime('%Y-%m-%d'),
    }
    save_followup(dir_path, data)
    return data[name]


def clear_followup(dir_path, name):
    """清除学员的跟进标记（重新加入预警列表）。"""
    data = load_followup(dir_path)
    if name in data:
        del data[name]
        save_followup(dir_path, data)
        return True
    return False


def get_followup(dir_path, name):
    """获取指定学员的跟进状态。"""
    return load_followup(dir_path).get(name, {})
