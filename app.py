import os
import json
import secrets
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, File
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///网盘.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB

# ========== 邮件配置 ==========
app.config['MAIL_SERVER'] = 'smtp.qq.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = ''  # 发件邮箱地址
app.config['MAIL_PASSWORD'] = ''  # 邮箱授权码
app.config['MAIL_DEFAULT_SENDER'] = ''  # 默认发件人

# ========== 管理后台 ==========
app.config['ADMIN_USERNAME'] = 'admin'
app.config['ADMIN_PASSWORD'] = 'admin123'

# ========== 加载持久化配置 ==========
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f'[配置加载失败] {e}')
    return {}

def save_config(cfg):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'[配置保存失败] {e}')

cfg = load_config()
if cfg.get('mail_server'):
    app.config['MAIL_SERVER'] = cfg['mail_server']
if cfg.get('mail_port'):
    app.config['MAIL_PORT'] = cfg['mail_port']
if cfg.get('mail_username'):
    app.config['MAIL_USERNAME'] = cfg['mail_username']
    app.config['MAIL_DEFAULT_SENDER'] = cfg['mail_username']
if cfg.get('mail_password'):
    app.config['MAIL_PASSWORD'] = cfg['mail_password']
if cfg.get('admin_username'):
    app.config['ADMIN_USERNAME'] = cfg['admin_username']
if cfg.get('admin_password'):
    app.config['ADMIN_PASSWORD'] = cfg['admin_password']

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'csv', 'mp4', 'avi', 'mkv', 'mov', 'webm', 'wmv', 'flv', 'mp3', 'wav', 'flac', 'docx', 'pptx', 'xlsx', 'zip', 'rar', '7z', 'iso', 'dmg', 'apk', 'exe', 'py', 'js', 'html', 'css', 'json', 'xml', 'md', 'log'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_share_code():
    return secrets.token_urlsafe(6)

# ==================== 认证路由 ====================

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

# ==================== 验证码找回密码功能 ====================

import random

def generate_otp():
    """生成6位数字验证码"""
    return ''.join([str(random.randint(0, 9)) for _ in range(6)])

# 内存存储验证码 (生产环境应使用Redis)
otp_store = {}

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        action = request.form.get('action', '')
        
        if action == 'send_otp':
            email = request.form.get('email', '').strip()
            user = User.query.filter_by(email=email).first()
            
            if not user:
                # AJAX 请求返回 JSON
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'error': '该邮箱未注册'}), 400
                flash('该邮箱未注册', 'danger')
                return render_template('forgot_password.html')
            
            otp = generate_otp()
            otp_store[email] = {
                'otp': otp,
                'expiry': datetime.utcnow() + timedelta(minutes=5),
                'attempts': 0
            }
            
            mail_error = send_otp_email(email, otp)
            if mail_error:
                # 发送失败，清除刚才生成的验证码，不暴露给用户
                if email in otp_store:
                    del otp_store[email]
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': '邮件发送失败，请检查邮件配置或稍后重试'}), 500
                flash('⚠️ 邮件发送失败，请检查邮件配置或稍后重试', 'warning')
                return render_template('forgot_password.html')
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'message': f'验证码已发送到 {email}，有效期5分钟'})
            
            flash(f'验证码已发送到 {email}，有效期5分钟', 'success')
            return render_template('forgot_password.html', email=email, show_otp_input=True)
        
        elif action == 'verify_otp':
            email = request.form.get('email', '').strip()
            otp_input = request.form.get('otp', '').strip()
            
            if email not in otp_store:
                flash('请先获取验证码', 'danger')
                return redirect(url_for('forgot_password'))
            
            otp_data = otp_store[email]
            
            if otp_data['attempts'] >= 3:
                del otp_store[email]
                flash('验证码错误次数过多，请重新获取', 'danger')
                return redirect(url_for('forgot_password'))
            
            if datetime.utcnow() > otp_data['expiry']:
                del otp_store[email]
                flash('验证码已过期，请重新获取', 'danger')
                return redirect(url_for('forgot_password'))
            
            if otp_input != otp_data['otp']:
                otp_data['attempts'] += 1
                flash(f'验证码错误，还剩{3-otp_data["attempts"]}次机会', 'danger')
                return redirect(url_for('forgot_password'))
            
            token = secrets.token_urlsafe(32)
            user = User.query.filter_by(email=email).first()
            user.reset_token = token
            user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            
            flash('验证成功，请设置新密码', 'success')
            return redirect(url_for('reset_password', token=token))
    
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    
    if not user or user.reset_token_expiry < datetime.utcnow():
        flash('重置链接已过期，请重新申请', 'danger')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not new_password or len(new_password) < 6:
            flash('密码长度至少6位', 'danger')
            return render_template('reset_password.html', token=token)
        
        if new_password != confirm_password:
            flash('两次密码输入不一致', 'danger')
            return render_template('reset_password.html', token=token)
        
        # 更新密码并清除重置令牌
        user.password = new_password
        user.reset_token = ''
        user.reset_token_expiry = None
        db.session.commit()
        
        flash('密码重置成功，请使用新密码登录', 'success')
        return redirect(url_for('login'))
    
    return render_template('reset_password.html', token=token)


def send_otp_email(to_email, otp):
    """发送验证码邮件，返回True表示失败，False表示成功"""
    try:
        sender = app.config['MAIL_DEFAULT_SENDER'] or app.config['MAIL_USERNAME']
        password = app.config['MAIL_PASSWORD']
        
        if not sender or not password:
            print(f'[验证码] 邮件未配置，验证码: {otp} -> {to_email}')
            return True
        
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = to_email
        msg['Subject'] = '【个人网盘】邮箱验证码'
        
        body = f'''
<html>
<body>
<p>你好！</p>
<p>你的邮箱验证码是：</p>
<h2 style="color:#4CAF50;letter-spacing:5px;text-align:center">{otp}</h2>
<p>有效期5分钟，请勿告知他人。</p>
<p>如果你没有请求验证码，请忽略此邮件。</p>
<p>—— 个人网盘</p>
</body>
</html>
'''
        msg.attach(MIMEText(body, 'html', 'utf-8'))
        
        server = smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT'])
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        server.quit()
        return False
        
    except Exception as e:
        print(f'发送邮件失败: {e}')
        return True


# ==================== 用户设置页面 ====================

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        # 修改密码
        old_password = request.form.get('old_password', '')
        new_password = request.form.get('new_password', '')
        
        if old_password == current_user.password and new_password and len(new_password) >= 6:
            current_user.password = new_password
            db.session.commit()
            flash('密码修改成功', 'success')
        elif old_password != current_user.password:
            flash('原密码错误', 'danger')
        elif not new_password or len(new_password) < 6:
            flash('新密码至少6位', 'danger')
        
        return redirect(url_for('settings'))
    
    return render_template('settings.html', user=current_user)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        email = request.form.get('email', '').strip()
        
        if not all([username, password, email]):
            flash('请填写所有字段', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('邮箱已注册', 'danger')
            return render_template('register.html')
        
        new_user = User(
            username=username,
            password=password,
            email=email
        )
        db.session.add(new_user)
        db.session.commit()
        flash('注册成功，请登录', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        
        if user and user.password == password:
            login_user(user)
            flash('登录成功', 'success')
            return redirect(url_for('dashboard'))
        
        flash('用户名或密码错误', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已退出登录', 'info')
    return redirect(url_for('index'))

# ==================== 用户主面板 ====================

@app.route('/dashboard')
@login_required
def dashboard():
    files = File.query.filter_by(user_id=current_user.id).order_by(File.uploaded_at.desc()).all()
    return render_template('dashboard.html', files=files, user=current_user)

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    # AJAX请求 - 返回JSON
    if 'file' not in request.files:
        return jsonify({'error': '没有选择文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': '不支持的文件类型'}), 400
    
    # 获取重命名（如果有）
    rename = request.form.get('rename', '').strip()
    
    filename = secure_filename(file.filename)
    
    # 如果用户设置了重命名，使用重命名作为display_name和实际文件名
    if rename:
        # 保留原始后缀
        original_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        if original_ext:
            # 验证重命名后的文件扩展名是否允许
            if '.' not in rename or rename.rsplit('.', 1)[1].lower() != original_ext:
                rename = f"{secure_filename(rename)}.{original_ext}"
            else:
                rename = secure_filename(rename)
            new_filename = rename
        else:
            new_filename = secure_filename(rename)
        display_name = rename
    else:
        new_filename = filename
        display_name = filename
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
    file.save(filepath)
    
    file_size = os.path.getsize(filepath)
    file_ext = new_filename.rsplit('.', 1)[1].lower() if '.' in new_filename else ''
    
    new_file = File(
        name=new_filename,
        filename=new_filename,
        display_name=display_name,
        file_type=file_ext,
        size=file_size,
        user_id=current_user.id
    )
    db.session.add(new_file)
    db.session.commit()
    return jsonify({'success': True, 'message': '文件上传成功'})

@app.route('/file/<int:file_id>/delete', methods=['POST'])
@login_required
def delete_file(file_id):
    f = File.query.get_or_404(file_id)
    if f.user_id != current_user.id:
        flash('无权删除此文件', 'danger')
        return redirect(url_for('dashboard'))
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    
    db.session.delete(f)
    db.session.commit()
    flash('文件已删除', 'success')
    return redirect(url_for('dashboard'))

@app.route('/file/<int:file_id>/share')
@login_required
def share_file(file_id):
    f = File.query.get_or_404(file_id)
    if f.user_id != current_user.id:
        flash('无权分享此文件', 'danger')
        return redirect(url_for('dashboard'))
    
    if f.is_shared and f.share_code:
        share_url = url_for('shared_file', code=f.share_code, _external=True)
    else:
        code = create_share_code()
        while File.query.filter_by(share_code=code).first():
            code = create_share_code()
        f.share_code = code
        f.is_shared = True
        db.session.commit()
        share_url = url_for('shared_file', code=code, _external=True)
    
    return jsonify({'share_url': share_url})

# ==================== 分享API ====================

@app.route('/api/share/<int:file_id>', methods=['POST'])
@login_required
def api_share_file(file_id):
    f = File.query.get_or_404(file_id)
    if f.user_id != current_user.id:
        return jsonify({'error': '无权分享此文件'}), 403
    
    # 支持重命名显示
    rename = request.json.get('rename', '').strip() if request.json else ''
    if rename:
        f.display_name = rename
    
    # 支持设置密码
    password = request.json.get('password', '').strip() if request.json else ''
    if password:
        f.share_password = password
    else:
        f.share_password = None
    
    # 先保存修改（重命名、密码）
    db.session.commit()
    
    # 如果已有分享码，直接返回
    if f.is_shared and f.share_code:
        share_url = url_for('shared_file', code=f.share_code, _external=True)
        return jsonify({'share_url': share_url, 'display_name': f.display_name})
    
    # 生成新的分享码
    code = create_share_code()
    while File.query.filter_by(share_code=code).first():
        code = create_share_code()
    f.share_code = code
    f.is_shared = True
    db.session.commit()
    
    share_url = url_for('shared_file', code=code, _external=True)
    return jsonify({'share_url': share_url, 'display_name': f.display_name, 'code': code})

# ==================== 文件预览 ====================

@app.route('/file/<int:file_id>/preview')
@login_required
def preview_file(file_id):
    f = File.query.get_or_404(file_id)
    if f.user_id != current_user.id and not f.is_shared:
        flash('无权预览此文件', 'danger')
        return redirect(url_for('dashboard'))
    
    return render_template('preview.html', file=f)

@app.route('/shared/<code>')
def shared_file(code):
    f = File.query.filter_by(share_code=code).first_or_404()
    f.views += 1
    db.session.commit()
    return render_template('shared_preview.html', file=f)

# ==================== 管理员页面 ====================

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    from flask import session
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == 'admin123':
            session['admin'] = True
            flash('管理员登录成功', 'success')
            return redirect(url_for('admin_panel'))
        flash('密码错误', 'danger')
    return render_template('admin_login.html')

@app.route('/admin/panel')
def admin_panel():
    from flask import session
    if not session.get('admin'):
        flash('请先登录管理员', 'warning')
        return redirect(url_for('admin_login'))
    total_users = User.query.count()
    total_files = File.query.count()
    recent_users = User.query.order_by(User.created_at.desc()).limit(20).all()
    recent_files = File.query.order_by(File.uploaded_at.desc()).limit(20).all()
    storage = sum(f.size for f in File.query.all())
    
    return render_template('admin_panel.html', 
                         total_users=total_users, 
                         total_files=total_files,
                         storage=storage,
                         recent_users=recent_users,
                         recent_files=recent_files,
                         mail_server=app.config['MAIL_SERVER'],
                         mail_port=app.config['MAIL_PORT'],
                         mail_username=app.config['MAIL_USERNAME'],
                         mail_password='',
                         admin_username=app.config['ADMIN_USERNAME'])

# ==================== API路由 ====================

@app.route('/api/files')
@login_required
def api_files():
    files = File.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        'id': f.id,
        'name': f.name,
        'size': f.size,
        'file_type': f.file_type,
        'uploaded_at': f.uploaded_at.isoformat(),
        'is_shared': f.is_shared,
        'views': f.views
    } for f in files])


# ==================== 管理员API ====================

@app.route('/api/admin/users')
def api_admin_users():
    from flask import session
    if not session.get('admin'):
        return jsonify({'error': '无权限'}), 403
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    users = User.query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'users': [{
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'is_admin': u.is_admin,
            'created_at': u.created_at.isoformat(),
            'file_count': File.query.filter_by(user_id=u.id).count(),
            'total_size': sum(f.size for f in File.query.filter_by(user_id=u.id).all())
        } for u in users.items],
        'total': users.total,
        'page': users.page,
        'pages': users.pages
    })


@app.route('/api/admin/user/<int:user_id>/delete', methods=['DELETE'])
def api_admin_delete_user(user_id):
    from flask import session
    if not session.get('admin'):
        return jsonify({'error': '无权限'}), 403
    
    user = User.query.get_or_404(user_id)
    if user.username == 'admin':
        return jsonify({'error': '不能删除admin账户'}), 400
    
    # 删除用户文件
    files = File.query.filter_by(user_id=user_id).all()
    for f in files:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], f.filename))
        except FileNotFoundError:
            pass
        db.session.delete(f)
    
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/admin/user/<int:user_id>/toggle-admin', methods=['POST'])
def api_admin_toggle_admin(user_id):
    from flask import session
    if not session.get('admin'):
        return jsonify({'error': '无权限'}), 403
    
    user = User.query.get_or_404(user_id)
    if user.username == 'admin':
        return jsonify({'error': '不能修改admin权限'}), 400
    
    user.is_admin = not user.is_admin
    db.session.commit()
    
    return jsonify({'success': True, 'is_admin': user.is_admin})


@app.route('/api/admin/user/<int:user_id>/reset-password', methods=['POST'])
def api_admin_reset_password(user_id):
    from flask import session
    if not session.get('admin'):
        return jsonify({'error': '无权限'}), 403
    
    data = request.json
    new_password = data.get('new_password', '').strip()
    
    if not new_password or len(new_password) < 6:
        return jsonify({'error': '密码至少6位'}), 400
    
    user = User.query.get_or_404(user_id)
    user.password = new_password
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/admin/files')
def api_admin_files():
    from flask import session
    if not session.get('admin'):
        return jsonify({'error': '无权限'}), 403
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    file_type = request.args.get('file_type', '')
    
    query = File.query
    if file_type:
        query = query.filter_by(file_type=file_type)
    
    files = query.order_by(File.uploaded_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'files': [{
            'id': f.id,
            'name': f.name,
            'display_name': f.display_name,
            'file_type': f.file_type,
            'size': f.size,
            'user_id': f.user_id,
            'user': User.query.get(f.user_id).username if User.query.get(f.user_id) else 'unknown',
            'uploaded_at': f.uploaded_at.isoformat(),
            'is_shared': f.is_shared,
            'views': f.views
        } for f in files.items],
        'total': files.total,
        'page': files.page,
        'pages': files.pages
    })


@app.route('/api/admin/file/<int:file_id>/delete', methods=['DELETE'])
def api_admin_delete_file(file_id):
    from flask import session
    if not session.get('admin'):
        return jsonify({'error': '无权限'}), 403
    
    f = File.query.get_or_404(file_id)
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], f.filename))
    except FileNotFoundError:
        pass
    db.session.delete(f)
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/admin/stats')
def api_admin_stats():
    from flask import session
    if not session.get('admin'):
        return jsonify({'error': '无权限'}), 403
    
    total_users = User.query.count()
    total_files = File.query.count()
    total_size = sum(f.size for f in File.query.all())
    shared_count = File.query.filter_by(is_shared=True).count()
    
    # 按文件类型统计
    file_type_stats = {}
    for f in File.query.all():
        ft = f.file_type
        file_type_stats[ft] = file_type_stats.get(ft, 0) + 1
    
    # 按日期统计最近7天
    from collections import Counter
    recent_uploads = Counter()
    now = datetime.utcnow()
    for i in range(7):
        day = (now - timedelta(days=i)).strftime('%Y-%m-%d')
        count = File.query.filter(File.uploaded_at >= day, File.uploaded_at < (datetime.strptime(day, '%Y-%m-%d') + timedelta(days=1))).count()
        recent_uploads[day] = count
    
    return jsonify({
        'total_users': total_users,
        'total_files': total_files,
        'total_size': total_size,
        'total_size_human': total_size / (1024*1024*1024),
        'shared_count': shared_count,
        'file_type_stats': file_type_stats,
        'recent_uploads': dict(recent_uploads)
    })


@app.route('/api/admin/storage-clear', methods=['POST'])
def api_admin_storage_clear():
    from flask import session
    if not session.get('admin'):
        return jsonify({'error': '无权限'}), 403
    
    uploaded_folder = app.config['UPLOAD_FOLDER']
    files_removed = 0
    total_freed = 0
    
    # 获取所有已记录的上传文件
    recorded_files = File.query.with_entities(File.filename).all()
    recorded_filenames = [f[0] for f in recorded_files]
    
    # 删除未记录的孤立文件
    if os.path.exists(uploaded_folder):
        for fname in os.listdir(uploaded_folder):
            if fname not in recorded_filenames:
                fpath = os.path.join(uploaded_folder, fname)
                if os.path.isfile(fpath):
                    fsize = os.path.getsize(fpath)
                    os.remove(fpath)
                    total_freed += fsize
                    files_removed += 1
    
    return jsonify({
        'success': True,
        'files_removed': files_removed,
        'space_freed': total_freed
    })


@app.route('/api/admin/user/<int:user_id>/files')
def api_admin_user_files(user_id):
    from flask import session
    if not session.get('admin'):
        return jsonify({'error': '无权限'}), 403
    
    user = User.query.get_or_404(user_id)
    files = File.query.filter_by(user_id=user_id).order_by(File.uploaded_at.desc()).all()
    
    return jsonify({
        'user': user.username,
        'files': [{
            'id': f.id,
            'name': f.name,
            'file_type': f.file_type,
            'size': f.size,
            'uploaded_at': f.uploaded_at.isoformat(),
            'is_shared': f.is_shared
        } for f in files]
    })

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    with app.app_context():
        db.create_all()
    
    # ==================== 管理员配置API ====================
    
    @app.route('/api/admin/settings/mail', methods=['POST'])
    def api_admin_set_mail_config():
        from flask import session
        if not session.get('admin'):
            return jsonify({'error': '无权限'}), 403
        data = request.json
        app.config['MAIL_SERVER'] = data.get('mail_server', 'smtp.qq.com')
        app.config['MAIL_PORT'] = int(data.get('mail_port', 587))
        app.config['MAIL_USERNAME'] = data.get('mail_username', '')
        app.config['MAIL_PASSWORD'] = data.get('mail_password', '')
        app.config['MAIL_DEFAULT_SENDER'] = data.get('mail_username', '')
        # 持久化
        cfg = load_config()
        cfg['mail_server'] = app.config['MAIL_SERVER']
        cfg['mail_port'] = app.config['MAIL_PORT']
        cfg['mail_username'] = app.config['MAIL_USERNAME']
        cfg['mail_password'] = app.config['MAIL_PASSWORD']
        cfg['admin_username'] = app.config.get('ADMIN_USERNAME', 'admin')
        cfg['admin_password'] = app.config.get('ADMIN_PASSWORD', 'admin123')
        save_config(cfg)
        return jsonify({'success': True})
    
    @app.route('/api/admin/settings/admin', methods=['POST'])
    def api_admin_set_admin_config():
        from flask import session
        if not session.get('admin'):
            return jsonify({'error': '无权限'}), 403
        data = request.json
        new_username = data.get('admin_username', '').strip()
        new_password = data.get('admin_password', '').strip()
        if not new_username:
            return jsonify({'error': '管理员用户名不能为空'}), 400
        app.config['ADMIN_USERNAME'] = new_username
        if new_password:
            app.config['ADMIN_PASSWORD'] = new_password
        # 持久化
        cfg = load_config()
        cfg['admin_username'] = app.config['ADMIN_USERNAME']
        cfg['admin_password'] = app.config['ADMIN_PASSWORD']
        cfg['mail_server'] = app.config.get('MAIL_SERVER', 'smtp.qq.com')
        cfg['mail_port'] = app.config.get('MAIL_PORT', 587)
        cfg['mail_username'] = app.config.get('MAIL_USERNAME', '')
        cfg['mail_password'] = app.config.get('MAIL_PASSWORD', '')
        save_config(cfg)
        return jsonify({'success': True})
    
    @app.route('/api/admin/clear-otp', methods=['POST'])
    def api_clear_otp():
        from flask import session
        if not session.get('admin'):
            return jsonify({'error': '无权限'}), 403
        global otp_store
        otp_store.clear()
        return jsonify({'success': True})
    app.run(host='0.0.0.0', port=5000, debug=True)
