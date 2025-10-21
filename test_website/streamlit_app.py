# streamlit_app.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from pathlib import Path

# ===================== 页面基础 =====================
st.set_page_config(page_title="数据聚合处理网站", page_icon="🧮", layout="wide")
st.title("数据聚合处理网站")
st.caption("用户自选横/纵坐标 · 时间列自动派生（小时/日期/星期/月）· 原始/已聚合统一处理 · 多参量小多图")

# ===================== 读取 CSV（上传优先，默认兜底） =====================
DEFAULT = Path(__file__).parent / "data" / "hourly_trips.csv"
up = st.file_uploader("上传 CSV（原始明细或已聚合均可）", type=["csv"])

def read_csv_any(src):
    # 自动识别常见分隔符
    return pd.read_csv(src, sep=None, engine="python")

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

# ===================== 辅助：识别“像时间”的列、可数值列 =====================
def can_parse_datetime(series) -> float:
    """返回该列可解析为时间戳的比例（0~1）"""
    try:
        return pd.to_datetime(series, errors="coerce").notna().mean()
    except Exception:
        return 0.0

def is_numeric_like(series) -> bool:
    """是否“像数值”——能转为数值且非空占比>50%"""
    try:
        return pd.to_numeric(series, errors="coerce").notna().mean() > 0.5
    except Exception:
        return False

datetime_candidates = [c for c in raw.columns if can_parse_datetime(raw[c]) > 0.5]
numeric_candidates  = [c for c in raw.columns if is_numeric_like(raw[c])]

# ===================== 侧边栏：X/Y 选择、时间派生、聚合方式 =====================
with st.sidebar:
    st.subheader("维度与度量")

    # 1) 横坐标 X：可选任意列
    x_col = st.selectbox("横坐标 (X)", options=list(raw.columns), help="可选时间/数值/类别列。时间列可进行派生后聚合")

    # 2) 如果 X 是时间列，给出派生方式；否则无派生
    x_is_datetime = x_col in datetime_candidates
    x_time_mode = None
    if x_is_datetime:
        x_time_mode = st.selectbox(
            "时间派生",
            ["小时(0–23)", "日期", "星期(一~日)", "月份(1~12)"],
            help="从时间列派生一个离散分组键，并按此聚合"
        )

    # 3) 纵坐标 Y：只能选数值列，且不能与 X 相同
    y_options = [c for c in numeric_candidates if c != x_col]
    # 允许默认不选，交由下面的“空选择拦截”处理
    y_cols = st.multiselect(
        "纵坐标 (Y，可多选)",
        options=y_options,
        default=[],
        placeholder="请选择 1~3 个数值列，例如 trips、avg_tip …"
    )

    # 4) 聚合方式（当没选 Y 时禁用掉）
    agg_fn = st.selectbox(
        "聚合方式（对 Y 列）",
        ["sum", "mean", "median", "max", "min"],
        index=0,
        disabled=(len(y_cols) == 0)
    )

    st.divider()
    st.caption(
        "提示：若上传原始明细，时间列可派生为小时/日期/星期/月后再聚合；"
        "若上传已聚合表（如含 pickup_hour/trips），也可直接选择任意列作为 X。"
    )

# ===================== 构造分组键 X_key（含时间派生） =====================
df = raw.copy()

if x_is_datetime:
    ts = pd.to_datetime(df[x_col], errors="coerce")
    if x_time_mode == "小时(0–23)":
        df["_X_key"] = ts.dt.hour
    elif x_time_mode == "日期":
        df["_X_key"] = ts.dt.date.astype("string")
    elif x_time_mode == "星期(一~日)":
        wd = ts.dt.weekday
        mapping = {0:"一", 1:"二", 2:"三", 3:"四", 4:"五", 5:"六", 6:"日"}
        df["_X_key"] = wd.map(mapping)
        # 固定顺序
        cat_type = pd.CategoricalDtype(categories=list(mapping.values()), ordered=True)
        df["_X_key"] = df["_X_key"].astype(cat_type)
    elif x_time_mode == "月份(1~12)":
        df["_X_key"] = ts.dt.month
    else:
        df["_X_key"] = ts.astype("string")
else:
    # 非时间：直接用原值作为分组键（转 string 以兼容类别/混合）
    df["_X_key"] = df[x_col].astype("string")

# 把 Y 列尽量转数值，后续聚合会更稳
for c in y_cols:
    df[c] = pd.to_numeric(df[c], errors="coerce")

# ===================== “未选择 Y” 的友好提示（核心改动） =====================
if len(y_cols) == 0:
    st.info("👉 请在左侧 **选择至少一个纵坐标（数值列）** 后再查看图表。")
    with st.expander("我能选择哪些列？（数值列清单）", expanded=False):
        st.write(y_options if y_options else "当前数据中未检测到可用的数值列。")
    st.stop()  # 终止后续聚合/绘图，避免 pandas 抛错

# ===================== 分组聚合（对每个 Y 应用同一聚合函数） =====================
df = df.dropna(subset=["_X_key"] + y_cols)
grouped = df.groupby("_X_key")
agg_map = {c: agg_fn for c in y_cols}

# 计算聚合视图；同时计算计数 trips 作为参考（高亮用）
df_view = grouped.agg(agg_map).reset_index().rename(columns={"_X_key": x_col})
df_view["trips"] = grouped.size().values  # 计数，仅做参考高亮（可无视）

# 对小时/月份做自然排序；数值列自动排序；类别列保持原出现顺序
if x_is_datetime and x_time_mode in ["小时(0–23)", "月份(1~12)"]:
    try:
        df_view[x_col] = pd.to_numeric(df_view[x_col], errors="coerce")
        df_view = df_view.sort_values(x_col)
    except Exception:
        pass
elif pd.api.types.is_numeric_dtype(df_view[x_col]):
    df_view = df_view.sort_values(x_col)

# ===================== 展示：小多图 =====================
st.subheader(f"按「{x_col}」聚合（{agg_fn}）")
st.caption(
    f"X = 「{x_col}」{' · 时间派生：'+x_time_mode if x_is_datetime else ''}；"
    f"Y = {y_cols}；样本数 = {int(df.shape[0]):,}"
)

if df_view.empty:
    st.warning("聚合后没有可展示的数据。请检查 X/Y 选择与数据有效性。")
else:
    # 若有 trips，可用 trips 的峰值位置来高亮（仅做视觉提示）
    peak_x = None
    if "trips" in df_view.columns and df_view["trips"].notna().any():
        try:
            peak_x = df_view.loc[df_view["trips"].idxmax(), x_col]
        except Exception:
            peak_x = None

    for y in y_cols:
        st.markdown(f"**· {y}**")
        colors = []
        for xv in df_view[x_col]:
            if (peak_x is not None) and (str(xv) == str(peak_x)):
                colors.append("#E45756")
            else:
                colors.append("#4C78A8")

        fig = px.bar(df_view, x=x_col, y=y, labels={x_col: "X", y: y})
        fig.update_traces(marker_color=colors, hovertemplate=f"{x_col}=%{{x}}<br>{y}=%{{y}}<extra></extra>")
        st.plotly_chart(fig, use_container_width=True)

# ===================== 视图下载 & 原表预览 =====================
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
