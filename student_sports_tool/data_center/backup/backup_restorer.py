# -*- coding: utf-8 -*-
"""备份恢复：从 zip 还原档案目录 + Android 数据转换。"""
import os
import sqlite3
import zipfile
import logging
from datetime import datetime

from archive_manager import (
    backup_directory, restore_from_zip, extract_android_assets,
    cleanup_android_assets, make_backup_filename
)
import android_backup_parser as abp
from backup.backup_creator import do_auto_backup


def do_restore(zip_path, target_dir, progress_cb=None, conflict_resolutions=None):
    """执行恢复：从 zip 还原档案目录。

    恢复流程：
    1. 自动备份当前数据（防误覆盖）
    2. 时光机快照：备份 meta_index.db 到 _db_snapshots/（v5 优化6 新增）
    3. 还原 .xlsx 学员档案
    4. 检测 Android 端 .db / export_meta.json / 签到照片，提取并转换
    5. 解析 Android 数据，调用 excel_builder / lesson_manager 写入桌面端 Excel
       - v5 优化4 新增：根据 conflict_resolutions 处理冲突学员
         （merge / overwrite / rename / skip）
    6. 清理 _android 临时目录

    参数:
        conflict_resolutions: List[Dict]，每项含 student_name / action / new_name。
            为空或 None 时按"已存在则跳过创建、合并课时"原默认逻辑执行。

    返回: (restored_count, auto_backup_path)
    """
    zip_path = os.path.normpath(zip_path)
    target_dir = os.path.normpath(target_dir)
    if progress_cb:
        progress_cb('正在检测当前档案...')
    # 自动备份当前数据
    auto_backup_path = None
    if os.path.isdir(target_dir):
        auto_name = make_backup_filename('恢复前自动备份')
        auto_backup_path = os.path.join(os.path.dirname(zip_path), auto_name)
        if progress_cb:
            progress_cb('正在自动备份当前数据...')
        backup_directory(target_dir, auto_backup_path)

    # === v5 优化6 新增：时光机快照 ===
    # 在还原 .xlsx 之前，先备份当前 SQLite 索引数据库
    # 失败静默处理，绝不阻塞 do_restore 主流程
    db_snap_path = None
    try:
        import db_snapshot_manager as dsm
        if progress_cb:
            progress_cb('正在生成数据库时光机快照...')
        db_snap_path = dsm.create_snapshot(reason='restore', dir_path=target_dir)
        if db_snap_path and progress_cb:
            progress_cb(f'数据库快照已生成：{os.path.basename(db_snap_path)}')
    except (FileNotFoundError, PermissionError, sqlite3.DatabaseError) as e:
        logging.error(f'数据库快照生成失败：原因={e}', exc_info=True)
        if progress_cb:
            progress_cb(f'数据库快照生成跳过：{e}')

    # 1. 还原 .xlsx 学员档案
    if progress_cb:
        progress_cb('正在从备份还原 Excel 档案...')
    count = restore_from_zip(zip_path, target_dir, progress_cb=progress_cb)

    # 2. 提取 Android 端资源
    if progress_cb:
        progress_cb('正在检测 Android 端备份数据...')
    assets = extract_android_assets(zip_path, target_dir, progress_cb=progress_cb)
    has_android_data = assets['db_path'] or assets['meta_path']

    if has_android_data:
        if progress_cb:
            progress_cb('正在解析 Android 数据并转换为桌面端格式...')
        android_count = _convert_android_to_excel(
            target_dir, assets, progress_cb, conflict_resolutions
        )
        if progress_cb:
            progress_cb(f'Android 数据转换完成：新增 {android_count} 位学员档案')
            if assets['photo_count']:
                progress_cb(f'签到照片已迁移至 photos/ 目录：{assets["photo_count"]} 张')
        count += android_count

    # 3. 清理临时目录
    cleanup_android_assets(target_dir)

    if progress_cb:
        progress_cb(f'恢复完成：共 {count} 个档案')

    # === 终极架构：重建 SQLite 索引（性能加速层）===
    # 索引数据源优先级：
    # 1. _convert_android_to_excel 已通过 side-effect 写入索引（has_android_data 时）
    # 2. 回退到扫描档案目录重建（无 Android 数据或前一步失败）
    try:
        import meta_index_store as mis
        if not has_android_data or not mis.is_index_available(target_dir):
            indexed = mis.rebuild_index_from_dir(target_dir, force=True)
            if progress_cb:
                progress_cb(f'SQLite 索引重建完成（目录扫描）：{indexed} 位学员')
        else:
            if progress_cb:
                last = mis.get_last_rebuild_time(target_dir)
                progress_cb(f'SQLite 索引已就绪（最近重建：{last}）')
    except (FileNotFoundError, PermissionError, sqlite3.DatabaseError) as e:
        logging.error(f'SQLite 索引重建失败：目录={target_dir}，原因={e}', exc_info=True)
        if progress_cb:
            progress_cb(f'SQLite 索引重建跳过：{e}')

    # === v4 新增：恢复成功后立即触发一次自动备份 ===
    # 防止恢复后的数据再次丢失，备份恢复后的最新状态到 AutoBackups/
    # 静默执行：失败仅记录日志，不影响恢复流程
    try:
        do_auto_backup(target_dir, progress_cb=None)
    except (FileNotFoundError, PermissionError, zipfile.BadZipFile) as e:
        logging.error(f'恢复后自动备份失败：目录={target_dir}，原因={e}', exc_info=True)

    return count, auto_backup_path


def _read_sports_db_json(db_path):
    """裸 sqlite3 直读 Android sports_coach_db，返回 {students, lessons, packages}。

    abp.parse_db 的降级回退：不经 android_backup_parser 封装层，直接打开
    Room SQLite 读取核心表（students / lessons / archived_lessons /
    lesson_packages，packages 作为旧版表名备选），复用 abp 的行归一化函数，
    输出结构与 parse_db 完全一致。

    防御原则：表缺失静默跳过，任何 sqlite3.DatabaseError 均吞掉返回空结构，
    绝不阻塞 do_restore 主流程。
    """
    result = {'students': [], 'lessons': [], 'packages': []}
    if not db_path or not os.path.exists(db_path):
        return result
    try:
        uri = f'file:{db_path}?mode=ro'
        conn = sqlite3.connect(uri, uri=True)
        try:
            tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }

            def _all(table):
                cols = [
                    row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')
                ]
                if not cols:
                    return []
                return [
                    dict(zip(cols, row))
                    for row in conn.execute(f'SELECT * FROM "{table}"')
                ]

            # 学员
            if 'students' in tables:
                for row in _all('students'):
                    item = abp._normalize_student(row)
                    if item['name']:
                        result['students'].append(item)

            # 课时明细（合并 archived_lessons，按 student_name+date 去重）
            seen_lessons = set()
            for table in ('lessons', 'archived_lessons'):
                if table in tables:
                    for row in _all(table):
                        item = abp._normalize_lesson(row)
                        if not item['student_name']:
                            continue
                        key = (item['student_name'], item['date'])
                        if key in seen_lessons:
                            continue
                        seen_lessons.add(key)
                        result['lessons'].append(item)

            # 课时包
            pkg_table = 'lesson_packages' if 'lesson_packages' in tables else (
                'packages' if 'packages' in tables else None
            )
            if pkg_table:
                for row in _all(pkg_table):
                    item = abp._normalize_package(row)
                    if item['student_name']:
                        result['packages'].append(item)
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        pass
    return result


def _convert_android_to_excel(target_dir, assets, progress_cb=None,
                              conflict_resolutions=None):
    """将 Android 解析数据转换为桌面端 Excel。

    参数:
        target_dir: 桌面端档案目录
        assets: extract_android_assets 返回的 dict
        progress_cb: 进度回调
        conflict_resolutions: v5 优化4 新增，冲突解决策略列表
            [{student_name, action: 'merge'|'overwrite'|'rename'|'skip', new_name}]

    返回: 新增学员档案数
    """
    # 延迟导入，避免循环依赖与无 Android 数据时的加载开销
    import excel_builder
    import lesson_manager

    # v5 优化4：构建冲突解决索引 {原名: resolution}
    resolution_map = {}
    if conflict_resolutions:
        for r in conflict_resolutions:
            name = (r.get('student_name') or '').strip()
            if name:
                resolution_map[name] = r

    # 优先 meta.json，回退 .db（解析失败时降级为裸 sqlite3 直读核心表）
    parsed = None
    if assets['meta_path'] and os.path.exists(assets['meta_path']):
        parsed = abp.parse_meta_json(assets['meta_path'])
    if not parsed and assets['db_path'] and os.path.exists(assets['db_path']):
        try:
            parsed = abp.parse_db(assets['db_path'])
        except (FileNotFoundError, PermissionError, zipfile.BadZipFile, sqlite3.DatabaseError) as e:
            logging.error(f'Android 数据库解析失败：{assets["db_path"]}，原因={e}', exc_info=True)
            if progress_cb:
                progress_cb(f'Android 数据库解析失败：{e}，尝试直接读取核心表')
            parsed = _read_sports_db_json(assets['db_path'])

    if not parsed or not (parsed.get('students') or parsed.get('lessons') or parsed.get('packages')):
        return 0

    if progress_cb:
        progress_cb(abp.summarize(parsed))

    # === 终极架构：解析后立即重建 SQLite 索引 ===
    # 此时 parsed 仍在内存中，是建立强索引的最佳时机
    # 索引建立失败不影响后续 Excel 写入流程
    try:
        import meta_index_store as mis
        indexed = mis.rebuild_index_from_parsed(parsed, target_dir)
        if progress_cb and indexed > 0:
            progress_cb(f'SQLite 索引建立完成：{indexed} 位学员（查询提速 10x）')
    except (FileNotFoundError, PermissionError, sqlite3.DatabaseError) as e:
        logging.error(f'SQLite 索引建立失败：原因={e}', exc_info=True)
        if progress_cb:
            progress_cb(f'SQLite 索引建立跳过：{e}')

    students = parsed.get('students', [])
    lessons = parsed.get('lessons', [])
    packages = parsed.get('packages', [])

    # 按学员名聚合课时明细
    lessons_by_name = {}
    for les in lessons:
        name = les.get('student_name', '').strip()
        if not name:
            continue
        lessons_by_name.setdefault(name, []).append(les)

    # 按学员名聚合课时包
    pkg_by_name = {}
    for pkg in packages:
        name = pkg.get('student_name', '').strip()
        if not name:
            continue
        pkg_by_name[name] = pkg

    # === 幂等合并（v23.6 修复）：手机备份是全量快照，自动同步会反复推送同一批
    # 课时；add_lesson 无去重，二次推送曾导致 PC 明细/已上课时翻倍放大。
    # 以（学员, 日期, 节数, 内容, 备注）全字段为幂等键，跳过 PC 已有记录。
    existing_lesson_keys = _existing_lesson_keys(target_dir)

    new_count = 0
    for stu in students:
        name = stu.get('name', '').strip()
        if not name:
            continue

        # v5 优化4：根据冲突解决策略处理
        resolution = resolution_map.get(name)
        action = resolution.get('action') if resolution else None
        new_name = resolution.get('new_name') if resolution else None

        # 跳过策略：直接跳过此学员，不导入任何数据
        if action == 'skip':
            if progress_cb:
                progress_cb(f'已跳过学员：{name}（教练选择"跳过此条"）')
            continue

        # 重命名策略：用新名称创建档案，不影响本地已有同名学员
        # 后续 add_lesson / set_total_lessons 也使用新名称
        effective_name = new_name if (action == 'rename' and new_name) else name

        # 安全文件名（兼容 Windows 非法字符）
        safe_name = _safe_filename(effective_name)
        file_path = os.path.join(target_dir, f'{safe_name}.xlsx')

        # 覆盖策略：先删除本地已有档案（含课时记录）
        if action == 'overwrite' and os.path.exists(file_path):
            try:
                os.remove(file_path)
                if progress_cb:
                    progress_cb(f'已删除本地档案（覆盖策略）：{name}')
            except OSError as e:
                if progress_cb:
                    progress_cb(f'删除本地档案失败 [{name}]：{e}')

        # 若学员档案不存在，则创建空档案（带基本信息）
        if not os.path.exists(file_path):
            student_data = {
                'name': effective_name,
                'age': stu.get('age'),
                'gender': stu.get('gender') or '男',
                'school': stu.get('school') or '',
                'phone': stu.get('phone') or '',
                # 遗传与生活习惯字段（身高预测用，两端一致透传）
                'father_height': stu.get('father_height'),
                'mother_height': stu.get('mother_height'),
                'sleep_hours': stu.get('sleep_hours'),
                'nutrition_score': stu.get('nutrition_score'),
                'sports_mins': stu.get('sports_mins'),
                # 毫秒级更新时间（LWW 判新，往返保真）
                'updated_at': stu.get('updated_at'),
                'date': datetime.now().strftime('%Y-%m-%d'),
                'table_type': 'primary',
                'grade': None,
                'sheet_tag': 'Android导入' + ('（重命名）' if action == 'rename' else ''),
                'zk_plan': '',
                'evaluation': '',
                'records': {},
            }
            try:
                excel_builder.append_record(student_data, target_dir)
                new_count += 1
                if progress_cb:
                    progress_cb(f'已创建学员档案：{effective_name}')
            except (FileNotFoundError, PermissionError) as e:
                logging.error(f'创建档案失败 [{effective_name}]：{file_path}，原因={e}', exc_info=True)
                if progress_cb:
                    progress_cb(f'创建档案失败 [{effective_name}]：{e}')
                continue
        elif action == 'merge' and progress_cb:
            # 合并策略：保留本地档案，仅合并课时记录
            progress_cb(f'已存在档案，执行合并：{name}')

        # === v23.2 推送方向 LWW：手机端学员资料较新 → 刷新 PC 花名册 ===
        # 覆盖默认策略与显式 merge；新建档路径不走此分支（手机时间戳已随 info 落盘）
        if os.path.exists(file_path) and action != 'overwrite':
            merge_result = _lww_merge_roster(target_dir, effective_name, stu)
            if progress_cb and merge_result == 'updated':
                progress_cb(f'学员资料已按手机端更新（LWW）：{effective_name}')

        # 同步该学员的课时明细（使用 effective_name；幂等键去重防重复放大）
        # 重命名策略下，远端 lessons 是按原 name 聚合的
        source_lessons = lessons_by_name.get(name, [])
        for les in source_lessons:
            try:
                les_date = les.get('date') or datetime.now().strftime('%Y-%m-%d')
                les_count = int(les.get('count') or 1)
                les_content = les.get('content') or ''
                les_note = les.get('note') or ''
                key = (effective_name, str(les_date), les_count,
                       str(les_content), str(les_note))
                if key in existing_lesson_keys:
                    continue
                lesson_manager.add_lesson(
                    target_dir, effective_name,
                    les_date, les_count, les_content, les_note,
                )
                existing_lesson_keys.add(key)
            except (FileNotFoundError, PermissionError) as e:
                logging.error(f'同步课时失败 [{effective_name}]：目录={target_dir}，原因={e}', exc_info=True)
                continue

        # 同步课时包总课时
        pkg = pkg_by_name.get(name)
        if pkg and pkg.get('total'):
            try:
                lesson_manager.set_total_lessons(
                    target_dir, effective_name, int(pkg['total'])
                )
            except (FileNotFoundError, PermissionError) as e:
                logging.error(f'同步课时包失败 [{effective_name}]：目录={target_dir}，原因={e}', exc_info=True)

    return new_count


def _existing_lesson_keys(target_dir: str) -> set:
    """收集 PC 端已有课时明细的幂等键（学员, 日期, 节数, 内容, 备注）。

    日期统一归一化为 date 的 ISO 字符串（PC 明细单元格可能是 datetime 或 str）。
    读取失败静默返回空集合——退化为旧行为（重复追加），不阻塞恢复主流程。
    """
    keys = set()
    try:
        import lesson_manager as _lm
        for rec in _lm.get_detail(target_dir):
            d = _lm._norm_date(rec.get('date'))
            keys.add((
                rec.get('name'),
                d.isoformat() if d else str(rec.get('date') or ''),
                _to_int(rec.get('count')),
                str(rec.get('content') or ''),
                str(rec.get('note') or ''),
            ))
    except Exception:
        logging.exception('收集已有课时幂等键失败（退化为不去重）')
    return keys


def _to_int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _lww_merge_roster(target_dir: str, name: str, stu: dict) -> str:
    """手机推送方向的花名册 LWW 合并（v23.2）。

    失败静默降级（返回 'skipped'），不阻塞课时/课时包合并主流程。
    """
    import sys
    try:
        try:
            import profile_manager as pm
        except ImportError:
            # 独立进程（sync_server）场景：补齐 student_profile 导入路径
            root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))
            for p in (root, os.path.join(root, 'student_profile')):
                if p not in sys.path:
                    sys.path.insert(0, p)
            import profile_manager as pm
        return pm.merge_student_from_phone(target_dir, stu)
    except Exception:
        logging.exception(f'花名册 LWW 合并失败 [{name}]')
        return 'skipped'


def _safe_filename(name: str) -> str:
    """清洗 Windows 非法文件名字符（M5-S1 集成）。"""
    # 延迟导入避免循环
    try:
        from filename_sanitizer import sanitize_filename
        return sanitize_filename(name)
    except ImportError:
        # 回退：基础清洗
        for ch in r'\/:*?"<>|':
            name = name.replace(ch, '_')
        return name.strip().rstrip('.')
