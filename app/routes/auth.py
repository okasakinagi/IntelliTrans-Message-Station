import re

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user

from app.extensions import login_manager
from app.models.user import User

bp = Blueprint("auth", __name__, url_prefix="/auth")

# 用户名校验规则：支持字母、数字、下划线及中文，长度 1~32 位
_USERNAME_RE = re.compile(r"^[\w\u4e00-\u9fff]{1,32}$")


@login_manager.user_loader
def load_user(user_id: str):
    """Flask-Login 回调：根据 session 中存储的 user_id 重新加载用户对象。"""
    return User.get(user_id)


@bp.route("/login", methods=["GET", "POST"])
def login():
    """登录视图：GET 显示表单，POST 处理登录逻辑。"""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        # 服务端校验用户名合法性，防止空用户名或特殊字符注入
        if username and _USERNAME_RE.match(username):
            user = User(username)
            login_user(user)
            return redirect(url_for("main.index"))
    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    """登出视图：清除 session 并跳转到登录页。"""
    logout_user()
    return redirect(url_for("auth.login"))
