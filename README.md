# 个人网盘 📁

## 功能特性
- ✅ 用户注册/登录
- ✅ 文件上传/下载
- ✅ 文件预览（支持图片、PDF、Word、Excel、PPT等）
- ✅ 文件分享（生成分享链接）
- ✅ 管理员面板（独立页面，用户端不显示入口）
- ✅ 毛玻璃UI设计
- ✅ 响应式布局

## 安装部署
```bash
cd /root/个人网盘
pip install -r requirements.txt
python app.py
```

## 访问地址
- 主页面：http://localhost:5000
- 管理员：http://localhost:5000/admin （密码：admin123）

## 目录结构
```
个人网盘/
├── app.py          # 主程序
├── models.py       # 数据库模型
├── requirements.txt
├── templates/      # HTML模板
└── static/
    ├── css/style.css
    ├── js/main.js
    └── uploads/    # 上传文件存储
```
