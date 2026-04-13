import re

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user

from app.extensions import login_manager
from app.models.user import User

bp = Blueprint("auth", __name__, url_prefix="/auth")

_USERNAME_RE = re.compile(r"^[\w\u4e00-\u9fff]{1,32}$")


@login_manager.user_loader
def load_user(user_id: str):
    return User.get(user_id)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        if username and _USERNAME_RE.match(username):
            user = User(username)
            login_user(user)
            return redirect(url_for("main.index"))
    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
