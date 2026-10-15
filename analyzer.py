# -*- coding: utf-8 -*-
"""数据处理核心：读取、筛选、清洗、排序、编辑、透视、统计、诊断

对外提供的函数：
- load_file                     读入 CSV、Excel（自动尝试中文编码）
- apply_filter / natural_to_query   pandas 表达式筛选、中文自然语言转表达式
- sort_by / set_value           排序、修改指定单元格（排序后仍能正确定位行）
- normalize_columns             规范列名（全角转半角、去空格）
- fill_with                      缺失值填充（均值/中位数/众数/固定值/前向/后向/插值）
- drop_na_rows / drop_na_cols     删除缺失行、缺失列（可全部删，也可只删指定项）
- pivot_table                   数据透视
- summarize / diagnose          统计摘要、数据质量诊断

清洗类函数统一返回 (新数据, 处理明细, pandas 代码) 三元组，便于界面实现"操作即代码"。
"""

import keyword
import re

import pandas as pd


# 表达式中作为逻辑运算符使用、不能被当作列名替换的词
_LOGICAL_WORDS = {"and", "or", "not", "in", "is"}


def load_file(path):
    """读取 CSV / Excel 文件，自动尝试常见中文编码"""
    if path.lower().endswith(".csv"):
        # gb18030 是 gbk 的超集，能多兜住一批老编码文件；utf-8 文件在 utf-8-sig 一步就会成功
        for enc in ("utf-8-sig", "gb18030", "utf-8"):
            try:
                return pd.read_csv(path, encoding=enc)
            except UnicodeDecodeError:
                continue
        raise ValueError("无法识别文件编码")
    return pd.read_excel(path)


def _fullwidth_to_halfwidth(text):
    """全角字符转半角，全角空格转普通空格"""
    result = []
    for ch in text:
        code = ord(ch)
        if code == 0x3000:
            result.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        else:
            result.append(ch)
    return "".join(result)


def normalize_columns(df):
    """规范列名：全角转半角、去空格。返回 (新表, 修改对照, 代码)"""
    mapping = {}
    for col in df.columns:
        mapping[col] = _fullwidth_to_halfwidth(str(col)).strip().replace(" ", "")
    changed = {o: n for o, n in mapping.items() if o != n}
    code = [f"df = df.rename(columns={changed!r})  # 规范列名"] if changed else []
    return df.rename(columns=mapping), changed, code


# 填充方法：名称 → 适用说明（界面按这个顺序一步一步引导用户选择）
FILL_METHODS = {
    "均值": "用这一列的均值填补（适合数值列、缺失比较随机）",
    "中位数": "用这一列的中位数填补（数值列，比均值更抗极端值）",
    "众数": "用出现最多的值填补（类别列、文本列的默认做法）",
    "固定值": "全部填成你指定的值（保留“这里原本是空的”这层含义）",
    "前向填充": "用上一行的值填补（适合有时间先后顺序的数据）",
    "后向填充": "用下一行的值填补（适合有时间先后顺序的数据）",
    "线性插值": "在前后两个有效值之间按位置插值（适合连续数值）",
}
FILL_ORDER = ["均值", "中位数", "众数", "固定值", "前向填充", "后向填充", "线性插值"]
# 只能用在数值列上的方法
_NUMERIC_ONLY = ("均值", "中位数", "线性插值")


def fill_with(df, columns, method, custom_value=None):
    """按指定方法填充指定列的缺失值。返回 (新表, 说明列表, 代码列表)"""
    df = df.copy()
    details, codes = [], []
    for col in columns:
        n = int(df[col].isna().sum())
        if n == 0:
            continue
        if method in _NUMERIC_ONLY and not pd.api.types.is_numeric_dtype(df[col]):
            raise ValueError(f"「{col}」是文本列，不能用「{method}」填充，"
                             f"请改用「众数」或「固定值」。")

        if method == "均值":
            value = float(round(df[col].mean(), 2))
            df[col] = df[col].fillna(value)
            how, code = f"该列均值 {value}", f"df[{col!r}] = df[{col!r}].fillna({value!r})"
        elif method == "中位数":
            value = float(round(df[col].median(), 2))
            df[col] = df[col].fillna(value)
            how, code = f"该列中位数 {value}", f"df[{col!r}] = df[{col!r}].fillna({value!r})"
        elif method == "众数":
            mode = df[col].mode(dropna=True)
            if len(mode) == 0:
                raise ValueError(f"列「{col}」整列都是空值，算不出众数。"
                                 "请改用「固定值」，或先检查这一列的数据。")
            # 数值列保持数值类型，避免把整列变成文本
            value = float(mode.iloc[0]) if pd.api.types.is_numeric_dtype(df[col]) else str(mode.iloc[0])
            df[col] = df[col].fillna(value)
            how, code = f"该列众数 {value!r}", f"df[{col!r}] = df[{col!r}].fillna({value!r})"
        elif method == "固定值":
            value = _parse_value(custom_value)
            df[col] = df[col].fillna(value)
            how, code = f"固定值 {value!r}", f"df[{col!r}] = df[{col!r}].fillna({value!r})"
        elif method == "前向填充":
            df[col] = df[col].ffill()
            how, code = "上一行的值", f"df[{col!r}] = df[{col!r}].ffill()"
        elif method == "后向填充":
            df[col] = df[col].bfill()
            how, code = "下一行的值", f"df[{col!r}] = df[{col!r}].bfill()"
        elif method == "线性插值":
            df[col] = df[col].interpolate()
            how, code = "前后有效值之间的线性插值", f"df[{col!r}] = df[{col!r}].interpolate()"
        else:
            raise ValueError(f"未知的填充方法：{method}")

        # 前向/后向填充可能填不满（开头或结尾没有可参照的值）
        left = int(df[col].isna().sum())
        tail = f"（开头还有 {left} 个缺失值没法用这个办法填）" if left else ""
        details.append(f"列「{col}」按{how} 填充 {n} 个缺失值{tail}")
        codes.append(f"{code}  # 按{how} 填充 {n} 个缺失值{tail}")
    return df, details, codes


def drop_na_rows(df, subset=None):
    """删除含缺失值的行。返回 (新表, 删除行数, 代码)
    subset=None：删除所有含缺失值的行
    subset=行标签列表：只删除列表中指定的这些行"""
    n0 = len(df)
    if subset is None:
        new = df.dropna()
        code = "df = df.dropna()  # 删除所有含缺失值的行"
    else:
        labels = list(subset)
        new = df.drop(index=labels)
        code = f"df = df.drop(index={labels!r})  # 删除指定的行"
    return new, n0 - len(new), [code]


def drop_na_cols(df, subset=None):
    """删除含缺失值的列。返回 (新表, 被删列名列表, 代码)
    subset=None：删除所有含缺失值的列
    subset=列名列表：只删除列表中指定的这些列"""
    if subset is None:
        cols = [c for c in df.columns if bool(df[c].isna().any())]
        code = "df = df.dropna(axis=1)  # 删除所有含缺失值的列"
    else:
        cols = list(subset)
        code = f"df = df.drop(columns={cols!r})  # 删除指定的列"
    return df.drop(columns=cols), cols, [code]


def missing_rows(df):
    """列出所有含缺失值的行标签（供界面让用户挑选要删除的行）"""
    return list(df.index[df.isna().any(axis=1)])


def missing_columns(df):
    """列出所有含缺失值的列名（供界面让用户挑选要删除的列）"""
    return [c for c in df.columns if bool(df[c].isna().any())]


def drop_duplicate_rows(df):
    """删除完全重复的行。返回 (新表, 删除行数, 代码)"""
    n0 = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    return df, n0 - len(df), ["df = df.drop_duplicates().reset_index(drop=True)  # 删除重复行"]


def to_numeric(df, column):
    """把某列强制转成数值（转不了的置空）。返回 (新表, 失败数, 代码)"""
    df = df.copy()
    converted = pd.to_numeric(df[column], errors="coerce")
    failed = int(converted.isna().sum() - df[column].isna().sum())
    df[column] = converted
    return df, failed, [f'df[{column!r}] = pd.to_numeric(df[{column!r}], errors="coerce")  # 转数值型']


def apply_filter(df, expr):
    """按条件表达式筛选行，例如：年龄 > 18 and 城市 == '北京'
    列名带空格或全角字符时 pandas 筛选引擎不支持，因此先把列名换成
    合法别名再执行；表达式里写原始列名或规范写法都能识别"""
    # 1. 为每列生成合法标识符别名（跳过 Python 关键字，如 class、and）
    alias, used = {}, set()
    for i, col in enumerate(df.columns):
        c = str(col)
        norm = _fullwidth_to_halfwidth(c).strip().replace(" ", "")
        ok = _is_plain_name(norm)
        a = norm if ok else f"col_{i}"
        base, n = a, 2
        while a in used:
            a = f"{base}_{n}"
            n += 1
        used.add(a)
        alias[c] = a

    # 2. 表达式里的列名（原始写法或规范写法）统一替换为别名
    #    先用占位符再还原，防止替换结果被二次替换
    candidates = {}
    for c, a in alias.items():
        norm = _fullwidth_to_halfwidth(c).strip().replace(" ", "")
        if norm in _LOGICAL_WORDS:  # and/or/not 等是逻辑运算符，替换会破坏表达式
            continue
        candidates[c] = a
        candidates[norm] = a
    keys = sorted(candidates, key=len, reverse=True)
    placeholders = {k: "\x00%d\x00" % j for j, k in enumerate(keys)}
    parts = re.split(r"('[^']*'|\"[^\"]*\")", expr)  # 引号内的字符串不处理
    for i, part in enumerate(parts):
        if i % 2 == 1:
            continue
        for k in keys:
            part = re.sub(r"(?<![\w\x00])" + re.escape(k) + r"(?![\w\x00])",
                          placeholders[k], part)
        parts[i] = part
    expr2 = "".join(parts)
    for k in keys:
        expr2 = expr2.replace(placeholders[k], candidates[k])

    # 3. 用别名表执行筛选，再把列名换回来
    safe_df = df.rename(columns=alias)
    result = safe_df.query(expr2, engine="python")
    result.columns = df.columns
    return result.reset_index(drop=True)


def _is_plain_name(name):
    """列名本身是一个合法标识符时，query 表达式里可以直接写"""
    return name.isidentifier() and not name[:1].isdigit() and not keyword.iskeyword(name)


def query_expr(df, expr):
    """给「生成代码」用的表达式：把 query 认不出来的列名（含空格、数字开头、
    或 Python 关键字）用反引号包起来，这样复制到别处也能直接运行"""
    bad = sorted({str(c) for c in df.columns if not _is_plain_name(str(c))},
                 key=len, reverse=True)
    if not bad:
        return expr
    parts = re.split(r"('[^']*'|\"[^\"]*\")", expr)  # 引号里的字面量不动
    marks = {}
    for i in range(0, len(parts), 2):
        for j, name in enumerate(bad):
            holder = f"\x03{j}\x03"
            marks[holder] = f"`{name}`"
            for alias in {name, _fullwidth_to_halfwidth(name).strip().replace(" ", "")}:
                parts[i] = re.sub(r"(?<![\w\x03])" + re.escape(alias) + r"(?![\w\x03])",
                                  holder, parts[i])
    out = "".join(parts)
    for holder, text in marks.items():
        out = out.replace(holder, text)
    return out


# 中文连接词/比较词 → pandas 语法；长的写在前面，避免被短词抢先替换
_CN_RULES = [
    ("大于等于", ">="), ("小于等于", "<="), ("不等于", "!="),
    # 「是不是」必须排在「不是」前面：这里是按顺序的子串替换，
    # 先命中「不是」会把「是不是」拆成「是 !=」，得到非法表达式
    ("是不是", "=="), ("不是", "!="),
    ("大于", ">"), ("小于", "<"), ("等于", "=="),
    ("并且", "and"), ("而且", "and"), ("且", "and"),
    ("或者", "or"), ("或", "or"),
    ("是", "=="),
]
# 比较符右侧的「词」需要加引号（数字保持原样；正好是列名时按列处理，见 natural_to_query）
_OP_VALUE_RE = re.compile(r"(>=|<=|==|!=|>|<)\s*([A-Za-z\u4e00-\u9fff_][\w\u4e00-\u9fff]*)")


# 引号：英文的 ' " 与中文的 “” ‘’ 「」 『』 都支持
_QUOTE_RE = re.compile(r'"([^"]*)"|\'([^\']*)\'|“([^”]*)”|‘([^’]*)’|「([^」]*)」|『([^』]*)』')
# 下面这些词里含有比较词的字（如「是否」「是的」里的「是」），但不是比较词，先保护起来
_CN_PROTECT = ["是否", "是的", "是吧"]


def natural_to_query(text, columns=None):
    """中文自然语言条件 → pandas 查询表达式
    例：年龄大于18且性别是女 → 年龄 > 18 and 性别 == '女'

    列名或文本值都可以用引号括起来，中文引号（「」『』“”‘’）和
    英文引号（' "）都支持；引号里的内容不会被当成关键词拆开。
    传入 columns（当前数据的列名列表）后，比较符右边如果写的是另
    一个列名（列与列相比），就不加引号，按列处理。"""
    out = text.strip()
    quoted = []

    # 1. 先把引号里的内容整个取出来，换成占位符
    def keep(m):
        inner = next(g for g in m.groups() if g is not None)
        quoted.append(inner)
        return f"\x01{len(quoted) - 1}\x01"

    out = _QUOTE_RE.sub(keep, out)

    # 2. 保护「是否」这类含比较词字样的普通词
    protected = []
    for word in _CN_PROTECT:
        while word in out:
            protected.append(word)
            out = out.replace(word, f"\x02{len(protected) - 1}\x02", 1)

    # 3. 替换中文比较词与连接词，并给比较符右边的文本值补引号
    #    右边的词如果正好是列名（列与列相比），不加引号
    col_words = set()
    if columns:
        for c in columns:
            c = str(c)
            col_words.add(c)
            col_words.add(_fullwidth_to_halfwidth(c).strip().replace(" ", ""))
    for cn, py in _CN_RULES:
        out = out.replace(cn, f" {py} ")
    out = _OP_VALUE_RE.sub(
        lambda m: f"{m.group(1)} {m.group(2)}" if m.group(2) in col_words
                  else f"{m.group(1)} '{m.group(2)}'", out)
    out = " ".join(out.split())

    # 4. 还原占位符：后面紧跟比较符的当列名（不加引号），否则当文本值（补英文单引号）
    def restore(m):
        kind, idx = m.group(1), int(m.group(2))
        if kind == "\x02":
            return protected[idx]
        tail = out[m.end():].lstrip()
        if re.match(r"(>=|<=|==|!=|>|<)", tail):
            return quoted[idx]  # 比较符左边，是列名
        if quoted[idx] in col_words:
            return quoted[idx]  # 显式写了列名（列与列相比），不加引号
        return repr(quoted[idx])

    out = re.sub(r"(\x01|\x02)(\d+)(?:\x01|\x02)", restore, out)
    return " ".join(out.split())


def sort_by(df, column, ascending=True):
    """按某列排序（保留原行标签，供编辑单元格时正确定位）"""
    return df.sort_values(by=column, ascending=ascending, kind="mergesort")


def _parse_value(text):
    """把界面输入的文字转成合适类型：能转数字就转，否则按文本"""
    try:
        value = float(text)
        if value.is_integer():
            value = int(value)
        return value
    except (ValueError, TypeError):
        # float(None) 抛的是 TypeError，不是 ValueError；空值当作文本处理
        return text if text is not None else ""


def set_value(df, row_label, column, text):
    """按行标签修改单个单元格的值"""
    df.loc[row_label, column] = _parse_value(text)
    return df


AGG_FUNCS = {"平均值": "mean", "总和": "sum", "计数": "count", "最大值": "max", "最小值": "min"}


def pivot_table(df, index_col, column_col, value_col, agg_name):
    """数据透视：行分组 × 列分组，对值列做聚合"""
    agg = AGG_FUNCS[agg_name]
    # 三个参数都用标量而不是单元素列表：pandas 就不会再套一层「值列名」，
    # 列名直接是分组值，与生成代码 df.pivot_table(index=..., columns=...,
    # values=...) 的执行结果一致
    table = pd.pivot_table(df, index=index_col, columns=column_col,
                           values=value_col, aggfunc=agg)
    table = table.round(2)
    table.columns = [str(c) for c in table.columns]
    return table.reset_index()


def summarize(df):
    """统计摘要：数值列给均值/最值，文本列给去重数"""
    lines = [f"共 {df.shape[0]} 行 × {df.shape[1]} 列", ""]
    num = df.select_dtypes(include="number")
    if len(num.columns) > 0:
        lines.append("【数值列统计】")
        # 中文列名按双格宽度对齐，防止表头和数据错位
        with pd.option_context("display.unicode.east_asian_width", True):
            lines.append(num.describe().round(2).to_string())
        lines.append("")
    text = df.select_dtypes(exclude="number")
    if len(text.columns) > 0:
        lines.append("【文本列统计】")
        for col in text.columns:
            lines.append(f"  · {col}：{df[col].nunique()} 种取值，缺失 {int(df[col].isna().sum())} 个")
    return "\n".join(lines)


def diagnose(df):
    """数据质量诊断：逐列给出缺失情况、类型、异常值数量和处理建议"""
    rows = []
    total = len(df)
    for col in df.columns:
        s = df[col]
        miss = int(s.isna().sum())
        rate = miss / total if total else 0.0
        is_num = pd.api.types.is_numeric_dtype(s)
        outliers = 0
        if is_num:
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            if iqr > 0:
                outliers = int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())
        if rate > 0.5:
            advice = "缺失过多，建议删除该列"
        elif rate > 0:
            advice = "建议用均值填充" if is_num else "建议用众数填充"
        elif outliers > 0:
            advice = f"有 {outliers} 个异常值，建议检查"
        else:
            advice = "质量良好"
        rows.append({
            "列名": col,
            "类型": "数值" if is_num else "文本",
            "缺失数": miss,
            "缺失率": f"{rate:.1%}",
            "异常值": outliers if is_num else "-",
            "建议": advice,
        })
    return pd.DataFrame(rows)
