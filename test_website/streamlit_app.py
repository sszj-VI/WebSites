# streamlit_app.py —— 合并版（侧边栏可见 & 显眼开关 + 主题模板/单项修改 + 原有功能）
import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from html import escape

# ---------- 页面基础：默认展开侧边栏 ----------
st.set_page_config(
    page_title="数据聚合处理网站",
    page_icon="🧮",
    layout="wide",
    initial_sidebar_state="expanded"  # ✅ 无论是否有文件，都默认展开侧边栏
)

# ---------- 轻量 CSS：紧凑布局 + 显眼的侧边栏开关 ----------
def apply_compact_css():
    st.markdown("""
    <style>
      .block-container { padding-top: 1.2rem; padding-bottom: 1.2rem; }
      section[data-testid="stSidebar"] { padding-top: .6rem !important; }
      h1, .stMarkdown h1 { letter-spacing:.5px; }
      .stCaption { color:#6b7280 !important; }
      div[data-testid="stExpander"] {
        border-radius: 12px; box-shadow: 0 2px 10px rgba(20,30,60,.04);
      }
      .stDownloadButton > button { border-radius:10px; }
      .modebar { filter: opacity(75%); }

      /* 让右上角的侧边栏开关更显眼 */
      [data-testid="collapsedControl"], 
      button[title="Toggle sidebar"],
      button[kind="header"] {
        position: relative !important;
        z-index: 999;
      }
      [data-testid="collapsedControl"] > div,
      button[title="Toggle sidebar"],
      button[kind="header"] {
        background: rgba(46, 144, 250, .15) !important;
        border-radius: 999px !important;
        padding: 6px 8px !important;
        box-shadow: 0 0 0 2px rgba(46, 144, 250, .25);
        animation: glow 2.6s ease-in-out infinite;
      }
      [data-testid="collapsedControl"] svg, 
      button[title="Toggle sidebar"] svg,
      button[kind="header"] svg {
        transform: scale(1.15);
      }
      @keyframes glow {
        0%   { box-shadow: 0 0 0 2px rgba(46,144,250,.25); }
        50%  { box-shadow: 0 0 0 5px rgba(46,144,250,.35); }
        100% { box-shadow: 0 0 0 2px rgba(46,144,250,.25); }
      }
    </style>
    """, unsafe_allow_html=True)

apply_compact_css()

# ---------- 主题：从 theme_user.toml 读取 + 运行时覆盖 ----------
try:
    import tomllib  # Py3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # Py3.10 及以下

DEFAULT_THEME = {
    "primaryColor": "#4C78A8",
    "backgroundColor": "#FFFFFF",
    "secondaryBackgroundColor": "#F6F8FB",
    "textColor": "#1F2937",
    "barColor": "#4C78A8",
    "peakColor": "#E45756",
}

def load_user_theme():
    theme = DEFAULT_THEME.copy()
    for p in ("theme_user.toml", "data/theme_user.toml", ".streamlit/theme_user.toml"):
        if os.path.exists(p):
            try:
                with open(p, "rb") as f:
                    conf = tomllib.load(f)
                theme.update(conf.get("theme", {}))
                break
            except Exception:
                pass
    return theme

def apply_theme_css(theme: dict):
    st.markdown(f"""
    <style>
      .stApp {{
        background: {theme["backgroundColor"]} !important;
        color: {theme["textColor"]} !important;
      }}
      section[data-testid="stSidebar"] {{
        background: {theme["secondaryBackgroundColor"]} !important;
      }}
      .stButton>button, .stDownloadButton>button, .stFileUploader>div>button {{
        background: {theme["primaryColor"]} !important;
        border-color: {theme["primaryColor"]} !important;
        color: white !important;
      }}
    </style>
    """, unsafe_allow_html=True)

THEME = load_user_theme()
apply_theme_css(THEME)

# 图表颜色存入会话
if "BAR_COLOR" not in st.session_state:
    st.session_state["BAR_COLOR"] = THEME.get("barColor", "#4C78A8")
if "PEAK_COLOR" not in st.session_state:
    st.session_state["PEAK_COLOR"] = THEME.get("peakColor", "#E45756")

# ---------- 主题模板与单项修改控件 ----------
PRESET_THEMES = {
    "Calm Blue（清爽蓝）": {
        "primaryColor": "#4C78A8",
        "backgroundColor": "#FFFFFF",
        "secondaryBackgroundColor": "#F6F8FB",
        "textColor": "#1F2937",
        "barColor": "#4C78A8",
        "peakColor": "#E45756",
    },
    "Dark Slate（暗黑冷灰）": {
        "primaryColor": "#60A5FA",
        "backgroundColor": "#0B1220",
        "secondaryBackgroundColor": "#111827",
        "textColor": "#E5E7EB",
        "barColor": "#60A5FA",
        "peakColor": "#F87171",
    },
    "Ocean Breeze（海蓝清新）": {
        "primaryColor": "#0EA5E9",
        "backgroundColor": "#F8FAFC",
        "secondaryBackgroundColor": "#EFF6FF",
        "textColor": "#0F172A",
        "barColor": "#0284C7",
        "peakColor": "#F59E0B",
    },
    "Warm Sunset（暖色橙光）": {
        "primaryColor": "#F97316",
        "backgroundColor": "#FFFDF9",
        "secondaryBackgroundColor": "#FFF3E8",
        "textColor": "#1F2937",
        "barColor": "#F97316",
        "peakColor": "#DC2626",
    },
    "Graphite Violet（石墨紫）": {
        "primaryColor": "#8B5CF6",
        "backgroundColor": "#1F2430",
        "secondaryBackgroundColor": "#2B3140",
        "textColor": "#E5E7EB",
        "barColor": "#8B5CF6",
        "peakColor": "#F97316",
    },
}

def _theme_toml_text(theme: dict, bar: str, peak: str) -> str:
    keys = ["primaryColor","backgroundColor","secondaryBackgroundColor","textColor","barColor","peakColor"]
    kv = {**theme, "barColor": bar, "peakColor": peak}
    return "[theme]\n" + "\n".join(f'{k}="{kv[k]}"' for k in keys)

def theme_controls(theme: dict):
    with st.sidebar.expander("🎨 主题设置", expanded=False):
        mode = st.radio("方式", ["选择模板", "单项修改"], horizontal=True)

        if mode == "选择模板":
            preset = st.selectbox("主题模板", list(PRESET_THEMES.keys()))
            c1, c2 = st.columns([1,1])
            if c1.button("应用模板", use_container_width=True):
                p = PRESET_THEMES[preset]
                for k in ["primaryColor","backgroundColor","secondaryBackgroundColor","textColor"]:
                    theme[k] = p[k]
                st.session_state["BAR_COLOR"]  = p["barColor"]
                st.session_state["PEAK_COLOR"] = p["peakColor"]
                st.success(f"已应用：{preset}")
                apply_theme_css(theme)
            st.download_button(
                "下载该模板为 theme_user.toml",
                _theme_toml_text(PRESET_THEMES[preset], PRESET_THEMES[preset]["barColor"], PRESET_THEMES[preset]["peakColor"]).encode("utf-8"),
                file_name="theme_user.toml",
                mime="text/plain",
                use_container_width=True
            )
        else:
            items = st.multiselect(
                "选择要修改的项",
                ["primaryColor","backgroundColor","secondaryBackgroundColor","textColor","barColor","peakColor"]
            )
            cols = st.columns(2)
            for i, k in enumerate(items):
                if k in ["barColor","peakColor"]:
                    default = st.session_state["BAR_COLOR"] if k=="barColor" else st.session_state["PEAK_COLOR"]
                    new = cols[i%2].color_picker(k, default)
                    if k == "barColor":
                        st.session_state["BAR_COLOR"] = new
                    else:
                        st.session_state["PEAK_COLOR"] = new
                else:
                    new = cols[i%2].color_picker(k, theme.get(k, DEFAULT_THEME[k]))
                    theme[k] = new
            apply_theme_css(theme)
            st.download_button(
                "下载当前主题为 theme_user.toml",
                _theme_toml_text(theme, st.session_state["BAR_COLOR"], st.session_state["PEAK_COLOR"]).encode("utf-8"),
                file_name="theme_user.toml",
                mime="text/plain",
                use_container_width=True
            )
    return theme

# 先渲染一个“基础侧边栏”（即使没有文件也可见）
with st.sidebar:
    st.subheader("🎛 面板")
    st.caption("右上角按钮可展开/收起侧栏。上传 CSV 后解锁“维度与度量”。")

# 主题控件总是可用（不依赖数据）
THEME = theme_controls(THEME)

# ---------- 顶部 ----------
st.title("数据聚合处理网站")
st.caption("用户自选横/纵坐标 · 时间列可派生（小时/日期/星期/月） · 动态范围筛选 · 多参量/多图 · 主题可定制")

# ---------- 上传 CSV ----------
up = st.file_uploader("上传 CSV（原始明细或已聚合均可）", type=["csv"])

def read_csv_any(src):
    return pd.read_csv(src, sep=None, engine="python")

# 侧边栏“维度与度量”标题总出现；无文件时仅提示
with st.sidebar:
    st.subheader("维度与度量")

if up is None:
    with st.sidebar:
        st.info("请先上传 CSV 解锁这里的设置。")
    st.info("请上传 CSV 文件以开始分析。")
    st.stop()

try:
    raw = read_csv_any(up)
except Exception as e:
    st.error(f"读取 CSV 失败：{e}")
    st.stop()

if raw.empty:
    st.error("读取到的表为空，请检查 CSV 内容。")
    st.stop()

st.toast("✅ 文件上传成功，正在解析…", icon="✅")

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

# ---------- 侧边栏：真正的数据依赖控件 ----------
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
        mapping = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}
        df["_X_key"] = wd.map(mapping)
        cat_type = pd.CategoricalDtype(categories=list(mapping.values()), ordered=True)
        df["_X_key"] = df["_X_key"].astype(cat_type)
    elif x_time_mode == "月份(1~12)":
        df["_X_key"] = ts.dt.month
    else:
        df["_X_key"] = ts.astype("string")
else:
    df["_X_key"] = df[x_col].astype("string")

# 转数值
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

# ---------- 图表风格与小工具 ----------
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
        fig.add_vline(x=peak_x, line_width=1, line_dash="dot", line_color=st.session_state["PEAK_COLOR"])
        try:
            ymax = float(pd.Series(fig.data[0].y).max())
        except Exception:
            ymax = None
        fig.add_annotation(
            x=peak_x, y=ymax,
            text="峰值", showarrow=True, arrowhead=2, ax=20, ay=-30,
            font=dict(color=st.session_state["PEAK_COLOR"]),
            arrowcolor=st.session_state["PEAK_COLOR"],
            bgcolor="rgba(255,255,255,.7)"
        )
    return fig

def chips(items):
    return " ".join([
        f"<span style='background:#eef2ff;color:#3730a3;border-radius:12px;padding:2px 8px;margin-right:6px;font-size:12px'>{escape(str(i))}</span>"
        for i in items
    ])

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

        colors = [
            st.session_state["PEAK_COLOR"] if (peak_x is not None and str(v) == str(peak_x))
            else st.session_state["BAR_COLOR"]
            for v in df_view[x_col]
        ]
        fig = px.bar(df_view, x=x_col, y=y)
        fig.update_traces(
            marker_color=colors,
            hovertemplate=f"{x_col}=%{{x}}<br>{y}=%{{y}}<extra></extra>"
        )
        fig = style_bar(fig, x_col, y, peak_x=peak_x, title=None)
        st.plotly_chart(
            fig, use_container_width=True,
            config={
                "displaylogo": False,
                "modeBarButtonsToRemove": ["lasso2d","select2d","autoscale","zoomIn2d","zoomOut2d"]
            }
        )

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
