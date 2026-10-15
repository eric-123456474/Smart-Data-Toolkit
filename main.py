# -*- coding: utf-8 -*-
"""智能数据处理与分析工具 —— 面向中文用户的可视化数据分析工具
运行方式：python main.py

主要功能：
1. 表格浏览：列宽按内容自适应（表头单行完整显示），横向滚动可看到全部列，每页 200 行分页
2. 选中单元格时在表格下方完整显示其内容，长文本不被截断；双击单元格可直接修改
3. 数据筛选：支持 pandas 表达式与中文自然语言（如「年龄大于18且性别是女」）
4. 数据清洗：规范列名、填充缺失值、删除含缺失行、删除重复行、文本列转数值
5. 图表绘制：直方图、柱状图、折线图、散点图、箱线图、饼图，中文标签防重叠，可存图
6. 数据透视：行分组 × 列分组 × 值列 × 聚合方式
7. 数据体检：逐列诊断缺失率、异常值并给出处理建议
8. 统计摘要：各列计数、均值、标准差、最值与分位数
9. 操作转代码：每一步操作自动生成可直接运行的 pandas 代码，支持一键复制分享
10. 多数据集管理：可同时挂载多个数据集随时切换，处理结果可导出为 CSV
"""

import importlib.util
import math
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont

import pandas as pd

_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_mod(mod_name, file_name):
    """按文件路径加载同目录下的模块（避免依赖当前工作目录）"""
    spec = importlib.util.spec_from_file_location(mod_name, os.path.join(_DIR, file_name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


analyzer = _load_mod("analyzer", "analyzer.py")
plotter = _load_mod("plotter", "plotter.py")

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402
from matplotlib import pyplot as plt  # noqa: E402  (plotter 已统一设定 Agg 后端)

PAGE_SIZE = 200  # 表格每页显示的行数

# 引用模块中的函数
load_file = analyzer.load_file
normalize_columns = analyzer.normalize_columns
fill_with = analyzer.fill_with
FILL_METHODS = analyzer.FILL_METHODS
FILL_ORDER = analyzer.FILL_ORDER
drop_na_rows = analyzer.drop_na_rows
drop_na_cols = analyzer.drop_na_cols
missing_rows = analyzer.missing_rows
missing_columns = analyzer.missing_columns
drop_duplicate_rows = analyzer.drop_duplicate_rows
to_numeric = analyzer.to_numeric
apply_filter = analyzer.apply_filter
query_expr = analyzer.query_expr
natural_to_query = analyzer.natural_to_query
sort_by = analyzer.sort_by
set_value = analyzer.set_value
pivot_table = analyzer.pivot_table
summarize = analyzer.summarize
diagnose = analyzer.diagnose
_parse_value = analyzer._parse_value
AGG_FUNCS = analyzer.AGG_FUNCS
make_figure = plotter.make_figure
CHART_TYPES = plotter.CHART_TYPES


def _plot_code(chart, x, y=None):
    """把一次绘图操作翻译成可运行的 matplotlib 代码，供「生成代码」展示"""
    lines = [
        "import matplotlib.pyplot as plt",
        "plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']  # 让中文正常显示",
        "plt.rcParams['axes.unicode_minus'] = False",
    ]
    title = None
    if chart == "直方图":
        lines.append(f"df[{x!r}].hist(bins=15)")
        title = f"{x} 分布直方图"
    elif chart == "柱状图":
        lines.append(f"df.groupby({x!r})[{y!r}].mean().plot(kind='bar')")
        title = f"各{x}的{y}平均值"
    elif chart == "折线图":
        lines.append(f"df.sort_values({x!r}).plot(x={x!r}, y={y!r})")
        title = f"{y} 随 {x} 的变化"
    elif chart == "散点图":
        lines.append(f"df.plot(kind='scatter', x={x!r}, y={y!r})")
        title = f"{x} 与 {y} 的关系"
    elif chart == "箱线图":
        lines.append(f"df.boxplot(column={y!r}, by={x!r})")
        title = f"{y} 按 {x} 分组"
    elif chart == "饼图":
        lines.append(f"df[{x!r}].value_counts().plot(kind='pie', autopct='%.1f%%')")
        title = f"{x} 占比"
    if title:
        lines.append("plt.title(%r)" % title)
    lines.append("plt.show()")
    return "\n".join(lines)


class EasyTableApp:
    def __init__(self, root):
        self.root = root
        self.root.title("智能数据处理与分析工具")
        self.root.geometry("1280x780")

        self.datasets = {}    # {名称: DataFrame}，支持多数据集切换
        self.current = None   # 当前数据集名称
        self.df_view = None   # 当前显示（可能被筛选/排序）
        self.filtered = False
        self.filter_expr = None
        self.sort_col = None     # 当前排序列
        self.sort_asc = True
        self.ops_log = []        # 操作记录 [(操作说明, 对应代码), ...]
        self.fig = None          # 当前图表
        self.page = 0            # 当前页码（从 0 开始）
        self.cell_col_idx = 0    # 最近点击的列序号，用于显示完整单元格内容
        self._col_widths = {}    # 列宽缓存：切换数据集/数据变更时算一次，翻页与排序复用

        self._build_toolbar()
        self._build_log()   # 先占住底部空间，避免图表撑高后把「操作日志」挤出窗口
        self._build_body()
        self.log("欢迎使用智能数据处理与分析工具！请点击「导入数据」载入 CSV/Excel 文件，或点「加载示例」体验内置示例数据。")

    # ---------- 界面搭建 ----------

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=4)
        bar.pack(side=tk.TOP, fill=tk.X)
        btns = [
            ("导入数据", self.load_file),
            ("加载示例", self.load_sample),
            ("重置视图", self.reset_data),
            ("数据体检", self.show_diagnose),
            ("统计摘要", self.show_summary),
            ("生成代码", self.show_code),
            ("导出 CSV", self.save_csv),
        ]
        for text, cmd in btns:
            ttk.Button(bar, text=text, command=cmd).pack(side=tk.LEFT, padx=3)

    def _build_body(self):
        body = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        # 左：数据集导航
        nav = ttk.LabelFrame(body, text="数据集", padding=4)
        body.add(nav, weight=1)
        self.nav_list = tk.Listbox(nav, exportselection=False)
        self.nav_list.pack(fill=tk.BOTH, expand=True)
        self.nav_list.bind("<<ListboxSelect>>", self.switch_dataset)

        # 中：表格
        center = ttk.Frame(body)
        body.add(center, weight=4)
        self.tree = ttk.Treeview(center, show="headings")
        vsb = ttk.Scrollbar(center, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(center, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        pagebar = ttk.Frame(center)
        pagebar.grid(row=2, column=0, sticky="ew", pady=(2, 0))
        ttk.Button(pagebar, text="上一页", width=8,
                   command=lambda: self._goto_page(-1)).pack(side=tk.LEFT)
        self.page_label = ttk.Label(pagebar, text="第 1/1 页")
        self.page_label.pack(side=tk.LEFT, padx=8)
        ttk.Button(pagebar, text="下一页", width=8,
                   command=lambda: self._goto_page(1)).pack(side=tk.LEFT)
        ttk.Label(pagebar, text="（双击单元格可直接修改；点击表头排序）",
                  foreground="gray").pack(side=tk.LEFT, padx=10)

        # 选中单元格时在下方完整显示其内容，避免长文本被列宽截断
        self.cell_label = ttk.Label(center, text="", anchor="w", wraplength=900)
        self.cell_label.grid(row=3, column=0, sticky="ew", pady=(2, 0))

        self.status = ttk.Label(center, text="未加载数据", anchor="w")
        self.status.grid(row=4, column=0, sticky="ew", pady=(2, 0))
        center.rowconfigure(0, weight=1)
        center.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self.edit_cell)
        self.tree.bind("<<TreeviewSelect>>", self.show_cell_value)
        self.tree.bind("<ButtonRelease-1>", self._on_cell_click)

        # 右：功能标签页
        tabs = ttk.Notebook(body)
        body.add(tabs, weight=2)
        self._tab_filter(tabs)
        self._tab_plot(tabs)
        self._tab_pivot(tabs)
        self._tab_clean(tabs)

    def _build_log(self):
        frame = ttk.LabelFrame(self.root, text="操作日志", padding=3)
        frame.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=(0, 6))
        self.log_text = tk.Text(frame, height=6, wrap="word")
        self.log_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.log_text.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=sb.set)

    def _tab_filter(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="筛选")
        ttk.Label(tab, text="条件写法：").pack(anchor="w")
        self.filter_mode = tk.StringVar(value="pandas")
        modebar = ttk.Frame(tab)
        modebar.pack(anchor="w", pady=2)
        ttk.Radiobutton(modebar, text="pandas 表达式", variable=self.filter_mode,
                        value="pandas").pack(side=tk.LEFT)
        ttk.Radiobutton(modebar, text="中文描述", variable=self.filter_mode,
                        value="chinese").pack(side=tk.LEFT, padx=6)
        self.filter_entry = ttk.Entry(tab)
        self.filter_entry.pack(fill=tk.X, pady=4)
        self.filter_entry.insert(0, "年龄 > 18")
        ttk.Button(tab, text="执行筛选", command=self.do_filter).pack(fill=tk.X, pady=2)
        ttk.Button(tab, text="清除筛选", command=self.clear_filter).pack(fill=tk.X, pady=2)
        ttk.Label(tab, text="pandas 表达式示例：\n年龄 > 18\n城市 == '北京'\n"
                            "数学成绩 >= 80 and 性别 == '女'",
                  foreground="gray", justify="left").pack(anchor="w", pady=6)
        ttk.Label(tab, text='中文描述示例：\n年龄大于18\n城市是北京并且性别是女\n'
                            '列名或文本值都可加引号，中文引号和英文引号都支持：\n'
                            '"城市"是"北京"、「是否生还」是「是」\n'
                            '两列相比直接写列名，如：身高大于体重',
                  foreground="gray", justify="left").pack(anchor="w")

    def _tab_plot(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="图表")
        ttk.Label(tab, text="图表类型：").pack(anchor="w")
        self.chart_type = ttk.Combobox(tab, values=CHART_TYPES, state="readonly")
        self.chart_type.set("直方图")
        self.chart_type.pack(fill=tk.X, pady=2)
        self.chart_type.bind("<<ComboboxSelected>>", lambda e: self._update_chart_hint())
        ttk.Label(tab, text="X 列：").pack(anchor="w")
        self.x_col = ttk.Combobox(tab, state="readonly")
        self.x_col.pack(fill=tk.X, pady=2)
        ttk.Label(tab, text="Y 列：").pack(anchor="w")
        self.y_col = ttk.Combobox(tab, state="readonly")
        self.y_col.pack(fill=tk.X, pady=2)
        self.chart_hint = ttk.Label(tab, text="", foreground="gray")
        self.chart_hint.pack(anchor="w")
        ttk.Button(tab, text="生成图表", command=self.do_plot).pack(fill=tk.X, pady=4)
        ttk.Button(tab, text="保存图表为图片", command=self.save_figure).pack(fill=tk.X, pady=2)
        self.plot_frame = ttk.Frame(tab)
        self.plot_frame.pack(fill=tk.BOTH, expand=True, pady=4)
        self._update_chart_hint()

    def _tab_pivot(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="透视")
        ttk.Label(tab, text="行分组：").pack(anchor="w")
        self.pv_index = ttk.Combobox(tab, state="readonly")
        self.pv_index.pack(fill=tk.X, pady=2)
        ttk.Label(tab, text="列分组：").pack(anchor="w")
        self.pv_column = ttk.Combobox(tab, state="readonly")
        self.pv_column.pack(fill=tk.X, pady=2)
        ttk.Label(tab, text="值列（数值）：").pack(anchor="w")
        self.pv_value = ttk.Combobox(tab, state="readonly")
        self.pv_value.pack(fill=tk.X, pady=2)
        ttk.Label(tab, text="聚合方式：").pack(anchor="w")
        self.pv_agg = ttk.Combobox(tab, values=list(AGG_FUNCS.keys()), state="readonly")
        self.pv_agg.set("平均值")
        self.pv_agg.pack(fill=tk.X, pady=2)
        ttk.Button(tab, text="生成透视表", command=self.do_pivot).pack(fill=tk.X, pady=6)
        ttk.Label(tab, text="示例：行分组=城市，列分组=性别，值列=数学成绩",
                  foreground="gray", justify="left").pack(anchor="w")

    def _tab_clean(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="清洗")
        for text, cmd in [
            ("规范列名", self.do_normalize),
            ("填充缺失值", self.open_fill_dialog),
            ("删除缺失行", lambda: self.open_delete_dialog("row")),
            ("删除缺失列", lambda: self.open_delete_dialog("col")),
            ("删除重复行", self.do_drop_duplicates),
        ]:
            ttk.Button(tab, text=text, command=cmd).pack(fill=tk.X, pady=2)
        ttk.Separator(tab, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        ttk.Label(tab, text="选择列转数值型：").pack(anchor="w")
        self.convert_col = ttk.Combobox(tab, state="readonly")
        self.convert_col.pack(fill=tk.X, pady=2)
        ttk.Button(tab, text="转换", command=self.do_to_numeric).pack(fill=tk.X, pady=2)

    # ---------- 通用 ----------

    @property
    def df(self):
        return self.datasets.get(self.current)

    def log(self, msg):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)

    def require_data(self):
        if self.df is None:
            messagebox.showinfo("提示", "请先导入或加载数据")
            return False
        return True

    def add_dataset(self, name, df):
        """注册数据集并在导航列表中选中"""
        if name in self.datasets:  # 重名自动加序号
            i = 2
            while f"{name}_{i}" in self.datasets:
                i += 1
            name = f"{name}_{i}"
        self.datasets[name] = df
        self.nav_list.insert(tk.END, name)
        self.nav_list.selection_clear(0, tk.END)
        self.nav_list.selection_set(tk.END)
        self.nav_list.see(tk.END)
        self.switch_dataset()

    def switch_dataset(self, event=None):
        sel = self.nav_list.curselection()
        if not sel:
            return
        self.current = self.nav_list.get(sel[0])
        self.filtered = False
        self.filter_expr = None
        self.sort_col = None
        self.sort_asc = True
        self.page = 0
        self.cell_col_idx = 0   # 换了数据集，重置单元格列序号，避免沿用上一个数据集的列
        self.df_view = self.df
        self._compute_widths()
        self.refresh()

    def _measure_col(self, col, series, f_head, f_cell):
        """单列宽度：取表头和前 500 行内容的最大宽度（保证二者都完整显示）"""
        w = f_head.measure(str(col))
        for v in series.head(500):
            if pd.notna(v):
                w = max(w, f_cell.measure(str(v)))
        return min(max(w + 26, 64), 340)

    def _compute_widths(self):
        """列宽按内容自适应，结果存入缓存；只在切换数据集和数据变更时重算"""
        self._col_widths = {}
        if self.df is None:
            return
        f_head = tkfont.nametofont("TkHeadingFont")
        f_cell = tkfont.nametofont("TkDefaultFont")
        for c in self.df.columns:
            self._col_widths[str(c)] = self._measure_col(c, self.df[c], f_head, f_cell)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.cell_label.config(text="")
        if self.df_view is None:
            self.status.config(text="未加载数据")
            self.page_label.config(text="第 1/1 页")
            return
        df = self.df_view
        cols = [str(c) for c in df.columns]

        # 分页
        total_pages = max(1, math.ceil(len(df) / PAGE_SIZE))
        if self.page >= total_pages:
            self.page = total_pages - 1
        start = self.page * PAGE_SIZE
        page_df = df.iloc[start:start + PAGE_SIZE]

        self.tree["columns"] = cols
        for c in cols:
            # 表头单行显示：Tk 表头行高固定，多行文字会被裁掉
            self.tree.heading(c, text=c, command=lambda c=c: self.sort_column(c))
            # 列宽用缓存（切换数据集/数据变更时已按内容算好），翻页与排序直接复用
            w = self._col_widths.get(c)
            if w is None:
                w = self._measure_col(c, df[c],
                                      tkfont.nametofont("TkHeadingFont"),
                                      tkfont.nametofont("TkDefaultFont"))
            self.tree.column(c, width=w, minwidth=48, anchor="center", stretch=False)

        for _, row in page_df.iterrows():
            vals = ["" if pd.isna(v) else str(v) for v in row]
            self.tree.insert("", tk.END, values=vals)

        tip = f"{self.current}：{len(df)} 行 × {len(df.columns)} 列"
        if self.filtered:
            tip += f"（已筛选，原 {len(self.df)} 行）"
        if self.sort_col:
            tip += f"（按「{self.sort_col}」{'升序' if self.sort_asc else '降序'}）"
        tip += f"  |  缺失值 {int(self.df.isna().sum().sum())} 个"
        self.status.config(text=tip)
        self.page_label.config(text=f"第 {self.page + 1}/{total_pages} 页")
        self.root.title(f"智能数据处理与分析工具 - {self.current}")
        # 更新所有列下拉框
        num_cols = list(self.df.select_dtypes(include="number").columns)
        for combo in (self.x_col, self.y_col, self.convert_col, self.pv_index, self.pv_column):
            combo["values"] = cols
        self.pv_value["values"] = num_cols
        if cols:
            self.x_col.set(cols[0])
            self.y_col.set(num_cols[0] if num_cols else cols[0])
            self.convert_col.set(cols[0])
            self.pv_index.set(cols[0])
            self.pv_column.set(cols[min(1, len(cols) - 1)])
            self.pv_value.set(num_cols[0] if num_cols else cols[0])

    def _update_chart_hint(self):
        hints = {"直方图": "只需选 X 列（数值）", "饼图": "只需选 X 列（分类）"}
        self.chart_hint.config(text=hints.get(self.chart_type.get(), "需要选 X 列和 Y 列"))

    def _on_cell_click(self, event):
        """记录鼠标点击的列，供 show_cell_value 显示完整单元格内容"""
        if self.tree.identify_region(event.x, event.y) not in ("cell", "tree"):
            return
        col_id = self.tree.identify_column(event.x)  # 形如 "#3"
        if col_id and col_id[1:].isdigit():
            self.cell_col_idx = int(col_id[1:]) - 1
        self.show_cell_value()

    def show_cell_value(self, event=None):
        """选中单元格时，在表格下方完整显示其内容（长文本不再被列宽截断）"""
        sel = self.tree.selection()
        if not sel or self.df_view is None:
            self.cell_label.config(text="")
            return
        idx = self.cell_col_idx
        cols = list(self.df_view.columns)
        if not (0 <= idx < len(cols)):
            return
        global_pos = self.page * PAGE_SIZE + self.tree.index(sel[0])
        if global_pos >= len(self.df_view):
            return
        value = self.df_view.iloc[global_pos, idx]
        shown = "（空值）" if pd.isna(value) else str(value)
        self.cell_label.config(text=f"当前单元格【{cols[idx]}】= {shown}")

    def _goto_page(self, delta):
        if self.df_view is None:
            return
        total_pages = max(1, math.ceil(len(self.df_view) / PAGE_SIZE))
        new_page = min(max(self.page + delta, 0), total_pages - 1)
        if new_page != self.page:
            self.page = new_page
            self.refresh()

    def _record(self, title, code):
        """记录一步操作，保存「操作说明 + 对应代码」，供「生成代码」输出带注释的代码"""
        self.ops_log.append((title, code))

    def _mutate(self, new_df, title, log_msg, code):
        """清洗类操作的统一收尾：替换数据、清筛选与排序标记、记代码、刷新"""
        self.datasets[self.current] = new_df
        self.filtered = False
        self.filter_expr = None
        self.sort_col = None
        self.page = 0
        self.df_view = new_df
        self._compute_widths()
        if code:
            self._record(title, code)
        self.log(log_msg)
        self.refresh()

    # ---------- 数据集操作 ----------

    def load_sample(self):
        """手动加载内置示例数据（不自动加载，由用户决定）"""
        path = os.path.join(_DIR, "示例数据.csv")
        if not os.path.exists(path):
            messagebox.showinfo("提示", f"未找到示例数据文件：\n{path}")
            return
        try:
            df = load_file(path)
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            return
        self.add_dataset("示例数据", df)
        self.ops_log = []  # 换了数据集，清空操作记录，避免生成代码混入上一个数据集的步骤
        self.log(f"已加载示例数据：{df.shape[0]} 行 × {df.shape[1]} 列（含缺失值，适合演示清洗）")

    def load_file(self):
        path = filedialog.askopenfilename(
            title="导入数据",
            filetypes=[("CSV 文件", "*.csv"), ("Excel 文件", "*.xlsx")],
        )
        if not path:
            return
        try:
            df = load_file(path)
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            return
        name = os.path.splitext(os.path.basename(path))[0]
        self.add_dataset(name, df)
        self.ops_log = []  # 换了数据集，清空操作记录，避免生成代码混入上一个数据集的步骤
        self.log(f"已导入「{name}」：{df.shape[0]} 行 × {df.shape[1]} 列")

    def reset_data(self):
        if not self.require_data():
            return
        self.filtered = False
        self.filter_expr = None
        self.sort_col = None
        self.page = 0
        self.df_view = self.df
        self.refresh()
        self.log("视图已重置（排序与筛选已清除；清洗后的数据保留，如需原始数据请重新导入）")

    # ---------- 表格交互 ----------

    def sort_column(self, col):
        """点击表头排序（只影响显示，不改原数据）"""
        if self.df_view is None:
            return
        asc = not (self.sort_col == col and self.sort_asc)  # 同一列再次点击则反向
        try:
            self.df_view = sort_by(self.df_view, col, asc)
        except Exception as e:
            self.log(f"排序失败：{e}")
            return
        self.sort_col, self.sort_asc = col, asc
        self.page = 0
        self.refresh()
        self.log(f"已按「{col}」{'升序' if asc else '降序'}排列")

    def edit_cell(self, event):
        """双击单元格编辑（筛选状态下不允许，避免错位）"""
        if self.df is None:
            return
        if self.tree.identify_region(event.x, event.y) != "cell":
            return  # 双击表头是排序，不弹编辑提示
        if self.filtered:
            messagebox.showinfo("提示", "筛选状态下不能直接编辑，请先点「清除筛选」再修改")
            return
        row_iid = self.tree.identify_row(event.y)
        col_idx = int(self.tree.identify_column(event.x)[1:]) - 1
        col_name = self.df.columns[col_idx]
        row_pos = self.tree.index(row_iid)
        # 屏幕行 → 数据的真实行标签：排序后行序会变，必须用 df_view 反查
        real_label = self.df_view.index[self.page * PAGE_SIZE + row_pos]
        x, y, w, h = self.tree.bbox(row_iid, f"#{col_idx + 1}")
        old = self.df.loc[real_label, col_name]
        entry = ttk.Entry(self.tree)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, "" if pd.isna(old) else str(old))
        entry.focus()

        def commit(_=None):
            text = entry.get()
            entry.destroy()
            self.datasets[self.current] = set_value(self.df, real_label, col_name, text)
            self.df_view = self.df
            for _col in filter(None, [self.sort_col]):  # 编辑后保持原有排序
                self.df_view = sort_by(self.df_view, _col, self.sort_asc)
            self._record(f"修改单元格（行 {real_label}，列 {col_name}）",
                         f"df.loc[{real_label!r}, {col_name!r}] = {_parse_value(text)!r}")
            self.refresh()
            self.log(f"已修改 [行 {real_label}, {col_name}]：{old} → {text}")

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", lambda e: entry.destroy())

    # ---------- 功能 ----------

    def do_filter(self):
        if not self.require_data():
            return
        raw = self.filter_entry.get().strip()
        if not raw:
            return
        if self.filter_mode.get() == "chinese":
            # 传入列名表：比较符右边若是另一个列名（列与列相比），不加引号
            expr = natural_to_query(raw, list(self.df.columns))
            self.log(f"中文条件「{raw}」已转换为：{expr}")
        else:
            expr = raw
        try:
            self.df_view = apply_filter(self.df, expr)
        except Exception as e:
            messagebox.showerror("筛选失败",
                                 f"表达式无法执行：\n{e}\n\n"
                                 "请检查列名是否正确；列名或文本值都可以用引号括起来，\n"
                                 "中文引号「」和英文引号 ' ' 都支持。")
            return
        self.filtered = True
        self.filter_expr = expr
        self.sort_col = None
        self.page = 0
        # 生成代码用 query_expr 处理特殊列名（含空格/数字开头/关键字），保证复制出去也能跑
        q = query_expr(self.df, expr)
        engine = ", engine='python'" if "`" in q else ""
        self._record(f"筛选：{raw}", f"df = df.query({q!r}{engine})")
        self.log(f"筛选「{raw}」：{len(self.df)} 行 → {len(self.df_view)} 行")
        self.refresh()

    def clear_filter(self):
        if not self.require_data():
            return
        self.filtered = False
        self.filter_expr = None
        self.sort_col = None
        self.page = 0
        self.df_view = self.df
        self.log("筛选已清除，显示全部数据")
        self.refresh()

    def do_normalize(self):
        if not self.require_data():
            return
        new_df, changed, codes = normalize_columns(self.df)
        if changed:
            pairs = "；".join(f"「{o}」→「{n}」" for o, n in changed.items())
            self._mutate(new_df, "规范列名", f"列名已规范：{pairs}", "\n".join(codes))
        else:
            self.log("列名无需修改")

    # ---------- 填充缺失值（分步引导） ----------

    def open_fill_dialog(self):
        """一步一步引导填充缺失值：第 1 步选列 → 第 2 步选方法 → 第 3 步确认方案"""
        if not self.require_data():
            return
        missing = missing_columns(self.df)
        if not missing:
            messagebox.showinfo("提示", "当前数据没有含缺失值的列，不需要填充")
            return

        state = {"step": 1, "cols": list(missing), "method": FILL_ORDER[0], "value": ""}
        titles = {
            1: "第 1 步：选择要填充的列",
            2: "第 2 步：选择填充方法",
            3: "第 3 步：确认填充方案",
        }

        win = tk.Toplevel(self.root)
        win.title("填充缺失值")
        win.geometry("580x560")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="填充缺失值", font=tkfont.Font(size=12, weight="bold")
                  ).pack(anchor="w", padx=14, pady=(10, 0))
        title = ttk.Label(win, text="", foreground="#4C78A8")
        title.pack(anchor="w", padx=14, pady=(4, 2))
        body = ttk.Frame(win, padding=(14, 4))
        body.pack(fill=tk.BOTH, expand=True)
        bar = ttk.Frame(win, padding=(14, 8))
        bar.pack(side=tk.BOTTOM, fill=tk.X)

        def render():
            """每一步都重建界面，用户随时能看到自己在第几步、该做什么"""
            for w in body.winfo_children():
                w.destroy()
            for w in bar.winfo_children():
                w.destroy()
            title.configure(text=f"{titles[state['step']]}（共 3 步）")
            [render_columns, render_method, render_confirm][state["step"] - 1]()

        def render_columns():
            ttk.Label(body, text="下面列出所有含缺失值的列，勾选你要填充的（可多选）：").pack(anchor="w")
            wrap = ttk.Frame(body)
            wrap.pack(fill=tk.BOTH, expand=True, pady=4)
            lb = tk.Listbox(wrap, selectmode=tk.EXTENDED)
            sb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=lb.yview)
            lb.configure(yscrollcommand=sb.set)
            lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            for i, c in enumerate(missing):
                lb.insert(tk.END, f"{c}（缺失 {int(self.df[c].isna().sum())} 个）")
                if c in state["cols"]:
                    lb.selection_set(i)

            def to_method():
                chosen = [missing[i] for i in lb.curselection()]
                if not chosen:
                    messagebox.showinfo("提示", "请至少勾选一列")
                    return
                state["cols"] = chosen
                state["step"] = 2
                render()

            ttk.Button(bar, text="全选", command=lambda: lb.selection_set(0, tk.END)).pack(side=tk.LEFT)
            ttk.Button(bar, text="取消", command=win.destroy).pack(side=tk.RIGHT)
            ttk.Button(bar, text="下一步：选方法", command=to_method).pack(side=tk.RIGHT, padx=4)

        def render_method():
            ttk.Label(body, text="选择填充方法，每种方法都标了适用场景：").pack(anchor="w")
            var = tk.StringVar(value=state["method"])
            for name in FILL_ORDER:
                box = ttk.Frame(body)
                box.pack(fill=tk.X, pady=2)
                ttk.Radiobutton(box, text=name, variable=var, value=name).pack(anchor="w")
                ttk.Label(box, text="　　" + FILL_METHODS[name], foreground="gray",
                          wraplength=500, justify="left").pack(anchor="w")

            ttk.Button(bar, text="上一步：选列",
                       command=lambda: (state.update(step=1), render())).pack(side=tk.LEFT)
            ttk.Button(bar, text="取消", command=win.destroy).pack(side=tk.RIGHT)
            ttk.Button(bar, text="下一步：确认",
                       command=lambda: (state.update(method=var.get(), step=3), render())
                       ).pack(side=tk.RIGHT, padx=4)

        def render_confirm():
            ttk.Label(body, text=f"已选列：{'、'.join(str(c) for c in state['cols'])}\n"
                                 f"填充方法：{state['method']}").pack(anchor="w")
            entry = None
            if state["method"] == "固定值":
                row = ttk.Frame(body)
                row.pack(fill=tk.X, pady=6)
                ttk.Label(row, text="固定值：").pack(side=tk.LEFT)
                entry = ttk.Entry(row)
                entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
                entry.insert(0, state["value"])
            ttk.Label(body, text="下面是即将执行的填充方案，确认无误再点「确认填充」：").pack(anchor="w", pady=(6, 2))
            show = tk.Text(body, height=9, wrap="word")
            show.pack(fill=tk.BOTH, expand=True)
            ok = {"pass": False}

            def preview(*_):
                """先用一个副本试算，把每列填什么值列给用户看，填不了就说清原因"""
                if entry is not None:
                    state["value"] = entry.get()
                try:
                    _, details, _ = fill_with(self.df, state["cols"], state["method"], state["value"])
                except ValueError as e:
                    ok["pass"] = False
                    show.delete("1.0", "end")
                    show.insert("1.0", f"这套方案暂时不能用：\n\n{e}\n\n请回到上一步换一种方法。")
                    return
                ok["pass"] = True
                show.delete("1.0", "end")
                show.insert("1.0", "将为以下列填充：\n\n"
                            + "\n".join("  · " + d for d in details)
                            + "\n\n确认后改动会写入数据，并自动生成对应的 pandas 代码。")

            preview()
            if entry is not None:
                entry.bind("<KeyRelease>", preview)

            def confirm():
                if not ok["pass"]:
                    messagebox.showinfo("提示", "请先按上面的提示换一种方法")
                    return
                win.destroy()
                self._do_fill(state["cols"], state["method"], state["value"])

            ttk.Button(bar, text="上一步：选方法",
                       command=lambda: (state.update(step=2), render())).pack(side=tk.LEFT)
            ttk.Button(bar, text="取消", command=win.destroy).pack(side=tk.RIGHT)
            ttk.Button(bar, text="确认填充", command=confirm).pack(side=tk.RIGHT, padx=4)

        render()
        win.wait_window()

    def _do_fill(self, cols, method, value=None):
        """按选定方案执行填充，并把这一步写入操作记录"""
        try:
            new_df, details, codes = fill_with(self.df, cols, method, value)
        except ValueError as e:
            messagebox.showerror("填充失败", str(e))
            return
        if not details:
            self.log("所选列没有需要填充的缺失值")
            return
        for d in details:
            self.log(d)
        self._mutate(new_df, f"填充缺失值（{method}）", f"按「{method}」填充完成", "\n".join(codes))

    # ---------- 删除缺失行 / 列 ----------

    def open_delete_dialog(self, kind):
        """弹出选择框：删除所有缺失行（列），还是从列出的全部缺失行（列）中勾选特定项删除
        kind：'row' 表示行，'col' 表示列"""
        if not self.require_data():
            return
        is_row = kind == "row"
        unit = "行" if is_row else "列"
        items = missing_rows(self.df) if is_row else missing_columns(self.df)
        if not items:
            messagebox.showinfo("提示", f"当前数据没有含缺失值的{unit}")
            return

        win = tk.Toplevel(self.root)
        win.title(f"删除缺失{unit}")
        win.geometry("520x480")
        win.transient(self.root)
        win.grab_set()

        mode = tk.StringVar(value="all")
        ttk.Radiobutton(win, text=f"删除所有缺失{unit}（共 {len(items)} 个）",
                        variable=mode, value="all").pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Radiobutton(win, text=f"删除特定缺失{unit}（在下方自行勾选）",
                        variable=mode, value="some").pack(anchor="w", padx=12)
        ttk.Label(win, text="按住 Ctrl 点选多个，或按住 Shift 连选：",
                  foreground="gray").pack(anchor="w", padx=12, pady=(6, 2))

        body = ttk.Frame(win)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        listbox = tk.Listbox(body, selectmode=tk.EXTENDED)
        sb = ttk.Scrollbar(body, orient=tk.VERTICAL, command=listbox.yview)
        listbox.configure(yscrollcommand=sb.set)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        for it in items:
            listbox.insert(tk.END, self._describe_item(kind, it))

        def select_all_items():
            mode.set("some")
            listbox.selection_set(0, tk.END)

        def confirm():
            if mode.get() == "all":
                chosen = None
            else:
                chosen = [items[i] for i in listbox.curselection()]
                if not chosen:
                    messagebox.showinfo("提示", f"请先在列表中选择要删除的{unit}")
                    return
            win.destroy()
            self._delete_missing(kind, chosen)

        bar = ttk.Frame(win)
        bar.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=8)
        ttk.Button(bar, text="确认删除", command=confirm).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bar, text="取消", command=win.destroy).pack(side=tk.RIGHT)
        ttk.Button(bar, text="全选", command=select_all_items).pack(side=tk.LEFT)
        win.wait_window()

    def _describe_item(self, kind, item):
        """把待删除的行/列渲染成一句可读的文字"""
        if kind == "col":
            return f"{item}（缺失 {int(self.df[item].isna().sum())} 个）"
        # 用列表包住取行：万一行标签重复，返回的是多行 DataFrame 而不是单个值
        row = self.df.loc[[item]]
        miss_cols = [c for c in self.df.columns if row[c].isna().any()]
        shown = "、".join(str(c) for c in miss_cols[:3])
        if len(miss_cols) > 3:
            shown += f" 等 {len(miss_cols)} 列"
        return f"行 {item}：缺失 {shown}"

    def _delete_missing(self, kind, chosen=None):
        """执行删除；chosen=None 表示删除全部缺失行/列，否则只删选中的"""
        if kind == "row":
            new_df, n, codes = drop_na_rows(self.df, chosen)
            title = "删除所有缺失行" if chosen is None else "删除指定缺失行"
            if n > 0:
                self._mutate(new_df, title, f"{title}：已删除 {n} 行", "\n".join(codes))
            else:
                self.log("没有含缺失值的行")
        else:
            new_df, cols, codes = drop_na_cols(self.df, chosen)
            title = "删除所有缺失列" if chosen is None else "删除指定缺失列"
            if cols:
                names = "、".join(str(c) for c in cols[:5]) + (" 等" if len(cols) > 5 else "")
                self._mutate(new_df, title, f"{title}：已删除 {len(cols)} 列（{names}）",
                             "\n".join(codes))
            else:
                self.log("没有含缺失值的列")

    def do_drop_duplicates(self):
        if not self.require_data():
            return
        new_df, n, codes = drop_duplicate_rows(self.df)
        if n > 0:
            self._mutate(new_df, "删除重复行", f"已删除 {n} 行重复记录", "\n".join(codes))
        else:
            self.log("没有重复行")

    def do_to_numeric(self):
        if not self.require_data():
            return
        col = self.convert_col.get()
        if not col:
            return
        new_df, failed, codes = to_numeric(self.df, col)
        msg = f"列「{col}」已转数值型" + (f"，{failed} 个值无法转换已置空" if failed else "")
        self._mutate(new_df, f"列「{col}」转数值型", msg, "\n".join(codes))

    def do_pivot(self):
        if not self.require_data():
            return
        i, c, v, a = self.pv_index.get(), self.pv_column.get(), self.pv_value.get(), self.pv_agg.get()
        if not all([i, c, v, a]):
            messagebox.showinfo("提示", "请把行分组、列分组、值列、聚合方式都选上")
            return
        if v == i or v == c:
            messagebox.showwarning(
                "选择无效",
                f"值列「{v}」不能和分组列重复。\n\n正确示例：行分组=城市，列分组=性别，值列=数学成绩"
            )
            return
        if i == c:
            messagebox.showwarning(
                "选择无效",
                f"行分组和列分组不能都是「{i}」。\n\n正确示例：行分组=城市，列分组=性别，值列=数学成绩"
            )
            return
        try:
            table = pivot_table(self.df, i, c, v, a)
        except Exception as e:
            messagebox.showerror("透视失败", str(e))
            return
        self.add_dataset(f"透视_{self.current}", table)
        self._record(f"生成透视表（按「{i}」分组，对比「{c}」，统计「{v}」的{a}）",
                     f"df = df.pivot_table(index={i!r}, columns={c!r}, values={v!r}, "
                     f"aggfunc={AGG_FUNCS[a]!r})")
        self.log(f"透视表已生成：按「{i}」分组、对比「{c}」、统计「{v}」的{a}")

    def show_summary(self):
        if not self.require_data():
            return
        win = tk.Toplevel(self.root)
        win.title(f"统计摘要 - {self.current}")
        win.geometry("680x480")
        text = tk.Text(win, wrap="none", font=("NSimSun", 10))  # 中文等宽字体，保证对齐
        text.pack(fill=tk.BOTH, expand=True)
        text.insert(tk.END, summarize(self.df))
        text.config(state=tk.DISABLED)
        self.log("统计摘要已生成（见弹出窗口）")

    def show_diagnose(self):
        """数据体检：逐列诊断缺失率、异常值并给出处理建议"""
        if not self.require_data():
            return
        report = diagnose(self.df)
        win = tk.Toplevel(self.root)
        win.title(f"数据质量诊断 - {self.current}")
        win.geometry("820x420")
        tree = ttk.Treeview(win, columns=list(report.columns), show="headings")
        for c in report.columns:
            tree.heading(c, text=c)
            tree.column(c, width=120, anchor="center")
        for _, row in report.iterrows():
            tree.insert("", tk.END, values=list(row))
        tree.pack(fill=tk.BOTH, expand=True)
        self._record("数据质量诊断（仅查看，不修改数据）", "# 这一步只查看数据质量，未修改数据")
        # 数值列的「异常值」是整数，0 表示没有异常；只有 >0 才算真有问题
        bad = [r["列名"] for _, r in report.iterrows()
               if r["缺失数"] > 0 or (r["异常值"] != "-" and int(r["异常值"]) > 0)]
        self.log("数据体检完成：" + ("、".join(bad) + " 存在缺失或异常值，详见弹窗" if bad else "各列质量良好"))

    def show_code(self):
        win = tk.Toplevel(self.root)
        win.title("操作对应的 pandas 代码")
        win.geometry("620x460")
        text = tk.Text(win, wrap="none", font=("Consolas", 10))
        text.pack(fill=tk.BOTH, expand=True)
        lines = ["import pandas as pd", "",
                 "df = pd.read_csv('你的文件.csv')  # 换成你自己的文件", ""]
        if self.ops_log:
            for i, (title, code) in enumerate(self.ops_log, 1):
                lines.append(f"# ========== 操作 {i}：{title} ==========")
                lines.append(code)
                lines.append("")
        else:
            lines.append("# （还没有执行过操作）")
        content = "\n".join(lines)
        text.insert(tk.END, content)
        text.config(state=tk.DISABLED)

        def copy_all():
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.log("代码已复制到剪贴板，可直接粘贴到 Jupyter 或编辑器运行")

        ttk.Button(win, text="复制全部代码", command=copy_all).pack(fill=tk.X, padx=8, pady=6)

    def do_plot(self):
        if not self.require_data():
            return
        chart, x, y = self.chart_type.get(), self.x_col.get(), self.y_col.get()
        if not x:
            return
        # 先清掉旧画布再关旧图：绘图失败时面板是空的，不会残留一张已关闭的旧图
        for w in self.plot_frame.winfo_children():
            w.destroy()
        if self.fig is not None:  # 关掉上一张图，避免 figure 越积越多
            plt.close(self.fig)
            self.fig = None
        try:
            self.fig = make_figure(self.df_view, chart, x, y if y else None)
        except Exception as e:
            messagebox.showerror("绘图失败", str(e))
            return
        self._record(f"绘制「{chart}」：X={x}" + (f"，Y={y}" if chart not in ("直方图", "饼图") else ""),
                     _plot_code(chart, x, y if y else None))
        canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.log(f"已生成「{chart}」：X={x}" + (f"，Y={y}" if chart not in ("直方图", "饼图") else ""))

    def save_figure(self):
        if self.fig is None:
            messagebox.showinfo("提示", "请先生成图表")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png", initialfile="图表.png",
            filetypes=[("PNG 图片", "*.png")],
        )
        if path:
            self.fig.savefig(path, dpi=150, bbox_inches="tight")
            self.log(f"图表已保存：{path}")

    def save_csv(self):
        if not self.require_data():
            return
        data = self.df_view if self.filtered else self.df   # 导出当前视图而非全量
        suffix = "筛选结果" if self.filtered else "处理后"
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile=f"{self.current}_{suffix}.csv",
            filetypes=[("CSV 文件", "*.csv")],
        )
        if path:
            data.to_csv(path, index=False, encoding="utf-8-sig")
            self.log(f"已导出 {len(data)} 行：{path}")


if __name__ == "__main__":
    root = tk.Tk()
    app = EasyTableApp(root)
    root.mainloop()
