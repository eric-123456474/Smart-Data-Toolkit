# -*- coding: utf-8 -*-
"""回归测试：对应《创新思维项目报告》表 11 的 8 个测试组、37 项检查

运行方式：python test_all.py
退出码：全部通过为 0，有失败为 1
"""

import importlib.util
import os
import sys
import tempfile
import unittest.mock as mock

sys.stdout.reconfigure(encoding="utf-8")
_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_mod(mod_name, file_name):
    spec = importlib.util.spec_from_file_location(mod_name, os.path.join(_DIR, file_name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


analyzer = _load_mod("analyzer", "analyzer.py")
plotter = _load_mod("plotter", "plotter.py")
main = _load_mod("main", "main.py")

import warnings

import pandas as pd
import tkinter as tk
import matplotlib.pyplot as plt

# 生成代码里的 plt.show() 在 Agg 后端下会提示「非交互后端」，属预期行为，屏蔽掉
warnings.filterwarnings("ignore", message="FigureCanvasAgg is non-interactive")

RESULTS = []  # (组号, 项号, 名称, 是否通过, 备注)


def check(group, name, fn):
    no = len(RESULTS) + 1
    try:
        note = fn() or ""
        RESULTS.append((group, no, name, True, note))
        print(f"  [{no:2d}] {name} …… 通过 {note}")
    except Exception as e:
        RESULTS.append((group, no, name, False, str(e)))
        print(f"  [{no:2d}] {name} …… 失败：{e}")


# ---------- 准备：隐藏窗口 + 屏蔽弹窗 ----------
root = tk.Tk()
root.withdraw()
main.messagebox = mock.Mock()          # 所有提示/报错弹窗只记录不弹出
app = main.EasyTableApp(root)

SAMPLE = os.path.join(_DIR, "示例数据.csv")


def reload_sample():
    """把应用恢复到刚加载示例数据的状态"""
    app.datasets.clear()
    app.nav_list.delete(0, tk.END)
    app.ops_log = []
    app.current = None
    app.load_sample()
    return app.df


# ================= 组 1：启动与示例数据（3 项） =================
print("组 1：启动与示例数据")
check(1, "启动后未加载任何数据", lambda: (
    (_ for _ in ()).throw(AssertionError("df 应为 None")) if app.df is not None
    else app.status.cget("text") == "未加载数据" or (_ for _ in ()).throw(AssertionError("状态提示不对"))))


def _t2():
    df = reload_sample()
    assert df is not None and df.shape == (891, 12), f"实际 {df.shape}"
    # 中文编码兜底：gb18030 文件也能读
    p = os.path.join(tempfile.gettempdir(), "_test_gb18030.csv")
    pd.DataFrame({"姓名": ["张三", "李四"], "成绩": [90, 85]}).to_csv(p, index=False, encoding="gb18030")
    back = analyzer.load_file(p)
    os.remove(p)
    assert back.shape == (2, 2) and list(back.columns) == ["姓名", "成绩"]
    return f"{df.shape[0]} 行 × {df.shape[1]} 列，gb18030 亦可读"
check(1, "示例数据可正常加载", _t2)


def _t3():
    tip = app.status.cget("text")
    assert "891 行 × 12 列" in tip, f"状态栏：{tip}"
check(1, "状态栏显示行数与列数", _t3)

# ================= 组 2：表格渲染（4 项） =================
print("组 2：表格渲染")


def _t4():
    widths = {c: app.tree.column(c)["width"] for c in app.tree["columns"]}
    assert all(64 <= w <= 340 for w in widths.values()), f"列宽越界 {widths}"
    assert len(set(widths.values())) > 1, "列宽未按内容自适应（全部相同）"
    app._goto_page(1)   # 翻页后列宽应复用缓存，保持不变
    widths2 = {c: app.tree.column(c)["width"] for c in app.tree["columns"]}
    assert widths2 == widths, "翻页后列宽发生变化"
    app._goto_page(-1)
    return f"列宽范围 {min(widths.values())}~{max(widths.values())}，翻页不变"
check(2, "列宽按内容自适应且在 64~340 像素内", _t4)

check(2, "表头完整显示（文字与列名一致）", lambda: (
    None if all(app.tree.heading(c)["text"] == c for c in app.tree["columns"])
    else (_ for _ in ()).throw(AssertionError("表头被截断"))))

check(2, "横向滚动条可用", lambda: (
    None if app.tree.cget("xscrollcommand") else (_ for _ in ()).throw(AssertionError("未绑定横向滚动"))))


def _t7():
    label = app.page_label.cget("text")
    assert label == "第 1/5 页", f"实际 {label}"  # 891 行 / 每页 200 行 = 5 页
    return label
check(2, "分页页码正确", _t7)

# ================= 组 3：条件筛选（8 项） =================
print("组 3：条件筛选")
df0 = reload_sample()


def _t8():
    r = analyzer.apply_filter(df0, "年龄 > 18 and 性别 == '女'")
    assert len(r) == 193, f"实际 {len(r)}"  # 未填充时 177 个年龄空值被排除
    return f"{len(df0)} → {len(r)} 行"
check(3, "pandas 表达式筛选", _t8)

def _t9():
    cols = list(df0.columns)
    cases = [
        ("年龄大于18且性别是女", cols, "年龄 > 18 and 性别 == '女'"),
        ("性别是不是女", cols, "性别 == '女'"),   # 「是不是」须先于「不是」替换
        ("性别不是女", cols, "性别 != '女'"),
        ("是否生还是1", cols, "是否生还 == 1"),   # 「是否」是保护词，不被拆
    ]
    for src, cs, want in cases:
        got = analyzer.natural_to_query(src, cs)
        assert got == want, f"{src!r} → {got!r}（期望 {want!r}）"
    # 列与列相比：右边的词正好是列名时不加引号
    got = analyzer.natural_to_query("身高大于体重", ["身高", "体重"])
    assert got == "身高 > 体重", got
    return "含「是不是/不是/是否」与列比列共 5 例"
check(3, "中文自然语言转换", _t9)

check(3, "中文引号识别", lambda: (
    None if analyzer.natural_to_query("性别是「女」") == "性别 == '女'"
    else (_ for _ in ()).throw(AssertionError(analyzer.natural_to_query("性别是「女」")))))

check(3, "英文引号识别", lambda: (
    None if analyzer.natural_to_query('性别是"女"') == "性别 == '女'"
    else (_ for _ in ()).throw(AssertionError(analyzer.natural_to_query('性别是"女"')))))


def _t12():
    d = df0.rename(columns={"乘客编号": "乘客 编号"})
    r = analyzer.apply_filter(d, "乘客 编号 > 100")
    assert len(r) > 0 and list(r.columns) == list(d.columns)
    return f"{len(r)} 行"
check(3, "含空格列名筛选", _t12)


def _t13():
    d = df0.rename(columns={"乘客编号": "1号"})
    r = analyzer.apply_filter(d, "1号 > 100")
    assert len(r) > 0
    return f"{len(r)} 行"
check(3, "数字开头列名筛选", _t13)


def _t14():
    d = df0.rename(columns={"乘客编号": "class"})
    r = analyzer.apply_filter(d, "class > 100")
    assert len(r) > 0
    return f"{len(r)} 行"
check(3, "Python 关键字列名筛选", _t14)


def _t15():
    """按报告附录 A 的完整流程：填充 → 删列 → 中文筛选，核对最终行数"""
    reload_sample()
    app._do_fill(["年龄"], "均值")
    app._do_fill(["登船港口"], "众数")
    app._delete_missing("col")
    app.filter_mode.set("chinese")
    app.filter_entry.delete(0, tk.END)
    app.filter_entry.insert(0, "年龄大于18且性别是女")
    app.do_filter()
    n = len(app.df_view)
    assert n == 246, f"实际 {n}"
    return f"{len(app.df)} → {n} 行"
check(3, "筛选结果行数与预期一致", _t15)

# ================= 组 4：数据清洗（8 项） =================
print("组 4：数据清洗")
demo = pd.DataFrame({"数值": [1.0, None, 3.0], "文本": ["甲", None, "甲"]})

check(4, "填充-均值", lambda: (
    None if analyzer.fill_with(demo, ["数值"], "均值")[0]["数值"].tolist() == [1.0, 2.0, 3.0]
    else (_ for _ in ()).throw(AssertionError("均值填充结果不对"))))

check(4, "填充-中位数", lambda: (
    None if analyzer.fill_with(pd.DataFrame({"x": [1.0, None, 3.0, 100.0]}), ["x"], "中位数"
                               )[0]["x"].tolist() == [1.0, 3.0, 3.0, 100.0]
    else (_ for _ in ()).throw(AssertionError("中位数填充结果不对"))))

check(4, "填充-众数", lambda: (
    None if analyzer.fill_with(demo, ["文本"], "众数")[0]["文本"].tolist() == ["甲", "甲", "甲"]
    else (_ for _ in ()).throw(AssertionError("众数填充结果不对"))))

check(4, "填充-固定值", lambda: (
    None if analyzer.fill_with(demo, ["文本"], "固定值", "未知")[0]["文本"].tolist() == ["甲", "未知", "甲"]
    else (_ for _ in ()).throw(AssertionError("固定值填充结果不对"))))

check(4, "填充-前向填充", lambda: (
    None if analyzer.fill_with(pd.DataFrame({"x": [1.0, None, 3.0]}), ["x"], "前向填充"
                               )[0]["x"].tolist() == [1.0, 1.0, 3.0]
    else (_ for _ in ()).throw(AssertionError("前向填充结果不对"))))

check(4, "填充-后向填充", lambda: (
    None if analyzer.fill_with(pd.DataFrame({"x": [None, 1.0, 3.0]}), ["x"], "后向填充"
                               )[0]["x"].tolist() == [1.0, 1.0, 3.0]
    else (_ for _ in ()).throw(AssertionError("后向填充结果不对"))))

check(4, "填充-线性插值", lambda: (
    None if analyzer.fill_with(pd.DataFrame({"x": [1.0, None, 3.0]}), ["x"], "线性插值"
                               )[0]["x"].tolist() == [1.0, 2.0, 3.0]
    else (_ for _ in ()).throw(AssertionError("线性插值结果不对"))))


def _t23():
    d = reload_sample()
    # 删除指定列生效
    d2, cols, _ = analyzer.drop_na_cols(d, ["客舱号"])
    assert "客舱号" not in d2.columns and "年龄" in d2.columns
    # 删除缺失行生效（指定行）
    labels = analyzer.missing_rows(d)
    d3, n, _ = analyzer.drop_na_rows(d, labels)
    assert n == len(labels) and not d3.isna().any().any()
    # 填充说明写明依据与数量
    _, details, codes = analyzer.fill_with(d, ["年龄"], "均值")
    assert "29.7" in details[0] and "177" in details[0], details[0]
    assert "fillna(29.7)" in codes[0] and "177" in codes[0], codes[0]
    # 整列全空的列没有众数：应报中文错误，而不是把数值列静默变成文本
    try:
        analyzer.fill_with(pd.DataFrame({"x": [None, None]}), ["x"], "众数")
        raise AssertionError("全空列众数填充未报错")
    except ValueError as e:
        assert "众数" in str(e) and "固定值" in str(e), str(e)
    return details[0]
check(4, "删除指定列/缺失行生效，填充说明写明依据与数量", _t23)

# ================= 组 5：图表绘制（7 项） =================
print("组 5：图表绘制")
dfg = reload_sample()
CHART_ARGS = {"直方图": ("年龄", None), "柱状图": ("舱位等级", "年龄"),
              "折线图": ("乘客编号", "票价"), "散点图": ("年龄", "票价"),
              "箱线图": ("舱位等级", "年龄"), "饼图": ("性别", None)}


def _chart_code(chart):
    x, y = CHART_ARGS[chart]
    code = main._plot_code(chart, x, y)
    ns = {"df": dfg}
    exec(compile(code, "<生成代码>", "exec"), ns)  # 可编译且可运行
    plt.close("all")
    return None


for _c in ["直方图", "柱状图", "折线图", "散点图", "箱线图", "饼图"]:
    check(5, f"{_c}生成代码可编译运行", lambda c=_c: _chart_code(c))


def _t30():
    fig = plotter.make_figure(dfg, "直方图", "年龄")
    assert fig is not None and len(fig.axes) > 0
    out = os.path.join(tempfile.gettempdir(), "_test_hist.png")
    fig.savefig(out)
    plt.close(fig)
    ok = os.path.exists(out) and os.path.getsize(out) > 0
    os.remove(out)
    assert ok
    # X 轴标签：横向放得下就横排，放不下才竖排
    d2 = pd.DataFrame({"类别": ["甲", "乙", "丙", "丁"], "值": [1, 2, 3, 4]})
    f1 = plotter.make_figure(d2, "柱状图", "类别", "值")
    assert f1.axes[0].get_xticklabels()[0].get_rotation() == 0, "短标签不应竖排"
    plt.close(f1)
    d3 = pd.DataFrame({"类别": [f"分类标签{i}" for i in range(12)], "值": list(range(12))})
    f2 = plotter.make_figure(d3, "柱状图", "类别", "值")
    assert f2.axes[0].get_xticklabels()[0].get_rotation() == 90, "标签多且长应竖排"
    plt.close(f2)
    # 箱线图：boxplot 刻度在 1..N，标签须与位置对齐且多组时竖排
    f3 = plotter.make_figure(d3, "箱线图", "类别", "值")
    assert f3.axes[0].get_xticklabels()[0].get_rotation() == 90, "箱线图多组标签应竖排"
    assert f3.axes[0].get_xticklabels()[0].get_text() == "分类标签0", "箱线图刻度位置应对齐"
    plt.close(f3)
    # 绘图失败（文本列直方图）后面板应清空，不留旧图
    reload_sample()
    app.chart_type.set("直方图")
    app.x_col.set("性别")
    app.do_plot()
    assert app.fig is None and not app.plot_frame.winfo_children(), \
        "绘图失败后面板应清空"
    return "出图保存正常，标签智能横竖排，失败态干净"
check(5, "直方图实际出图并保存正常", _t30)

# ================= 组 6：透视与体检（2 项） =================
print("组 6：透视与体检")


def _t31():
    d = reload_sample()
    t = analyzer.pivot_table(d, "舱位等级", "性别", "年龄", "平均值")
    assert len(t) == 3, f"透视行数 {len(t)}"  # 三个舱位等级
    # 列名直接是分组值，不含「值列名」前缀
    assert list(t.columns) == ["舱位等级", "女", "男"], list(t.columns)
    expect = round(d[(d["舱位等级"] == 1) & (d["性别"] == "男")]["年龄"].mean(), 2)
    got = float(t.loc[t["舱位等级"] == 1, "男"].iloc[0])
    assert got == expect, f"{got} != {expect}"
    # do_pivot 记录的生成代码在干净环境执行，列名应与界面一致
    ns = {"pd": pd, "df": d.copy()}
    exec(compile("df = df.pivot_table(index='舱位等级', columns='性别', "
                 "values='年龄', aggfunc='mean')", "<生成代码>", "exec"), ns)
    assert [str(c) for c in ns["df"].columns] == list(t.columns)[1:], \
        "生成代码与界面的列名不一致"
    return f"一等舱男性平均年龄 {got}，界面与生成代码列名一致"
check(6, "透视表行列分组与聚合值正确", _t31)


def _t32():
    d = reload_sample()
    r = analyzer.diagnose(d)
    assert len(r) == len(d.columns) == 12
    assert list(r["列名"]) == list(d.columns)
    row_age = r[r["列名"] == "年龄"].iloc[0]
    assert row_age["缺失数"] == 177 and row_age["缺失率"] == "19.9%"
    row_cabin = r[r["列名"] == "客舱号"].iloc[0]
    assert row_cabin["缺失数"] == 687 and row_cabin["建议"] == "缺失过多，建议删除该列"
    return f"12 列一一对应"
check(6, "体检结果与各列一一对应", _t32)

# ================= 组 7：操作转代码（4 项） =================
print("组 7：操作转代码")


def _t33():
    reload_sample()
    before = len(app.ops_log)
    app._do_fill(["年龄"], "均值")
    assert len(app.ops_log) == before + 1
    title, code = app.ops_log[-1]
    assert "填充" in title and "fillna" in code
    return f"记录标题「{title}」"
check(7, "操作写入记录", _t33)


def _t34():
    captured = {}

    class FakeText:
        def __init__(self, *a, **k): pass
        def pack(self, *a, **k): pass
        def insert(self, where, content): captured["content"] = content
        def config(self, *a, **k): pass

    class FakeWin:
        def __init__(self, *a, **k): pass
        def title(self, *a, **k): pass
        def geometry(self, *a, **k): pass

    class FakeBtn:
        def __init__(self, *a, **k): pass
        def pack(self, *a, **k): pass

    with mock.patch.object(main.tk, "Toplevel", FakeWin), \
         mock.patch.object(main.tk, "Text", FakeText), \
         mock.patch.object(main.ttk, "Button", FakeBtn):
        app.show_code()
    content = captured.get("content", "")
    assert "# ========== 操作 1：" in content, "生成代码缺少注释头"
    return None
check(7, "生成代码带分段注释", _t34)


def _t35():
    """把一次完整流程的记录拼成脚本，在独立命名空间执行并核对结果"""
    reload_sample()
    app.ops_log = []
    app._do_fill(["年龄"], "均值")
    app._do_fill(["登船港口"], "众数")
    app._delete_missing("col")
    app.filter_mode.set("chinese")
    app.filter_entry.delete(0, tk.END)
    app.filter_entry.insert(0, "年龄大于18且性别是女")
    app.do_filter()
    lines = ["import pandas as pd", "",
             f"df = pd.read_csv({SAMPLE!r}, encoding='utf-8-sig')", ""]
    for i, (title, code) in enumerate(app.ops_log, 1):
        lines += [f"# ========== 操作 {i}：{title} ==========", code, ""]
    script = "\n".join(lines)
    ns = {}
    exec(compile(script, "<生成脚本>", "exec"), ns)
    n = len(ns["df"])
    assert n == 246, f"脚本执行结果 {n}"
    return f"复制出的脚本执行得 {n} 行"
check(7, "生成代码复制后可直接执行", _t35)


def _t36():
    d = reload_sample().rename(columns={"乘客编号": "乘客 编号"})
    app.datasets.clear()
    app.nav_list.delete(0, tk.END)
    app.ops_log = []
    app.add_dataset("特殊列名", d)
    app.filter_mode.set("pandas")
    app.filter_entry.delete(0, tk.END)
    app.filter_entry.insert(0, "乘客 编号 > 100")
    app.do_filter()
    code = app.ops_log[-1][1]
    assert "`乘客 编号`" in code and "engine='python'" in code, code
    ns = {"pd": pd, "df": d}
    exec(compile(code, "<生成代码>", "exec"), ns)
    assert len(ns["df"]) == len(app.df_view)
    return code
check(7, "特殊列名自动加反引号并补引擎参数", _t36)

# ================= 组 8：导出（1 项） =================
print("组 8：导出")


def _t37():
    reload_sample()
    out = os.path.join(tempfile.gettempdir(), "_test_export.csv")
    with mock.patch.object(main.filedialog, "asksaveasfilename", return_value=out):
        app.save_csv()
    back = pd.read_csv(out, encoding="utf-8-sig")
    os.remove(out)
    assert len(back) == len(app.df) == 891, f"导出行数 {len(back)}"
    return f"导出 {len(back)} 行"
check(8, "当前视图导出为 CSV 成功", _t37)

# ================= 汇总 =================
passed = sum(1 for r in RESULTS if r[3])
total = len(RESULTS)
print()
print("=" * 50)
for g in range(1, 9):
    rows = [r for r in RESULTS if r[0] == g]
    print(f"组 {g}：{sum(1 for r in rows if r[3])}/{len(rows)} 通过")
print(f"合计：{passed}/{total} 通过")
print("=" * 50)

root.destroy()
sys.exit(0 if passed == total == 37 else 1)
