# -*- coding: utf-8 -*-
from __future__ import annotations
import time
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


# =============== 基础设置 ===============
st.set_page_config(
    page_title="数据聚合处理网站",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 顶部+两侧浅色渐变 + 标题整体下移 75px
st.markdown(
    """
    <style>
      /* 整体背景由上到下浅蓝渐变 */
      .stApp {
        background: linear-gradient(180deg, #e9f3ff 0%, #f7fbff 100%);
      }
      /* 标题区整体下移 */
      .main .block-container{
        padding-top: 75px !important;
      }
      /* 两侧竖向渐变条（不占内容空间） */
      body::before, body::after {
        content: "";
        position: fixed;
        top: 0; bottom: 0; width: 10px;
        pointer-events: none; z-index: 0;
      }
      body::before {
        left: 0;
        background: linear-gradient(#ffdf80, #70a1ff);
        opacity: .25;
      }
      body::after {
        right: 0;
        background: linear-gradient(#ffdf80, #70a1ff);
        opacity: .25;
      }
      /* 让侧边栏始终可见更醒目（宽一点） */
      [data-testid="stSidebar"] { width: 300px; min-width: 300px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# 数据保存目录
BASE_DIR   = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# =============== 工具函数 ===============
def list_saved_csvs(limit: int = 30) -> List[Path]:
    """列出已保存 CSV（按修改时间倒序）"""
    files = list(UPLOAD_DIR.glob("*.csv"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df


def detect_numeric_cols(df: pd.DataFrame) -> List[str]:
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def detect_time_cols(df: pd.DataFrame) -> List[str]:
    tcols = []
    for c in df.columns:
        try:
            pd.to_datetime(df[c], errors="raise")
            tcols.append(c)
        except Exception:
            pass
    return tcols


def human_size(num_bytes: int) -> str:
    """简单的人类可读大小"""
    units = ["B", "KB", "MB", "GB"]
    size = float(num_bytes)
    for u in units:
        if size < 1024.0:
            return f"{size:.1f}{u}"
        size /= 1024.0
    return f"{size:.1f}TB"


def save_and_activate(uploaded) -> None:
    """保存上传文件并立即设为当前数据集（自动激活）"""
    import uuid
    fname = f"{Path(uploaded.name).stem}_{int(time.time())}_{uuid.uuid4().hex[:6]}.csv"
    save_path = UPLOAD_DIR / fname
    with open(save_path, "wb") as f:
        f.write(uploaded.getbuffer())

    df = read_csv(save_path)
    st.session_state["current_file_path"] = str(save_path)
    st.session_state["df"] = df
    st.session_state["numeric_cols"] = detect_numeric_cols(df)
    st.session_state["time_cols"] = detect_time_cols(df)
    st.success(f"已上传并载入：{uploaded.name}")


def open_saved_file(path: Path) -> None:
    """从“已保存”打开并激活"""
    df = read_csv(path)
    st.session_state["current_file_path"] = str(path)
    st.session_state["df"] = df
    st.session_state["numeric_cols"] = detect_numeric_cols(df)
    st.session_state["time_cols"] = detect_time_cols(df)
    st.success(f"已载入：{path.name}")


def aggregate(
    df: pd.DataFrame,
    x_col: str,
    y_cols: List[str],
    agg: str,
    time_derive: str,
) -> pd.DataFrame:
    """按 x 和 y_cols 做聚合；若 x 是时间列，可派生小时/日/周/月"""
    data = df.copy()

    # 时间派生
    if time_derive != "不派生":
        # 若不是时间类型先转
        if not pd.api.types.is_datetime64_any_dtype(data[x_col]):
            data[x_col] = pd.to_datetime(data[x_col], errors="coerce")

        if time_derive == "小时(0-23)":
            data["_X"] = data[x_col].dt.hour
        elif time_derive == "日(YYYY-MM-DD)":
            data["_X"] = data[x_col].dt.date
        elif time_derive == "周(1-53)":
            data["_X"] = data[x_col].dt.isocalendar().week.astype(int)
        elif time_derive == "月(YYYY-MM)":
            data["_X"] = data[x_col].dt.to_period("M").astype(str)
        else:
            data["_X"] = data[x_col]
    else:
        data["_X"] = data[x_col]

    # 只保留 y_cols
    y_cols = [c for c in y_cols if c in data.columns]
    if not y_cols:
        return pd.DataFrame()

    grouped = data.groupby("_X")[y_cols].agg(agg).reset_index().rename(columns={"_X": "X"})
    return grouped


# =============== 状态初始化 ===============
for k, v in {
    "df": None,
    "current_file_path": "",
    "numeric_cols": [],
    "time_cols": [],
}.items():
    st.session_state.setdefault(k, v)


# =============== 主体 ===============
st.title("数据聚合处理网站")
st.caption("上传 CSV → 左侧选择 X/时间派生/Y/聚合与范围 → 右侧出图与导出")

# --- 上传 / 已保存文件（主区域） ---
with st.container(border=True):
    st.subheader("上传 CSV（原始细粒或已聚合均可）", divider=True)
    up = st.file_uploader("Drag and drop file here", type=["csv"], label_visibility="collapsed")
    if up is not None:
        # 上传即自动激活
        save_and_activate(up)

# 已保存列表
with st.container(border=True):
    st.subheader("已保存文件（最近）", divider=True)
    files = list_saved_csvs()
    if not files:
        st.info("暂无已保存文件。请先上传。")
    else:
        labels = [
            f"{p.name} · {human_size(p.stat().st_size)} · {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(p.stat().st_mtime))}"
            for p in files
        ]
        idx = st.selectbox("从列表里选择并打开：", range(len(files)), format_func=lambda i: labels[i], index=0)
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("打开此文件", use_container_width=True):
                open_saved_file(files[idx])
        with col2:
            st.text_input("文件绝对路径", str(files[idx]), disabled=True)


# --- 侧栏：维度与度量 ---
st.sidebar.header("维度与度量")

has_df = st.session_state["df"] is not None
df = st.session_state["df"]

# x 维度（所有列都可以选；没有 df 时禁用）
all_cols = list(df.columns) if has_df else []
x_col = st.sidebar.selectbox(
    "横坐标 (X)",
    all_cols if has_df else ["请先上传/选择 CSV 文件"],
    disabled=not has_df,
    index=0 if has_df else None,
)

# 时间派生
time_choices = ["不派生", "小时(0-23)", "日(YYYY-MM-DD)", "周(1-53)", "月(YYYY-MM)"]
time_gran = st.sidebar.selectbox(
    "时间派生",
    time_choices,
    disabled=not has_df or (has_df and x_col not in st.session_state["time_cols"] and time_choices),
    help="当 X 为时间列时，可以派生出小时/日/周/月；若不是时间列本项会禁用。",
)

# y 选择（多选，需要数值列）
y_cols = st.sidebar.multiselect(
    "纵坐标 (Y，可多选)",
    st.session_state["numeric_cols"] if has_df else [],
    max_selections=3,
    placeholder="请选择 1-3 个数值列",
    disabled=not has_df,
)

agg = st.sidebar.selectbox(
    "聚合方式（对 Y 列）",
    ["sum", "mean", "max", "min", "count"],
    disabled=not has_df,
)

# 先提醒
if not has_df:
    st.info("👉 请先上传/选择 CSV 文件。")
else:
    st.success(f"当前数据：{Path(st.session_state['current_file_path']).name} · 行数 {len(df):,}")

# --- 出图与表格 ---
if has_df and x_col and y_cols:
    grouped = aggregate(df, x_col, y_cols, agg, time_gran)

    if grouped.empty:
        st.warning("没有可聚合的数据，请检查 X/Y/聚合方式。")
    else:
        # X 范围滑条（仅当 X 为数值或整数）
        if pd.api.types.is_numeric_dtype(grouped["X"]):
            xmin, xmax = int(grouped["X"].min()), int(grouped["X"].max())
            lo, hi = st.sidebar.slider("X 范围", min_value=xmin, max_value=xmax, value=(xmin, xmax))
            grouped = grouped[(grouped["X"] >= lo) & (grouped["X"] <= hi)]

        # 画图
        st.subheader(f"按「{x_col}」聚合（{agg}）", divider=True)
        fig = px.bar(grouped, x="X", y=y_cols[0], title="", labels={"X": "X"})
        # 追加其余 y 作为叠加柱
        for c in y_cols[1:]:
            fig.add_bar(x=grouped["X"], y=grouped[c], name=c)
        # 高亮最大值所在 x
        try:
            max_idx = grouped[y_cols[0]].idxmax()
            max_x = grouped.loc[max_idx, "X"]
            fig.add_vline(x=max_x, line_color="tomato", line_width=2, opacity=0.6)
        except Exception:
            pass
        st.plotly_chart(fig, use_container_width=True)

        # 当前聚合视图
        st.subheader("当前聚合视图（可下载）", divider=True)
        st.dataframe(grouped, use_container_width=True, height=380)
        st.download_button(
            "下载当前聚合 CSV",
            grouped.to_csv(index=False).encode("utf-8-sig"),
            file_name="aggregated_view.csv",
            mime="text/csv",
            use_container_width=True,
        )

        # 原始数据预览
        with st.expander("原始数据预览（前 200 行）"):
            st.dataframe(df.head(200), use_container_width=True)

else:
    # 没有足够条件时的友好提示
    st.info("👉 请在左侧至少选择一个横坐标 (X) 与一个数值列 (Y) ，再查看图表。")
