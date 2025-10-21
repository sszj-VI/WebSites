import streamlit as st, pandas as pd, plotly.express as px
st.set_page_config(page_title="按小时聚合展示", layout="wide")
st.title("按小时聚合展示")

# 支持现场上传；未上传就读仓库里的CSV
up = st.file_uploader("上传一份同结构 CSV（可选）", type=["csv"])
df = pd.read_csv(up) if up else pd.read_csv("data/hourly_trips.csv")

# 基础校验与类型
assert "pickup_hour" in df.columns and "trips" in df.columns, "CSV 需含 pickup_hour,trips 列"
df["pickup_hour"] = df["pickup_hour"].astype(int)
df["trips"] = pd.to_numeric(df["trips"], errors="coerce")
has_tip = "avg_tip" in df.columns

# 侧边筛选
with st.sidebar:
    st.subheader("筛选")
    hr_min, hr_max = st.slider("展示小时范围", 0, 23, (0, 23))
    show_pct = st.checkbox("显示占比（% of total）", value=False)
    smooth = st.checkbox("显示移动平均（3小时）", value=False)

view = df[(df["pickup_hour"] >= hr_min) & (df["pickup_hour"] <= hr_max)].copy()
view = view.sort_values("pickup_hour")
total = view["trips"].sum()
view["share"] = (view["trips"] / total * 100).round(2) if total else 0
if smooth and len(view) >= 3:
    view["trips_sma3"] = view["trips"].rolling(3, center=True).mean()

# 指标卡
c1, c2, c3 = st.columns(3)
peak = view.iloc[view["trips"].idxmax()] if len(view) else pd.Series({"pickup_hour":0,"trips":0})
c1.metric("总行程数", f"{int(total):,}")
c2.metric("最忙时段", f"{int(peak['pickup_hour']):02d}:00", f"{int(peak['trips']) if total else 0:,}")
c3.metric("平均小费(区间)", f"{view['avg_tip'].mean():.2f}" if has_tip else "—")

# 主图
if show_pct:
    fig = px.bar(view, x="pickup_hour", y="share", labels={"pickup_hour":"小时","share":"占比(%)"})
else:
    ycol = "trips_sma3" if smooth and "trips_sma3" in view else "trips"
    fig = px.bar(view, x="pickup_hour", y=ycol, labels={"pickup_hour":"小时","trips":"数量"})
st.plotly_chart(fig, use_container_width=True)

# 小费折线（可选）
if has_tip:
    fig2 = px.line(view, x="pickup_hour", y="avg_tip", markers=True,
                   labels={"pickup_hour":"小时","avg_tip":"平均小费"})
    st.plotly_chart(fig2, use_container_width=True)

# 下载当前视图
st.download_button("下载当前视图CSV",
                   view.to_csv(index=False).encode("utf-8"),
                   file_name="hourly_view.csv", mime="text/csv")

st.caption("说明：Kaggle(PySpark)完成聚合；网页只做筛选/占比/平滑等轻计算，保证演示秒开。")
