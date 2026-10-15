<div align="center">

# Smart Data Toolkit · 智能数据处理与分析工具

**A desktop data-analysis toolkit for Chinese users — filter data in natural Chinese, and every GUI operation is transcribed into runnable pandas code.**

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![pandas](https://img.shields.io/badge/pandas-data%20analysis-green)
![matplotlib](https://img.shields.io/badge/matplotlib-visualization-orange)
![Tests](https://img.shields.io/badge/Tests-37%20passed-brightgreen)
![License](https://img.shields.io/badge/License-MIT-yellow)

</div>

---

## Why this project

Between "opening a CSV in Excel" and "writing pandas", there is a gap that most Chinese users fall into:

- **Encoding traps** — a CSV saved by Excel is GBK, by pandas it is UTF-8; opening it the wrong way crashes or mojibake.
- **Full-width punctuation** — Chinese input methods produce `（）` `，` `'` that silently break filters and column names.
- **Illegal identifiers** — column names like `乘客 编号` or `是否生还` cannot be written directly in `df.query()`.

This toolkit is a **transparent bridge**: the user only needs to speak Chinese, while the tool faithfully translates every click into standard pandas code — so the user learns pandas *by using it*.

## ✨ Highlights (for reviewers)

### 1. Chinese natural-language filtering — a rule-ordered transpiler
A deterministic rule engine (not an LLM) converts `年龄大于18且性别是女` into `df.query("年龄 > 18 and 性别 == '女'")`. The engineering behind it:
- **Rule ordering matters**: `是不是` must be rewritten *before* `不是`, otherwise `性别是不是女` corrupts into the illegal expression `性别 == != '女'`.
- **Placeholder protection**: replacements are staged through sentinels so that overlapping substrings never re-replace each other.
- **Identifier repair**: column names that are illegal in `query` (spaces, leading digits, Python keywords) are auto-wrapped in backticks with `engine='python'`, so copied code runs anywhere.

### 2. Ops-as-Code — a reproducibility contract
Every cleaning function returns a uniform `(new_df, human_details, pandas_code)` triple. The GUI appends each code line to an operation log, so **the data state and the generated script can never drift apart**. View-only operations (sorting, chart zoom) are deliberately excluded from the log to keep the script 1:1 with real transformations. The guarantee is test-verified: the generated script is re-executed in the test suite and reproduces the exact result (891 → 246 rows).

### 3. Data check-up & guided cleaning
Per-column diagnosis of missing rates and outliers with actionable suggestions. Method guards prevent silent corruption — e.g. mode-filling an all-null numeric column raises a friendly Chinese error instead of quietly converting the column to strings.

### 4. Adaptive tick-label layout for CJK
X-axis labels are rotated to vertical **only when horizontal space is insufficient** (rendered-width estimation: CJK = 1 unit, ASCII = 0.5). Short categories like 生还/遇难 stay horizontal; a 20-group boxplot auto-rotates — including the `boxplot` 1..N tick-offset pitfall.

### 5. A robustness layer for real-world files
Encoding fallback chain (`utf-8-sig → gb18030 → utf-8`), full-width → half-width normalization for both column names and filter expressions, long-first replacement so logic words like `and/or` are never corrupted.

## Features

| # | Feature | Description |
|---|---------|-------------|
| 1 | Table browser | Auto-fit column widths, full headers in one line, horizontal scroll, 200-row paging |
| 2 | Cell editing | Double-click to edit; full cell content shown below the table |
| 3 | Data filtering | pandas expressions **and** Chinese natural language |
| 4 | Data cleaning | Normalize column names, 7 missing-value fill methods, drop rows/cols, dedup, type coercion |
| 5 | Charts | 6 chart types, CJK-aware label layout, save as PNG |
| 6 | Pivot table | row × column grouping with aggregation |
| 7 | Data check-up | per-column missing rate / outlier diagnosis with suggestions |
| 8 | Statistics summary | count / mean / std / quantiles per column |
| 9 | Ops-as-Code | every operation generates runnable pandas code, one-click copy |
| 10 | Multi-dataset | mount and switch multiple datasets, export to CSV |

## Quick Start

```bash
git clone https://github.com/eric-123456474/Smart-Data-Toolkit.git
cd Smart-Data-Toolkit
pip install pandas matplotlib openpyxl
python main.py
```

Requires Python 3.8+. Runs on Windows / macOS / Linux — pure desktop, no server, no account.

## Chinese Natural-Language Filtering — Examples

| You type | Generated expression |
|----------|---------------------|
| `年龄大于18且性别是女` | `年龄 > 18 and 性别 == '女'` |
| `性别是不是女` | `性别 == '女'` |
| `性别不是女` | `性别 != '女'` |
| `身高大于体重` | `身高 > 体重` (column vs column — just write both names) |
| `票价大于等于50 或 是否生还是1` | `票价 >= 50 or 是否生还 == 1` |

Chinese/English quotes are both accepted; the generated code is always normalized to valid Python.

## Ops-as-Code — Every Click Becomes Code

Sample of a real generated script (loading the sample data, two fills, one column drop, one Chinese filter):

```python

import pandas as pd

df = pd.read_csv('你的文件.csv')  # 换成你自己的文件

# ========== 操作 1：填充缺失值 ==========
df['年龄'] = df['年龄'].fillna(29.7)  # 按该列均值 29.7 填充 177 个缺失值

# ========== 操作 2：填充缺失值 ==========
df['登船港口'] = df['登船港口'].fillna('南安普顿')  # 按该列众数 '南安普顿' 填充 2 个缺失值

# ========== 操作 3：删除所有缺失列 ==========
df = df.dropna(axis=1)  # 删除所有含缺失值的列

# ========== 操作 4：筛选 ==========
df = df.query("年龄 > 18 and 性别 == '女'")  # 年龄大于18且性别是女
```

Paste it into any Python environment and it reproduces the whole session — 891 rows in, 246 rows out.

## Engineering Practices

- **Three-layer architecture** — GUI (`main.py`) / logic (`analyzer.py`) / plotting (`plotter.py`) fully decoupled; the logic layer has zero GUI dependencies and is independently testable.
- **Uniform function contract** — all cleaning functions return `(new_df, details, code)`.
- **State consistency by design** — sorting/view operations intentionally never enter the op log.
- **Headless test suite** — 8 groups / 37 regression checks, runnable without a display.

## Project Layout

````
smart-data-toolkit/
├── main.py        # GUI: layout, events, table rendering
├── analyzer.py    # Logic: filter / clean / pivot / stats (zero GUI deps)
├── plotter.py     # Charts: 6 types + CJK label layout
├── test_all.py    # Regression tests: 8 groups / 37 checks
├── 示例数据.csv    # Built-in sample: Titanic 891×12 (Chinese columns)
└── README.md
````

## Test Suite

```bash
python test_all.py
```

Covers: startup & sample loading, table rendering, filtering (incl. special column names), all 7 fill methods, 6 chart types, pivot & diagnosis, ops-as-code (generated script re-executed end-to-end), and CSV export.

## Sample Data

`示例数据.csv` is adapted from the [Kaggle Titanic dataset](https://www.kaggle.com/c/titanic) — column names translated into Chinese, original missing values preserved (age 177, cabin 687, embarked 2) so the cleaning features are demonstrable.

## Author

**eric-123456474** · [github.com/eric-123456474](https://github.com/eric-123456474)

## License

[MIT](LICENSE) © 2026 eric-123456474

---

<div align="center">

## 中文说明

</div>

### 这是什么

**智能数据处理与分析工具**是一个面向中文用户的桌面数据分析软件：不会写代码的人也能完成筛选、清洗、绘图、透视、统计，同时每一步操作都会自动翻译成标准 pandas 代码——既是一个立即可用的分析工具，也是一扇学习 pandas 的窗口。

两个差异化特性：**中文自然语言筛选**与**操作即代码**。

### 项目动机

在「用 Excel 打开 CSV」和「会写 pandas」之间，中文用户面临三道现实的墙：

1. **编码陷阱**——Excel 另存的 CSV 是 GBK，pandas 默认读 UTF-8，读错直接报错或乱码；
2. **全角标点**——中文输入法带出的 `（）` `，` `'` 会让筛选条件和列名静默失效；
3. **非法标识符**——`乘客 编号`、`是否生还` 这类列名无法直接写进 `df.query()`。

本工具要做一座**透明的桥**：用户只管说中文，工具把每一次点击如实翻译成标准 pandas 代码——用着用着，pandas 就学会了。

### 功能一览

| # | 功能 | 说明 |
|---|------|------|
| 1 | 表格浏览 | 列宽自适应、表头单行完整显示、横向滚动、每页 200 行分页 |
| 2 | 单元格编辑 | 双击修改，完整内容在表格下方展示 |
| 3 | 数据筛选 | pandas 表达式 + 中文自然语言 |
| 4 | 数据清洗 | 规范列名、7 种缺失值填充、删除行/列、去重、文本转数值 |
| 5 | 图表绘制 | 6 种图表、中文标签智能横竖排、保存 PNG |
| 6 | 数据透视 | 行分组 × 列分组 × 聚合方式 |
| 7 | 数据体检 | 逐列缺失率/异常值诊断并给出处理建议 |
| 8 | 统计摘要 | 各列计数、均值、标准差、分位数 |
| 9 | 操作即代码 | 每一步自动生成可运行的 pandas 代码，一键复制 |
| 10 | 多数据集管理 | 多表挂载随时切换，结果可导出 CSV |

### 快速开始

```bash
git clone https://github.com/eric-123456474/Smart-Data-Toolkit.git
cd Smart-Data-Toolkit
pip install pandas matplotlib openpyxl
python main.py
```

需要 Python 3.8+，Windows / macOS / Linux 均可运行。纯桌面应用，零联网、零账号、零配置。

### 中文自然语言筛选

| 输入 | 生成表达式 |
|------|-----------|
| `年龄大于18且性别是女` | `年龄 > 18 and 性别 == '女'` |
| `性别是不是女` | `性别 == '女'` |
| `性别不是女` | `性别 != '女'` |
| `身高大于体重` | `身高 > 体重`（两列相比，直接写列名） |
| `票价大于等于50 或 是否生还是1` | `票价 >= 50 or 是否生还 == 1` |

中文引号、英文引号都能识别；生成的代码始终是可直接运行的合法 Python。

### 操作即代码

每一步操作自动生成对应的 pandas 代码。以下是一段真实的生成示例（加载示例数据 → 均值填充 → 众数填充 → 删除缺失列 → 中文筛选）：

```python
import pandas as pd

df = pd.read_csv('你的文件.csv')  # 换成你自己的文件

# ========== 操作 1：填充缺失值 ==========
df['年龄'] = df['年龄'].fillna(29.7)  # 按该列均值 29.7 填充 177 个缺失值

# ========== 操作 2：填充缺失值 ==========
df['登船港口'] = df['登船港口'].fillna('南安普顿')  # 按该列众数 '南安普顿' 填充 2 个缺失值

# ========== 操作 3：删除所有缺失列 ==========
df = df.dropna(axis=1)  # 删除所有含缺失值的列

# ========== 操作 4：筛选 ==========
df = df.query("年龄 > 18 and 性别 == '女'")  # 年龄大于18且性别是女
```

把这段代码粘到任何 Python 环境里，都能复现整场分析——891 行进，246 行出。

设计细节：排序、图表缩放这类**视图操作刻意不写入日志**，保证生成的代码与真实数据变换一一对应，不多不少。

### 核心技术点

**1. 规则有序的中文自然语言转换器**
`是不是` 必须先于 `不是` 替换，否则 `性别是不是女` 会被拆成非法表达式 `性别 == != '女'`；替换经过占位符中转，防止子串互相污染；含空格/数字开头/Python 关键字的列名自动用反引号包裹并补 `engine='python'`，复制出去的代码到处能跑。

**2. 操作即代码的函数契约**
所有清洗函数统一返回 `(新表, 处理明细, pandas 代码)` 三元组；测试套件会把生成的代码真实重新执行一遍，验证能精确复现结果（891 行 → 246 行）。

**3. 数据体检与防误操作守卫**
逐列诊断缺失率与异常值并给出建议；方法守卫防止静默污染——例如对整列为空的数值列做众数填充会给出中文报错引导，而不是悄悄把整列变成文本。

**4. 中日韩文字标签的智能横竖排**
按渲染宽度估算（中日韩字符记 1、英文数字记 0.5），横排放得下就不旋转，放不下才自动竖排；并处理了 `boxplot` 刻度从 1 开始而非 0 的偏移坑。

**5. 真实文件的健壮层**
编码回退链（utf-8-sig → gb18030 → utf-8）、全角标点自动规范化、长词优先替换防止逻辑词被破坏。

### 工程实践

- **三层架构**：界面（main.py）/ 逻辑（analyzer.py）/ 绘图（plotter.py）完全解耦，逻辑层零界面依赖、可独立测试；
- **统一契约**：清洗类函数一律返回三元组；
- **状态一致性**：视图操作不入日志是刻意设计；
- **无头测试**：8 组 37 项回归，无需显示环境即可运行。

### 项目结构

````
smart-data-toolkit/
├── main.py        # 主程序：界面布局、事件响应、表格渲染
├── analyzer.py    # 数据逻辑：筛选/清洗/透视/统计（零界面依赖）
├── plotter.py     # 绘图：6 种图表 + 中文标签智能横竖排
├── test_all.py    # 回归测试：8 组 37 项
├── 示例数据.csv    # 内置示例：泰坦尼克 891×12（中文列名）
└── README.md
````

### 运行测试

```bash
python test_all.py
```

覆盖：启动与示例加载、表格渲染、条件筛选（含特殊列名）、全部 7 种填充方法、6 种图表、透视与体检、操作转代码（生成代码真实端到端复跑）、CSV 导出。

### 示例数据

`示例数据.csv` 改编自 [Kaggle 泰坦尼克数据集](https://www.kaggle.com/c/titanic) ：列名译为中文，并保留原始缺失值（年龄 177、客舱号 687、登船港口 2），方便演示清洗功能。

### 作者

**eric-123456474** · [GitHub 主页](https://github.com/eric-123456474)

### 许可证

[MIT](LICENSE) © 2026 eric-123456474


