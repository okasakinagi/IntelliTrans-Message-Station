"""生成 IntelliTrans 项目架构图和工作流图。

运行：python scripts/generate_diagrams.py
输出：img/architecture.png、img/message-flow.png、img/online-presence.png
"""

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
from pathlib import Path

matplotlib.rcParams["font.family"] = ["Microsoft YaHei", "SimHei", "sans-serif"]
matplotlib.rcParams["axes.unicode_minus"] = False

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "img"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 配色方案 ─────────────────────────────────────────────
C = {
    "pink": "#ec4899",
    "pink_light": "#fce7f3",
    "blue": "#3b82f6",
    "blue_light": "#dbeafe",
    "purple": "#8b5cf6",
    "purple_light": "#ede9fe",
    "green": "#10b981",
    "green_light": "#d1fae5",
    "orange": "#f59e0b",
    "orange_light": "#fef3c7",
    "red": "#ef4444",
    "red_light": "#fee2e2",
    "gray": "#6b7280",
    "gray_light": "#f3f4f6",
    "dark": "#1e293b",
    "white": "#ffffff",
    "border": "#e2e8f0",
}


def box(ax, x, y, w, h, text, color, text_color="white", fontsize=11, bold=True, radius=0.15):
    """绘制一个圆角矩形文本框。"""
    bbox = dict(boxstyle=f"round,pad=0.3,rounding_size={radius * 10}",
                facecolor=color, edgecolor=color, alpha=0.95)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fontsize, fontweight="bold" if bold else "normal",
            color=text_color, bbox=bbox, zorder=3)


def sub_box(ax, x, y, w, h, title, items, color, text_color="#1e293b"):
    """绘制带标题和子项的容器。"""
    bbox = dict(boxstyle="round,pad=0.3,rounding_size=6",
                facecolor=color, edgecolor=color, alpha=0.25)
    ax.text(x + w / 2, y + h - 0.15, title, ha="center", va="top",
            fontsize=8, fontweight="bold", color=text_color, zorder=3)
    for i, item in enumerate(items):
        ax.text(x + w / 2, y + h - 0.38 - i * 0.18, item, ha="center", va="top",
                fontsize=7, color="#475569", zorder=3)
    rect = mpatches.FancyBboxPatch((x, y), w, h,
                                    boxstyle="round,pad=0.15,rounding_size=6",
                                    facecolor=color, edgecolor=color, alpha=0.15, zorder=2)
    ax.add_patch(rect)


def arrow(ax, x1, y1, x2, y2, color="#94a3b8", lw=1.5):
    """绘制箭头。"""
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=color, lw=lw,
                                connectionstyle="arc3,rad=0"), zorder=2)


def curved_arrow(ax, x1, y1, x2, y2, rad=0.2, color="#94a3b8", lw=1.5):
    """绘制曲线箭头。"""
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=color, lw=lw,
                                connectionstyle=f"arc3,rad={rad}"), zorder=2)


def label_arrow(ax, x1, y1, x2, y2, text, color="#64748b", rad=0):
    """绘制带标签的箭头。"""
    mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=color, lw=1.5,
                                connectionstyle=f"arc3,rad={rad}"), zorder=2)
    ax.text(mid_x, mid_y + 0.05, text, ha="center", va="bottom",
            fontsize=7, color=color, style="italic", zorder=3)


# ═══════════════════════════════════════════════════════════
# 图 1：系统架构图
# ═══════════════════════════════════════════════════════════
def draw_architecture():
    fig, ax = plt.subplots(1, 1, figsize=(14, 8))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 8)
    ax.axis("off")
    fig.patch.set_facecolor("#f8fafc")

    # 标题
    ax.text(7, 7.6, "IntelliTrans 消息站 — 系统架构", ha="center", fontsize=18,
            fontweight="bold", color=C["dark"])

    # ── 浏览器 ──
    box(ax, 5.2, 5.8, 3.6, 1.0, "浏览器 (chat.js)\nSocket.IO / HTTP 双通道", C["purple"])

    # ── Flask 应用层 ──
    box(ax, 5.2, 3.7, 3.6, 1.2, "Flask + Socket.IO\n(threading 模式)", C["blue"])
    sub_box(ax, 5.4, 3.85, 0.9, 0.75, "路由层", ["auth", "main", "messages"], C["blue_light"])
    sub_box(ax, 6.55, 3.85, 0.9, 0.75, "服务层", ["redis_svc", "workflow_svc"], C["blue_light"])
    sub_box(ax, 7.7, 3.85, 0.9, 0.75, "模型层", ["User\n(Mixin)"], C["blue_light"])

    # ── Redis ──
    box(ax, 1.5, 1.5, 5.0, 1.0, "", C["red"])
    ax.text(4.0, 2.5, "Redis 中间件", ha="center", fontsize=12, fontweight="bold", color="white", zorder=3)
    sub_box(ax, 1.7, 1.65, 1.1, 0.65, "Pub/Sub", ["消息广播"], C["red_light"])
    sub_box(ax, 2.95, 1.65, 1.1, 0.65, "List", ["历史记录"], C["red_light"])
    sub_box(ax, 4.2, 1.65, 1.1, 0.65, "Set", ["房间 / 私聊"], C["red_light"])
    sub_box(ax, 5.45, 1.65, 0.9, 0.65, "String", ["在线状态"], C["red_light"])

    # ── AI 工作流 ──
    box(ax, 9.5, 1.5, 3.5, 1.0, "", C["green"])
    ax.text(11.25, 2.5, "AI 工作流 (Coze)", ha="center", fontsize=12, fontweight="bold", color="white", zorder=3)
    sub_box(ax, 9.7, 1.65, 0.9, 0.65, "安全检查", ["is_safe"], C["green_light"])
    sub_box(ax, 10.75, 1.65, 0.9, 0.65, "语言检测", ["detect"], C["green_light"])
    sub_box(ax, 11.8, 1.65, 0.9, 0.65, "AI 翻译", ["translate"], C["green_light"])
    sub_box(ax, 12.85, 1.65, 0.9, 0.65, "推荐回复", ["suggest"], C["green_light"])

    # ── 箭头 ──
    arrow(ax, 7.0, 3.7, 7.0, 2.82)  # Flask → Redis
    arrow(ax, 7.0, 3.7, 11.25, 2.82)  # Flask → AI

    # 垂直箭头：浏览器 ↔ Flask
    arrow(ax, 7.0, 5.8, 7.0, 4.9)
    arrow(ax, 6.6, 5.1, 6.6, 5.8)

    # 标签
    ax.text(7.3, 3.25, "Redis Pub/Sub + List + Set", fontsize=7, color=C["gray"], ha="center")
    ax.text(10.5, 3.25, "HTTP POST (fail-open)", fontsize=7, color=C["gray"], ha="center")
    ax.text(7.8, 5.45, "WS / HTTP 降级", fontsize=7, color=C["gray"], ha="left")

    # ── 图例 ──
    legend_text = "双通道：WebSocket 优先（实时） → HTTP 轮询（降级）\n容错：AI 故障 → fail-open 放行 → 核心消息不中断\n存储：零数据库，全部状态在 Redis 中（TTL 自愈）"
    ax.text(7, 1.1, legend_text, ha="center", fontsize=8, color=C["gray"], style="italic")

    fig.tight_layout()
    path = OUTPUT_DIR / "architecture.png"
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  ✓ {path}")


# ═══════════════════════════════════════════════════════════
# 图 2：消息处理流程图
# ═══════════════════════════════════════════════════════════
def draw_message_flow():
    fig, ax = plt.subplots(1, 1, figsize=(14, 7))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 7)
    ax.axis("off")
    fig.patch.set_facecolor("#f8fafc")

    ax.text(7, 6.7, "消息处理流程", ha="center", fontsize=18, fontweight="bold", color=C["dark"])

    # ── 节点 ──
    nodes = [
        (1.5, 5.2, 2.4, 0.9, "用户发送消息", C["purple"]),                     # 0
        (5.5, 5.2, 2.4, 0.9, "AI 工作流调用\n安全检查", C["blue"]),             # 1
        (5.5, 3.5, 2.4, 0.9, "语言检测 &\n翻译判断", C["blue"]),               # 2
        (1.5, 3.5, 2.4, 0.9, "内容被拦截\n(HTTP 422)", C["red"]),              # 3
        (5.5, 1.8, 2.4, 0.9, "自动翻译 +\n推荐回复", C["green"]),              # 4
        (9.5, 1.8, 2.4, 0.9, "仅翻译\n(手动模式)", C["orange"]),               # 5
        (9.5, 5.2, 2.4, 0.9, "fail-open\n放行消息", C["gray"]),               # 6
    ]

    for x, y, w, h, text, color in nodes:
        box(ax, x, y, w, h, text, color, fontsize=9)

    # ── 正常流程箭头 ──
    arrow(ax, 3.9, 5.65, 5.5, 5.65)  # 0 → 1
    arrow(ax, 6.7, 5.2, 6.7, 4.4)    # 1 → 2 (safe)
    arrow(ax, 6.7, 3.5, 6.7, 2.7)    # 2 → 4 (need translate)

    # ── 分支箭头 ──
    arrow(ax, 5.5, 5.65, 5.5, 5.2)
    curved_arrow(ax, 5.0, 5.65, 2.1, 4.4, rad=-0.4, color=C["red"])  # 1 → 3 (unsafe)
    curved_arrow(ax, 8.2, 5.2, 11.9, 5.2, rad=-0.3, color=C["gray"])  # 1 → 6 (fail)

    curved_arrow(ax, 8.2, 3.95, 11.9, 2.55, rad=-0.3, color=C["orange"])  # 2 → 5 (manual translate)

    # ── 标签 ──
    ax.text(4.7, 5.9, "POST", fontsize=7, color=C["gray"])
    ax.text(6.95, 4.85, "is_safe=true", fontsize=7, color=C["green"])
    ax.text(6.95, 3.15, "needs_translation=true", fontsize=7, color=C["green"])
    ax.text(3.5, 5.2, "is_safe=false", fontsize=7, color=C["red"], ha="center")
    ax.text(9.8, 5.9, "API 超时/异常", fontsize=7, color=C["gray"], ha="center")
    ax.text(9.8, 3.45, "is_translation_requested\n=true", fontsize=7, color=C["orange"], ha="center")

    # ── 底部说明 ──
    ax.text(7, 0.7, "推荐回复仅在新消息自动调用时生成（手动翻译不生成，节省资源）| 前端过滤自己的消息不显示推荐回复",
            ha="center", fontsize=7, color=C["gray"], style="italic")

    fig.tight_layout()
    path = OUTPUT_DIR / "message-flow.png"
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  ✓ {path}")


# ═══════════════════════════════════════════════════════════
# 图 3：在线状态流转图
# ═══════════════════════════════════════════════════════════
def draw_online_presence():
    fig, ax = plt.subplots(1, 1, figsize=(14, 6))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 6)
    ax.axis("off")
    fig.patch.set_facecolor("#f8fafc")

    ax.text(7, 5.7, "在线状态 Presence — Redis TTL 自愈机制", ha="center",
            fontsize=16, fontweight="bold", color=C["dark"])

    # ── 四个阶段 ──
    stages = [
        (1.0, 3.2, 2.5, 1.4, "① 连接建立\n─────\nSocket connect", "SETEX\nkey=online:user\nTTL=60s", C["green"], C["green_light"]),
        (4.2, 3.2, 2.5, 1.4, "② 持续活跃\n─────\n发消息 / 切房间", "续期 TTL\n每次 Socket 事件\n自动调用续期", C["blue"], C["blue_light"]),
        (7.4, 3.2, 2.5, 1.4, "③ 心跳降级\n─────\nHTTP /presence", "轮询模式\n每 8s 请求\n续期 TTL", C["orange"], C["orange_light"]),
        (10.6, 3.2, 2.5, 1.4, "④ 自动过期\n─────\n断开 / 闲置", "TTL 过期\n60s 无活动\nDEL key", C["red"], C["red_light"]),
    ]

    for x, y, w, h, title, detail, color, light in stages:
        box(ax, x, y, w, h, title, color, fontsize=9)
        ax.text(x + w / 2, y + 0.25, detail, ha="center", va="center",
                fontsize=7, color="#475569", zorder=3)

    # ── 流程箭头 ──
    arrow(ax, 3.5, 3.9, 4.2, 3.9)
    arrow(ax, 6.7, 3.9, 7.4, 3.9)
    arrow(ax, 9.9, 3.9, 10.6, 3.9)

    # 回到第一步的循环箭头
    curved_arrow(ax, 13.1, 3.0, 2.0, 3.0, rad=0.6, color=C["purple"], lw=1.2)
    ax.text(7, 1.6, "用户重新上线 → 重新连接 → SETEX 重新写入", ha="center",
            fontsize=8, color=C["purple"], style="italic")

    # 底部说明
    ax.text(7, 0.8, "核心设计：每次 Socket 活动自动续期 → 无需手动清理 → 断开 60s 后自动消失 → 多 Worker 共享 Redis",
            ha="center", fontsize=7, color=C["gray"], style="italic")

    fig.tight_layout()
    path = OUTPUT_DIR / "online-presence.png"
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  ✓ {path}")


# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("生成架构图...")
    draw_architecture()
    draw_message_flow()
    draw_online_presence()
    print("完成！图片保存在 img/ 目录。")
