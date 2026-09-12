# -*- coding: utf-8 -*-
"""协调层：体测档案业务逻辑控制器。

职责：
- 维护档案类型 / 评估表预设常量
- 从 UI 表格收集成绩记录与评估块
- 构造学员数据载荷并写入 Excel（含文件占用检测）
- 同步总课时与本次课时明细到 lesson_manager
- 扫描档案目录、加载学员元信息、打开课时/档案目录

单一职责：本文件不创建任何 Qt 控件，不直接操作 UI；
所有 UI 数据由调用方传入，所有结果以 dict / list / tuple 返回。
"""
import os
import logging

from excel_builder import append_record, read_student_meta
import lesson_manager as lm
from standards import SCORE_TYPES


#==== 预设常量 ====

# 评估表预设项
POSTURE_BLOCKS = [
    ('肩颈检测', [('头前伸距离(cm)', ''), ('肩峰高低差(cm)', ''), ('颈部侧弯', '')]),
    ('脊柱骨盆', [('脊柱侧弯角度', ''), ('骨盆前倾', ''), ('高低肩', '')]),
    ('下肢检测', [('X型腿/O型腿', ''), ('扁平足', ''), ('膝过伸', '')]),
    ('训练方案建议', [('矫正动作', ''), ('训练频率', ''), ('注意事项', '')]),
]
WEIGHT_BLOCKS = [
    ('身体数据', [('身高(cm)', ''), ('体重(kg)', ''), ('BMI', ''), ('体脂率(%)', '')]),
    ('体能基础测试', [('50米跑(秒)', ''), ('立定跳远(cm)', ''), ('仰卧起坐(次)', '')]),
    ('减重目标与计划', [('目标体重(kg)', ''), ('减重周期', ''), ('饮食建议', ''), ('运动建议', '')]),
]

# 类型选项：(显示名, table_type, grade, sheet_tag, zk_plan)
TYPE_OPTIONS = [
    ('小学1年级', 'primary', 1, '1年级', None),
    ('小学2年级', 'primary', 2, '2年级', None),
    ('小学3年级', 'primary', 3, '3年级', None),
    ('小学4年级', 'primary', 4, '4年级', None),
    ('小学5年级', 'primary', 5, '5年级', None),
    ('小学6年级', 'primary', 6, '6年级', None),
    # 初中/高中体测：与 Android Standards.kt JUNIOR_DATA / SENIOR_DATA 对齐
    ('初中体测(初一)', 'junior', 7, '初一', None),
    ('初中体测(初二)', 'junior', 8, '初二', None),
    ('初中体测(初三)', 'junior', 9, '初三', None),
    ('高中体测(高一)', 'senior', 10, '高一', None),
    ('高中体测(高二)', 'senior', 11, '高二', None),
    ('高中体测(高三)', 'senior', 12, '高三', None),
    ('中考(2026新方案)', 'zhongkao', None, '中考2026', '2026新方案'),
    ('中考(2025旧方案)', 'zhongkao_old', None, '中考2025', '2025旧方案'),
    ('体态矫正评估', 'posture', None, '体态评估', None),
    ('体重管理评估', 'weight', None, '体重管理', None),
]


#==== 数据收集 ====

def collect_records_from_table(table):
    """从成绩录入表格收集 {项目名: {value, score, grade}}。

    参数:
        table: QTableWidget，列定义为 [项目, 单位, 满分, 及格, 实测, 得分, 等级]
    返回:
        dict {项目名: {'value':str, 'score':float|None, 'grade':str}}
    """
    from PySide6.QtGui import QColor
    records = {}
    for i in range(table.rowCount()):
        it_name = table.item(i, 0)
        it_val = table.item(i, 4)
        if not it_name or not it_val:
            continue
        name = it_name.text()
        val = it_val.text().strip()
        if not val:
            continue
        score = None
        grade = ''
        it_sc = table.item(i, 5)
        if it_sc and it_sc.text() and it_sc.text() not in ('—', ''):
            try:
                score = float(it_sc.text())
                it_gr = table.item(i, 6)
                grade = it_gr.text() if it_gr else ''
            except ValueError:
                pass
        records[name] = {'value': val, 'score': score, 'grade': grade}
    return records


def collect_blocks_from_table(table):
    """从评估表（体态/体重管理）收集分组数据。

    参数:
        table: QTableWidget，列定义为 [项目, 内容]，含跨列分组标题行
    返回:
        list [(title, [(label, value), ...]), ...]
    """
    from PySide6.QtGui import QColor
    blocks = []
    cur_title = ''
    cur_rows = []
    for i in range(table.rowCount()):
        it0 = table.item(i, 0)
        it1 = table.item(i, 1)
        if not it0:
            continue
        # 合并的标题行：it1 为空且 it0 是白色标题样式
        if it1 is None or (it1.text() == '' and it0.foreground().color() == QColor('#ffffff')):
            if cur_title:
                blocks.append((cur_title, cur_rows))
            cur_title = it0.text()
            cur_rows = []
        else:
            cur_rows.append((it0.text(), it1.text() if it1 else ''))
    if cur_title:
        blocks.append((cur_title, cur_rows))
    return blocks


#==== 学员载荷构造 ====

def build_student_payload(name, age, gender, school, phone, date_str,
                          ttype, grade, sheet_tag, zk_plan, evaluation,
                          records=None, blocks=None):
    """构造学员数据 dict，供 append_record 写入 Excel。

    参数:
        records: 成绩字典（primary/zhongkao 类型必填）
        blocks:  评估块列表（posture/weight 类型必填）
    返回:
        dict
    """
    student = {
        'name': name, 'age': age, 'gender': gender,
        'school': school, 'phone': phone, 'date': date_str,
        'table_type': ttype, 'grade': grade, 'sheet_tag': sheet_tag,
        'zk_plan': zk_plan or '', 'evaluation': evaluation,
    }
    if ttype in SCORE_TYPES:
        student['records'] = records or {}
    else:
        student['blocks'] = blocks or []
    return student


#==== 文件占用检测 ====

def check_file_writable(file_path):
    """检测文件是否可写（未被 Excel 等占用）。

    返回:
        (True, None) 可写；(False, file_path) 被占用
    """
    if not os.path.exists(file_path):
        return True, None
    try:
        with open(file_path, 'a'):
            pass
        return True, None
    except PermissionError:
        return False, file_path


#==== 保存测评 ====

def save_assessment(student, dir_path, total_lessons_input=None,
                    lesson_count_input=None, lesson_content_input=None):
    """保存测评记录 + 同步课时。

    参数:
        student: build_student_payload 构造的 dict
        dir_path: 档案目录
        total_lessons_input: 总课时输入（str 或 None）
        lesson_count_input: 本次课时数输入（str 或 None）
        lesson_content_input: 本次训练内容（str 或 None）
    返回:
        tuple (sheet_name, file_path, lesson_msg)
    抛出:
        PermissionError - 文件被占用（调用方应捕获并提示）
        Exception - 其他保存异常
    """
    name = student['name']
    file_path = os.path.join(dir_path, f"{name}.xlsx")
    ok, occupied = check_file_writable(file_path)
    if not ok:
        raise PermissionError(f'文件被占用：{occupied}')

    sheet, fpath = append_record(student, dir_path)
    lesson_msg = ''

    # 同步总课时
    if total_lessons_input:
        try:
            total = int(total_lessons_input)
            if total >= 0:
                lm.set_total_lessons(dir_path, name, total)
                lesson_msg = f'\n总课时已同步：{total} 课时'
            else:
                lesson_msg = '\n总课时为负数，已忽略'
        except ValueError:
            lesson_msg = '\n总课时输入非整数，已忽略'

    # 同步本次课时明细
    if lesson_count_input:
        try:
            count = int(lesson_count_input)
            if count > 0:
                content = (lesson_content_input or '').strip() or '体能训练'
                lm.add_lesson(
                    dir_path, name,
                    student['date'], count, content, ''
                )
                lesson_msg += f'\n本次课时明细已写入：{count} 课时'
            elif count < 0:
                lesson_msg += '\n本次课时数无效，已忽略'
        except ValueError:
            lesson_msg += '\n本次课时数非整数，已忽略'

    return sheet, fpath, lesson_msg


#==== 学员扫描 / 元信息加载 ====

def scan_students(dir_path):
    """扫描档案目录下的学员名列表（按文件名排序）。

    返回: list[str] 学员名（不含 .xlsx 扩展名）
    """
    if not os.path.isdir(dir_path):
        return []
    names = []
    for f in sorted(os.listdir(dir_path)):
        if f.lower().endswith('.xlsx') and not f.startswith('~$'):
            names.append(f[:-5])
    return names


def load_student_meta(name, dir_path):
    """加载学员元信息。

    返回: dict {'info':dict, 'records':list} 或 None（读取失败）
    """
    file_path = os.path.join(dir_path, f"{name}.xlsx")
    return read_student_meta(file_path)


def get_lesson_total_for(name, dir_path):
    """获取指定学员的总课时。

    返回: int 总课时（0 表示未设置）；异常时返回 0
    """
    try:
        summary = lm.get_summary(dir_path)
        stu = next((s for s in summary if s['name'] == name), None)
        if stu and stu['total'] > 0:
            return stu['total']
    except Exception:
        logging.exception('获取学员总课时失败')
    return 0


#==== 文件 / 目录打开 ====

def ensure_lesson_file(dir_path):
    """确保课时记录文件存在，返回文件路径。"""
    fpath = lm._lesson_file_path(dir_path)
    if not os.path.exists(fpath):
        lm._ensure_file(dir_path)
    return fpath


def open_lesson_file(dir_path):
    """打开课时记录 Excel 文件。

    返回: (True, fpath) 成功；(False, err_str) 失败
    """
    if not dir_path:
        return False, '请先选择档案目录'
    fpath = ensure_lesson_file(dir_path)
    try:
        os.startfile(fpath)
        return True, fpath
    except OSError as e:
        return False, f'无法打开文件：{e}'


def open_archive_dir(dir_path):
    """在系统资源管理器中打开档案目录。

    返回: (True, None) 成功；(False, msg) 失败
    """
    if not dir_path or not os.path.isdir(dir_path):
        return False, '档案目录不存在，请先选择。'
    os.startfile(dir_path)
    return True, None
