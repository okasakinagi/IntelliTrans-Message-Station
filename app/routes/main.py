from flask import Blueprint, render_template

# 主路由蓝图：负责首页等通用页面
bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    """首页：渲染聊天室主界面。"""
    return render_template("index.html")
