# test_website/streamlit_app.py
import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

# ============ 页面基础 ============
st.set_page_config(page_title="24 小时出行面板", page_icon="🕒", layout="wide")
st.title("24 小时出行面板")
st.caption("峰值、占比与小费趋势 · 支持上传同结构 CSV（可上传原始明细或已聚合表）")

# ============ 数据加载：上传优先 → 默认兜底（已聚合） → 提示 ============
DEFAULT_AGG = Path(__file__).parent / "data" / "hourly_trips.csv"
up = st.file_uploader("上传原始或已聚合的 CSV（均可）", type=["csv"])

def load_csv(src):
    # 自动识别常见分隔符
    return pd.read_csv(src, sep=None, engine="python")

if up is not None:
    raw = load_csv(up)
elif DEFAULT_AGG.exists():
    raw = load_csv(DEFAULT_AGG)
else:
    st.info("请上传 CSV；或先放置示例 data/hourly_trips.csv。")
    st.stop()

# ============ 原始/已聚合自适应 ============
CANDIDATE_TIME_COLS = [
    "tpep_pickup_datetime","pickup_datetime","pickup_time","pickup_ts",
    "started_at","start_time","timestamp","datetime","date","time"
]
CANDIDATE_TIP_COLS = ["avg_tip","tip_amount","tip","tip_amt"]

def to_num(s): return pd.to_numeric(s, errors="coerce")
def is_aggregated(df): return {"pickup_hour","trips"}.issubset(df.columns)

def aggregate_hourly(df):
    """从原始明细聚合到小时级：trips +（若有）avg_tip"""
    time_col = next((c for c in CANDIDATE_TIME_COLS if c in df.columns), None)
    if time_col is None:
        return None
    ts = pd.to_datetime(df[time_col], errors="coerce")
    out = pd.DataFrame({"pickup_hour": ts.dt.hour})
    out["trips"] = 1

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
        agg = out.groupby("pickup_hour", dropna=True).agg(trips=("trips","sum")).reset_index()

    agg = agg.dropna(subset=["pickup_hour"]).copy()
    agg["pickup_hour"] = agg["pickup_hour"].astype(int)
    return agg.sort_values("pickup_hour")

# 得到 df（小时级）
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
        st.error("未识别到时间列；请上传包含时间戳的原始明细，或已聚合表（pickup_hour,trips[,avg_tip]）。")
        st.stop()

# ============ 侧边栏：筛选 & 多参量选择 ============
with st.sidebar:
    st.subheader("筛选")

    DEFAULT_RANGE = (0, 23)
    if "hour_range" not in st.session_state:
        st.session_state["hour_range"] = DEFAULT_RANGE
    hour_range = st.slider("展示小时范围", 0, 23, value=st.session_state["hour_range"], key="hour_range")
    hr_min, hr_max = hour_range

    # 可选参量 = df 中所有数值列（排除 pickup_hour）
    numeric_cols = [c for c in df.columns if c != "pickup_hour" and pd.api.types.is_numeric_dtype(df[c])]
    # 默认选 trips（若存在），否则选第一个数值列
    default_choices = ["trips"] if "trips" in numeric_cols else (numeric_cols[:1] if numeric_cols else [])
    selected_metrics = st.multiselect("选择参量（可多选）", options=numeric_cols, default=default_choices,
                                     help="可同时选择多个参量进行统计与绘图")

    # “显示占比”仅对 trips 有意义；多选时也只作用于 trips 那张图
    enable_share = ("trips" in selected_metrics)
    show_pct = st.checkbox("显示占比（仅对 trips）", value=False, disabled=not enable_share)
    smooth   = st.checkbox("显示移动平均（3小时）", value=False)

    st.divider()
    st.markdown("**提示**：多选时将生成小多图（每个参量一张），避免不同量纲混在一张图难以阅读。")
    def reset_range(): st.session_state["hour_range"] = DEFAULT_RANGE
    st.button("重置筛选为 0–23 点", on_click=reset_range)

# 过滤 & 排序
view = df[(df["pickup_hour"] >= hr_min) & (df["pickup_hour"] <= hr_max)].copy().sort_values("pickup_hour")
if len(view) == 0:
    st.warning("当前筛选范围内没有数据。"); st.stop()

# KPI 仍基于 trips（如不存在则给兜底）
total = float(view["trips"].sum()) if "trips" in view.columns else float("nan")
if "trips" in view.columns and view["trips"].notna().any():
    peak_row = view.loc[view["trips"].idxmax()]
    peak_hour = int(peak_row["pickup_hour"]); peak_trips = int(peak_row["trips"])
    peak_share = (peak_trips / total * 100) if total else 0.0
else:
    peak_hour, peak_trips, peak_share = 0, 0, 0.0

c1, c2, c3 = st.columns(3)
c1.metric("总行程数", f"{int(total):,}" if pd.notnull(total) else "—")
c2.metric("最忙时段", f"{peak_hour:02d}:00", f"{peak_trips:,}" if peak_trips else "—")
c3.metric("峰值占比", f"{peak_share:.2f}%" if peak_trips else "—")

# ============ 图表 ============
tab1, tab2 = st.tabs(["主图（多参量）", "数据表"])

with tab1:
    if not selected_metrics:
        st.info("请至少选择一个参量。")
    else:
        # 单选：保持原先单图风格
        if len(selected_metrics) == 1:
            metric = selected_metrics[0]
            plot_df = view.copy()

            # trips 的占比/平滑
            if metric == "trips" and show_pct:
                plot_df["share"] = (plot_df["trips"] / total * 100).round(2) if total > 0 else 0.0
                ycol, y_label = "share", "占比(%)"
            else:
                ycol, y_label = metric, metric

            if smooth and ycol in plot_df.columns and ycol != "share" and len(plot_df) >= 3:
                plot_df[f"{ycol}_sma3"] = plot_df[ycol].rolling(3, center=True).mean()
                ycol_plot = f"{ycol}_sma3"
            else:
                ycol_plot = ycol

            # 峰值高亮依据 trips（若有）
            colors = ["#E45756" if ("trips" in view.columns and int(h) == peak_hour) else "#4C78A8"
                      for h in plot_df["pickup_hour"]]
            fig = px.bar(plot_df, x="pickup_hour", y=ycol_plot,
                         labels={"pickup_hour":"小时", ycol_plot:y_label})
            fig.update_traces(marker_color=colors,
                              hovertemplate="小时=%{x}<br>"+y_label+"=%{y}<extra></extra>")
            # 注释（若该小时存在 ycol_plot 的值）
            try:
                if "trips" in view.columns and peak_trips > 0 and ycol_plot in plot_df.columns:
                    ann_y = plot_df.loc[plot_df["pickup_hour"] == peak_hour, ycol_plot].iloc[0]
                    fig.add_annotation(x=peak_hour, y=ann_y, text="峰值(以 trips)", showarrow=True, yshift=10)
            except Exception:
                pass

            st.plotly_chart(fig, use_container_width=True)

        # 多选：为每个参量画一张“小多图”
        else:
            for metric in selected_metrics:
                st.subheader(f"· {metric}")
                plot_df = view.copy()
                ycol, y_label = metric, metric

                # 仅对 trips 做占比
                if metric == "trips" and show_pct:
                    plot_df["share"] = (plot_df["trips"] / total * 100).round(2) if total > 0 else 0.0
                    ycol, y_label = "share", "占比(%)"

                # 平滑
                if smooth and ycol in plot_df.columns and ycol != "share" and len(plot_df) >= 3:
                    plot_df[f"{ycol}_sma3"] = plot_df[ycol].rolling(3, center=True).mean()
                    ycol_plot = f"{ycol}_sma3"
                else:
                    ycol_plot = ycol

                colors = ["#E45756" if ("trips" in view.columns and int(h) == peak_hour) else "#4C78A8"
                          for h in plot_df["pickup_hour"]]
                fig = px.bar(plot_df, x="pickup_hour", y=ycol_plot,
                             labels={"pickup_hour":"小时", ycol_plot:y_label})
                fig.update_traces(marker_color=colors,
                                  hovertemplate="小时=%{x}<br>"+y_label+"=%{y}<extra></extra>")
                st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.dataframe(view.reset_index(drop=True), use_container_width=True, hide_index=True)

# ============ 下载当前视图 ============
st.download_button(
    "下载当前视图CSV",
    view.to_csv(index=False).encode("utf-8"),
    file_name="hourly_view.csv",
    mime="text/csv"
)
