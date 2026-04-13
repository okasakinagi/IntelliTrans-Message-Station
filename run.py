# 应用入口：创建 Flask 实例并启动 Socket.IO 服务器
from app import create_app, socketio

# 通过工厂函数创建应用，环境由 FLASK_ENV 环境变量决定
app = create_app()

if __name__ == "__main__":
    # 监听所有网络接口，端口 5000；debug 模式跟随配置文件
    socketio.run(app, host="0.0.0.0", port=5000, debug=app.config["DEBUG"])
