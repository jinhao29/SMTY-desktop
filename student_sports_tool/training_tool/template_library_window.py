# -*- coding: utf-8 -*-
"""UI 层：训练计划模板库浏览与选用窗口。

职责：
- 左侧树形分类浏览模板，右侧显示详情
- 支持弱项推荐（根据学员最近测评匹配模板）
- 选用模板时通过回调将动作序列载入训练编排页
- 支持保存自定义模板
"""
import modern_dialog as dialog
import os
import json
import uuid
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem,
    QGroupBox, QLabel, QPushButton, QTextEdit, QMessageBox, QFileDialog,
    QDialog, QFormLayout, QLineEdit, QSpinBox, QInputDialog, QCheckBox,
    QListWidget, QListWidgetItem
)

from template_manager import (
    load_all_templates, get_categories, save_custom_template,
    delete_custom_template, is_custom
)
from template_recommender import recommend_templates, extract_weaknesses


class TemplateLibraryWindow(QWidget):
    """训练计划模板库窗口。

    参数:
        on_apply_callback: 选用模板时的回调 (exercises: list) -> None
        dir_getter: 返回档案目录的回调（用于弱项推荐，可选）
    """

    def __init__(self, on_apply_callback=None, dir_getter=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('训练计划模板库')
        self.resize(900, 600)
        self._on_apply = on_apply_callback
        self._dir_getter = dir_getter
        self._templates = []
        self._current_template = None
        self._init_ui()
        self._load_templates()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(16, 16, 16, 16)

        # 顶部操作栏
        top = QHBoxLayout()
        title = QLabel('训练计划模板库')
        _f = QFont('微软雅黑'); _f.setPointSize(16); _f.setBold(True)
        title.setFont(_f)
        top.addWidget(title)
        top.addStretch()
        self.btn_recommend = QPushButton('弱项推荐', objectName='secondary')
        self.btn_recommend.clicked.connect(self.on_recommend)
        top.addWidget(self.btn_recommend)
        self.btn_save_custom = QPushButton('保存当前为自定义模板', objectName='secondary')
        self.btn_save_custom.clicked.connect(self.on_save_custom)
        top.addWidget(self.btn_save_custom)
        self.btn_delete = QPushButton('删除模板', objectName='danger')
        self.btn_delete.clicked.connect(self.on_delete)
        top.addWidget(self.btn_delete)
        lay.addLayout(top)

        # 主体：左树 / 右详情
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)

        # 左：分类树
        gb_tree = QGroupBox('模板列表')
        gb_tree.setObjectName('card')
        tl = QVBoxLayout(gb_tree)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self.on_tree_clicked)
        tl.addWidget(self.tree)
        splitter.addWidget(gb_tree)

        # 右：详情
        gb_detail = QGroupBox('模板详情')
        gb_detail.setObjectName('card')
        dl = QVBoxLayout(gb_detail)
        self.lbl_name = QLabel('请选择模板')
        _f2 = QFont('微软雅黑'); _f2.setPointSize(14); _f2.setBold(True)
        self.lbl_name.setFont(_f2)
        self.lbl_name.setStyleSheet('color:#FF6B47;')
        dl.addWidget(self.lbl_name)

        self.lbl_meta = QLabel('')
        self.lbl_meta.setStyleSheet('color:#9B9B9B; font-size:12px;')
        dl.addWidget(self.lbl_meta)

        self.lbl_goal = QLabel('')
        self.lbl_goal.setWordWrap(True)
        dl.addWidget(self.lbl_goal)

        dl.addWidget(QLabel('训练动作：'))
        self.lw_exercises = QListWidget()
        dl.addWidget(self.lw_exercises, 1)

        # 使用按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_apply = QPushButton('使用此模板', objectName='primary')
        self.btn_apply.clicked.connect(self.on_apply)
        btn_row.addWidget(self.btn_apply)
        dl.addLayout(btn_row)

        splitter.addWidget(gb_detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        lay.addWidget(splitter, 1)

    def _load_templates(self):
        """加载模板并填充树。"""
        self._templates = load_all_templates()
        self.tree.clear()
        categories = get_categories()
        for cat in categories:
            cat_item = QTreeWidgetItem(self.tree, [cat])
            cat_item.setFont(0, QFont('微软雅黑', bold=True))
            cat_item.setForeground(0, QColor('#FF6B47'))
            for tpl in self._templates:
                if tpl['category'] == cat:
                    name = tpl['name']
                    if is_custom(tpl):
                        name += ' ★'
                    item = QTreeWidgetItem(cat_item, [name])
                    item.setData(0, Qt.UserRole, tpl)
            self.tree.expandItem(cat_item)

    def on_tree_clicked(self, item, column):
        """点击树节点：显示模板详情。"""
        tpl = item.data(0, Qt.UserRole)
        if not tpl:
            return
        self._current_template = tpl
        self.lbl_name.setText(tpl['name'])
        custom_tag = '（自定义）' if is_custom(tpl) else '（预设）'
        self.lbl_meta.setText(
            f"{custom_tag}  分类：{tpl['category']}  "
            f"强度：{tpl.get('intensity', '-')}  时长：{tpl.get('duration_min', '-')}分钟")
        self.lbl_goal.setText(f"目标：{tpl.get('goal', '-')}\n适用：{tpl.get('target_students', '-')}")
        # 动作列表
        self.lw_exercises.clear()
        for ex in tpl.get('exercises', []):
            text = f"{ex['name']}    {ex['sets']}组 × {ex['reps']}    {ex.get('note', '')}"
            self.lw_exercises.addItem(QListWidgetItem(text))
        # 自定义模板才能删除
        self.btn_delete.setEnabled(is_custom(tpl))

    def on_apply(self):
        """选用当前模板：通过回调载入动作序列。"""
        if not self._current_template:
            dialog.info(self, '提示', '请先选择模板')
            return
        exercises = self._current_template.get('exercises', [])
        if self._on_apply:
            self._on_apply(exercises)
        dialog.info(self, '已载入', f'模板 [{self._current_template["name"]}] 的动作已载入训练编排页')
        self.close()

    def on_recommend(self):
        """弱项推荐：根据学员最近测评匹配模板。"""
        if not self._dir_getter:
            dialog.info(self, '提示', '未提供档案目录，无法推荐')
            return
        dir_path = self._dir_getter()
        if not dir_path or not os.path.isdir(dir_path):
            dialog.warn(self, '提示', '请先选择有效的档案目录')
            return
        # 选择学员
        from PySide6.QtWidgets import QComboBox
        from archive_manager import scan_student_files
        students = [f[0][:-5] for f in scan_student_files(dir_path)]
        if not students:
            dialog.info(self, '提示', '档案目录下无学员档案')
            return
        name, ok = QInputDialog.getItem(
            self, '选择学员', '选择要推荐模板的学员：', students, 0, False)
        if not ok or not name:
            return
        # 读取测评记录
        try:
            from excel_builder import read_student_meta
            meta = read_student_meta(os.path.join(dir_path, f'{name}.xlsx'))
            if not meta:
                dialog.warn(self, '提示', f'读取 {name} 档案失败')
                return
            records = meta.get('records', [])
            weaknesses = extract_weaknesses(records)
            if not weaknesses:
                dialog.info(self, '提示', f'{name} 暂无弱项数据或无测评记录')
                return
            recommended = recommend_templates(weaknesses, self._templates)
            if not recommended:
                dialog.info(self, '提示', f'未找到匹配 {", ".join(weaknesses)} 的模板')
                return
            # 高亮推荐模板
            self.tree.clearSelection()
            msg = f'弱项：{", ".join(weaknesses)}\n\n推荐模板：\n'
            for i, tpl in enumerate(recommended, 1):
                msg += f'{i}. {tpl["name"]}（{tpl["category"]}）\n'
            dialog.info(self, '弱项推荐', msg)
        except Exception as e:
            dialog.error(self, '推荐失败', str(e))

    def on_save_custom(self):
        """保存当前模板为自定义模板。"""
        if not self._current_template:
            dialog.info(self, '提示', '请先选择模板')
            return
        tpl = self._current_template
        name, ok = QInputDialog.getText(
            self, '保存自定义模板', '模板名称：', text=tpl['name'] + '_自定义')
        if not ok or not name.strip():
            return
        new_tpl = {
            'id': f'custom_{uuid.uuid4().hex[:8]}',
            'name': name.strip(),
            'category': tpl['category'],
            'goal': tpl.get('goal', ''),
            'target_students': tpl.get('target_students', ''),
            'intensity': tpl.get('intensity', '中'),
            'duration_min': tpl.get('duration_min', 45),
            'applicable_weakness': tpl.get('applicable_weakness', []),
            'exercises': tpl.get('exercises', []),
        }
        save_custom_template(new_tpl)
        self._load_templates()
        dialog.info(self, '已保存', f'自定义模板 [{name}] 已保存')

    def on_delete(self):
        """删除自定义模板。"""
        if not self._current_template or not is_custom(self._current_template):
            return
        tpl = self._current_template
        reply = dialog.confirm(
            self, '确认删除', f'确认删除自定义模板 [{tpl["name"]}]？')
        if reply :
            delete_custom_template(tpl['id'])
            self._load_templates()
            self.lbl_name.setText('请选择模板')
            self.lbl_meta.setText('')
            self.lbl_goal.setText('')
            self.lw_exercises.clear()
            dialog.info(self, '已删除', f'模板 [{tpl["name"]}] 已删除')
