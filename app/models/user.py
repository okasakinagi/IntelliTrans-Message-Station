from flask_login import UserMixin


class User(UserMixin):
    """轻量级内存用户模型，身份信息存储于 Flask session 中。

    本项目聚焦于消息层，故不引入数据库；
    生产级系统应将用户信息持久化到数据库。
    """

    def __init__(self, username: str):
        self.username = username

    def get_id(self) -> str:
        """Flask-Login 要求实现，返回用于标识用户的唯一字符串。"""
        return self.username

    @staticmethod
    def get(user_id: str) -> "User | None":
        """从 session 中的 user_id 重建 User 对象。"""
        if user_id:
            return User(user_id)
        return None
