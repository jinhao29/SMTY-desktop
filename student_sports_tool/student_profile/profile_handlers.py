# -*- coding: utf-8 -*-
"""学员档案事件处理（mixin）：新增/编辑/删除/搜索/右键菜单等信号槽逻辑。

拆分自 profile_screen.py（P2 超大文件拆分）。
以 mixin 形式混入 ProfileScreen，方法内通过 self 访问主界面成员，
信号槽连接仍在 ProfileScreen._init_ui 组装阶段完成，不破坏交互。
"""
import os
import sys

import modern_dialog as dialog
from PySide6.QtWidgets import QDialog, QMessageBox, QMenu

import profile_manager as pm
from profile_dialogs import StudentEditDialog
from profile_lesson_dialog import LessonEditDialog


class ProfileHandlersMixin:
    """学员档案界面的事件处理方法集合。"""

    def _on_search(self, text):
        """优化5：搜索过滤由代理模型负责，无需重查存储。"""
        self._proxy_model.set_keyword(text or '')
        # 底部栏同步「当前显示数量」（预警名单仍基于全量数据）
        if hasattr(self, '_all_students'):
            self._update_header_and_footer(self._all_students)

    def _on_table_context_menu(self, pos):
        """右键菜单：恢复已停用学员。"""
        # 优化5：通过 rowAt 获取代理模型行号，再经 proxy 取数据
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        s = self._proxy_model.get_student_at_proxy(row)
        if not s:
            return
        name = s.get('name', '')
        is_inactive = not s.get('is_active', True)
        menu = QMenu(self)
        if is_inactive:
            act_reactivate = menu.addAction('恢复此学员')
            act_reactivate.triggered.connect(lambda: self._on_reactivate(name))
        else:
            act_edit = menu.addAction('编辑')
            act_edit.triggered.connect(self.on_edit)
            act_lesson = menu.addAction('修改课时')
            act_lesson.triggered.connect(self.on_edit_lesson)
            act_deactivate = menu.addAction('停用此学员')
            act_deactivate.triggered.connect(lambda: self._on_deactivate(name))
        if menu.actions():
            menu.exec(self.table.viewport().mapToGlobal(pos))

    def _on_reactivate(self, name: str):
        """恢复已停用学员。"""
        archive_dir = self._get_dir()
        if not archive_dir:
            return
        reply = dialog.confirm(
            self, '确认恢复',
            f'确定恢复学员 [{name}] 为启用状态吗？\n恢复后将重新出现在正常学员列表中。',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if not reply:
            return
        try:
            pm.reactivate_student(archive_dir, name)
            self.refresh()
            dialog.info(self, '已恢复', f'学员 [{name}] 已恢复启用')
        except Exception as e:
            dialog.error(self, '恢复失败', str(e))

    def _on_deactivate(self, name: str):
        """快捷停用学员（与删除按钮等价，但仅停用当前选中行）。"""
        archive_dir = self._get_dir()
        if not archive_dir:
            return
        reply = dialog.confirm(
            self, '确认停用',
            f'确定停用学员 [{name}] 吗？\n（软删除：所有数据保留，可随时恢复）',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if not reply:
            return
        try:
            pm.delete_student(archive_dir, name)
            self.refresh()
        except Exception as e:
            dialog.error(self, '停用失败', str(e))

    def on_add(self):
        archive_dir = self._get_dir()
        if not archive_dir:
            dialog.warn(self, '提示', '请先在「体测档案」Tab 设置档案目录')
            return
        dlg = StudentEditDialog(self, student=None, archive_dir=archive_dir)
        if dlg.exec() == QDialog.Accepted:
            self.refresh()

    def on_edit(self):
        archive_dir = self._get_dir()
        if not archive_dir:
            return
        row = self.table.currentIndex().row()
        if row < 0:
            dialog.info(self, '提示', '请先选中要编辑的学员')
            return
        # 优化5：通过代理模型行号取数据
        name = self._proxy_model.get_student_name_at_proxy(row)
        if not name:
            return
        students = pm.list_students(archive_dir)
        student = next((s for s in students if s['name'] == name), None)
        if not student:
            return
        dlg = StudentEditDialog(self, student=student, archive_dir=archive_dir)
        if dlg.exec() == QDialog.Accepted:
            self.refresh()

    def on_edit_lesson(self):
        """直接修改选中学员的课时信息（总课时 + 历史明细编辑）。"""
        archive_dir = self._get_dir()
        if not archive_dir:
            return
        row = self.table.currentIndex().row()
        if row < 0:
            dialog.info(self, '提示', '请先选中要修改课时的学员')
            return
        name = self._proxy_model.get_student_name_at_proxy(row)
        if not name:
            return
        # 添加搜索路径以导入 lesson_window 与 lesson_manager
        _parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _parent not in sys.path:
            sys.path.insert(0, _parent)
        try:
            import lesson_manager as lm
        except Exception as e:
            dialog.error(self, '加载失败', f'无法加载课时模块：{e}')
            return
        dlg = LessonEditDialog(self, name=name, archive_dir=archive_dir, lesson_mgr=lm)
        if dlg.exec() == QDialog.Accepted:
            self.refresh()

    def on_del(self):
        """停用学员（软删除）：保留所有数据，仅标记 is_active=False。"""
        archive_dir = self._get_dir()
        if not archive_dir:
            return
        row = self.table.currentIndex().row()
        if row < 0:
            dialog.info(self, '提示', '请先选中要停用的学员')
            return
        name = self._proxy_model.get_student_name_at_proxy(row)
        if not name:
            return
        reply = dialog.confirm(
            self, '确认停用',
            f'确定停用学员 [{name}] 吗？\n\n'
            f'（软删除：所有档案、课时、测评历史完整保留，\n'
            f'可随时通过「显示已停用学员」右键恢复）',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply:
            try:
                pm.delete_student(archive_dir, name)
                self.refresh()
            except Exception as e:
                dialog.error(self, '停用失败', str(e))

    def on_growth_tools(self):
        """打开成长工具弹窗（身高预测 / 营养方案 / 体型历史）。"""
        archive_dir = self._get_dir()
        if not archive_dir:
            dialog.warn(self, '提示', '请先在「体测档案」Tab 设置档案目录')
            return
        from growth_tools_dialog import GrowthToolsDialog
        row = self.table.currentIndex().row()
        name = self._proxy_model.get_student_name_at_proxy(row) if row >= 0 else ''
        dlg = GrowthToolsDialog(self, archive_dir=archive_dir, student_name=name or '')
        dlg.exec()
