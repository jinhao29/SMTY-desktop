# -*- coding: utf-8 -*-
"""智能推荐随机搭配（build_random_lesson）自检。

跑法: pytest test_random_recommend.py -q  （在 training_tool 目录内）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lesson_plan_loader as lpl  # noqa: E402

PLANS = lpl.load_all_plans()
GROUPS = [g for g in PLANS if PLANS[g]]


def test_plans_loaded():
    """4 份分龄教案至少加载出 2 组（容错个别文件损坏）。"""
    assert len(GROUPS) >= 2, f'教案加载不足: {list(PLANS)}'


def test_random_lesson_structure():
    """合成课结构完整：三段齐全、动作数量合理。"""
    g = GROUPS[0]
    lesson = lpl.build_random_lesson(g, PLANS)
    assert lesson is not None
    assert lesson.age_group == g
    assert lesson.core_content, '核心内容不应为空'
    warm = lpl.parse_exercises_to_list(lesson.warmup.exercises)
    cool = lparse = lpl.parse_exercises_to_list(lesson.cooldown.exercises)
    assert 2 <= len(warm) <= 4, f'热身动作数异常: {warm}'
    assert 2 <= len(cool) <= 3, f'放松动作数异常: {cool}'
    assert 2 <= len(lesson.main_sections) <= 3, '主项类别数应在 2-3'
    for sec in lesson.main_sections:
        assert sec.category
        moves = lpl.parse_exercises_to_list(sec.exercises)
        assert moves, f'类别 {sec.category} 动作为空'
        assert sec.duration


def test_random_varies():
    """多次合成结果应有变化（随机性）。"""
    g = GROUPS[0]
    outs = set()
    for _ in range(8):
        lesson = lpl.build_random_lesson(g, PLANS)
        assert lesson is not None
        outs.add(lesson.warmup.exercises + '|' + lesson.main_sections[0].exercises)
    assert len(outs) >= 2, '8 次合成结果完全相同，随机性失效'


def test_moves_come_from_pool():
    """合成课的动作必须来自该年龄段教案池（允许"循环组合："整块前缀）。"""
    g = GROUPS[0]
    pool = set()
    for l in PLANS[g]:
        pool.update(lpl.parse_exercises_to_list(l.warmup.exercises))
        pool.update(lpl.parse_exercises_to_list(l.cooldown.exercises))
        for sec in l.main_sections:
            moves = lpl.parse_exercises_to_list(sec.exercises)
            if len(moves) >= 5:
                pool.update(moves)
            else:
                pool.update(moves)
    lesson = lpl.build_random_lesson(g, PLANS)
    assert lesson is not None
    for text in [lesson.warmup.exercises, lesson.cooldown.exercises]:
        for m in lpl.parse_exercises_to_list(text):
            assert m in pool, f'动作不在教案池: {m}'
    for sec in lesson.main_sections:
        for m in lpl.parse_exercises_to_list(sec.exercises):
            if m.startswith('循环组合：'):
                continue  # 整块原文，来自教案
            assert m in pool, f'主项动作不在教案池: {m}'


def test_lesson_to_blocks():
    """合成课可转换为 SingleTab 区块结构。"""
    g = GROUPS[0]
    lesson = lpl.build_random_lesson(g, PLANS)
    blocks = lpl.lesson_to_blocks(lesson)
    assert len(blocks) == 3
    assert blocks[0].tasks, '热身区块不应为空'
    assert blocks[1].tasks, '主项区块不应为空'


if __name__ == '__main__':
    test_plans_loaded()
    test_random_lesson_structure()
    test_random_varies()
    test_moves_come_from_pool()
    test_lesson_to_blocks()
    print('ALL PASS')
