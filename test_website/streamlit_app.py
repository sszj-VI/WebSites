# streamlit_app.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# =============== 页面基础 ===============
st.set_page_config(page_title="数据聚合处理网站", page_icon="🧮", layout="wide")
st.title("数据聚合处理网站")
st.caption("用户自选横/纵坐标 · 时间列可派生（小时/日期/星期/月）· 动态范围筛选 · 多参量小多图")

# =============== 上传 CSV（默认无文件） ===============
up = st.file_uploader("上传 CSV（原始明细或已聚合均可）", type=["csv"])

def read_csv_any(src):
    # 自动识别常见分隔符
    return pd.read_csv(src, sep=None, engine="python")

if up is None:
    st.info("请上传 CSV 文件以开始分析。")
    st.stop()

raw = read_csv_any(up)
if raw.empty:
    st.error("读取到的表为空，请检查 CSV 内容。")
    st.stop()

# =============== 工具：识别时间列 & 数值列 ===============
def can_parse_datetime(series) -> float:
    try:
        return pd.to_datetime(series, errors="coerce").notna().mean()
    except Exception:
        return 0.0

def is_numeric_like(series) -> bool:
    try:
        return pd.to_numeric(series, errors="coerce").notna().mean() > 0.5
    except Exception:
        return False

datetime_candidates = [c for c in raw.columns if can_parse_datetime(raw[c]) > 0.5]
numeric_candidates  = [c for c in raw.columns if is_numeric_like(raw[c])]

# =============== 侧边栏（只有在有文件时才出现） ===============
with st.sidebar:
    st.subheader("维度与度量")

    # 1) 横坐标 X
    x_col = st.selectbox("横坐标 (X)", options=list(raw.columns), help="可选时间/数值/类别列。时间列可派生后聚合")

    # 2) 时间派生
    x_is_datetime = x_col in datetime_candidates
    x_time_mode = None
    if x_is_datetime:
        x_time_mode = st.selectbox(
            "时间派生",
            ["小时(0–23)", "日期", "星期(一~日)", "月份(1~12)"],
            help="从时间列派生一个分组键后再聚合"
        )

    # 3) 纵坐标 Y（数值列，且不能与 X 相同）
    y_options = [c for c in numeric_candidates if c != x_col]
    y_key = f"ycols::{x_col}"  # 切换 X 时 Y 自动重置
    y_cols = st.multiselect(
        "纵坐标 (Y，可多选)",
        options=y_options,
        default=[],
        key=y_key,
        placeholder="请选择 1~3 个数值列，例如 trips、avg_tip …"
    )

    # 4) 聚合方式（未选 Y 时禁用）
    agg_fn = st.selectbox(
        "聚合方式（对 Y 列）",
        ["sum", "mean", "median", "max", "min"],
        index=0,
        disabled=(len(y_cols) == 0)
    )

# =============== 构造分组键 X_key（含时间派生） ===============
df = raw.copy()

if x_is_datetime:
    ts = pd.to_datetime(df[x_col], errors="coerce")
    if x_time_mode == "小时(0–23)":
        df["_X_key"] = ts.dt.hour
    elif x_time_mode == "日期":
        # 保留 date 类型，便于日期区间筛选
        df["_X_key"] = ts.dt.date
    elif x_time_mode == "星期(一~日)":
        wd = ts.dt.weekday
        mapping = {0:"一", 1:"二", 2:"三", 3:"四", 4:"五", 5:"六", 6:"日"}
        df["_X_key"] = wd.map(mapping)
        cat_type = pd.CategoricalDtype(categories=list(mapping.values()), ordered=True)
        df["_X_key"] = df["_X_key"].astype(cat_type)
    elif x_time_mode == "月份(1~12)":
        df["_X_key"] = ts.dt.month
    else:
        df["_X_key"] = ts.astype("string")
else:
    # 非时间：直接作为分组键（转 string）
    df["_X_key"] = df[x_col].astype("string")

# Y 转数值
for c in y_cols:
    df[c] = pd.to_numeric(df[c], errors="coerce")

# 未选 Y 的友好提示
if len(y_cols) == 0:
    st.info("👉 请在左侧 **选择至少一个纵坐标（数值列）** 后再查看图表。")
    st.stop()

# =============== 聚合（对每个 Y 应用相同聚合函数） ===============
df = df.dropna(subset=["_X_key"] + y_cols)
grouped = df.groupby("_X_key")
agg_map = {c: agg_fn for c in y_cols}
df_view = grouped.agg(agg_map).reset_index().rename(columns={"_X_key": x_col})

# 排序
if x_is_datetime and x_time_mode in ["小时(0–23)", "月份(1~12)"]:
    try:
        df_view[x_col] = pd.to_numeric(df_view[x_col], errors="coerce")
        df_view = df_view.sort_values(x_col)
    except Exception:
        pass
elif pd.api.types.is_numeric_dtype(df_view[x_col]):
    df_view = df_view.sort_values(x_col)

# =============== 侧边栏 · 显示范围（动态类型） ===============
with st.sidebar:
    st.subheader("显示范围")
    # 针对不同类型的 X，提供不同的筛选方式
    x_vals = df_view[x_col]

    if x_is_datetime and x_time_mode == "日期":
        # 日期区间
        xv = pd.to_datetime(x_vals, errors="coerce")
        if xv.notna().any():
            min_d = xv.min().date(); max_d = xv.max().date()
            d_range = st.date_input("日期范围", (min_d, max_d))
            if isinstance(d_range, tuple) and len(d_range) == 2:
                mask = (xv.dt.date >= d_range[0]) & (xv.dt.date <= d_range[1])
                df_view = df_view.loc[mask]
    elif pd.api.types.is_numeric_dtype(x_vals):
        # 数值范围（小范围整型用滑条，否则用数字输入）
        try:
            x_min = float(np.nanmin(x_vals)); x_max = float(np.nanmax(x_vals))
            unique_cnt = pd.unique(x_vals).shape[0]
            if str(x_vals.dtype).startswith("int") and unique_cnt <= 100:
                rng = st.slider("X 范围", min_value=int(x_min), max_value=int(x_max),
                                value=(int(x_min), int(x_max)))
                df_view = df_view[(x_vals >= rng[0]) & (x_vals <= rng[1])]
            else:
                c1, c2 = st.columns(2)
                v_min = c1.number_input("X 最小值", value=float(x_min))
                v_max = c2.number_input("X 最大值", value=float(x_max))
                df_view = df_view[(x_vals >= v_min) & (x_vals <= v_max)]
        except Exception:
            pass
    else:
        # 类别或星期：多选
        cats = list(pd.unique(x_vals.astype("string")))
        chosen = st.multiselect("选择 X 类别", options=cats, default=cats)
        df_view = df_view[df_view[x_col].astype("string").isin(chosen)]

# =============== 展示：小多图 ===============
st.subheader(f"按「{x_col}」聚合（{agg_fn}）")
st.caption(
    f"X = 「{x_col}」{' · 时间派生：'+x_time_mode if x_is_datetime else ''}；"
    f"Y = {y_cols}；样本数 = {int(df.shape[0]):,}"
)

if df_view.empty:
    st.warning("当前筛选条件下没有可展示的数据。请调整显示范围或更换 Y。")
else:
    for y in y_cols:
        st.markdown(f"**· {y}**")
        # 按当前 y 的峰值高亮
        peak_x = None
        if df_view[y].notna().any():
            try:
                peak_x = df_view.loc[df_view[y].idxmax(), x_col]
            except Exception:
                peak_x = None

        colors = []
        for xv in df_view[x_col]:
            if (peak_x is not None) and (str(xv) == str(peak_x)):
                colors.append("#E45756")
            else:
                colors.append("#4C78A8")

        fig = px.bar(df_view, x=x_col, y=y, labels={x_col: "X", y: y})
        fig.update_traces(marker_color=colors,
                          hovertemplate=f"{x_col}=%{{x}}<br>{y}=%{{y}}<extra></extra>")
        st.plotly_chart(fig, use_container_width=True)

# =============== 视图下载 & 原表预览 ===============
tab1, tab2 = st.tabs(["当前聚合视图 (可下载)", "原始数据预览"])

with tab1:
    st.dataframe(df_view, use_container_width=True, hide_index=True)
    st.download_button(
        "下载当前聚合视图 CSV",
        df_view.to_csv(index=False).encode("utf-8"),
        file_name="aggregated_view.csv",
        mime="text/csv"
    )

with tab2:
    st.dataframe(raw.head(200), use_container_width=True, hide_index=True)
