# -*- coding: utf-8 -*-
"""
生成项目简介 PPT（python-pptx）。

输出：lab_scripts/intro.pptx

包含 10 张幻灯片：
  1. 封面
  2. 项目目标
  3. 系统架构（4 层闭环）
  4. 核心能力（6 阶段一览）
  5. Phase 1：事件驱动仿真
  6. Phase 2-3：拓扑重构 + 规则引擎
  7. Phase 4：规则生成
  8. Phase 5：可视化仪表盘
  9. 关键指标汇总
  10. 未来工作

运行：
  gridcal-env/Scripts/python.exe lab_scripts/build_ppt.py
"""

import os
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN


# ============ 配色
BLUE = RGBColor(0x19, 0x76, 0xD2)        # 主色
DARK = RGBColor(0x21, 0x21, 0x21)
GRAY = RGBColor(0x66, 0x66, 0x66)
LIGHT = RGBColor(0xF5, 0xF5, 0xF5)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x4C, 0xAF, 0x50)
ORANGE = RGBColor(0xFF, 0x98, 0x00)
RED = RGBColor(0xF4, 0x43, 0x36)

# 中文字体
CN_FONT = "Microsoft YaHei"
EN_FONT = "Calibri"


def set_text(run, text, font_size=18, bold=False, color=DARK, font=CN_FONT):
    """设置文字 run 的样式。"""
    run.text = text
    run.font.name = font
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.color.rgb = color


def add_title(slide, text, top=Inches(0.3), height=Inches(0.7)):
    """添加大标题。"""
    tx = slide.shapes.add_textbox(Inches(0.5), top, Inches(9), height)
    tf = tx.text_frame
    p = tf.paragraphs[0]
    set_text(p.add_run(), text, font_size=28, bold=True, color=BLUE)
    p.alignment = PP_ALIGN.LEFT
    return tx


def add_subtitle(slide, text, top=Inches(1.0)):
    """添加副标题（小字）。"""
    tx = slide.shapes.add_textbox(Inches(0.5), top, Inches(9), Inches(0.4))
    tf = tx.text_frame
    p = tf.paragraphs[0]
    set_text(p.add_run(), text, font_size=14, color=GRAY)
    return tx


def add_bullet_list(slide, items, left=0.5, top=1.7, width=9, height=4,
                     font_size=16, color=DARK):
    """添加项目符号列表。"""
    tx = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tx.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        # 用 • 作项目符号
        set_text(p.add_run(), f"•  {item}", font_size=font_size, color=color)
        p.space_after = Pt(8)
    return tx


def add_kpi_card(slide, left, top, width, height, label, value, color=BLUE):
    """添加 KPI 卡片（带圆角矩形）。"""
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                   Inches(left), Inches(top), Inches(width), Inches(height))
    box.fill.solid()
    box.fill.fore_color.rgb = LIGHT
    box.line.color.rgb = color
    box.line.width = Pt(0)

    tf = box.text_frame
    tf.word_wrap = True
    p1 = tf.paragraphs[0]
    set_text(p1.add_run(), label, font_size=11, color=GRAY)
    p2 = tf.add_paragraph()
    set_text(p2.add_run(), value, font_size=20, bold=True, color=color)
    return box


def add_image(slide, path, left, top, width=None, height=None):
    """插入图片。"""
    if not os.path.exists(path):
        return None
    pic = slide.shapes.add_picture(path, Inches(left), Inches(top),
                                     width=Inches(width) if width else None,
                                     height=Inches(height) if height else None)
    return pic


# ============ 幻灯片构造
def slide_cover(prs):
    blank = prs.slide_layouts[6]
    s = prs.slides.add_slide(blank)

    # 顶部色块
    band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(1.2))
    band.fill.solid()
    band.fill.fore_color.rgb = BLUE
    band.line.fill.background()

    # 标题
    tx = s.shapes.add_textbox(Inches(0.5), Inches(2.5), Inches(9), Inches(1.5))
    tf = tx.text_frame
    p = tf.paragraphs[0]
    set_text(p.add_run(), "⚡ 电网事件驱动仿真与", font_size=40, bold=True, color=DARK)
    p2 = tf.add_paragraph()
    set_text(p2.add_run(), "自动投切决策系统", font_size=40, bold=True, color=DARK)

    # 副标题
    tx = s.shapes.add_textbox(Inches(0.5), Inches(4.2), Inches(9), Inches(0.5))
    p = tx.text_frame.paragraphs[0]
    set_text(p.add_run(), "Power Grid Event-Driven Simulation & Auto-Switching Decision System",
             font_size=14, color=GRAY, font=EN_FONT)

    # 作者信息
    tx = s.shapes.add_textbox(Inches(0.5), Inches(5.5), Inches(9), Inches(1.5))
    tf = tx.text_frame
    p = tf.paragraphs[0]
    set_text(p.add_run(), "作者：liuka", font_size=14, color=DARK)
    p2 = tf.add_paragraph()
    set_text(p2.add_run(), "日期：2026-10-06", font_size=14, color=DARK)
    p3 = tf.add_paragraph()
    set_text(p3.add_run(), "技术栈：Python · VeraGrid · Plotly · Dash · Stable-Baselines3",
             font_size=12, color=GRAY, font=EN_FONT)


def slide_goal(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(s, "项目目标")
    add_subtitle(s, "构建事件驱动的电网仿真平台，支撑自动投切策略的离线生成与在线验证")

    items = [
        "稳态运行：模拟真实电网拓扑 + 负荷/电源时序",
        "动态扰动：负荷新增/退出、发电机跳机、线路故障等事件注入",
        "自动投切：根据电网状态自动生成开关/切负荷/调出力等动作",
        "实时观测：拓扑、节点电压、支路载流、发电机出力、损耗的时间序列",
        "规则生成：从大量仿真数据中归纳出保护/重构规则",
    ]
    add_bullet_list(s, items, top=1.7, font_size=18)


def slide_architecture(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(s, "系统架构")
    add_subtitle(s, "4 层闭环：从事件注入到拓扑修改形成完整决策回路")

    # 4 个方框
    boxes = [
        ("① 事件注入器", "负荷/发电机/线路事件", "event_sim.inject()"),
        ("② 仿真引擎", "VeraGrid 潮流/动态/短路", "vg.power_flow()"),
        ("③ 状态观测器", "拓扑/电压/载流快照", "snapshot()"),
        ("④ 规则引擎", "IF-THEN 规则 + 冷却", "RuleEngine"),
    ]
    box_w, box_h, gap = 2.0, 1.4, 0.2
    start_left = 0.6
    top = 1.8
    for i, (title, desc, code) in enumerate(boxes):
        left = start_left + i * (box_w + gap)
        b = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                Inches(left), Inches(top), Inches(box_w), Inches(box_h))
        b.fill.solid()
        b.fill.fore_color.rgb = BLUE
        b.line.fill.background()
        tf = b.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        set_text(p.add_run(), title, font_size=14, bold=True, color=WHITE)
        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        set_text(p2.add_run(), desc, font_size=11, color=WHITE)
        p3 = tf.add_paragraph()
        p3.alignment = PP_ALIGN.CENTER
        set_text(p3.add_run(), code, font_size=10, color=LIGHT, font=EN_FONT)

    # 闭环箭头说明
    tx = s.shapes.add_textbox(Inches(0.5), Inches(3.5), Inches(9), Inches(2))
    tf = tx.text_frame
    tf.word_wrap = True
    items = [
        "事件 -> 仿真 -> 状态观测 -> 规则评估 -> 动作 -> 修改拓扑 -> 下一周期",
        "",
        "关键特性：",
        "• 规则冷却机制防止抖动（避免低电压-切-恢复-又触发的循环）",
        "• Simulator 规则触发后立即 re-PF（零延迟优化）",
        "• 拓扑可投切（Line + active 标志，比 Switch 类更灵活）",
    ]
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        if i == 0:
            set_text(p.add_run(), item, font_size=14, bold=True, color=BLUE, font=EN_FONT)
        elif item.startswith("•"):
            set_text(p.add_run(), item, font_size=13, color=DARK)
        elif item == "":
            p.space_after = Pt(4)
        else:
            set_text(p.add_run(), item, font_size=14, bold=True, color=DARK)


def slide_phases_overview(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(s, "核心能力")
    add_subtitle(s, "6 个阶段，端到端闭环")

    phases = [
        ("Phase 1", "事件驱动仿真", "5 事件 → 91 步全收敛", GREEN),
        ("Phase 2", "拓扑可控建模", "F1B 失电 25→1 步", GREEN),
        ("Phase 3", "规则引擎 v1", "4 条规则改善指标", GREEN),
        ("Phase B", "真实负荷扰动", "ZIP/闪变/启停", GREEN),
        ("Phase 4", "规则生成", "30+ 候选评估排名", GREEN),
        ("Phase 5", "可视化仪表盘", "Plotly 单文件 HTML", GREEN),
    ]
    box_w, box_h = 2.8, 1.6
    gap = 0.15
    start_left = 0.5
    top = 1.7
    for i, (name, title, kpi, color) in enumerate(phases):
        row, col = i // 3, i % 3
        left = start_left + col * (box_w + gap)
        t = top + row * (box_h + 0.3)

        b = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                Inches(left), Inches(t), Inches(box_w), Inches(box_h))
        b.fill.solid()
        b.fill.fore_color.rgb = LIGHT
        b.line.color.rgb = color
        b.line.width = Pt(1.5)

        tf = b.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        set_text(p.add_run(), name, font_size=14, bold=True, color=color)
        p2 = tf.add_paragraph()
        set_text(p2.add_run(), title, font_size=14, bold=True, color=DARK)
        p3 = tf.add_paragraph()
        p3.space_before = Pt(8)
        set_text(p3.add_run(), kpi, font_size=12, color=GRAY)

    # 下方说明
    tx = s.shapes.add_textbox(Inches(0.5), Inches(5.2), Inches(9), Inches(0.5))
    p = tx.text_frame.paragraphs[0]
    set_text(p.add_run(), "外加 6 个增强 Phase (A-F)：YAML 化 / 场景库 / R004 v2 / RL 训练 / 蒙特卡洛 / 实时 Dash",
             font_size=12, color=GRAY)


def slide_phase1(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(s, "Phase 1：事件驱动仿真")
    add_subtitle(s, "在 IEEE 14 上验证 5 事件剧本，全 91 步收敛")

    items = [
        "6 种事件类型：load_add/drop, gen_trip/commit, line_trip/close",
        "Simulator 主循环：基线 → 步进 → 事件 → 潮流 → 快照 → 记录",
        "VeraGrid 6.0.22 实测：pf.Sbus 单位是 MW（不是 pu）",
        "修复了多个 API bug：loading 字段垃圾值、rate 默认 1.0、GBK 编码",
        "支持 IEEE 14/30/57/118/300 + Kundur RMS 等多套测试系统",
    ]
    add_bullet_list(s, items, top=1.5, height=2.5, font_size=14)

    add_image(s, "lab_scripts/exp03_event_driven_sim.png", left=0.5, top=4.2, height=3.0)


def slide_phase2_3(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(s, "Phase 2 + 3：拓扑重构 + 规则引擎")
    add_subtitle(s, "5-bus 辐射状 feeder + 4 条保护规则")

    # 上半：拓扑示意
    tx = s.shapes.add_textbox(Inches(0.5), Inches(1.4), Inches(9), Inches(1.5))
    tf = tx.text_frame
    tf.word_wrap = True
    items = [
        "辐射状 feeder：SRC → S01/S02 → F1A/F2A → S13/S24 → F1B/F2B + TIE",
        "Line + active 标志表达可投切开关（比 Switch 类更灵活）",
        "R001_UVLS  低压减载（V<0.93pu → 切 30%）",
        "R002_OVGR  过压减出力（V>1.10pu → 降 20%）",
        "R003_OVERLOAD  重载切负荷（loading>130% → 末端切 10%）",
        "R004_RECONFIGURE  失电检测 + 闭合 TIE（v2 还支持故障隔离）",
    ]
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        if item.startswith("R"):
            set_text(p.add_run(), item, font_size=13, color=BLUE, font=EN_FONT)
        else:
            set_text(p.add_run(), "•  " + item, font_size=13, color=DARK)

    # 下半：图片
    add_image(s, "lab_scripts/exp05_reconfigure.png", left=0.5, top=4.0, height=3.2)


def slide_phase4(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(s, "Phase 4：规则生成（枚举 + 仿真评估）")
    add_subtitle(s, "批量评估候选规则，按综合评分排名")

    items = [
        "RuleSpec 数据模型（family / threshold / target / action_param）",
        "4 类规则生成器：UVLS / OVGR / OVERLOAD / RECONF",
        "评分函数：score = 100·min_v − 0.1·max_load − 2·blackout − ... ",
        "双场景对比（轻负荷 vs 高负荷），复合规则评估",
        "RECONF_TIE 在两个场景都获胜（F1B 失电 0 步 vs baseline 25 步）",
    ]
    add_bullet_list(s, items, left=0.5, top=1.5, height=2.5, font_size=14)

    add_image(s, "lab_scripts/exp07_rule_generation.png", left=0.5, top=4.2, height=3.0)


def slide_phase5(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(s, "Phase 5 + F：可视化")
    add_subtitle(s, "Plotly 单文件 HTML + Dash 真·实时仪表盘")

    items = [
        "Plotly 拓扑图（节点按电压着色 + 线路按载流着色）",
        "拓扑动画（▶ 播放按钮 + 时间滑块）",
        "4 子图时序曲线（电压/载流/出力/损耗）",
        "8 个关键指标卡片 + 事件/规则日志表",
        "Dash 版本：浏览器打开 http://127.0.0.1:8050，1 秒自动刷新",
    ]
    add_bullet_list(s, items, left=0.5, top=1.5, height=2.5, font_size=14)

    add_image(s, "lab_scripts/exp08_dashboard.html", left=0.5, top=4.2, height=3.0) if os.path.exists("lab_scripts/exp08_dashboard.png") else None
    # If dashboard.png doesn't exist, just describe
    if not os.path.exists("lab_scripts/exp08_dashboard.png"):
        tx = s.shapes.add_textbox(Inches(0.5), Inches(4.5), Inches(9), Inches(2.5))
        p = tx.text_frame.paragraphs[0]
        set_text(p.add_run(), "[仪表盘 HTML 文件位于 lab_scripts/exp08_dashboard.html]",
                 font_size=14, color=GRAY)


def slide_metrics(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(s, "关键指标汇总")
    add_subtitle(s, "从 Phase 1 到 Phase F 的累积成果")

    # 4 个 KPI 卡片
    kpis = [
        ("代码模块", "6 核心 + 14 demo", BLUE),
        ("仿真场景", "7 典型剧本", BLUE),
        ("Commit 数", "12+ 次", BLUE),
        ("总代码行", "~4500 行", BLUE),
        ("Phase 通过率", "3/7 (基线)", ORANGE),
        ("蒙特卡洛 N", "200 次", GREEN),
        ("RL 训练步", "3000 (PPO)", GREEN),
        ("Dash 实时", "1s 刷新", GREEN),
    ]
    box_w, box_h = 2.1, 1.3
    gap = 0.15
    start_left = 0.5
    top = 1.7
    for i, (label, value, color) in enumerate(kpis):
        row, col = i // 4, i % 4
        left = start_left + col * (box_w + gap)
        t = top + row * (box_h + 0.2)
        add_kpi_card(s, left, t, box_w, box_h, label, value, color=color)

    # 下方说明
    tx = s.shapes.add_textbox(Inches(0.5), Inches(4.5), Inches(9), Inches(2.5))
    tf = tx.text_frame
    tf.word_wrap = True
    items = [
        "关键修复（API 踩坑）:",
        "• pf.Sbus/Sf 单位是 MW（不是 pu）",
        "• pf.loading 字段对未通流支路返回垃圾值",
        "• VeraGrid 默认 ln.rate=1.0（必须显式设置）",
        "• Simulator 规则触发后立即 re-PF（消除 1 步延迟）",
        "• R004 故障隔离：自动找下游分段开关（修复了 slack 边界 bug）",
    ]
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        if item.endswith(":"):
            set_text(p.add_run(), item, font_size=14, bold=True, color=DARK)
        else:
            set_text(p.add_run(), item, font_size=12, color=DARK)


def slide_future(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(s, "未来工作")
    add_subtitle(s, "在现有基础上可扩展的方向")

    items = [
        "RL 训练规模化：当前 3000 步 PPO 不稳定，扩展到 10k+ 步并调优奖励函数",
        "基准通过率提升：当前 3/7，需更激进的协调规则（网络重构 + 协调切负荷）",
        "Dash 增强：手动注入事件滑块、参数调节、SCADA 真实数据接入",
        "规则库 YAML 化扩展：现有 4 条规则可加 10+ 条（OVL 区域化、UVLS 分级）",
        "概率潮流指导规则生成：用 PPF 得到的违反概率作为目标函数",
        "在线学习：把仿真环境部署为 RL 服务，支持真实电网数据回灌训练",
        "论文/技术报告：6 个 Phase + 6 个增强 Phase 足够写一篇会议论文",
    ]
    add_bullet_list(s, items, top=1.7, font_size=16)


def slide_thanks(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])

    # 顶部色块
    band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(1.2))
    band.fill.solid()
    band.fill.fore_color.rgb = BLUE
    band.line.fill.background()

    # 标题
    tx = s.shapes.add_textbox(Inches(0.5), Inches(3.0), Inches(9), Inches(1.5))
    tf = tx.text_frame
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    set_text(p.add_run(), "谢谢！", font_size=56, bold=True, color=DARK)
    p2 = tf.add_paragraph()
    p2.alignment = PP_ALIGN.CENTER
    set_text(p2.add_run(), "Thanks for watching", font_size=20, color=GRAY, font=EN_FONT)

    # 项目信息
    tx = s.shapes.add_textbox(Inches(0.5), Inches(5.0), Inches(9), Inches(2))
    tf = tx.text_frame
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    set_text(p.add_run(), "代码仓库：C:\\code\\research", font_size=14, color=GRAY, font=EN_FONT)
    p2 = tf.add_paragraph()
    p2.alignment = PP_ALIGN.CENTER
    set_text(p2.add_run(), "备份位置：E:\\Git\\power-grid-sim.git", font_size=14, color=GRAY, font=EN_FONT)
    p3 = tf.add_paragraph()
    p3.alignment = PP_ALIGN.CENTER
    set_text(p3.add_run(), "设计文档：docs\\DESIGN.md", font_size=14, color=GRAY, font=EN_FONT)


# ============ 主函数
def main():
    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(7.5)

    slide_cover(prs)
    slide_goal(prs)
    slide_architecture(prs)
    slide_phases_overview(prs)
    slide_phase1(prs)
    slide_phase2_3(prs)
    slide_phase4(prs)
    slide_phase5(prs)
    slide_metrics(prs)
    slide_future(prs)
    slide_thanks(prs)

    out = "lab_scripts/intro.pptx"
    prs.save(out)
    print(f"PPT 已生成: {out}")
    print(f"  共 {len(prs.slides)} 张幻灯片")


if __name__ == "__main__":
    main()
