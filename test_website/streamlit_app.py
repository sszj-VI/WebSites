import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from html import escape
from pathlib import Path
import hashlib, re, io

# ---------------- 页面配置 ----------------
st.set_page_config(
    page_title="数据聚合处理网站",
    page_icon="🧮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------- 轻量样式（含两侧黄→蓝渐变、更显眼的侧栏开关） ----------------
def apply_compact_css():
    st.markdown("""
    <style>
      .block-container { padding-top: 1.2rem; padding-bottom: 1.2rem; }
      section[data-testid="stSidebar"] { padding-top: .6rem !important; }
      .modebar { filter: opacity(75%); }
      [data-testid="collapsedControl"], button[title="Toggle sidebar"] {
        position: relative !important; z-index: 999;
        background: rgba(76,120,168,.18) !important;
        border-radius: 999px !important; padding: 6px 8px !important;
        box-shadow: 0 0 0 2px rgba(76,120,168,.28);
      }
      .stApp{
        background-color:#fff !important;
        background-image:
          linear-gradient(180deg, rgba(245,158,11,.42) 0%, rgba(37,99,235,.42) 100%),
          linear-gradient(180deg, rgba(245,158,11,.42) 0%, rgba(37,99,235,.42) 100%);
        background-repeat: no-repeat,no-repeat;
        background-position: left top, right top;
        background-size: 24px 100vh, 24px 100vh;
        background-attachment: fixed,fixed;
      }
    </style>
    """, unsafe_allow_html=True)
apply_compact_css()

# ---------------- 小工具 ----------------
BAR_COLOR  = "#4C78A8"
PEAK_COLOR = "#E45756"

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
    return fig

def chips(items):
    return " ".join([f"<span style='background:#eef2ff;color:#3730a3;border-radius:12px;padding:2px 8px;margin-right:6px;font-size:12px'>{escape(str(i))}</span>" for i in items])

# ---------------- 持久化：uploads/ ----------------
UPLOADS_DIR = Path("uploads"); UPLOADS_DIR.mkdir(exist_ok=True)

def _sanitize(name:str)->str: return re.sub(r"[^A-Za-z0-9_.-]+","_",name)
def _sha12(b:bytes)->str:    return hashlib.sha1(b).hexdigest()[:12]

@st.cache_data(show_spinner=False)
def load_csv_from_path(path_str:str)->pd.DataFrame:
    return pd.read_csv(path_str, sep=None, engine="python")

def read_csv_any(src):
    if isinstance(src,(str,Path)):
        return load_csv_from_path(str(src))
    bio = io.BytesIO(src.getbuffer() if hasattr(src,"getbuffer") else src.read())
    return pd.read_csv(bio, sep=None, engine="python")

def restore_by_sha(sha:str):
    matches = list(UPLOADS_DIR.glob(f"{sha}_*"))
    return matches[0] if matches else None

def save_uploaded_auto(up_file):
    """自动保存上传文件，返回(保存路径, sha, 文件名)"""
    data = up_file.getbuffer() if hasattr(up_file,"getbuffer") else up_file.read()
    if isinstance(data, memoryview): data = data.tobytes()
    sha = _sha12(data)
    fname = f"{sha}_{_sanitize(up_file.name)}"
    path = UPLOADS_DIR / fname
    if not path.exists(): path.write_bytes(data)
    return path, sha, fname

# ---------------- 顶部 ----------------
st.title("数据聚合处理网站")
st.caption("上传 CSV → 左侧选择 X/时间派生/Y/聚合与范围 → 右侧出图与导出")

# ---------------- 上传/恢复 ----------------
up = st.file_uploader("上传 CSV（原始或已聚合均可）", type=["csv"])

saved_sha = st.query_params.get("file", None)
restored_path = restore_by_sha(saved_sha) if saved_sha else None

# 统一数据来源：优先新上传（并自动保存与写 URL），否则尝试从 URL 恢复
source = None
if up is not None:
    path, sha, fname = save_uploaded_auto(up)
    st.query_params["file"] = sha            # 写入 URL
    source = str(path)                        # 直接使用磁盘文件
    # 不强制 st.rerun，避免循环；当前会直接用新文件渲染
elif restored_path is not None and restored_path.exists():
    source = str(restored_path)
else:
    st.info("📄 请先上传 CSV 文件开始分析。")
    st.stop()

# 读取数据
try:
    raw = read_csv_any(source)
except Exception as e:
    st.error(f"读取 CSV 失败：{e}")
    st.stop()
if raw.empty:
    st.error("读取到空表，请检查 CSV 内容。")
    st.stop()

# ---------------- 侧边栏（把功能都放左侧） ----------------
with st.sidebar:
    st.header("维度与度量")

    # 自动识别时间列、数值列
    def can_dt(s)->float:
        try:  return pd.to_datetime(s, errors="coerce").notna().mean()
        except: return 0.0
    def is_num(s)->bool:
        try:  return pd.to_numeric(s, errors="coerce").notna().mean() > .5
        except: return False

    dt_cols  = [c for c in raw.columns if can_dt(raw[c])>0.5]
    num_cols = [c for c in raw.columns if is_num(raw[c])]

    x_col = st.selectbox("横坐标 (X) 🌐", options=list(raw.columns), help="可选时间/数值/类别列；时间列可派生粒度")
    x_is_dt = x_col in dt_cols
    x_time_mode = None
    if x_is_dt:
        x_time_mode = st.selectbox("时间派生 ⏱️", ["小时(0–23)","日期","星期(一~日)","月份(1~12)"], help="从时间列派生一个分组键再聚合")

    y_options = [c for c in num_cols if c != x_col]
    y_cols = st.multiselect("纵坐标 (Y，可多选) 📈", options=y_options, placeholder="请选择 1~3 个数值列", help="建议 1~3 个指标")
    agg_fn = st.selectbox("聚合方式（对 Y）🧮", ["sum","mean","median","max","min"], disabled=(len(y_cols)==0))

# ---------------- 构造分组键 ----------------
df = raw.copy()
if x_is_dt:
    ts = pd.to_datetime(df[x_col], errors="coerce")
    if x_time_mode == "小时(0–23)": df["_X_key"] = ts.dt.hour
    elif x_time_mode == "日期":    df["_X_key"] = ts.dt.date
    elif x_time_mode == "星期(一~日)":
        wd = ts.dt.weekday; mapping = {0:"一",1:"二",2:"三",3:"四",4:"五",5:"六",6:"日"}
        s = wd.map(mapping); cat = pd.CategoricalDtype(categories=list(mapping.values()), ordered=True)
        df["_X_key"] = s.astype(cat)
    elif x_time_mode == "月份(1~12)": df["_X_key"] = ts.dt.month
    else: df["_X_key"] = ts.astype("string")
else:
    df["_X_key"] = df[x_col].astype("string")

# Y → 数值
for c in y_cols: df[c] = pd.to_numeric(df[c], errors="coerce")

# 未选 Y 给出提示
if len(y_cols)==0:
    st.info("👉 请在左侧 **选择至少一个纵坐标（数值列）** 再查看图表。")
    st.stop()

# ---------------- 聚合 ----------------
with st.spinner("正在计算聚合视图…"):
    df = df.dropna(subset=["_X_key"] + y_cols)
    grouped = df.groupby("_X_key")
    agg_map = {c: agg_fn for c in y_cols}
    df_view = grouped.agg(agg_map).reset_index().rename(columns={"_X_key": x_col})

# 合理排序
if x_is_dt and x_time_mode in ["小时(0–23)","月份(1~12)"]:
    df_view[x_col] = pd.to_numeric(df_view[x_col], errors="coerce")
    df_view = df_view.sort_values(x_col)
elif pd.api.types.is_numeric_dtype(df_view[x_col]):
    df_view = df_view.sort_values(x_col)

# ---------------- 显示范围（也在侧边栏） ----------------
with st.sidebar:
    st.subheader("显示范围")
    x_vals = df_view[x_col]
    if x_is_dt and x_time_mode=="日期":
        xv = pd.to_datetime(x_vals, errors="coerce")
        if xv.notna().any():
            min_d, max_d = xv.min().date(), xv.max().date()
            d_range = st.date_input("日期范围", (min_d, max_d))
            if isinstance(d_range, tuple) and len(d_range)==2:
                mask = (xv.dt.date >= d_range[0]) & (xv.dt.date <= d_range[1])
                df_view = df_view.loc[mask]
    elif pd.api.types.is_numeric_dtype(x_vals):
        try:
            x_min, x_max = float(np.nanmin(x_vals)), float(np.nanmax(x_vals))
            uniq = pd.unique(x_vals).shape[0]
            if str(x_vals.dtype).startswith("int") and uniq<=100:
                r = st.slider("X 范围", min_value=int(x_min), max_value=int(x_max), value=(int(x_min), int(x_max)))
                df_view = df_view[(x_vals >= r[0]) & (x_vals <= r[1])]
            else:
                c1,c2 = st.columns(2)
                vmin = c1.number_input("X 最小值", value=float(x_min))
                vmax = c2.number_input("X 最大值", value=float(x_max))
                df_view = df_view[(x_vals >= vmin) & (x_vals <= vmax)]
        except: pass
    else:
        cats = list(pd.unique(x_vals.astype("string")))
        chosen = st.multiselect("选择 X 类别", options=cats, default=cats)
        df_view = df_view[df_view[x_col].astype("string").isin(chosen)]

# ---------------- 顶部说明 ----------------
st.subheader(f"按「{x_col}」聚合（{agg_fn}）")
st.markdown(
    f"**X：** `{x_col}` {' · ⏱️ '+x_time_mode if x_is_dt else ''}  "
    f"&nbsp;&nbsp; **Y：** {chips(y_cols)}  "
    f"&nbsp;&nbsp; **样本：** <span style='color:#6b7280'>{len(df):,}</span>",
    unsafe_allow_html=True
)

# ---------------- 图表 & 下载 ----------------
if df_view.empty:
    st.warning("当前筛选条件下没有可展示的数据。请调整范围或更换 Y。")
else:
    for y in y_cols:
        st.markdown(f"**· {y}**")
        peak_x = None
        if df_view[y].notna().any():
            try: peak_x = df_view.loc[df_view[y].idxmax(), x_col]
            except: peak_x = None
        colors = [PEAK_COLOR if (peak_x is not None and str(v)==str(peak_x)) else BAR_COLOR for v in df_view[x_col]]
        fig = px.bar(df_view, x=x_col, y=y)
        fig.update_traces(marker_color=colors, hovertemplate=f"{x_col}=%{{x}}<br>{y}=%{{y}}<extra></extra>")
        fig = style_bar(fig, x_col, y, peak_x=peak_x)
        st.plotly_chart(fig, use_container_width=True,
                        config={"displaylogo":False,
                                "modeBarButtonsToRemove":["lasso2d","select2d","autoscale","zoomIn2d","zoomOut2d"]})

tab1, tab2 = st.tabs(["当前聚合视图 (可下载)", "原始数据预览"])
with tab1:
    st.dataframe(df_view, use_container_width=True, hide_index=True)
    st.download_button("下载当前聚合视图 CSV",
                       df_view.to_csv(index=False).encode("utf-8"),
                       file_name="aggregated_view.csv", mime="text/csv")
with tab2:
    st.dataframe(raw.head(200), use_container_width=True, hide_index=True)
