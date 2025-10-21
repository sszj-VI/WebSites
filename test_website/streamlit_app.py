# test_website/streamlit_app.py
import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

# ============ 页面基础 ============
st.set_page_config(page_title="24小时出行面板", layout="wide")
st.title("24小时出行面板")
st.caption("平台（Kaggle/PySpark）可先做聚合；也支持读取原始明细并现场聚合到小时级。")

# ============ 数据加载：上传优先 → 默认兜底 → 提示 ============
# 默认兜底：已聚合的小表（可选）
DEFAULT_AGG = Path(__file__).parent / "data" / "hourly_trips.csv"
up = st.file_uploader("上传原始或已聚合的 CSV（均可）", type=["csv"])

def load_csv(src):
    # 自动识别分隔符，容错好一些
    return pd.read_csv(src, sep=None, engine="python")

if up is not None:
    raw = load_csv(up)
elif DEFAULT_AGG.exists():
    raw = load_csv(DEFAULT_AGG)
else:
    st.info("请上传 CSV；若无原始数据，可先用示例的 hourly_trips.csv。")
    st.stop()

# ============ 原始/已聚合自适应 ============
# 1) 候选的“时间戳列”、小费列名（按最常见命名覆盖）
CANDIDATE_TIME_COLS = [
    "tpep_pickup_datetime","pickup_datetime","pickup_time","pickup_ts",
    "started_at","start_time","timestamp","datetime","date","time"
]
CANDIDATE_TIP_COLS = ["avg_tip","tip_amount","tip","tip_amt"]

def to_num(s):
    return pd.to_numeric(s, errors="coerce")

# 2) 如果是已聚合表：必须包含 pickup_hour, trips（avg_tip 可选）
def is_aggregated(df):
    return {"pickup_hour","trips"}.issubset(df.columns)

def aggregate_hourly(df):
    """
    从原始明细聚合到小时级：
    - 识别时间列 -> 取 hour
    - trips = count
    - 如存在小费列 -> avg_tip = mean
    """
    time_col = next((c for c in CANDIDATE_TIME_COLS if c in df.columns), None)
    if time_col is None:
        return None  # 识别失败，让上层报友好错误

    ts = pd.to_datetime(df[time_col], errors="coerce")
    out = pd.DataFrame({"pickup_hour": ts.dt.hour})
    out["trips"] = 1

    # 处理可选小费
    tip_col = next((c for c in CANDIDATE_TIP_COLS if c in df.columns), None)
    if tip_col:
        df["_tip_num"] = to_num(df[tip_col])
        out = pd.concat([out, df["_tip_num"]], axis=1)

    if tip_col:
        agg = out.groupby("pickup_hour", dropna=True).agg(
            trips=("trips","sum"),
            avg_tip=("_tip_num","mean")
        ).reset_index()
        agg["avg_tip"] = agg["avg_tip"].round(2)
    else:
        agg = out.groupby("pickup_hour", dropna=True).agg(
            trips=("trips","sum")
        ).reset_index()
    agg = agg.dropna(subset=["pickup_hour"]).copy()
    agg["pickup_hour"] = agg["pickup_hour"].astype(int)
    return agg.sort_values("pickup_hour")

# 3) 统一得到 df（小时级）
if is_aggregated(raw):
    df = raw.copy()
    df["pickup_hour"] = to_num(df["pickup_hour"]).astype("Int64")
    df["trips"] = to_num(df["trips"])
    if "avg_tip" in df.columns:
        df["avg_tip"] = to_num(df["avg_tip"])
    df = df.dropna(subset=["pickup_hour","trips"]).copy()
    df["pickup_hour"] = df["pickup_hour"].astype(int)
    df = df.sort_values("pickup_hour")
else:
    df = aggregate_hourly(raw)
    if df is None:
        st.error("CSV 需包含：原始数据里的**时间戳列**（如 timestamp/pickup_datetime/started_at）"
                 "；或已聚合表的列 **pickup_hour, trips**（可选 avg_tip）。\n\n"
                 "若你用的是我给的原始样例，请确认第一行包含列名且时间列名为 `timestamp`。")
        st.stop()

# ============ 基础校验 & 类型处理（最终保险） ============
has_tip = "avg_tip" in df.columns
df["pickup_hour"] = pd.to_numeric(df["pickup_hour"], errors="coerce").astype(int)
df["trips"] = pd.to_numeric(df["trips"], errors="coerce")
if has_tip:
    df["avg_tip"] = pd.to_numeric(df["avg_tip"], errors="coerce")

df = df.dropna(subset=["pickup_hour","trips"]).copy()
df = df[(df["pickup_hour"] >= 0) & (df["pickup_hour"] <= 23)].sort_values("pickup_hour")

# ============ 侧边栏：筛选、说明、重置（不会回跳） ============
with st.sidebar:
    st.subheader("筛选")

    DEFAULT_RANGE = (0, 23)
    if "hour_range" not in st.session_state:
        st.session_state["hour_range"] = DEFAULT_RANGE

    hour_range = st.slider(
        "展示小时范围", 0, 23,
        value=st.session_state["hour_range"],
        key="hour_range"
    )
    hr_min, hr_max = hour_range

    show_pct = st.checkbox("显示占比（% of total）", value=False)
    smooth   = st.checkbox("显示移动平均（3小时）", value=False)

    st.divider()
    st.markdown("**使用说明**\n- 可上传原始明细或已聚合表\n- 勾选占比/平滑观察不同视图\n- 下面按钮一键重置")
    def reset_range():
        st.session_state["hour_range"] = DEFAULT_RANGE
    st.button("重置筛选为 0–23 点", on_click=reset_range)

# 过滤 & 排序
view = df[(df["pickup_hour"] >= hr_min) & (df["pickup_hour"] <= hr_max)].copy()
view = view.sort_values("pickup_hour")
if len(view) == 0:
    st.warning("当前筛选范围内没有数据，请调整滑块或上传其他 CSV。")
    st.stop()

# ============ 派生：占比/平滑 ============
total = float(view["trips"].sum())
if show_pct:
    view["share"] = (view["trips"] / total * 100).round(2) if total > 0 else 0.0

if smooth and len(view) >= 3:
    view["trips_sma3"] = view["trips"].rolling(3, center=True).mean()

# ============ KPI ============
if view["trips"].notna().any():
    peak_row = view.loc[view["trips"].idxmax()]
    peak_hour = int(peak_row["pickup_hour"])
    peak_trips = int(peak_row["trips"]) if pd.notnull(peak_row["trips"]) else 0
    peak_share = (peak_trips / total * 100) if total else 0.0
else:
    peak_hour, peak_trips, peak_share = 0, 0, 0.0

c1, c2, c3 = st.columns(3)
c1.metric("总行程数", f"{int(total):,}")
c2.metric("最忙时段", f"{peak_hour:02d}:00", f"{peak_trips:,}")
c3.metric("峰值占比", f"{peak_share:.2f}%")

# ============ 图表区域 ============
tab1, tab2, tab3 = st.tabs(["数量/占比", "平均小费", "数据概览"])

with tab1:
    if show_pct and total > 0:
        ycol = "share"; y_label = "占比(%)"
    else:
        ycol = "trips_sma3" if (smooth and "trips_sma3" in view.columns) else "trips"
        y_label = "数量"

    colors = ["#E45756" if int(h) == peak_hour else "#4C78A8" for h in view["pickup_hour"]]
    fig = px.bar(view, x="pickup_hour", y=ycol, labels={"pickup_hour":"小时", ycol: y_label})
    fig.update_traces(marker_color=colors, hovertemplate="小时=%{x}<br>"+y_label+"=%{y}<extra></extra>")
    ann_y = view.loc[view["pickup_hour"] == peak_hour, ycol].iloc[0] if peak_trips > 0 else None
    if ann_y is not None:
        fig.add_annotation(x=peak_hour, y=ann_y, text="峰值", showarrow=True, arrowhead=2, yshift=10)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    if has_tip and view["avg_tip"].notna().any():
        fig2 = px.line(view, x="pickup_hour", y="avg_tip", markers=True,
                       labels={"pickup_hour":"小时","avg_tip":"平均小费"})
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("当前数据不包含 `avg_tip` 列。")

with tab3:
    st.dataframe(view.reset_index(drop=True), use_container_width=True, hide_index=True)

# ============ 下载当前视图 ============
st.download_button(
    "下载当前视图CSV",
    view.to_csv(index=False).encode("utf-8"),
    file_name="hourly_view.csv",
    mime="text/csv"
)
