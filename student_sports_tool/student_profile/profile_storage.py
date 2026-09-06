# -*- coding: utf-8 -*-
"""数据层：学员档案 Excel 读写。

存储文件：档案目录下的「学员档案.xlsx」
工作表：学员信息
列结构：姓名 | 年龄 | 身高(cm) | 体重(kg) | BMI | 体型 | 年级 | 备注
        + 扩展列（性别 | 学校 | 电话 | 父身高 | 母身高 | 睡眠 | 营养评分 | 周运动）

设计约定：
- 学员姓名为主键，重名视为同一学员（更新而非新增）
- BMI 与体型由应用层计算后写入，避免读取时重复计算
- 与「课时记录.xlsx」通过学员姓名关联
- 软删除：通过隐藏 _meta 工作表的 is_active 字段标记停用状态，
  删除学员不再物理删除行，保留历史数据完整性（对齐 Android 端设计）
- 扩展列对齐 Android 端 Student 实体（性别/学校/电话/遗传与生活习惯字段），
  旧 8 列文件首次写入时自动追加表头，读取按表头名匹配、向后兼容
"""
import os
import json
import sys
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Side, Font, PatternFill

# 引入统一文件锁（位于父目录）
_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)
from file_lock import file_lock, with_retry, atomic_save_workbook

PROFILE_FILE = '学员档案.xlsx'
PROFILE_SHEET = '学员信息'
META_SHEET = '_meta'  # 隐藏工作表，存储 JSON 元数据（含 is_active 等状态字段）

PROFILE_HEADERS = ['姓名', '年龄', '身高(cm)', '体重(kg)', 'BMI', '体型', '年级', '备注']

# 扩展列（对齐 Android 端 Student 实体，v17 遗传与生活习惯字段 + 联系方式）
# 追加在原 8 列之后，不改动既有列顺序；旧文件首次写入时自动迁移补齐表头
EXTRA_HEADERS = ['性别', '学校', '电话', '父身高(cm)', '母身高(cm)',
                 '睡眠(h/天)', '营养评分(1-5)', '周运动(min/周)']
ALL_HEADERS = PROFILE_HEADERS + EXTRA_HEADERS

# 体型历史表（对齐 Android 端 BodyMetricHistory：每次测量追加一条）
BODY_SHEET = '体型历史'
BODY_HEADERS = ['姓名', '日期', '身高(cm)', '体重(kg)', 'BMI', '备注']

THIN = Side(style='thin', color='888888')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
LEFT = Alignment(horizontal='left', vertical='center', wrap_text=True)
HEADER_FILL = PatternFill(start_color='1F4E78', end_color='1F4E78', fill_type='solid')
HEADER_FONT = Font(bold=True, color='FFFFFF', name='微软雅黑')

# 年级选项（与移动端 13 级体系一致，新增学龄前选项）
GRADE_OPTIONS = [
    '学龄前',
    '小学一年级', '小学二年级', '小学三年级', '小学四年级', '小学五年级', '小学六年级',
    '初中一年级', '初中二年级', '初中三年级',
    '高中一年级', '高中二年级', '高中三年级',
    '中考', '高考', '其他',
]


def grade_short_label(grade: str) -> str:
    """将完整年级名转为短显示名（用于表格紧凑展示）。

    小学一年级 → 一年级；初中一年级 → 初一；高中一年级 → 高一；
    学龄前 → 空串（不显示）；其他原样返回。
    """
    if not grade or grade == '学龄前':
        return ''
    mapping = {
        '小学一年级': '一年级', '小学二年级': '二年级', '小学三年级': '三年级',
        '小学四年级': '四年级', '小学五年级': '五年级', '小学六年级': '六年级',
        '初中一年级': '初一', '初中二年级': '初二', '初中三年级': '初三',
        '高中一年级': '高一', '高中二年级': '高二', '高中三年级': '高三',
    }
    return mapping.get(grade, grade)


def _profile_file_path(dir_path: str) -> str:
    """返回学员档案文件的完整路径。"""
    return os.path.join(dir_path, PROFILE_FILE)


def ensure_file(dir_path: str) -> str:
    """确保学员档案文件存在，不存在则创建带表头的空文件。返回文件路径。"""
    fpath = _profile_file_path(dir_path)
    if os.path.exists(fpath):
        return fpath
    os.makedirs(dir_path, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = PROFILE_SHEET
    for i, h in enumerate(ALL_HEADERS, 1):
        c = ws.cell(row=1, column=i, value=h)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = CENTER
        c.border = BORDER
    # 列宽
    widths = [12, 8, 10, 10, 8, 12, 14, 24, 8, 16, 14, 11, 11, 11, 12, 13]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.freeze_panes = 'A2'
    # 初始化空 _meta 工作表
    _ensure_meta_sheet(wb)
    atomic_save_workbook(wb, fpath)
    return fpath


def _ensure_extra_columns(ws) -> None:
    """旧 8 列文件迁移：按 ALL_HEADERS 补齐缺失的扩展列表头（不改动既有列顺序）。"""
    existing = {str(ws.cell(row=1, column=c).value or '').strip()
                for c in range(1, ws.max_column + 1)}
    col = ws.max_column
    for h in ALL_HEADERS:
        if h in existing:
            continue
        col += 1
        c = ws.cell(row=1, column=col, value=h)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = CENTER
        c.border = BORDER


def _header_map(ws) -> dict:
    """表头名 → 列号映射（读取/写入均按表头定位，兼容旧 8 列文件）。"""
    return {str(ws.cell(row=1, column=c).value or '').strip(): c
            for c in range(1, ws.max_column + 1)}


def _num(value, default=0.0):
    """宽松数值转换：None/空串/非法值返回 default。"""
    try:
        v = float(value)
        return v
    except (TypeError, ValueError):
        return default


def _ensure_meta_sheet(wb) -> None:
    """确保 workbook 中存在 _meta 隐藏工作表，存储学员状态 JSON。

    元数据结构：{"students": {"张三": {"is_active": true}, ...}}
    """
    if META_SHEET not in wb.sheetnames:
        ws = wb.create_sheet(title=META_SHEET)
        ws.cell(row=1, column=1, value=json.dumps({'students': {}}, ensure_ascii=False))
        ws.sheet_state = 'hidden'


def _read_meta(wb) -> dict:
    """读取 _meta 工作表，返回元数据 dict。无 _meta 时返回空结构。"""
    if META_SHEET not in wb.sheetnames:
        return {'students': {}}
    ws = wb[META_SHEET]
    raw = ws.cell(row=1, column=1).value or '{}'
    try:
        meta = json.loads(raw)
        meta.setdefault('students', {})
        return meta
    except (json.JSONDecodeError, TypeError):
        return {'students': {}}


def _write_meta(wb, meta: dict) -> None:
    """写入元数据到 _meta 工作表（先删旧表再建新表，避免重复）。"""
    if META_SHEET in wb.sheetnames:
        del wb[META_SHEET]
    ws = wb.create_sheet(title=META_SHEET)
    ws.cell(row=1, column=1, value=json.dumps(meta, ensure_ascii=False))
    ws.sheet_state = 'hidden'


def read_all(dir_path: str) -> list:
    """读取所有学员档案。返回字典列表，每条含 headers 对应字段。

    身高/体重为空时返回 None（便于 UI 区分"未录入"与"0"）。
    每条记录额外含 is_active 字段（True/False，默认 True）。

    并发安全：使用 portalocker 文件锁防止读到正在写入的中间状态。
    """
    fpath = ensure_file(dir_path)

    def _do_read():
        with file_lock(fpath, mode='r', timeout=5.0):
            wb = load_workbook(fpath)
            ws = wb[PROFILE_SHEET]
            meta = _read_meta(wb)
            students_meta = meta.get('students', {})
            hmap = _header_map(ws)
            result = []
            for r in range(2, ws.max_row + 1):
                name = ws.cell(row=r, column=1).value
                if not name or not str(name).strip():
                    continue
                name = str(name).strip()

                def _cell(col_name):
                    col = hmap.get(col_name)
                    return ws.cell(row=r, column=col).value if col else None

                height_val = _cell('身高(cm)')
                weight_val = _cell('体重(kg)')
                # 从 _meta 读取 is_active 状态，默认 True
                stu_meta = students_meta.get(name, {})
                is_active = stu_meta.get('is_active', True)
                # 扩展列（旧文件缺失表头时取默认值，向后兼容）
                gender = str(_cell('性别') or '').strip()
                father = _num(_cell('父身高(cm)'))
                mother = _num(_cell('母身高(cm)'))
                result.append({
                    'name': name,
                    'age': _cell('年龄') or 0,
                    'height': float(height_val) if height_val not in (None, '', 0) else None,
                    'weight': float(weight_val) if weight_val not in (None, '', 0) else None,
                    'bmi': _cell('BMI') or 0,
                    'body_type': _cell('体型') or '',
                    'grade': _cell('年级') or '',
                    'note': _cell('备注') or '',
                    'gender': gender or '男',
                    'school': str(_cell('学校') or '').strip(),
                    'phone': str(_cell('电话') or '').strip(),
                    'father_height': father if father > 0 else None,
                    'mother_height': mother if mother > 0 else None,
                    'sleep_hours': _num(_cell('睡眠(h/天)')),
                    'nutrition_score': int(_num(_cell('营养评分(1-5)'))),
                    'sports_mins': int(_num(_cell('周运动(min/周)'))),
                    'updated_at': stu_meta.get('updated_at'),
                    'row': r,
                    'is_active': is_active,
                })
            return result

    return with_retry(_do_read, max_retries=3, retry_interval=1.0)


def remove_profile(dir_path: str, name: str) -> bool:
    """硬删除：从花名册移除学员行与 _meta 条目（不动 per-student xlsx，由调用方隔离）。

    返回 True 表示已删除；False 表示未找到。
    """
    fpath = ensure_file(dir_path)

    def _do_remove():
        with file_lock(fpath, timeout=5.0):
            wb = load_workbook(fpath)
            ws = wb[PROFILE_SHEET]
            for r in range(2, ws.max_row + 1):
                if str(ws.cell(row=r, column=1).value or '').strip() == name:
                    ws.delete_rows(r)
                    meta = _read_meta(wb)
                    meta.get('students', {}).pop(name, None)
                    _write_meta(wb, meta)
                    atomic_save_workbook(wb, fpath)
                    return True
            return False

    return with_retry(_do_remove, max_retries=3, retry_interval=1.0)


def set_active_status(dir_path: str, name: str, is_active: bool) -> bool:
    """设置学员的停用/启用状态（软删除/恢复）。

    参数:
        name: 学员姓名
        is_active: True 启用 / False 停用
    返回:
        True 表示状态已更新；False 表示未找到该学员

    并发安全：使用 portalocker 排他锁防止并发写入导致文件损坏。
    """
    fpath = ensure_file(dir_path)

    def _do_set():
        with file_lock(fpath, timeout=5.0):
            wb = load_workbook(fpath)
            ws = wb[PROFILE_SHEET]
            # 校验学员存在
            found = False
            for r in range(2, ws.max_row + 1):
                if str(ws.cell(row=r, column=1).value or '').strip() == name:
                    found = True
                    break
            if not found:
                return False
            meta = _read_meta(wb)
            meta.setdefault('students', {})
            stu_meta = meta['students'].setdefault(name, {})
            stu_meta['is_active'] = bool(is_active)
            # 停用视为数据变更刷新 LWW 时间戳；启用不刷新（save_student 的
            # upsert 刚写入来源端时间戳，此处覆盖会丢失 LWW 判新依据）
            if not is_active:
                stu_meta['updated_at'] = _now_ms()
            _write_meta(wb, meta)
            atomic_save_workbook(wb, fpath)
            return True

    return with_retry(_do_set, max_retries=3, retry_interval=1.0)


def _now_str() -> str:
    """返回当前时间的字符串表示（用于状态变更时间戳）。"""
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _now_ms() -> int:
    """当前时间毫秒时间戳（v23 双端同步 LWW 用，写入 _meta.students[name].updated_at）。"""
    import time
    return int(time.time() * 1000)


def upsert(dir_path: str, profile: dict) -> bool:
    """新增或更新学员档案（按姓名匹配）。

    参数:
        profile: 含 name, age, height, weight, bmi, body_type, grade, note

    并发安全：使用 portalocker 排他锁防止并发写入导致文件损坏。
    """
    fpath = ensure_file(dir_path)

    def _do_upsert():
        with file_lock(fpath, timeout=5.0):
            wb = load_workbook(fpath)
            _ensure_meta_sheet(wb)  # 兼容旧文件：补齐 _meta 工作表
            ws = wb[PROFILE_SHEET]
            _ensure_extra_columns(ws)  # 兼容旧 8 列文件：补齐扩展列表头
            hmap = _header_map(ws)
            # 查找已有行
            target_row = None
            is_reactivate = False
            for r in range(2, ws.max_row + 1):
                if str(ws.cell(row=r, column=1).value or '').strip() == profile['name']:
                    target_row = r
                    break
            if target_row is None:
                target_row = ws.max_row + 1 if ws.cell(row=ws.max_row, column=1).value else ws.max_row
                if ws.cell(row=target_row, column=1).value:
                    target_row += 1
                is_reactivate = True  # 新建学员默认为启用状态
            # 写入（身高/体重为 None 时写空单元格，保留"未录入"语义）
            height_val = profile.get('height')
            weight_val = profile.get('weight')
            values = {
                '姓名': profile['name'],
                '年龄': profile.get('age', 0),
                '身高(cm)': height_val if height_val not in (None, '', 0) else None,
                '体重(kg)': weight_val if weight_val not in (None, '', 0) else None,
                'BMI': profile.get('bmi', 0) if profile.get('bmi') else None,
                '体型': profile.get('body_type', ''),
                '年级': profile.get('grade', ''),
                '备注': profile.get('note', ''),
                '性别': profile.get('gender', '男') or '男',
                '学校': profile.get('school', ''),
                '电话': profile.get('phone', ''),
                '父身高(cm)': profile.get('father_height') or None,
                '母身高(cm)': profile.get('mother_height') or None,
                '睡眠(h/天)': profile.get('sleep_hours') or None,
                '营养评分(1-5)': profile.get('nutrition_score') or None,
                '周运动(min/周)': profile.get('sports_mins') or None,
            }
            for header, v in values.items():
                col = hmap.get(header)
                if not col:
                    continue
                cell = ws.cell(row=target_row, column=col, value=v)
                cell.border = BORDER
                cell.alignment = LEFT if header in ('备注', '学校') else CENTER
            # 每次 upsert 刷新 _meta：启用状态 + 毫秒级时间戳（v23 双端同步 LWW 判新依据）
            meta = _read_meta(wb)
            meta.setdefault('students', {})
            stu = meta['students'].setdefault(profile['name'], {})
            if is_reactivate:
                stu['is_active'] = True
            # LWW 保留来源端时间戳（如手机推送合并时透传），否则取当前时间
            stu['updated_at'] = int(profile['updated_at_ms']) \
                if profile.get('updated_at_ms') else _now_ms()
            _write_meta(wb, meta)
            atomic_save_workbook(wb, fpath)
            return True

    return with_retry(_do_upsert, max_retries=3, retry_interval=1.0)


def delete(dir_path: str, name: str) -> bool:
    """按姓名停用学员档案（软删除）。

    保留物理行，仅在 _meta 中将 is_active 置为 False。
    课时记录与历史测评数据完整保留，避免数据断层。
    若需恢复，调用 set_active_status(dir_path, name, True)。
    """
    return set_active_status(dir_path, name, False)


def physical_delete(dir_path: str, name: str) -> bool:
    """物理删除学员档案行（保留以兼容老接口/批量清理场景）。

    警告：此操作不可逆，会丢失学员基本信息。
    课时记录与测评历史文件不受影响（仍按姓名关联）。

    并发安全：使用 portalocker 排他锁。
    """
    fpath = ensure_file(dir_path)

    def _do_phys_del():
        with file_lock(fpath, timeout=5.0):
            wb = load_workbook(fpath)
            ws = wb[PROFILE_SHEET]
            for r in range(2, ws.max_row + 1):
                if str(ws.cell(row=r, column=1).value or '').strip() == name:
                    ws.delete_rows(r)
                    # 同步清理 _meta 中的状态记录
                    meta = _read_meta(wb)
                    meta.get('students', {}).pop(name, None)
                    _write_meta(wb, meta)
                    atomic_save_workbook(wb, fpath)
                    return True
            return False

    return with_retry(_do_phys_del, max_retries=3, retry_interval=1.0)


# ==================== 体型历史（对齐 Android BodyMetricHistory） ====================

def _ensure_body_sheet(wb) -> None:
    """确保体型历史工作表存在（幂等）。"""
    if BODY_SHEET in wb.sheetnames:
        return
    ws = wb.create_sheet(title=BODY_SHEET)
    for i, h in enumerate(BODY_HEADERS, 1):
        c = ws.cell(row=1, column=i, value=h)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = CENTER
        c.border = BORDER
    ws.sheet_state = 'hidden'  # 辅助表，不干扰用户浏览主表


def append_body_metric(dir_path: str, name: str, date_str: str,
                       height: float, weight: float, note: str = '') -> bool:
    """追加一条体型测量记录（同一天同学员仅保留最新一条）。

    BMI 由本层计算写入。身高/体重非法（≤0）时静默跳过。
    """
    h = float(height) if height not in (None, '', 0) else 0.0
    w = float(weight) if weight not in (None, '', 0) else 0.0
    if h <= 0 or w <= 0 or not name:
        return False
    bmi = round(w / ((h / 100.0) ** 2), 1)
    fpath = ensure_file(dir_path)

    def _do_append():
        with file_lock(fpath, timeout=5.0):
            wb = load_workbook(fpath)
            _ensure_body_sheet(wb)
            ws = wb[BODY_SHEET]
            # 同名同日期 → 覆盖（当天重复测量取最新值）；否则追加到表尾
            target_row = None
            for r in range(2, ws.max_row + 1):
                if str(ws.cell(row=r, column=1).value or '').strip() != name:
                    continue
                if str(ws.cell(row=r, column=2).value or '').strip() == date_str:
                    target_row = r
                    break
            row = target_row or (ws.max_row + 1)
            values = [name, date_str, h, w, bmi, note or '']
            for i, v in enumerate(values, 1):
                cell = ws.cell(row=row, column=i, value=v)
                cell.border = BORDER
                cell.alignment = CENTER if i < 6 else LEFT
            atomic_save_workbook(wb, fpath)
            return True

    return with_retry(_do_append, max_retries=3, retry_interval=1.0)


def read_body_metrics(dir_path: str, name: str) -> list:
    """读取指定学员的体型历史（按日期升序）。

    返回字典列表：{date, height, weight, bmi, note}
    """
    fpath = _profile_file_path(dir_path)
    if not os.path.exists(fpath):
        return []
    try:
        with file_lock(fpath, mode='r', timeout=5.0):
            wb = load_workbook(fpath)
            if BODY_SHEET not in wb.sheetnames:
                return []
            ws = wb[BODY_SHEET]
            result = []
            for r in range(2, ws.max_row + 1):
                if str(ws.cell(row=r, column=1).value or '').strip() != name:
                    continue
                result.append({
                    'date': str(ws.cell(row=r, column=2).value or '').strip(),
                    'height': _num(ws.cell(row=r, column=3).value),
                    'weight': _num(ws.cell(row=r, column=4).value),
                    'bmi': _num(ws.cell(row=r, column=5).value),
                    'note': str(ws.cell(row=r, column=6).value or '').strip(),
                })
            result.sort(key=lambda x: x['date'])
            return result
    except Exception:
        return []


# ==================== 学员扩展元数据（_meta.students[name] 泛化读写） ====================

def get_student_extra(dir_path: str, name: str, key: str, default=None):
    """读取学员扩展元数据（如膳食方案绑定 diet_plan）。"""
    fpath = _profile_file_path(dir_path)
    if not os.path.exists(fpath):
        return default
    try:
        with file_lock(fpath, mode='r', timeout=5.0):
            wb = load_workbook(fpath)
            stu_meta = _read_meta(wb).get('students', {}).get(name, {})
            return stu_meta.get(key, default)
    except Exception:
        return default


def set_student_extra(dir_path: str, name: str, key: str, value) -> bool:
    """写入学员扩展元数据（如膳食方案绑定 diet_plan）。"""
    fpath = _profile_file_path(dir_path)
    if not os.path.exists(fpath):
        return False

    def _do_set():
        with file_lock(fpath, timeout=5.0):
            wb = load_workbook(fpath)
            meta = _read_meta(wb)
            stu = meta.setdefault('students', {}).setdefault(name, {})
            stu[key] = value
            stu['updated_at'] = _now_str()
            _write_meta(wb, meta)
            atomic_save_workbook(wb, fpath)
            return True

    return with_retry(_do_set, max_retries=3, retry_interval=1.0)
