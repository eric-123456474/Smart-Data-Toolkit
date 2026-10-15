# -*- coding: utf-8 -*-
"""图表绘制：直方图/柱状图/折线图/散点图/箱线图/饼图，中文显示并防止文字重叠

- 自动按操作系统挑选中文字体（Windows / macOS / Linux）
- X 轴标签竖排、过长标签截断、饼图类别过多时合并为「其他」，避免文字重叠
- 兼容旧版 matplotlib 的箱线图参数
"""

import platform

import pandas as pd
import matplotlib

matplotlib.use("Agg")  # 无界面后端；嵌入 tkinter 时只取 Figure 对象，全程序只在此设定一次
import matplotlib.pyplot as plt

# 中文显示设置：按操作系统挑选可用字体
_system = platform.system()
if _system == "Windows":
    _fonts = ["Microsoft YaHei", "SimHei", "SimSun", "sans-serif"]
elif _system == "Darwin":
    _fonts = ["PingFang SC", "Hiragino Sans GB", "sans-serif"]
else:
    _fonts = ["Noto Sans CJK SC", "WenQuanYi Micro Hei", "sans-serif"]
plt.rcParams["font.sans-serif"] = _fonts
plt.rcParams["axes.unicode_minus"] = False

CHART_TYPES = ["直方图", "柱状图", "折线图", "散点图", "箱线图", "饼图"]


def _shorten(label, max_len=8):
    """过长的标签截断，防止文字重叠"""
    label = str(label)
    return label if len(label) <= max_len else label[:max_len - 1] + "…"


def _text_width(s):
    """标签的显示宽度：一个中文字符算 1，英文数字等半角字符算半个"""
    return sum(0.5 if ord(ch) < 128 else 1 for ch in str(s))


def _fix_xticks(ax, labels, positions=None):
    """X 轴标签防重叠：先估算横向空间，放得下就正常横排，放不下才竖排
    （旋转 90 度），过长标签同时截断，避免文字相互重叠"""
    labels = [_shorten(x) for x in labels]
    ax.set_xticks(list(range(len(labels))) if positions is None else list(positions))
    # 可用横排宽度约合 56 个中文字符（该值与 make_figure 的 figsize=(7, 4.8)
    # 耦合：7 英寸 ÷ 0.125 英寸/字。改画布宽度时须同步调整此阈值），
    # 标签数 ×（最宽标签 + 2 字间隔）超过它就竖排
    widest = max((_text_width(x) for x in labels), default=0)
    rotation = 90 if len(labels) * (widest + 2) > 56 else 0
    ax.set_xticklabels(labels, rotation=rotation, ha="center", fontsize=9)


def make_figure(df, chart_type, x_col, y_col=None):
    """根据选择生成 matplotlib 图表对象"""
    fig, ax = plt.subplots(figsize=(7, 4.8), dpi=100)

    if chart_type == "直方图":
        if not pd.api.types.is_numeric_dtype(df[x_col]):
            raise ValueError(f"直方图只能用于数值列，「{x_col}」是文本列。\n建议改用「饼图」查看各类别占比。")
        data = df[x_col].dropna()
        ax.hist(data, bins=15, color="#4C78A8", edgecolor="white")
        ax.set_xlabel(x_col)
        ax.set_ylabel("频数")
        ax.set_title(f"{x_col} 分布直方图")

    elif chart_type == "柱状图":
        grouped = df.groupby(x_col)[y_col].mean().round(2)
        labels = [str(i) for i in grouped.index]
        ax.bar(range(len(labels)), grouped.values, color="#F58518")
        _fix_xticks(ax, labels)
        ax.set_xlabel(x_col)
        ax.set_ylabel(f"{y_col}（平均值）")
        ax.set_title(f"各{x_col}的{y_col}平均值")
        # 柱顶标数值，错开放纵轴文字
        for i, v in enumerate(grouped.values):
            ax.text(i, v, str(v), ha="center", va="bottom", fontsize=8)

    elif chart_type == "折线图":
        data = df[[x_col, y_col]].dropna()
        try:  # X 能转数字就按数字排序，折线才不乱跳
            data = data.assign(**{x_col: pd.to_numeric(data[x_col])})
        except (ValueError, TypeError):
            pass
        data = data.sort_values(by=x_col).reset_index(drop=True)
        ax.plot(range(len(data)), data[y_col], marker="o", markersize=3, color="#54A24B")
        step = max(1, len(data) // 10)  # 最多标 10 个刻度，防止重叠
        positions = list(range(0, len(data), step))
        _fix_xticks(ax, [data[x_col].iloc[p] for p in positions], positions)
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.set_title(f"{y_col} 随 {x_col} 的变化")

    elif chart_type == "散点图":
        ax.scatter(df[x_col], df[y_col], alpha=0.7, color="#B279A2")
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.set_title(f"{x_col} 与 {y_col} 的关系")

    elif chart_type == "箱线图":
        groups = [(str(k), g[y_col].dropna()) for k, g in df.groupby(x_col)]
        labels = [g[0] for g in groups]
        ax.boxplot([g[1] for g in groups])
        # boxplot 默认把刻度放在 1..N，须显式传位置，_fix_xticks 才能对齐
        _fix_xticks(ax, labels, positions=range(1, len(labels) + 1))
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.set_title(f"{y_col} 按 {x_col} 分组的箱线图")

    elif chart_type == "饼图":
        counts = df[x_col].value_counts()
        # 类别太多时合并尾部为“其他”，防止标签挤在一起
        if len(counts) > 6:
            top = counts.head(5)
            top["其他"] = counts.iloc[5:].sum()
            counts = top
        labels = [_shorten(x) for x in counts.index]
        ax.pie(counts.values, labels=labels, autopct="%.1f%%",
               textprops={"fontsize": 9}, startangle=90)
        ax.set_title(f"{x_col} 占比")

    fig.tight_layout()  # 自动留白，避免标题和坐标轴文字被裁切
    return fig
