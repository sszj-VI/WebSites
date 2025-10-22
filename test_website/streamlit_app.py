# streamlit_app.py —— 本地持久化上传 + 自动恢复 + 两侧渐变条带
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from html import escape

# 新增：持久化 & 路由参数
from pathlib import Path
import hashlib, re, io

# ---------- 页面基础：默认展开侧边栏 ----------
st.set_page_config(
    page_title="数据聚合处理网站",
    page_icon="🧮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- 轻量 CSS：紧凑布局 + 显眼开关 + 两侧“黄→蓝”渐变条带 ----------
def apply_compact_css():
    st.markdown("""
    <style>
      /* 紧凑留白 */
      .block-container { padding-top: 1.2rem; padding-bottom: 1.2rem; }
      section[data-testid="stSidebar"] { padding-top: .6rem !important; }
      h1, .stMarkdown h1 { letter-spacing:.5px; }
      .stCaption { color:#6b7280 !important; }
      div[data-testid="stExpander"] {
        border-radius: 12px; box-shadow: 0 2px 10px rgba(20,30,60,.04);
      }
      .stDownloadButton > button { border-radius:10px; }
      .modebar { filter: opacity(75%); }

      /* 右上角侧边栏开关更显眼 */
      [data-testid="collapsedControl"],
      button[title="Toggle sidebar"],
      button[kind="header"] { position: relative !important; z-index: 999; }
      [data-testid="collapsedControl"] > div,
      button[title="Toggle sidebar"],
      button[kind="header"] {
        background: rgba(76,120,168,.18) !important;
        border-radius: 999px !important;
        padding: 6px 8px !important;
        box-shadow: 0 0 0 2px rgba(76,120,168,.28);
        animation: glow 2.6s ease-in-out infinite;
      }
      [data-testid="collapsedControl"] svg,
      button[title="Toggle sidebar"] svg,
      button[kind="header"] svg { transform: scale(1.15); }
      @keyframes glow {
        0% { box-shadow: 0 0 0 2px rgba(76,120,168,.28); }
        50% { box-shadow: 0 0 0 5px rgba(229,87,86,.30); }
        100% { box-shadow: 0 0 0 2px rgba(76,120,168,.28); }
      }

      /* —— 两侧渐变条带（更宽 + 黄→蓝） —— */
      .stApp{
        background-color: #ffffff !important;

        /* 左条带、右条带 */
        background-image:
          /* 左：从上到下 由黄到蓝 */
          linear-gradient(180deg, rgba(245,158,11,.42) 0%, rgba(37,99,235,.42) 100%),
          /* 右：从上到下 由黄到蓝（如需镜像可调换顺序） */
          linear-gradient(180deg, rgba(245,158,11,.42) 0%, rgba(37,99,235,.42) 100%);
        background-repeat: no-repeat, no-repeat;
        background-position: left top, right top;

        /* 条带宽度（可改 20~30px） */
        background-size: 24px 100vh, 24px 100vh;

        /* 固定在两侧，不随滚动抖动 */
        background-attachment: fixed, fixed;
      }
    </style>
    """, unsafe_allow_html=True)

apply_compact_css()

# ---------- 配色（图表用，固定色） ----------
BAR_COLOR  = "#4C78A8"
PEAK_COLOR = "#E45756"

# ---------- 图表统一风格 ----------
def style_bar(fig, x_col, y_col, peak_x=None, title=None):
    fig.update_layout(
        template="plotly_white",
        title=dict(text=title or "", x=0.0, xanchor="left", y=0.95, font=dict(size=18)),
        margin=dict(l=10, r=10, t=35, b=0),
        xaxis=dict(title="", showgrid=False, zeroline=False),
        yaxis=dict(title="", gridcolor="rgba(0,0,0,0.06)", zeroline=False),
        hovermode="x unified",
        font=dict(size=13),
    )
    if peak_x is not None:
        fig.add_vline(x=peak_x, line_width=1, line_dash="dot", line_color=PEAK_COLOR)
        try:
            ymax = float(pd.Series(fig.data[0].y).max())
        except Exception:
            ymax = None
        fig.add_annotation(
            x=peak_x, y=ymax, text="峰值", showarrow=True, arrowhead=2, ax=20, ay=-30,
            font=dict(color=PEAK_COLOR), arrowcolor=PEAK_COLOR, bgcolor="rgba(255,255,255,.7)"
        )
    return fig

def chips(items):
    return " ".join([
        f"<span style='background:#eef2ff;color:#3730a3;border-radius:12px;padding:2px 8px;margin-right:6px;font-size:12px'>{escape(str(i))}</span>"
        for i in items
    ])

# ===================== 本地持久化：uploads/ ===================== #
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

def _sanitize_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)

def _sha12(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()[:12]

def save_uploaded_file_to_disk(up_file):
    """
    保存 st.file_uploader 的文件到 uploads/：
    返回 (Path, sha, 保存文件名)
    """
    data = up_file.getbuffer() if hasattr(up_file, "getbuffer") else up_file.read()
    if isinstance(data, memoryview):
        data = data.tobytes()
    sha = _sha12(data)
    fname = f"{sha}_{_sanitize_name(up_file.name)}"
    path = UPLOADS_DIR / fname
    if not path.exists():
        path.write_bytes(data)
    return path, sha, fname

@st.cache_data(show_spinner=False)
def load_csv_from_path(path_str: str) -> pd.DataFrame:
    """从磁盘路径读取 CSV（带缓存）"""
    return pd.read_csv(path_str, sep=None, engine="python")

def read_csv_any(src):
    """
    兼容两种来源：
    - st.file_uploader 返回的 UploadedFile
    - 磁盘路径（str/Path）
    """
    if isinstance(src, (str, Path)):
        return load_csv_from_path(str(src))
    else:
        bio = io.BytesIO(src.getbuffer() if hasattr(src, "getbuffer") else src.read())
        return pd.read_csv(bio, sep=None, engine="python")

def restore_path_by_sha(sha: str):
    matches = list(UPLOADS_DIR.glob(f"{sha}_*"))
    return matches[0] if matches else None
# =============================================================== #

# ---------- 顶部 ----------
st.title("数据聚合处理网站")
st.caption("用户自选横/纵坐标 · 时间列可派生（小时/日期/星期/月） · 动态范围筛选 · 多参量/多图")

# ---------- 永远渲染一个“基础侧边栏”提示 ----------
with st.sidebar:
    st.subheader("🎛 面板")
    st.caption("右上角按钮可展开/收起侧栏。上传 CSV 后解锁“维度与度量”。")

# ---------- 上传区 + 本地持久化控制 ----------
c_up, c_ops = st.columns([4, 2])
with c_up:
    up = st.file_uploader("上传 CSV（原始明细或已聚合均可）", type=["csv"])

# 从 URL 恢复
saved_sha = st.query_params.get("file", None)
restored_path = restore_path_by_sha(saved_sha) if saved_sha else None

with c_ops:
    st.markdown("#### ")
    if up is not None:
        if st.button("💾 保存并记住"):
            path, sha, fname = save_uploaded_file_to_disk(up)
            st.query_params["file"] = sha
            st.success(f"已保存：{fname}")
            st.rerun()

    # 选择已保存文件
    saved_files = sorted(UPLOADS_DIR.glob("*.csv"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
    name2path = {p.name: p for p in saved_files}
    choice = st.selectbox("📂 已保存文件", ["（不选）"] + list(name2path.keys()))
    if choice != "（不选）":
        restored_path = name2path[choice]
        st.query_params["file"] = restored_path.name.split("_", 1)[0]
        st.rerun()

    if st.button("🧹 清除记忆（仅清 URL）"):
        st.query_params.clear()
        st.info("已清除链接记忆。若需物理删除文件，请到 uploads/ 目录手动删除。")
        st.rerun()

# 统一数据来源
source = None
if up is not None:
    source = up
elif restored_path is not None and Path(restored_path).exists():
    source = str(restored_path)
else:
    st.info("请上传 CSV 文件开始分析，或在右侧 **📂 已保存文件** 中选择。")
    st.stop()

# 读取数据
try:
    raw = read_csv_any(source)
except Exception as e:
    st.error(f"读取 CSV 失败：{e}")
    st.stop()
if raw.empty:
    st.error("读取到的表为空，请检查 CSV 内容。")
    st.stop()
st.toast("✅ 数据就绪", icon="✅")

# ---------- 工具：识别时间列/数值列 ----------
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

# ---------- 侧边栏：数据依赖控件 ----------
with st.sidebar:
    x_col = st.selectbox(
        "横坐标 (X) 🌐",
        options=list(raw.columns),
        help="可选时间/数值/类别列；若为时间列可派生为小时/日期/星期/月"
    )
    x_is_datetime = x_col in datetime_candidates
    x_time_mode = None
    if x_is_datetime:
        x_time_mode = st.selectbox(
            "时间派生 ⏱️",
            ["小时(0–23)", "日期", "星期(一~日)", "月份(1~12)"],
            help="从时间列派生一个分组键再聚合"
        )

    y_options = [c for c in numeric_candidates if c != x_col]
    y_key = f"ycols::{x_col}"  # 切换 X 时清空 Y
    y_cols = st.multiselect(
        "纵坐标 (Y，可多选) 📈",
        options=y_options,
        default=[],
        key=y_key,
        placeholder="请选择 1~3 个数值列，例如 trip_km、fare_amount、avg_speed_kmph …",
        help="建议选择 1~3 个指标，便于对比"
    )

    agg_fn = st.selectbox(
        "聚合方式（对 Y 列）🧮",
        ["sum", "mean", "median", "max", "min"],
        index=0,
        disabled=(len(y_cols) == 0)
    )

# ---------- 构造分组键（含时间派生） ----------
df = raw.copy()
if x_is_datetime:
    ts = pd.to_datetime(df[x_col], errors="coerce")
    if x_time_mode == "小时(0–23)":
        df["_X_key"] = ts.dt.hour
    elif x_time_mode == "日期":
        df["_X_key"] = ts.dt.date
    elif x_time_mode == "星期(一~日)":
        wd = ts.dt.weekday
        mapping = {0:"一",1:"二",2:"三",3:"四",4:"五",5:"六",6:"日"}
        df["_X_key"] = wd.map(mapping)
        cat_type = pd.CategoricalDtype(categories=list(mapping.values()), ordered=True)
        df["_X_key"] = df["_X_key"].astype(cat_type)
    elif x_time_mode == "月份(1~12)":
        df["_X_key"] = ts.dt.month
    else:
        df["_X_key"] = ts.astype("string")
else:
    df["_X_key"] = df[x_col].astype("string")

# Y → 数值
for c in y_cols:
    df[c] = pd.to_numeric(df[c], errors="coerce")

# 未选 Y：温和提示并停止
if len(y_cols) == 0:
    st.info("👉 请在左侧 **选择至少一个纵坐标（数值列）** 后再查看图表。")
    st.stop()

# ---------- 聚合 ----------
with st.spinner("正在计算聚合视图…"):
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

# ---------- 侧边栏：显示范围 ----------
with st.sidebar:
    st.subheader("显示范围")
    x_vals = df_view[x_col]
    if x_is_datetime and x_time_mode == "日期":
        xv = pd.to_datetime(x_vals, errors="coerce")
        if xv.notna().any():
            min_d = xv.min().date(); max_d = xv.max().date()
            d_range = st.date_input("日期范围", (min_d, max_d))
            if isinstance(d_range, tuple) and len(d_range) == 2:
                mask = (xv.dt.date >= d_range[0]) & (xv.dt.date <= d_range[1])
                df_view = df_view.loc[mask]
    elif pd.api.types.is_numeric_dtype(x_vals):
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
        cats = list(pd.unique(x_vals.astype("string")))
        chosen = st.multiselect("选择 X 类别", options=cats, default=cats)
        df_view = df_view[df_view[x_col].astype("string").isin(chosen)]

# ---------- 顶部描述 ----------
st.subheader(f"按「{x_col}」聚合（{agg_fn}）")
st.markdown(
    f"**X：** `{x_col}` {' · ⏱️ '+x_time_mode if x_is_datetime else ''}  "
    f"&nbsp;&nbsp; **Y：** {chips(y_cols)}  "
    f"&nbsp;&nbsp; **样本：** <span style='color:#6b7280'>{len(df):,}</span>",
    unsafe_allow_html=True
)

# ---------- 图表 ----------
if df_view.empty:
    st.warning("当前筛选条件下没有可展示的数据。请调整显示范围或更换 Y。")
else:
    for y in y_cols:
        st.markdown(f"**· {y}**")
        peak_x = None
        if df_view[y].notna().any():
            try:
                peak_x = df_view.loc[df_view[y].idxmax(), x_col]
            except Exception:
                peak_x = None

        colors = [PEAK_COLOR if (peak_x is not None and str(v)==str(peak_x)) else BAR_COLOR
                  for v in df_view[x_col]]
        fig = px.bar(df_view, x=x_col, y=y)
        fig.update_traces(marker_color=colors,
                          hovertemplate=f"{x_col}=%{{x}}<br>{y}=%{{y}}<extra></extra>")
        fig = style_bar(fig, x_col, y, peak_x=peak_x, title=None)
        st.plotly_chart(fig, use_container_width=True,
                        config={"displaylogo": False,
                                "modeBarButtonsToRemove": ["lasso2d","select2d","autoscale","zoomIn2d","zoomOut2d"]})

# ---------- 视图下载 & 原表预览 ----------
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
