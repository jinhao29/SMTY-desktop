# -*- coding: utf-8 -*-
"""处理器层：弱项→模板匹配推荐（纯逻辑，无状态）。

职责：
- 根据学员弱项项目列表匹配适用模板
- 按命中数排序返回推荐模板
- 提取弱项项目名称列表
"""


def recommend_templates(weakness_projects, all_templates, top_n=3):
    """根据弱项项目匹配模板，按命中数排序返回 top_n。

    参数:
        weakness_projects: 弱项项目名列表
        all_templates: 所有模板列表
        top_n: 返回数量上限

    返回: 推荐模板列表
    """
    if not weakness_projects:
        return []
    weakness_set = set(weakness_projects)
    scored = []
    for tpl in all_templates:
        applicable = set(tpl.get('applicable_weakness', []))
        hits = len(applicable & weakness_set)
        if hits > 0:
            scored.append((hits, tpl))
    scored.sort(key=lambda x: -x[0])
    return [tpl for _, tpl in scored[:top_n]]


def extract_weaknesses(records, top_n=2):
    """从测评记录中提取弱项项目名。

    参数:
        records: 学员测评记录（来自 _meta.records）
        top_n: 取得分最低的 N 项

    返回: 弱项项目名列表
    """
    if not records:
        return []
    last_record = records[-1]
    scores = last_record.get('scores', {})
    if not scores:
        return []

    # 按得分排序，取最低的 top_n 项
    sorted_items = sorted(
        scores.items(),
        key=lambda x: x[1].get('score') if x[1].get('score') is not None else 999
    )
    weak = []
    for proj, data in sorted_items[:top_n]:
        score = data.get('score')
        if score is not None and score < 75:  # 低于良好线
            weak.append(proj)
    return weak
