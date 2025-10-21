import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from pathlib import Path

# ============ 基础设置 ============
st.set_page_config(page_title="24 小时出行面板", page_icon="🕒", layout="wide")
st.title("24 小时出行面板")
st.caption("用户自选横纵坐标 · 自动识别时间列派生 · 原始/已聚合统一处理 · 多参量小多图")

# ============ 读取 CSV（上传优先，默认兜底） ============
DEFAULT = Path(__file__).parent / "data" / "hourly_trips.csv"
up = st.file_uploader("上传 CSV（原始明细或已聚合均可）", type=["csv"])

def read_csv_any(src):
    return pd.read_csv(src, sep=None, engine="python")  # 自动识别常见分隔符

if up is not None:
    raw = read_csv_any(up)
elif DEFAULT.exists():
    raw = read_csv_any(DEFAULT)
else:
    st.info("请上传 CSV；或在 data/hourly_trips.csv 放置一份示例。")
    st.stop()

if raw.empty:
    st.error("读取到的表为空，请检查 CSV 内容。")
    st.stop()

# ============ 推断类型：时间列候选 & 数值列候选 ============
def can_parse_datetime(series) -> float:
    """返回该列可解析为时间戳的比例（0~1）"""
    try:
        return pd.to_datetime(series, errors="coerce").notna().mean()
    except Exception:
        return 0.0

# 候选时间列：可解析率 > 0.5 的列
datetime_candidates = [c for c in raw.columns if can_parse_datetime(raw[c]) > 0.5]

# 数值列候选：能转为数值且非时间戳（即使原始是字符串也尝试转换）
def is_numeric_like(series):
    try:
        return pd.to_numeric(series, errors="coerce").notna().mean() > 0.5
    except Exception:
        return False

numeric_candidates = [c for c in raw.columns if is_numeric_like(raw[c])]

# ============ 侧边栏：选择 X、X 的时间派生、Y 列、聚合方式 ============
with st.sidebar:
    st.subheader("维度与度量")

    # 1) 横坐标 X：可选任意列（时间/数值/类别）
    x_col = st.selectbox("横坐标 (X)", options=list(raw.columns), help="可选时间/数值/类别列。时间列可进行派生后聚合")

    # 2) 若 X 是时间列，选派生方式；否则无派生
    x_is_datetime = x_col in datetime_candidates
    x_time_mode = None
    if x_is_datetime:
        x_time_mode = st.selectbox(
            "时间派生",
            ["小时(0–23)", "日期", "星期(一~日)", "月份(1~12)"],
            help="从时间列派生一个离散分组键，并按此聚合"
        )

    # 3) 纵坐标 Y：只能选数值列，且不能选择与 X 相同（若 X 也是数值列）
    y_options = [c for c in numeric_candidates if c != x_col]
    if not y_options:
        st.error("未检测到可用的数值列用于纵坐标，请检查数据。")
        st.stop()
    default_y = ["trips"] if "trips" in y_options else y_options[:1]
    y_cols = st.multiselect("纵坐标 (Y，可多选)", options=y_options, default=default_y,
                            help="仅数值列可作为度量；多选将生成多张小图")

    # 4) 选择聚合方式（对 Y 应用）
    agg_fn = st.selectbox("聚合方式（对 Y 列）", ["sum", "mean", "median", "max", "min"], index=0)

    st.divider()
    st.caption("提示：若上传原始明细，可将时间列派生为“小时/日期/星期/月”以便聚合；若上传已聚合表(如含 pickup_hour/trips)，也可直接选择任意列为 X。")

# ============ 生成用于绘图的数据：X 派生 + 分组聚合 ============
df = raw.copy()

# 1) 生成分组键 X_key
if x_is_datetime:
    ts = pd.to_datetime(df[x_col], errors="coerce")
    if x_time_mode == "小时(0–23)":
        df["_X_key"] = ts.dt.hour
    elif x_time_mode == "日期":
        df["_X_key"] = ts.dt.date.astype("string")
    elif x_time_mode == "星期(一~日)":
        # 周一=0，周日=6；映射到中文
        wd = ts.dt.weekday
        mapping = {0:"一",1:"二",2:"三",3:"四",4:"五",5:"六",6:"日"}
        df["_X_key"] = wd.map(mapping)
        # 固定顺序
        cat_type = pd.CategoricalDtype(categories=list(mapping.values()), ordered=True)
        df["_X_key"] = df["_X_key"].astype(cat_type)
    elif x_time_mode == "月份(1~12)":
        df["_X_key"] = ts.dt.month
    else:
        df["_X_key"] = ts.astype("string")
else:
    # 非时间：直接使用原值作为分组键（转为 string 以兼容类别/混合）
    df["_X_key"] = df[x_col].astype("string")

# 2) 仅保留 Y 列可转数值的部分
for c in y_cols:
    df[c] = pd.to_numeric(df[c], errors="coerce")
df = df.dropna(subset=["_X_key"] + y_cols)

# 3) 分组聚合（对每个 Y 应用同一个聚合函数）；同时计算计数 trips 作为参考
grouped = df.groupby("_X_key")
agg_map = {c: agg_fn for c in y_cols}
df_view = grouped.agg(agg_map).reset_index().rename(columns={"_X_key": x_col})
df_view["trips"] = grouped.size().values  # 计数（可做参考高亮）

# 4) 为“小时(0–23)”和“月份(1~12)”排序；数值/日期自动排序；类别按出现顺序
if x_is_datetime and x_time_mode in ["小时(0–23)", "月份(1~12)"]:
    try:
        df_view[x_col] = pd.to_numeric(df_view[x_col], errors="coerce")
        df_view = df_view.sort_values(x_col)
    except Exception:
        pass
elif pd.api.types.is_numeric_dtype(df_view[x_col]):
    df_view = df_view.sort_values(x_col)

# ============ 展示：小多图 ============
st.subheader(f"按「{x_col}」聚合（{agg_fn}）")
st.caption(f"X=「{x_col}」{' · 时间派生：'+x_time_mode if x_is_datetime else ''}；Y={y_cols}；样本数={int(df.shape[0]):,}")

if df_view.empty:
    st.warning("聚合后没有可展示的数据。请检查 X/Y 选择与数据有效性。")
else:
    # 如果同时选择了很多 Y，这里逐个渲染
    for y in y_cols:
        st.markdown(f"**· {y}**")
        # 若有 trips，可用 trips 的峰值位置来高亮（仅做视觉提示）
        peak_x = None
        if "trips" in df_view.columns and df_view["trips"].notna().any():
            try:
                peak_x = df_view.loc[df_view["trips"].idxmax(), x_col]
            except Exception:
                peak_x = None

        colors = []
        for xv in df_view[x_col]:
            if (peak_x is not None) and (str(xv) == str(peak_x)):
                colors.append("#E45756")
            else:
                colors.append("#4C78A8")

        fig = px.bar(df_view, x=x_col, y=y, labels={x_col:"X", y:y})
        fig.update_traces(marker_color=colors, hovertemplate=f"{x_col}=%{{x}}<br>{y}=%{{y}}<extra></extra>")
        st.plotly_chart(fig, use_container_width=True)

# ============ 原表/聚合表预览 & 下载 ============
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
