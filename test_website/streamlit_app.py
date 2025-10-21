# test_website/streamlit_app.py
import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

# ============ 页面基础 ============
st.set_page_config(page_title="按小时聚合展示", layout="wide")
st.title("按小时聚合展示")
st.caption("平台（Kaggle/PySpark）先做聚合 → 前端只做筛选/占比/平滑等轻计算，保证演示稳定。")

# ============ 数据加载：上传优先 → 默认兜底 → 提示 ============
DEFAULT = Path(__file__).parent / "data" / "hourly_trips.csv"
up = st.file_uploader("上传一份同结构 CSV（可选）", type=["csv"])

def load_csv(src):
    return pd.read_csv(src)

if up is not None:
    df = load_csv(up)
elif DEFAULT.exists():
    df = load_csv(DEFAULT)
else:
    st.info("未检测到默认数据。请上传一份 CSV（需包含列：**pickup_hour, trips**；可选 **avg_tip**）。")
    st.stop()

# ============ 基础校验 & 类型处理 ============
need = {"pickup_hour", "trips"}
if not need.issubset(df.columns):
    st.error("CSV 需包含列：pickup_hour, trips。可选列：avg_tip。")
    st.stop()

df["pickup_hour"] = pd.to_numeric(df["pickup_hour"], errors="coerce").astype("Int64")
df["trips"] = pd.to_numeric(df["trips"], errors="coerce")
has_tip = "avg_tip" in df.columns
if has_tip:
    df["avg_tip"] = pd.to_numeric(df.get("avg_tip"), errors="coerce")

df = df.dropna(subset=["pickup_hour", "trips"]).copy()
df["pickup_hour"] = df["pickup_hour"].astype(int)

# ============ 侧边栏：筛选、说明、重置（修复首次滑动回跳） ============
with st.sidebar:
    st.subheader("筛选")

    DEFAULT_RANGE = (0, 23)
    # 初始化会话状态（只在首次进入时设置一次）
    if "hour_range" not in st.session_state:
        st.session_state["hour_range"] = DEFAULT_RANGE

    # 绑定固定 key：第一次拖动就能记住，不会回跳
    hour_range = st.slider(
        "展示小时范围", 0, 23,
        value=st.session_state["hour_range"],
        key="hour_range"
    )
    hr_min, hr_max = hour_range

    show_pct = st.checkbox("显示占比（% of total）", value=False)
    smooth   = st.checkbox("显示移动平均（3小时）", value=False)

    st.divider()
    st.markdown("**使用说明**\n- 上传同结构 CSV 可即时更新\n- 勾选占比/平滑观察不同视图\n- 下面按钮可一键重置")

    # 用回调修改同名 key，避免同轮渲染直接覆写控件值导致的异常/回跳
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

# ============ KPI（用 loc 取峰值，避免索引越界；空/NaN 兜底） ============
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

# ============ 图表区域：Tabs ============
tab1, tab2, tab3 = st.tabs(["数量/占比", "平均小费", "数据概览"])

with tab1:
    # 主图：数量/占比 & 峰值高亮
    if show_pct and total > 0:
        ycol = "share"
        y_label = "占比(%)"
    else:
        ycol = "trips_sma3" if (smooth and "trips_sma3" in view.columns) else "trips"
        y_label = "数量"

    colors = ["#E45756" if int(h) == peak_hour else "#4C78A8" for h in view["pickup_hour"]]
    fig = px.bar(view, x="pickup_hour", y=ycol, labels={"pickup_hour":"小时", ycol: y_label})
    fig.update_traces(marker_color=colors, hovertemplate="小时=%{x}<br>"+y_label+"=%{y}<extra></extra>")
    # 注：取注释用的 y 值时，确保筛选过的列存在
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
