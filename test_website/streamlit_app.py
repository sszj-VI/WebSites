import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

st.set_page_config(page_title="按小时聚合展示", layout="wide")
st.title("按小时聚合展示")

# ---------- 数据加载：上传文件优先；否则读仓库默认；都没有则提示 ----------
DEFAULT = Path(__file__).parent / "data" / "hourly_trips.csv"
up = st.file_uploader("上传一份同结构 CSV（可选）", type=["csv"])

def load_csv(src):
    # 允许 file-like 对象（上传）或路径
    return pd.read_csv(src)

if up is not None:
    df = load_csv(up)
elif DEFAULT.exists():
    df = load_csv(DEFAULT)
else:
    st.info("请先上传一份 CSV（需包含列：pickup_hour, trips；可选 avg_tip）。")
    st.stop()

# ---------- 基础校验与类型 ----------
need = {"pickup_hour", "trips"}
if not need.issubset(df.columns):
    st.error("CSV 需包含列：pickup_hour, trips。可选列：avg_tip。")
    st.stop()

# 统一为数值类型，去除非法值
df["pickup_hour"] = pd.to_numeric(df["pickup_hour"], errors="coerce").astype("Int64")
df["trips"] = pd.to_numeric(df["trips"], errors="coerce")
has_tip = "avg_tip" in df.columns
if has_tip:
    df["avg_tip"] = pd.to_numeric(df.get("avg_tip"), errors="coerce")

df = df.dropna(subset=["pickup_hour", "trips"]).copy()
df["pickup_hour"] = df["pickup_hour"].astype(int)

# ---------- 侧边栏筛选 ----------
with st.sidebar:
    st.subheader("筛选")
    hr_min, hr_max = st.slider("展示小时范围", 0, 23, (0, 23))
    show_pct = st.checkbox("显示占比（% of total）", value=False)
    smooth = st.checkbox("显示移动平均（3小时）", value=False)

# 过滤与排序
view = df[(df["pickup_hour"] >= hr_min) & (df["pickup_hour"] <= hr_max)].copy()
view = view.sort_values("pickup_hour")

# 没数据兜底
if len(view) == 0:
    st.warning("当前筛选范围内没有数据，请调整滑块或上传其他 CSV。")
    st.stop()

# 计算占比、移动平均
total = float(view["trips"].sum())
if show_pct and total > 0:
    view["share"] = (view["trips"] / total * 100).round(2)

if smooth and len(view) >= 3:
    view["trips_sma3"] = view["trips"].rolling(3, center=True).mean()

# ---------- 指标卡（修复 idxmax 越界：用 loc，并对空/NaN 兜底） ----------
if view["trips"].notna().any():
    peak_row = view.loc[view["trips"].idxmax()]
    peak_hour = int(peak_row["pickup_hour"])
    peak_trips = int(peak_row["trips"]) if pd.notnull(peak_row["trips"]) else 0
else:
    peak_hour, peak_trips = 0, 0

c1, c2, c3 = st.columns(3)
c1.metric("总行程数", f"{int(total):,}")
c2.metric("最忙时段", f"{peak_hour:02d}:00", f"{peak_trips:,}")
if has_tip and view["avg_tip"].notna().any():
    c3.metric("平均小费(区间)", f"{view['avg_tip'].mean():.2f}")
else:
    c3.metric("平均小费(区间)", "—")

# ---------- 图表 ----------
# 1) 主图：柱状（数量 / 占比 / 平滑）
if show_pct and total > 0:
    fig = px.bar(view, x="pickup_hour", y="share",
                 labels={"pickup_hour": "小时", "share": "占比(%)"})
else:
    ycol = "trips_sma3" if (smooth and "trips_sma3" in view.columns) else "trips"
    fig = px.bar(view, x="pickup_hour", y=ycol,
                 labels={"pickup_hour": "小时", "trips": "数量"})
st.plotly_chart(fig, use_container_width=True)

# 2) 小费折线（可选）
if has_tip and view["avg_tip"].notna().any():
    fig2 = px.line(view, x="pickup_hour", y="avg_tip", markers=True,
                   labels={"pickup_hour": "小时", "avg_tip": "平均小费"})
    st.plotly_chart(fig2, use_container_width=True)

# ---------- 下载当前视图 ----------
st.download_button(
    "下载当前视图CSV",
    view.to_csv(index=False).encode("utf-8"),
    file_name="hourly_view.csv",
    mime="text/csv"
)

st.caption("说明：平台（Kaggle/PySpark）已完成聚合；网页只做筛选/占比/平滑等轻计算，保证演示稳定。")
