from flask import Flask, request, render_template_string, session, redirect, url_for, jsonify, g, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import re
import base64
import json
import requests
import ipaddress
import socket
import whois
from urllib.parse import urlparse
import concurrent.futures
import dns.resolver
import ssl
import random
import hashlib
from sqlalchemy import desc, func
from functools import wraps  
def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Bu işlem için admin yetkisi gereklidir!', 'error')
            return redirect(url_for('forum_home'))
        return f(*args, **kwargs)
    return decorated_function
app = Flask(__name__)



# Database configuration for Render
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///forum.db').replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('SECRET_KEY', 'vahset_render_2025_secure_key_forum')

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'forum_login'

# Forum Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    profile_pic = db.Column(db.String(200), default='default.png')
    bio = db.Column(db.String(500), default='')
    status = db.Column(db.String(100), default='Online')
    join_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    posts = db.relationship('Post', backref='author', lazy=True)
    messages_sent = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    messages_received = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy=True)
    is_banned = db.Column(db.Boolean, default=False)
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(50), default='General')
    likes = db.Column(db.Integer, default=0)
    views = db.Column(db.Integer, default=0)
    comments = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete-orphan')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    likes = db.Column(db.Integer, default=0)
    user = db.relationship('User', backref='comments')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_read = db.Column(db.Boolean, default=False)

class Visitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    page = db.Column(db.String(100))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# OSINT Variables
CORRECT_KEY = os.environ.get('ACCESS_KEY', 'vahset2025')
users_data = {}
osint_cache = {}
user_agents = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/537.36'
]

GITHUB_USERNAME = os.environ.get('GITHUB_USERNAME', 'cappyyyyyy')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'vahset')

# Initialize database
with app.app_context():
    db.create_all()

    # Admin kullanıcısını username veya email ile kontrol et
    existing_admin = User.query.filter(
        (User.username == 'cappyruhh') | 
        (User.email == 'admin@vahset.com')
    ).first()

    if not existing_admin:
        admin_user = User(
            username='cappyruhh',                    # ← Admin kullanıcı adı artık cappyruhh
            email='admin@vahset.com',                # İstersen bunu da değiştirebilirsin
            password_hash=generate_password_hash('You9090.'),  # Senin belirlediğin şifre
            is_admin=True,
            is_banned=False
        )
        db.session.add(admin_user)
        db.session.commit()
        print("✅ Yeni admin kullanıcısı oluşturuldu!")
        print("   Kullanıcı adı: cappyruhh")
        print("   Şifre       : You9090.")
        print("   Email       : admin@vahset.com")
    else:
        print("ℹ️ Admin kullanıcısı (cappyruhh) zaten mevcut, yeni oluşturulmadı.")

# OSINT Functions (kısaltılmış)
def parse_line_data(line):
    line = line.strip().rstrip(',')
    if not line or not line.startswith('('):
        return None
    
    if line.endswith('),'):
        line = line[:-1]
    
    if line.startswith('(') and line.endswith(')'):
        line = line[1:-1]
        
        values = []
        current = ""
        in_quotes = False
        quote_char = None
        in_brackets = 0
        
        for char in line:
            if char in ("'", '"') and not in_quotes and in_brackets == 0:
                in_quotes = True
                quote_char = char
                current += char
            elif char == quote_char and in_quotes:
                in_quotes = False
                current += char
            elif char == '[' and not in_quotes:
                in_brackets += 1
                current += char
            elif char == ']' and not in_quotes:
                in_brackets -= 1
                current += char
            elif char == ',' and not in_quotes and in_brackets == 0:
                values.append(current.strip())
                current = ""
            else:
                current += char
        
        if current:
            values.append(current.strip())
        
        if len(values) >= 9:
            user_id = values[0].strip().strip("'\"")
            email_encoded = values[1].strip().strip("'\"")
            email = "N/A"
            
            if email_encoded and email_encoded not in ['null', '', 'NULL']:
                try:
                    decoded = base64.b64decode(email_encoded)
                    email = decoded.decode('utf-8', errors='ignore')
                except:
                    email = email_encoded
            
            ip = values[8].strip().strip("'\"") if len(values) > 8 else "N/A"
            if ip in ['null', 'NULL']:
                ip = "N/A"
            
            return {
                'user_id': user_id,
                'email': email,
                'ip': ip,
                'encoded': email_encoded
            }
    
    return None

def load_data_from_github():
    global users_data
    
    print("=" * 70)
    print("🚀 VAHSET TERMINAL OSINT v3.0 - GITHUB DATA LOADER")
    print("=" * 70)
    
    all_users = {}
    
    # Sadece 2 dosya yükle (test için)
    github_files = [  
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part1.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part2.txt", 
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part3.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part4.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part5.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part6.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part7.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part8.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part9.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part10.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part11.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part12.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part13.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part14.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part15.txt" 
    
    ]
    
    total_loaded = 0
    
    for i, url in enumerate(github_files, 1):
        print(f"\n📖 GitHub'dan yükleniyor: data_part{i}.txt")
        
        try:
            headers = {'User-Agent': random.choice(user_agents)}
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                content = response.text
                lines = content.strip().split('\n')
                print(f"   ✅ Yüklendi: {len(lines)} satır")
                
                file_count = 0
                for line in lines:
                    data = parse_line_data(line)
                    if data:
                        all_users[data['user_id']] = {
                            'email': data['email'],
                            'ip': data['ip'],
                            'encoded': data['encoded']
                        }
                        file_count += 1
                        total_loaded += 1
                
                print(f"   📊 Parse edildi: {file_count} kayıt")
                
            elif response.status_code == 404:
                print(f"   ⚠️  Dosya bulunamadı: data_part{i}.txt")
            else:
                print(f"   ❌ Hata: {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Network hatası: {str(e)}")
    
    print(f"\n🎯 TOPLAM YÜKLENEN: {len(all_users):,} kullanıcı")
    users_data = all_users
    return all_users

# Visitor tracking
@app.before_request
def track_visitor():
    if request.endpoint and request.endpoint not in ['static', 'favicon']:
        try:
            visitor = Visitor(
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string[:200],
                page=request.endpoint
            )
            db.session.add(visitor)
            db.session.commit()
        except:
            pass

def get_total_visitors():
    try:
        return Visitor.query.count()
    except:
        return 0

def get_online_users():
    try:
        five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
        return Visitor.query.filter(Visitor.timestamp >= five_minutes_ago).distinct(Visitor.ip_address).count()
    except:
        return 0

def get_active_posts():
    try:
        return Post.query.count()
    except:
        return 0

def get_active_users():
    try:
        return User.query.count()
    except:
        return 0

class TerminalStyle:
    COLORS = {
        'black': '#0a0a0a',
        'dark': '#0d1117',
        'gray': '#161b22',
        'light_gray': '#21262d',
        'red': '#ff3333',
        'green': '#00ff00',
        'cyan': '#58a6ff',
        'yellow': '#ffcc00',
        'orange': '#ff9900',
        'purple': '#bc8cff',
        'pink': '#ff66cc',
        'white': '#f0f6fc',
        'blue': '#1f6feb',
        'terminal_green': '#00ff00',
        'matrix_green': '#00ff88'
    }
    
    GRADIENTS = {
        'terminal': 'linear-gradient(135deg, #0d1117 0%, #0a0a0a 50%, #161b22 100%)',
        'header': 'linear-gradient(90deg, #0d1117 0%, #161b22 100%)',
        'button': 'linear-gradient(90deg, #1f6feb 0%, #58a6ff 100%)',
        'danger': 'linear-gradient(90deg, #ff3333 0%, #ff6666 100%)',
        'success': 'linear-gradient(90deg, #00ff00 0%, #00cc00 100%)',
        'warning': 'linear-gradient(90deg, #ff9900 0%, #ffcc00 100%)',
        'terminal_green': 'linear-gradient(90deg, #00ff00 0%, #00cc00 100%)',
        'matrix': 'linear-gradient(90deg, #00ff00 0%, #00ff88 100%)'
    }

# Load OSINT data on startup
with app.app_context():
    print("\n" + "="*80)
    print("🚀 VAHSET TERMINAL OSINT v3.0 + FORUM")
    print("="*80)
    print("📦 GitHub'dan veriler yükleniyor...")
    users_data = load_data_from_github()
    print("✅ OSINT modülleri hazır")
    print("✅ Forum database hazır")
    print("="*80 + "\n")

@app.before_request
def before_request():
    g.users_data = users_data

# ==================== ORIGINAL OSINT ROUTES ====================

@app.route('/')
def index():
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('authenticated'):
        return redirect('/terminal')
    
    error = None
    if request.method == 'POST':
        entered_key = request.form.get('access_key')
        if entered_key == CORRECT_KEY:
            session['authenticated'] = True
            session.permanent = True
            return jsonify({'success': True, 'redirect': '/terminal'})
        else:
            error = "⚠️ Invalid access key!"
    
    colors = TerminalStyle.COLORS
    gradients = TerminalStyle.GRADIENTS
    
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>VAHSET TERMINAL OSINT | ACCESS</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-primary: {{ colors.black }};
                --bg-secondary: {{ colors.dark }};
                --bg-terminal: {{ colors.gray }};
                --accent-red: {{ colors.red }};
                --accent-green: {{ colors.green }};
                --accent-cyan: {{ colors.cyan }};
                --text-primary: {{ colors.white }};
                --text-secondary: #8b949e;
                --gradient-terminal: {{ gradients.terminal }};
                --gradient-matrix: {{ gradients.matrix }};
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'JetBrains Mono', monospace;
                background: var(--gradient-terminal);
                color: var(--text-primary);
                min-height: 100vh;
                overflow: hidden;
            }
            
            .matrix-background {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: #000;
                z-index: -2;
            }
            
            .matrix-rain {
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                opacity: 0.1;
                background: linear-gradient(transparent 90%, var(--accent-green) 100%);
                animation: matrixRain 20s linear infinite;
            }
            
            @keyframes matrixRain {
                0% { background-position: 0 0; }
                100% { background-position: 0 1000px; }
            }
            
            .terminal-container {
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                padding: 20px;
            }
            
            .mac-window {
                background: rgba(13, 17, 23, 0.95);
                border-radius: 12px;
                width: 100%;
                max-width: 500px;
                box-shadow: 
                    0 20px 60px rgba(0, 0, 0, 0.8),
                    0 0 0 1px rgba(255, 255, 255, 0.1),
                    inset 0 1px 0 rgba(255, 255, 255, 0.05);
                backdrop-filter: blur(20px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                overflow: hidden;
            }
            
            .mac-title-bar {
                background: rgba(22, 27, 34, 0.9);
                padding: 12px 20px;
                display: flex;
                align-items: center;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            .mac-buttons {
                display: flex;
                gap: 8px;
            }
            
            .mac-btn {
                width: 12px;
                height: 12px;
                border-radius: 50%;
                transition: all 0.3s ease;
            }
            
            .mac-btn.close { background: #ff5f56; }
            .mac-btn.minimize { background: #ffbd2e; }
            .mac-btn.maximize { background: #27ca3f; }
            
            .mac-btn.close:hover { background: #ff3b30; }
            .mac-btn.minimize:hover { background: #ffa500; }
            .mac-btn.maximize:hover { background: #1db853; }
            
            .mac-title {
                flex: 1;
                text-align: center;
                color: var(--text-secondary);
                font-size: 0.9em;
                letter-spacing: 0.5px;
            }
            
            .login-content {
                padding: 40px;
            }
            
            .terminal-header {
                text-align: center;
                margin-bottom: 30px;
            }
            
            .terminal-icon {
                font-size: 3em;
                color: var(--accent-green);
                margin-bottom: 15px;
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.7; }
            }
            
            .terminal-title {
                font-size: 1.8em;
                font-weight: 700;
                margin-bottom: 5px;
                background: var(--gradient-matrix);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            
            .terminal-subtitle {
                color: var(--text-secondary);
                font-size: 0.9em;
                letter-spacing: 2px;
                text-transform: uppercase;
            }
            
            .login-form {
                display: flex;
                flex-direction: column;
                gap: 20px;
            }
            
            .input-group {
                position: relative;
            }
            
            .terminal-input {
                background: rgba(22, 27, 34, 0.8);
                border: 1px solid rgba(88, 166, 255, 0.3);
                border-radius: 8px;
                color: var(--text-primary);
                font-family: 'JetBrains Mono', monospace;
                padding: 15px;
                width: 100%;
                font-size: 14px;
                letter-spacing: 1px;
                transition: all 0.3s ease;
            }
            
            .terminal-input:focus {
                outline: none;
                border-color: var(--accent-cyan);
                box-shadow: 0 0 20px rgba(88, 166, 255, 0.3);
                background: rgba(22, 27, 34, 0.9);
            }
            
            .input-label {
                position: absolute;
                left: 12px;
                top: -8px;
                background: var(--bg-secondary);
                padding: 0 8px;
                color: var(--accent-cyan);
                font-size: 0.8em;
            }
            
            .submit-btn {
                background: var(--gradient-matrix);
                border: none;
                border-radius: 8px;
                color: #000;
                font-family: 'JetBrains Mono', monospace;
                font-weight: 600;
                padding: 15px;
                font-size: 14px;
                cursor: pointer;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                letter-spacing: 1px;
                text-transform: uppercase;
            }
            
            .submit-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 25px rgba(0, 255, 0, 0.3);
            }
            
            .error-box {
                background: rgba(255, 51, 51, 0.1);
                border: 1px solid rgba(255, 51, 51, 0.3);
                border-radius: 8px;
                padding: 15px;
                color: var(--accent-red);
                font-size: 0.9em;
                display: flex;
                align-items: center;
                gap: 10px;
                animation: errorShake 0.5s;
            }
            
            @keyframes errorShake {
                0%, 100% { transform: translateX(0); }
                25% { transform: translateX(-5px); }
                75% { transform: translateX(5px); }
            }
            
            .login-footer {
                margin-top: 30px;
                text-align: center;
                color: var(--text-secondary);
                font-size: 0.8em;
                border-top: 1px solid rgba(255, 255, 255, 0.1);
                padding-top: 20px;
            }
            
            .version {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 5px;
                margin-top: 5px;
            }
            
            @media (max-width: 600px) {
                .mac-window {
                    margin: 10px;
                }
                
                .login-content {
                    padding: 30px 20px;
                }
            }
        </style>
    </head>
    <body>
        <div class="matrix-background">
            <div class="matrix-rain"></div>
        </div>
        
        <div class="terminal-container">
            <div class="mac-window">
                <div class="mac-title-bar">
                    <div class="mac-buttons">
                        <div class="mac-btn close"></div>
                        <div class="mac-btn minimize"></div>
                        <div class="mac-btn maximize"></div>
                    </div>
                    <div class="mac-title">vahset_terminal_login</div>
                </div>
                
                <div class="login-content">
                    <div class="terminal-header">
                        <div class="terminal-icon">
                            <i class="fas fa-terminal"></i>
                        </div>
                        <h1 class="terminal-title">VAHSET TERMINAL</h1>
                        <div class="terminal-subtitle">OSINT Intelligence Suite</div>
                    </div>
                    
                    <form id="loginForm" method="POST" class="login-form">
                        <div class="input-group">
                            <div class="input-label">ACCESS KEY</div>
                            <input type="password" 
                                   name="access_key" 
                                   class="terminal-input"
                                   placeholder="••••••••••••"
                                   required
                                   autofocus>
                        </div>
                        
                        <button type="submit" class="submit-btn">
                            <i class="fas fa-key"></i>
                            Authenticate & Boot
                        </button>
                        
                        {% if error %}
                        <div class="error-box">
                            <i class="fas fa-exclamation-triangle"></i>
                            {{ error }}
                        </div>
                        {% endif %}
                    </form>
                    
                    <div class="login-footer">
                        <div>GitHub Data Source • Real-time OSINT</div>
                        <div class="version">
                            <i class="fab fa-github"></i>
                            <span>v3.0 • Terminal Edition</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            document.getElementById('loginForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const formData = new FormData(this);
                const button = this.querySelector('.submit-btn');
                const originalText = button.innerHTML;
                
                // Loading state
                button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> BOOTING TERMINAL...';
                button.disabled = true;
                
                try {
                    const response = await fetch('/login', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        // Success - terminal boot sequence
                        button.innerHTML = '<i class="fas fa-check"></i> ACCESS GRANTED';
                        button.style.background = '{{ gradients.success }}';
                        
                        // Matrix effect before redirect
                        const matrix = document.querySelector('.matrix-rain');
                        matrix.style.opacity = '0.3';
                        
                        setTimeout(() => {
                            window.location.href = data.redirect;
                        }, 1500);
                    } else {
                        // Error state
                        button.innerHTML = originalText;
                        button.disabled = false;
                        
                        // Show error
                        const errorDiv = document.createElement('div');
                        errorDiv.className = 'error-box';
                        errorDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Invalid access key!';
                        
                        const existingError = document.querySelector('.error-box');
                        if (existingError) {
                            existingError.remove();
                        }
                        
                        this.appendChild(errorDiv);
                    }
                } catch (error) {
                    button.innerHTML = originalText;
                    button.disabled = false;
                    alert('Network error. Please try again.');
                }
            });
            
            // Matrix rain effect
            const matrixBg = document.querySelector('.matrix-background');
            for (let i = 0; i < 50; i++) {
                const drop = document.createElement('div');
                drop.className = 'matrix-rain';
                drop.style.left = `${Math.random() * 100}%`;
                drop.style.animationDelay = `${Math.random() * 20}s`;
                drop.style.animationDuration = `${10 + Math.random() * 20}s`;
                matrixBg.appendChild(drop);
            }
        </script>
    </body>
    </html>
    ''', error=error, colors=TerminalStyle.COLORS, gradients=TerminalStyle.GRADIENTS)

@app.route('/terminal', methods=['GET', 'POST'])
def terminal():
    if not session.get('authenticated'):
        return redirect('/login')
    
    result = None
    user_id = None
    search_time = None
    osint_type = request.form.get('osint_type', 'basic')
    ip_osint_result = None
    email_osint_result = None
    
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        search_time = datetime.now().strftime("%H:%M:%S")
        osint_type = request.form.get('osint_type', 'basic')
        
        if user_id:
            user_data = users_data.get(user_id)
            
            if user_data:
                result = {
                    'email': user_data['email'],
                    'ip': user_data['ip'],
                    'encoded': user_data.get('encoded', ''),
                    'status': 'success'
                }
                
                # OSINT analizleri (basitleştirilmiş)
                if osint_type == 'ip_osint' and user_data['ip'] != 'N/A':
                    ip_osint_result = {'status': 'Analysis would run here'}
                
                if osint_type == 'email_osint' and user_data['email'] != 'N/A':
                    email_osint_result = {'status': 'Analysis would run here'}
                    
            else:
                similar = []
                for uid in users_data.keys():
                    if user_id in uid or uid.startswith(user_id[:5]):
                        similar.append(uid)
                        if len(similar) >= 5:
                            break
                
                result = {
                    'status': 'error',
                    'message': 'User ID not found in database',
                    'similar': similar[:5]
                }
    
    colors = TerminalStyle.COLORS
    gradients = TerminalStyle.GRADIENTS
    total_users = len(users_data)
    
    sample_ids = list(users_data.keys())[:12] if users_data else []
    
    # Get forum stats
    total_visitors = get_total_visitors()
    online_users = get_online_users()
    
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>VAHSET TERMINAL OSINT | Dashboard</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-primary: {{ colors.black }};
                --bg-secondary: {{ colors.dark }};
                --bg-terminal: {{ colors.gray }};
                --accent-red: {{ colors.red }};
                --accent-green: {{ colors.green }};
                --accent-cyan: {{ colors.cyan }};
                --accent-yellow: {{ colors.yellow }};
                --accent-blue: {{ colors.blue }};
                --accent-purple: {{ colors.purple }};
                --text-primary: {{ colors.white }};
                --text-secondary: #8b949e;
                --gradient-header: {{ gradients.header }};
                --gradient-matrix: {{ gradients.matrix }};
                --gradient-purple: linear-gradient(90deg, {{ colors.purple }} 0%, {{ colors.pink }} 100%);
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'JetBrains Mono', monospace;
                background: var(--bg-primary);
                color: var(--text-primary);
                min-height: 100vh;
                overflow-x: hidden;
            }
            
            .matrix-grid {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: 
                    linear-gradient(rgba(0, 255, 0, 0.03) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(0, 255, 0, 0.03) 1px, transparent 1px);
                background-size: 20px 20px;
                z-index: -1;
                opacity: 0.3;
            }
            
            .terminal-wrapper {
                display: flex;
                flex-direction: column;
                min-height: 100vh;
            }
            
            /* Macbook Style Title Bar */
            .macbook-title-bar {
                background: linear-gradient(to bottom, #3a3a3a, #2a2a2a);
                height: 28px;
                display: flex;
                align-items: center;
                padding: 0 15px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                position: relative;
                border-bottom: 1px solid rgba(0, 0, 0, 0.3);
            }
            
            .macbook-buttons {
                display: flex;
                gap: 8px;
                position: absolute;
                left: 15px;
            }
            
            .macbook-btn {
                width: 12px;
                height: 12px;
                border-radius: 50%;
                transition: all 0.2s;
            }
            
            .macbook-btn.close { background: #ff5f56; }
            .macbook-btn.minimize { background: #ffbd2e; }
            .macbook-btn.maximize { background: #27ca3f; }
            
            .macbook-btn:hover {
                transform: scale(1.1);
                filter: brightness(1.2);
            }
            
            .macbook-title {
                flex: 1;
                text-align: center;
                color: rgba(255, 255, 255, 0.7);
                font-size: 0.85em;
                letter-spacing: 0.5px;
            }
            
            /* Main Header */
            .terminal-header {
                background: var(--gradient-header);
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                padding: 20px 30px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            
            .header-left {
                display: flex;
                align-items: center;
                gap: 20px;
            }
            
            .terminal-logo {
                display: flex;
                align-items: center;
                gap: 12px;
            }
            
            .logo-icon {
                font-size: 1.8em;
                color: var(--accent-green);
                animation: terminalGlow 2s infinite alternate;
            }
            
            @keyframes terminalGlow {
                from { text-shadow: 0 0 5px var(--accent-green); }
                to { text-shadow: 0 0 20px var(--accent-green); }
            }
            
            .logo-text {
                font-size: 1.4em;
                font-weight: 700;
                background: var(--gradient-matrix);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            
            .header-stats {
                display: flex;
                gap: 30px;
            }
            
            .stat-box {
                display: flex;
                flex-direction: column;
                align-items: center;
                padding: 10px 15px;
                background: rgba(22, 27, 34, 0.8);
                border-radius: 8px;
                border: 1px solid rgba(88, 166, 255, 0.2);
                min-width: 100px;
            }
            
            .stat-value {
                font-size: 1.2em;
                font-weight: 600;
                color: var(--accent-cyan);
            }
            
            .stat-label {
                font-size: 0.75em;
                color: var(--text-secondary);
                margin-top: 5px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            
            .header-right {
                display: flex;
                align-items: center;
                gap: 15px;
            }
            
            .github-badge {
                background: rgba(88, 166, 255, 0.1);
                padding: 8px 15px;
                border-radius: 20px;
                border: 1px solid rgba(88, 166, 255, 0.3);
                font-size: 0.9em;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .forum-btn {
                background: var(--gradient-purple);
                color: #000;
                border: none;
                padding: 8px 20px;
                border-radius: 20px;
                text-decoration: none;
                font-size: 0.9em;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                gap: 8px;
                font-weight: 600;
            }
            
            .forum-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 20px rgba(188, 140, 255, 0.5);
            }
            
            .logout-btn {
                background: rgba(255, 51, 51, 0.1);
                color: var(--accent-red);
                border: 1px solid var(--accent-red);
                padding: 8px 20px;
                border-radius: 20px;
                text-decoration: none;
                font-size: 0.9em;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .logout-btn:hover {
                background: var(--accent-red);
                color: #000;
            }
            
            /* Main Content */
            .terminal-main {
                flex: 1;
                padding: 30px;
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 30px;
                max-width: 1600px;
                margin: 0 auto;
                width: 100%;
            }
            
            @media (max-width: 1200px) {
                .terminal-main {
                    grid-template-columns: 1fr;
                }
            }
            
            /* Left Panel */
            .search-panel {
                background: rgba(22, 27, 34, 0.9);
                border: 1px solid rgba(88, 166, 255, 0.2);
                border-radius: 12px;
                padding: 25px;
                backdrop-filter: blur(10px);
            }
            
            .panel-title {
                font-size: 1.1em;
                font-weight: 600;
                margin-bottom: 20px;
                color: var(--accent-cyan);
                display: flex;
                align-items: center;
                gap: 10px;
                padding-bottom: 15px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            .search-form {
                display: flex;
                flex-direction: column;
                gap: 20px;
            }
            
            .input-wrapper {
                position: relative;
            }
            
            .terminal-input-large {
                background: rgba(10, 10, 10, 0.8);
                border: 1px solid rgba(88, 166, 255, 0.4);
                border-radius: 10px;
                color: var(--text-primary);
                font-family: 'JetBrains Mono', monospace;
                padding: 18px 20px;
                width: 100%;
                font-size: 15px;
                letter-spacing: 0.5px;
                transition: all 0.3s ease;
            }
            
            .terminal-input-large:focus {
                outline: none;
                border-color: var(--accent-green);
                box-shadow: 0 0 25px rgba(0, 255, 0, 0.3);
            }
            
            .osint-options {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 10px;
                margin: 15px 0;
            }
            
            .osint-option {
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 12px;
                background: rgba(88, 166, 255, 0.1);
                border: 1px solid rgba(88, 166, 255, 0.3);
                border-radius: 8px;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            
            .osint-option:hover {
                background: rgba(88, 166, 255, 0.2);
                transform: translateY(-2px);
            }
            
            .osint-option.selected {
                background: rgba(0, 255, 0, 0.2);
                border-color: var(--accent-green);
            }
            
            .osint-option input[type="radio"] {
                display: none;
            }
            
            .option-icon {
                color: var(--accent-cyan);
            }
            
            .option-text {
                font-size: 0.85em;
            }
            
            .execute-btn {
                background: var(--gradient-matrix);
                border: none;
                border-radius: 10px;
                color: #000;
                font-family: 'JetBrains Mono', monospace;
                font-weight: 600;
                padding: 18px;
                font-size: 15px;
                cursor: pointer;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                letter-spacing: 1px;
                text-transform: uppercase;
            }
            
            .execute-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 30px rgba(0, 255, 0, 0.4);
            }
            
            .execute-btn:active {
                transform: translateY(0);
            }
            
            .sample-section {
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            .sample-title {
                color: var(--text-secondary);
                margin-bottom: 15px;
                font-size: 0.9em;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .sample-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
                gap: 10px;
            }
            
            .sample-id {
                background: rgba(0, 255, 0, 0.1);
                border: 1px solid rgba(0, 255, 0, 0.3);
                border-radius: 6px;
                padding: 8px 10px;
                font-size: 0.8em;
                cursor: pointer;
                transition: all 0.3s ease;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                text-align: center;
            }
            
            .sample-id:hover {
                background: rgba(0, 255, 0, 0.2);
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(0, 255, 0, 0.2);
            }
            
            /* Right Panel */
            .results-panel {
                background: rgba(22, 27, 34, 0.9);
                border: 1px solid rgba(88, 166, 255, 0.2);
                border-radius: 12px;
                padding: 25px;
                backdrop-filter: blur(10px);
                display: flex;
                flex-direction: column;
            }
            
            .results-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            .search-time {
                color: var(--text-secondary);
                font-size: 0.85em;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .results-content {
                flex: 1;
                overflow-y: auto;
                max-height: 70vh;
                padding-right: 10px;
            }
            
            /* Scrollbar Styling */
            .results-content::-webkit-scrollbar {
                width: 6px;
            }
            
            .results-content::-webkit-scrollbar-track {
                background: rgba(0, 0, 0, 0.2);
                border-radius: 3px;
            }
            
            .results-content::-webkit-scrollbar-thumb {
                background: var(--accent-green);
                border-radius: 3px;
            }
            
            .no-search {
                text-align: center;
                padding: 60px 20px;
                color: var(--text-secondary);
            }
            
            .no-search-icon {
                font-size: 3.5em;
                color: var(--accent-green);
                opacity: 0.5;
                margin-bottom: 20px;
            }
            
            .result-card {
                background: rgba(10, 10, 10, 0.9);
                border: 1px solid rgba(0, 255, 0, 0.3);
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 20px;
                animation: slideIn 0.5s ease;
            }
            
            @keyframes slideIn {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            .result-status {
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 1px solid rgba(0, 255, 0, 0.2);
            }
            
            .status-success .status-icon {
                color: var(--accent-green);
            }
            
            .status-error .status-icon {
                color: var(--accent-red);
            }
            
            .status-icon {
                font-size: 1.5em;
            }
            
            .result-grid {
                display: grid;
                gap: 15px;
                margin-bottom: 20px;
            }
            
            .result-row {
                display: flex;
                align-items: center;
                padding: 12px 15px;
                background: rgba(0, 255, 0, 0.05);
                border-radius: 8px;
                border-left: 3px solid var(--accent-green);
            }
            
            .row-label {
                min-width: 120px;
                color: var(--accent-cyan);
                font-weight: 500;
                font-size: 0.9em;
            }
            
            .row-value {
                flex: 1;
                word-break: break-all;
                font-family: 'Courier New', monospace;
                font-size: 0.9em;
            }
            
            /* Footer */
            .terminal-footer {
                background: var(--gradient-header);
                border-top: 1px solid rgba(255, 255, 255, 0.1);
                padding: 20px 30px;
                text-align: center;
                color: var(--text-secondary);
                font-size: 0.85em;
            }
            
            .footer-grid {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 20px;
                max-width: 1200px;
                margin: 0 auto;
            }
            
            .footer-section {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 10px;
            }
            
            .footer-icon {
                color: var(--accent-green);
                font-size: 1.2em;
            }
            
            .footer-title {
                color: var(--accent-cyan);
                font-size: 0.9em;
                font-weight: 600;
            }
            
            .forum-stats {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 10px;
                margin-top: 20px;
                padding: 15px;
                background: rgba(188, 140, 255, 0.1);
                border-radius: 8px;
                border: 1px solid rgba(188, 140, 255, 0.3);
            }
            
            .forum-stat {
                text-align: center;
            }
            
            .forum-stat-value {
                font-size: 1.5em;
                color: var(--accent-purple);
                font-weight: bold;
            }
            
            .forum-stat-label {
                font-size: 0.8em;
                color: var(--text-secondary);
                margin-top: 5px;
            }
            
            /* Responsive */
            @media (max-width: 768px) {
                .terminal-header {
                    flex-direction: column;
                    gap: 15px;
                    padding: 15px;
                }
                
                .header-stats {
                    order: 3;
                    width: 100%;
                    justify-content: space-around;
                }
                
                .terminal-main {
                    padding: 15px;
                    gap: 15px;
                }
                
                .osint-options {
                    grid-template-columns: 1fr;
                }
                
                .sample-grid {
                    grid-template-columns: repeat(2, 1fr);
                }
                
                .footer-grid {
                    grid-template-columns: 1fr;
                    gap: 15px;
                }
            }
        </style>
    </head>
    <body>
        <div class="matrix-grid"></div>
        
        <div class="terminal-wrapper">
            <!-- Macbook Style Title Bar -->
            <div class="macbook-title-bar">
                <div class="macbook-buttons">
                    <div class="macbook-btn close"></div>
                    <div class="macbook-btn minimize"></div>
                    <div class="macbook-btn maximize"></div>
                </div>
                <div class="macbook-title">vahset_terminal_osint_v3.0</div>
            </div>
            
            <!-- Main Header -->
            <header class="terminal-header">
                <div class="header-left">
                    <div class="terminal-logo">
                        <div class="logo-icon">
                            <i class="fas fa-terminal"></i>
                        </div>
                        <div class="logo-text">VAHSET TERMINAL OSINT</div>
                    </div>
                </div>
                
                <div class="header-stats">
                    <div class="stat-box">
                        <div class="stat-value" id="liveTime">--:--:--</div>
                        <div class="stat-label">LIVE TIME</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value">{{ total_users|intcomma }}</div>
                        <div class="stat-label">RECORDS</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value" id="cacheSize">0</div>
                        <div class="stat-label">CACHE</div>
                    </div>
                </div>
                
                <div class="header-right">
                    <div class="github-badge">
                        <i class="fab fa-github"></i>
                        GitHub RAW
                    </div>
                    <a href="/forum" class="forum-btn">
                        <i class="fas fa-comments"></i>
                        FORUMA GEÇ
                    </a>
                    <a href="/logout" class="logout-btn">
                        <i class="fas fa-power-off"></i>
                        LOGOUT
                    </a>
                </div>
            </header>
            
            <!-- Main Content -->
            <main class="terminal-main">
                <!-- Left Panel - Search -->
                <div class="search-panel">
                    <div class="panel-title">
                        <i class="fas fa-search"></i>
                        OSINT QUERY TERMINAL
                    </div>
                    
                    <form method="POST" class="search-form">
                        <div class="input-wrapper">
                            <input type="text" 
                                   name="user_id" 
                                   class="terminal-input-large"
                                   placeholder="Enter User ID (e.g., 1379557223096914020)..."
                                   value="{{ user_id if user_id }}"
                                   required
                                   autofocus>
                        </div>
                        
                        <div class="panel-title">
                            <i class="fas fa-crosshairs"></i>
                            OSINT ANALYSIS TYPE
                        </div>
                        
                        <div class="osint-options">
                            <label class="osint-option {{ 'selected' if osint_type == 'basic' }}">
                                <input type="radio" name="osint_type" value="basic" {{ 'checked' if osint_type == 'basic' }}>
                                <div class="option-icon">
                                    <i class="fas fa-info-circle"></i>
                                </div>
                                <div class="option-text">Basic Info</div>
                            </label>
                            
                            <label class="osint-option {{ 'selected' if osint_type == 'ip_osint' }}">
                                <input type="radio" name="osint_type" value="ip_osint" {{ 'checked' if osint_type == 'ip_osint' }}>
                                <div class="option-icon">
                                    <i class="fas fa-network-wired"></i>
                                </div>
                                <div class="option-text">IP OSINT</div>
                            </label>
                            
                            <label class="osint-option {{ 'selected' if osint_type == 'email_osint' }}">
                                <input type="radio" name="osint_type" value="email_osint" {{ 'checked' if osint_type == 'email_osint' }}>
                                <div class="option-icon">
                                    <i class="fas fa-envelope"></i>
                                </div>
                                <div class="option-text">Email OSINT</div>
                            </label>
                        </div>
                        
                        <button type="submit" class="execute-btn">
                            <i class="fas fa-bolt"></i>
                            EXECUTE OSINT QUERY
                        </button>
                    </form>
                    
                    <div class="sample-section">
                        <div class="sample-title">
                            <i class="fas fa-database"></i>
                            SAMPLE DATABASE IDs
                        </div>
                        <div class="sample-grid">
                            {% for sample_id in sample_ids %}
                            <div class="sample-id" onclick="document.querySelector('.terminal-input-large').value='{{ sample_id }}'; document.querySelector('.terminal-input-large').focus();">
                                {{ sample_id[:12] }}...
                            </div>
                            {% endfor %}
                        </div>
                    </div>
                </div>
                
                <!-- Right Panel - Results -->
                <div class="results-panel">
                    <div class="results-header">
                        <div class="panel-title">
                            <i class="fas fa-file-code"></i>
                            QUERY RESULTS
                        </div>
                        {% if search_time %}
                        <div class="search-time">
                            <i class="far fa-clock"></i>
                            {{ search_time }}
                        </div>
                        {% endif %}
                    </div>
                    
                    <div class="results-content">
                        {% if not result %}
                        <div class="no-search">
                            <div class="no-search-icon">
                                <i class="fas fa-terminal"></i>
                            </div>
                            <h3>TERMINAL READY</h3>
                            <p>Enter a User ID and select OSINT type to begin analysis</p>
                            <p style="margin-top: 20px; font-size: 0.9em; opacity: 0.7;">
                                <i class="fas fa-info-circle"></i>
                                Database: {{ total_users|intcomma }} records loaded from GitHub
                            </p>
                            
                            <!-- Forum Stats -->
                            <div class="forum-stats">
                                <div class="forum-stat">
                                    <div class="forum-stat-value">{{ total_visitors }}</div>
                                    <div class="forum-stat-label">Forum Visitors</div>
                                </div>
                                <div class="forum-stat">
                                    <div class="forum-stat-value">{{ online_users }}</div>
                                    <div class="forum-stat-label">Online Now</div>
                                </div>
                            </div>
                        </div>
                        
                        {% else %}
                        <!-- Basic Results -->
                        <div class="result-card">
                            <div class="result-status {{ 'status-success' if result.status == 'success' else 'status-error' }}">
                                <div class="status-icon">
                                    {% if result.status == 'success' %}
                                    <i class="fas fa-check-circle"></i>
                                    {% else %}
                                    <i class="fas fa-times-circle"></i>
                                    {% endif %}
                                </div>
                                <div>
                                    {% if result.status == 'success' %}
                                    <h3 style="color: var(--accent-green);">RECORD FOUND</h3>
                                    {% else %}
                                    <h3 style="color: var(--accent-red);">RECORD NOT FOUND</h3>
                                    {% endif %}
                                </div>
                            </div>
                            
                            {% if result.status == 'success' %}
                            <div class="result-grid">
                                <div class="result-row">
                                    <div class="row-label">USER ID:</div>
                                    <div class="row-value">{{ user_id }}</div>
                                </div>
                                <div class="result-row">
                                    <div class="row-label">EMAIL:</div>
                                    <div class="row-value">{{ result.email }}</div>
                                </div>
                                <div class="result-row">
                                    <div class="row-label">IP ADDRESS:</div>
                                    <div class="row-value">{{ result.ip }}</div>
                                </div>
                                {% if result.encoded %}
                                <div class="result-row">
                                    <div class="row-label">BASE64 ENCODED:</div>
                                    <div class="row-value" style="font-size: 0.8em; opacity: 0.8;">
                                        {{ result.encoded }}
                                    </div>
                                </div>
                                {% endif %}
                            </div>
                            {% else %}
                            <div class="result-grid">
                                <div class="result-row">
                                    <div class="row-label">ERROR:</div>
                                    <div class="row-value">{{ result.message }}</div>
                                </div>
                                <div class="result-row">
                                    <div class="row-label">SEARCHED:</div>
                                    <div class="row-value">{{ user_id }}</div>
                                </div>
                            </div>
                            
                            {% if result.similar %}
                            <div style="margin-top: 20px; padding: 15px; background: rgba(0,255,0,0.1); border-radius: 8px;">
                                <div style="color: var(--accent-cyan); margin-bottom: 10px;">
                                    <i class="fas fa-random"></i> SIMILAR IDs FOUND
                                </div>
                                <div class="sample-grid">
                                    {% for similar_id in result.similar %}
                                    <div class="sample-id" 
                                         onclick="document.querySelector('.terminal-input-large').value='{{ similar_id }}'; document.querySelector('.terminal-input-large').focus();">
                                        {{ similar_id }}
                                    </div>
                                    {% endfor %}
                                </div>
                            </div>
                            {% endif %}
                            {% endif %}
                        </div>
                        {% endif %}
                    </div>
                </div>
            </main>
            
            <!-- Footer -->
            <footer class="terminal-footer">
                <div class="footer-grid">
                    <div class="footer-section">
                        <div class="footer-icon">
                            <i class="fas fa-bolt"></i>
                        </div>
                        <div class="footer-title">REAL-TIME OSINT</div>
                        <div style="font-size: 0.8em;">Live Intelligence Gathering</div>
                    </div>
                    
                    <div class="footer-section">
                        <div class="footer-icon">
                            <i class="fab fa-github"></i>
                        </div>
                        <div class="footer-title">GITHUB DATA SOURCE</div>
                        <div style="font-size: 0.8em;">{{ total_users|intcomma }} Records</div>
                    </div>
                    
                    <div class="footer-section">
                        <div class="footer-icon">
                            <i class="fas fa-shield-alt"></i>
                        </div>
                        <div class="footer-title">SECURE TERMINAL</div>
                        <div style="font-size: 0.8em;">Encrypted Session</div>
                    </div>
                    
                    <div class="footer-section">
                        <div class="footer-icon">
                            <i class="fas fa-comments"></i>
                        </div>
                        <div class="footer-title">ACTIVE FORUM</div>
                        <div style="font-size: 0.8em;">{{ total_visitors }} Members</div>
                    </div>
                </div>
            </footer>
        </div>
        
        <script>
            // Live time update
            function updateTime() {
                const now = new Date();
                const timeString = now.toLocaleTimeString('en-US', { 
                    hour12: false,
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit'
                });
                document.getElementById('liveTime').textContent = timeString;
            }
            
            // Update cache size
            function updateCacheSize() {
                const size = Math.floor(Math.random() * 100) + 50;
                document.getElementById('cacheSize').textContent = size + ' MB';
            }
            
            // OSINT option selection
            document.querySelectorAll('.osint-option').forEach(option => {
                option.addEventListener('click', function() {
                    document.querySelectorAll('.osint-option').forEach(opt => {
                        opt.classList.remove('selected');
                    });
                    this.classList.add('selected');
                    this.querySelector('input[type="radio"]').checked = true;
                });
            });
            
            // Initialize
            setInterval(updateTime, 1000);
            setInterval(updateCacheSize, 5000);
            updateTime();
            updateCacheSize();
        </script>
    </body>
    </html>
    ''', result=result, user_id=user_id, total_users=total_users, 
         sample_ids=sample_ids, search_time=search_time, osint_type=osint_type,
         ip_osint_result=ip_osint_result, email_osint_result=email_osint_result,
         total_visitors=total_visitors, online_users=online_users,
         colors=TerminalStyle.COLORS, gradients=TerminalStyle.GRADIENTS)

# ==================== FORUM ROUTES ====================

@app.route('/forum')
def forum_home():
    total_visitors = get_total_visitors()
    online_users = get_online_users()
    active_posts = get_active_posts()
    active_users = get_active_users()

    try:
        posts = Post.query.order_by(desc(Post.timestamp)).limit(10).all()
    except:
        posts = []

    categories = ['General', 'OSINT', 'Security', 'Programming', 'Off Topic']

    return render_template_string('''
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VAHSET COMMUNITY | Terminal Forum</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --bg-card: #21262d;
            --accent-green: #00ff00;
            --accent-cyan: #58a6ff;
            --accent-purple: #bc8cff;
            --accent-red: #ff3333;
            --text-primary: #f0f6fc;
            --text-secondary: #8b949e;
            --gradient-matrix: linear-gradient(90deg, #00ff00 0%, #00ff88 100%);
            --gradient-purple: linear-gradient(90deg, #bc8cff 0%, #ff66cc 100%);
            --gradient-header: linear-gradient(90deg, #0d1117 0%, #161b22 100%);
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'JetBrains Mono', monospace;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }

        .matrix-grid {
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background:
                linear-gradient(rgba(0, 255, 0, 0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 255, 0, 0.03) 1px, transparent 1px);
            background-size: 20px 20px;
            z-index: -1; opacity: 0.3;
        }

        .forum-container { max-width: 1200px; margin: 0 auto; padding: 20px; }

        .forum-header {
            background: var(--gradient-header);
            border: 1px solid rgba(0, 255, 0, 0.3);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            backdrop-filter: blur(10px);
        }

        .logo-area { display: flex; align-items: center; gap: 15px; }
        .logo-icon { font-size: 2.8em; color: var(--accent-green); }
        .logo-text h1 {
            background: var(--gradient-matrix);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-size: 2em;
            font-weight: 700;
        }
        .logo-text p { color: var(--text-secondary); font-size: 0.9em; margin-top: 4px; }

        .stats-area { display: flex; gap: 25px; }
        .stat-box {
            background: rgba(0, 255, 0, 0.1);
            border: 1px solid rgba(0, 255, 0, 0.4);
            border-radius: 10px;
            padding: 12px 20px;
            text-align: center;
            min-width: 100px;
        }
        .stat-number { font-size: 1.8em; font-weight: bold; color: var(--accent-green); }
        .stat-label { font-size: 0.85em; color: var(--text-secondary); margin-top: 5px; text-transform: uppercase; letter-spacing: 1px; }

        .nav-buttons { display: flex; gap: 12px; flex-wrap: wrap; }
        .nav-btn {
            padding: 10px 20px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.95em;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .btn-primary { background: var(--gradient-matrix); color: #000; }
        .btn-secondary { background: rgba(88, 166, 255, 0.15); color: var(--accent-cyan); border: 1px solid rgba(88, 166, 255, 0.4); }
        .btn-purple { background: var(--gradient-purple); color: #000; }
        .btn-danger { background: rgba(255, 51, 51, 0.15); color: var(--accent-red); border: 1px solid var(--accent-red); }
        .nav-btn:hover { transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0, 255, 0, 0.3); }

        .forum-main { display: grid; grid-template-columns: 280px 1fr; gap: 25px; }

        .sidebar {
            background: var(--bg-secondary);
            border: 1px solid rgba(88, 166, 255, 0.2);
            border-radius: 12px;
            padding: 25px;
            height: fit-content;
        }
        .sidebar-section { margin-bottom: 30px; }
        .section-title {
            color: var(--accent-cyan);
            font-size: 1em;
            font-weight: 600;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .category-list { list-style: none; }
        .category-item {
            padding: 12px;
            margin-bottom: 8px;
            border-radius: 8px;
            background: rgba(0, 255, 0, 0.05);
            transition: all 0.3s;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .category-item:hover { background: rgba(0, 255, 0, 0.15); transform: translateX(8px); }

        .posts-container {
            background: var(--bg-secondary);
            border: 1px solid rgba(88, 166, 255, 0.2);
            border-radius: 12px;
            padding: 30px;
        }
        .posts-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        .posts-header h2 { font-size: 1.4em; display: flex; align-items: center; gap: 10px; }

        .create-post-btn {
            background: var(--gradient-matrix);
            color: #000;
            border: none;
            padding: 12px 25px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            font-size: 1em;
            display: flex;
            align-items: center;
            gap: 10px;
            transition: all 0.3s;
        }
        .create-post-btn:hover { transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0, 255, 0, 0.4); }

        /* POST LIST STYLES */
        .post-list {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .post-card {
            background: var(--bg-card);
            border: 1px solid rgba(88, 166, 255, 0.1);
            border-radius: 10px;
            padding: 25px;
            transition: all 0.3s ease;
            position: relative;
        }

        .post-card:hover {
            border-color: rgba(0, 255, 0, 0.3);
            transform: translateY(-3px);
            box-shadow: 0 10px 25px rgba(0, 255, 0, 0.1);
        }

        .post-header {
            display: flex;
            align-items: center;
            margin-bottom: 15px;
            gap: 15px;
        }

        .post-author-avatar {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: var(--gradient-matrix);
            display: flex;
            align-items: center;
            justify-content: center;
            color: #000;
            font-weight: bold;
            font-size: 1.1em;
        }

        .post-author-info {
            flex: 1;
        }

        .post-author-name {
            font-weight: 600;
            color: var(--accent-cyan);
            text-decoration: none;
        }

        .post-author-name:hover {
            color: var(--accent-green);
        }

        .post-meta {
            display: flex;
            gap: 15px;
            color: var(--text-secondary);
            font-size: 0.85em;
            margin-top: 5px;
        }

        .post-title {
            font-size: 1.4em;
            font-weight: 600;
            margin-bottom: 15px;
            color: var(--text-primary);
            text-decoration: none;
            display: block;
        }

        .post-title:hover {
            color: var(--accent-cyan);
        }

        .post-content {
            color: var(--text-secondary);
            line-height: 1.6;
            margin-bottom: 20px;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .post-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-top: 15px;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
        }

        .post-stats {
            display: flex;
            gap: 20px;
        }

        .post-stat {
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-secondary);
            font-size: 0.9em;
        }

        .post-stat-icon {
            color: var(--accent-purple);
        }

        .post-category {
            background: rgba(188, 140, 255, 0.1);
            color: var(--accent-purple);
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 0.8em;
            font-weight: 500;
        }

        .read-more-btn {
            background: rgba(88, 166, 255, 0.1);
            color: var(--accent-cyan);
            text-decoration: none;
            padding: 8px 18px;
            border-radius: 6px;
            font-size: 0.9em;
            font-weight: 500;
            transition: all 0.3s;
        }

        .read-more-btn:hover {
            background: rgba(88, 166, 255, 0.2);
            transform: translateX(5px);
        }

        .no-posts {
            text-align: center;
            padding: 80px 20px;
            color: var(--text-secondary);
        }
        .no-posts-icon {
            font-size: 5em;
            color: var(--accent-green);
            opacity: 0.3;
            margin-bottom: 20px;
        }
        .no-posts h3 { font-size: 1.6em; margin-bottom: 15px; color: var(--text-primary); }
        .no-posts p { font-size: 1.1em; font-style: italic; }

        .forum-footer {
            text-align: center;
            padding: 30px 20px;
            color: var(--text-secondary);
            font-size: 0.9em;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            margin-top: 50px;
        }

        @media (max-width: 992px) {
            .forum-main { grid-template-columns: 1fr; }
            .sidebar { order: 2; }
        }

        @media (max-width: 768px) {
            .forum-header { flex-direction: column; gap: 20px; text-align: center; }
            .stats-area { justify-content: center; }
            .nav-buttons { justify-content: center; }
            .post-footer { flex-direction: column; gap: 15px; align-items: flex-start; }
            .post-stats { justify-content: space-between; width: 100%; }
        }
    </style>
</head>
<body>
    <div class="matrix-grid"></div>

    <div class="forum-container">
        <header class="forum-header">
            <div class="logo-area">
                <div class="logo-icon"><i class="fas fa-comments"></i></div>
                <div class="logo-text">
                    <h1>VAHSET COMMUNITY</h1>
                    <p>Terminal OSINT Forum</p>
                </div>
            </div>

            <div class="stats-area">
                <div class="stat-box">
                    <div class="stat-number">{{ total_visitors }}</div>
                    <div class="stat-label">Members</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{{ online_users }}</div>
                    <div class="stat-label">Online</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{{ active_posts }}</div>
                    <div class="stat-label">Posts</div>
                </div>
            </div>

            <div class="nav-buttons">
                {% if current_user.is_authenticated %}
                    <a href="/forum/messages" class="nav-btn btn-primary"><i class="fas fa-envelope"></i> Mesajlar</a>
                {% endif %}
                {% if current_user.is_authenticated and current_user.is_admin %}
                    <a href="/forum/admin" class="nav-btn" style="background:#ff3333;color:#000;"><i class="fas fa-shield-alt"></i> ADMIN PANEL</a>
                {% endif %}
                <a href="/terminal" class="nav-btn btn-purple"><i class="fas fa-terminal"></i> OSINT'E GEÇ</a>
                {% if current_user.is_authenticated %}
                    <a href="/forum/profile" class="nav-btn btn-primary"><i class="fas fa-user"></i> Profile</a>
                    <a href="/forum/logout" class="nav-btn btn-danger"><i class="fas fa-sign-out-alt"></i> Logout</a>
                {% else %}
                    <a href="/forum/login" class="nav-btn btn-primary"><i class="fas fa-sign-in-alt"></i> Login</a>
                    <a href="/forum/register" class="nav-btn btn-secondary"><i class="fas fa-user-plus"></i> Register</a>
                {% endif %}
            </div>
        </header>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}" style="padding:15px;border-radius:8px;margin-bottom:20px;background:rgba({{ '0,255,0' if category=='success' else '255,51,51' }},0.1);border:1px solid {{ 'var(--accent-green)' if category=='success' else 'var(--accent-red)' }};color:{{ 'var(--accent-green)' if category=='success' else 'var(--accent-red)' }};display:flex;align-items:center;gap:10px;">
                        <i class="fas fa-{{ 'check-circle' if category == 'success' else 'exclamation-triangle' }}"></i>
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <div class="forum-main">
            <aside class="sidebar">
                <div class="sidebar-section">
                    <h3 class="section-title"><i class="fas fa-list"></i> KATEGORİLER</h3>
                    <ul class="category-list">
                        {% for category in categories %}
                        <li class="category-item"><i class="fas fa-hashtag"></i> {{ category }}</li>
                        {% endfor %}
                    </ul>
                </div>

                <div class="sidebar-section">
                    <h3 class="section-title"><i class="fas fa-fire"></i> TRENDİNG</h3>
                    <div style="color:var(--text-secondary);line-height:1.8;">
                        • OSINT Techniques<br>
                        • Python Security<br>
                        • Network Analysis<br>
                        • Data Privacy
                    </div>
                </div>

                <div class="sidebar-section">
                    <h3 class="section-title"><i class="fas fa-info-circle"></i> FORUM KURALLARI</h3>
                    <div style="color:var(--text-secondary);font-size:0.9em;line-height:1.7;">
                        1. Be respectful<br>
                        2. No spam<br>
                        3. Keep it legal<br>
                        4. Help others
                    </div>
                </div>
            </aside>

            <main class="posts-container">
                <div class="posts-header">
                    <h2><i class="fas fa-comments"></i> SON TARTIŞMALAR</h2>
                    {% if current_user.is_authenticated %}
                        <button class="create-post-btn" onclick="window.location.href='/forum/create'">
                            <i class="fas fa-plus"></i> CREATE POST
                        </button>
                    {% endif %}
                </div>

                {% if posts %}
                    <div class="post-list">
                        {% for post in posts %}
                        <div class="post-card">
                            <div class="post-header">
                                <div class="post-author-avatar">
                                    {{ post.author.username[0]|upper }}
                                </div>
                                <div class="post-author-info">
                                    <a href="/forum/profile" class="post-author-name">
                                        {{ post.author.username }}
                                    </a>
                                    <div class="post-meta">
                                        <span><i class="far fa-clock"></i> {{ post.timestamp.strftime('%d.%m.%Y %H:%M') }}</span>
                                        <span><i class="fas fa-tag"></i> {{ post.category }}</span>
                                    </div>
                                </div>
                            </div>
                            
                            <a href="/forum/post/{{ post.id }}" class="post-title">
                                {{ post.title }}
                            </a>
                            
                            <div class="post-content">
                                {{ post.content|truncate(200, True, '...') }}
                            </div>
                            
                            <div class="post-footer">
                                <div class="post-stats">
                                    <span class="post-stat">
                                        <i class="far fa-eye post-stat-icon"></i>
                                        {{ post.views }} views
                                    </span>
                                    <span class="post-stat">
                                        <i class="far fa-comment post-stat-icon"></i>
                                        {{ post.comments|length }} comments
                                    </span>
                                    <span class="post-stat">
                                        <i class="far fa-heart post-stat-icon"></i>
                                        {{ post.likes }} likes
                                    </span>
                                </div>
                                <a href="/forum/post/{{ post.id }}" class="read-more-btn">
                                    Read More <i class="fas fa-arrow-right"></i>
                                </a>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                {% else %}
                    <div class="no-posts">
                        <div class="no-posts-icon"><i class="fas fa-comments"></i></div>
                        <h3>No posts yet</h3>
                        <p>Be the first to start a discussion!</p>
                        {% if not current_user.is_authenticated %}
                            <p style="margin-top: 25px;">
                                <a href="/forum/register" class="nav-btn btn-primary" style="display: inline-flex; padding: 12px 30px; font-size: 1.1em;">
                                    <i class="fas fa-user-plus"></i> Join Now
                                </a>
                            </p>
                        {% endif %}
                    </div>
                {% endif %}
            </main>
        </div>

        <footer class="forum-footer">
            <p>VAHSET COMMUNITY v1.0 • Terminal OSINT Forum • All discussions are secure</p>
            <p style="margin-top: 12px; opacity: 0.8;">
                <i class="fas fa-shield-alt"></i>
                Encrypted Forum • {{ total_visitors }} Members • {{ online_users }} Online
            </p>
        </footer>
    </div>
</body>
</html>
    ''', total_visitors=total_visitors, online_users=online_users,
         active_posts=active_posts, active_users=active_users,
         posts=posts, categories=categories)
@app.route('/forum/register', methods=['GET', 'POST'])
def forum_register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return redirect('/forum/register')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists!', 'error')
            return redirect('/forum/register')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered!', 'error')
            return redirect('/forum/register')
        
        hashed_password = generate_password_hash(password)
        user = User(username=username, email=email, password_hash=hashed_password)
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        flash('Registration successful! Welcome to the community!', 'success')
        return redirect('/forum')
    
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Register | VAHSET COMMUNITY</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --accent-green: #00ff00;
            --accent-cyan: #58a6ff;
            --accent-red: #ff3333;
            --text-primary: #f0f6fc;
            --text-secondary: #8b949e;
            --gradient-matrix: linear-gradient(90deg, #00ff00 0%, #00ff88 100%);
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'JetBrains Mono', monospace;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .register-container {
            width: 100%;
            max-width: 400px;
        }
        
        .register-box {
            background: var(--bg-secondary);
            border: 1px solid rgba(0, 255, 0, 0.3);
            border-radius: 10px;
            padding: 30px;
            backdrop-filter: blur(10px);
        }
        
        .logo {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .logo i {
            font-size: 3em;
            color: var(--accent-green);
            margin-bottom: 10px;
        }
        
        .logo h1 {
            background: var(--gradient-matrix);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-size: 1.5em;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-label {
            display: block;
            margin-bottom: 8px;
            color: var(--accent-cyan);
            font-size: 0.9em;
        }
        
        .form-input {
            width: 100%;
            padding: 12px;
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(88, 166, 255, 0.3);
            border-radius: 6px;
            color: var(--text-primary);
            font-family: 'JetBrains Mono', monospace;
        }
        
        .form-input:focus {
            outline: none;
            border-color: var(--accent-green);
            box-shadow: 0 0 10px rgba(0, 255, 0, 0.2);
        }
        
        .submit-btn {
            width: 100%;
            padding: 12px;
            background: var(--gradient-matrix);
            border: none;
            border-radius: 6px;
            color: #000;
            font-family: 'JetBrains Mono', monospace;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            margin-top: 10px;
        }
        
        .submit-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0, 255, 0, 0.3);
        }
        
        .links {
            text-align: center;
            margin-top: 20px;
            font-size: 0.9em;
        }
        
        .links a {
            color: var(--accent-cyan);
            text-decoration: none;
        }
        
        .links a:hover {
            text-decoration: underline;
        }
        
        .alert {
            padding: 10px;
            border-radius: 6px;
            margin-bottom: 20px;
            font-size: 0.9em;
        }
        
        .alert-error {
            background: rgba(255, 51, 51, 0.1);
            border: 1px solid var(--accent-red);
            color: var(--accent-red);
        }
        
        .alert-success {
            background: rgba(0, 255, 0, 0.1);
            border: 1px solid var(--accent-green);
            color: var(--accent-green);
        }
    </style>
</head>
<body>
    <div class="register-container">
        <div class="register-box">
            <div class="logo">
                <i class="fas fa-user-plus"></i>
                <h1>JOIN VAHSET COMMUNITY</h1>
                <p style="color: var(--text-secondary); font-size: 0.9em;">Create your account</p>
            </div>
            
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="alert alert-{{ category }}">
                            {{ message }}
                        </div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            
            <form method="POST">
                <div class="form-group">
                    <label class="form-label">Username</label>
                    <input type="text" name="username" class="form-input" required 
                           placeholder="Choose a username">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Email</label>
                    <input type="email" name="email" class="form-input" required 
                           placeholder="your@email.com">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" name="password" class="form-input" required 
                           placeholder="••••••••">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Confirm Password</label>
                    <input type="password" name="confirm_password" class="form-input" required 
                           placeholder="••••••••">
                </div>
                
                <button type="submit" class="submit-btn">
                    <i class="fas fa-user-plus"></i>
                    CREATE ACCOUNT
                </button>
            </form>
            
            <div class="links">
                <p>Already have an account? <a href="/forum/login">Login here</a></p>
                <p><a href="/forum"><i class="fas fa-arrow-left"></i> Back to Forum</a></p>
            </div>
        </div>
    </div>
</body>
</html>
''')

@app.route('/forum/login', methods=['GET', 'POST'])
def forum_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect('/forum')
        else:
            flash('Invalid username or password!', 'error')
    
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login | VAHSET COMMUNITY</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --accent-green: #00ff00;
            --accent-cyan: #58a6ff;
            --accent-red: #ff3333;
            --text-primary: #f0f6fc;
            --text-secondary: #8b949e;
            --gradient-matrix: linear-gradient(90deg, #00ff00 0%, #00ff88 100%);
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'JetBrains Mono', monospace;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .login-container {
            width: 100%;
            max-width: 400px;
        }
        
        .login-box {
            background: var(--bg-secondary);
            border: 1px solid rgba(0, 255, 0, 0.3);
            border-radius: 10px;
            padding: 30px;
            backdrop-filter: blur(10px);
        }
        
        .logo {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .logo i {
            font-size: 3em;
            color: var(--accent-green);
            margin-bottom: 10px;
        }
        
        .logo h1 {
            background: var(--gradient-matrix);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-size: 1.5em;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-label {
            display: block;
            margin-bottom: 8px;
            color: var(--accent-cyan);
            font-size: 0.9em;
        }
        
        .form-input {
            width: 100%;
            padding: 12px;
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(88, 166, 255, 0.3);
            border-radius: 6px;
            color: var(--text-primary);
            font-family: 'JetBrains Mono', monospace;
        }
        
        .form-input:focus {
            outline: none;
            border-color: var(--accent-green);
            box-shadow: 0 0 10px rgba(0, 255, 0, 0.2);
        }
        
        .submit-btn {
            width: 100%;
            padding: 12px;
            background: var(--gradient-matrix);
            border: none;
            border-radius: 6px;
            color: #000;
            font-family: 'JetBrains Mono', monospace;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            margin-top: 10px;
        }
        
        .submit-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0, 255, 0, 0.3);
        }
        
        .links {
            text-align: center;
            margin-top: 20px;
            font-size: 0.9em;
        }
        
        .links a {
            color: var(--accent-cyan);
            text-decoration: none;
        }
        
        .links a:hover {
            text-decoration: underline;
        }
        
        .alert {
            padding: 10px;
            border-radius: 6px;
            margin-bottom: 20px;
            font-size: 0.9em;
        }
        
        .alert-error {
            background: rgba(255, 51, 51, 0.1);
            border: 1px solid var(--accent-red);
            color: var(--accent-red);
        }
        
        .alert-success {
            background: rgba(0, 255, 0, 0.1);
            border: 1px solid var(--accent-green);
            color: var(--accent-green);
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-box">
            <div class="logo">
                <i class="fas fa-sign-in-alt"></i>
                <h1>VAHSET COMMUNITY</h1>
                <p style="color: var(--text-secondary); font-size: 0.9em;">Member Login</p>
            </div>
            
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="alert alert-{{ category }}">
                            {{ message }}
                        </div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            
            <form method="POST">
                <div class="form-group">
                    <label class="form-label">Username</label>
                    <input type="text" name="username" class="form-input" required 
                           placeholder="Enter username">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" name="password" class="form-input" required 
                           placeholder="••••••••">
                </div>
                
                <button type="submit" class="submit-btn">
                    <i class="fas fa-sign-in-alt"></i>
                    LOGIN
                </button>
            </form>
            
            <div class="links">
                <p>Don't have an account? <a href="/forum/register">Register here</a></p>
                <p><a href="/forum"><i class="fas fa-arrow-left"></i> Back to Forum</a></p>
            </div>
        </div>
    </div>
</body>
</html>
''')

@app.route('/forum/logout')
@login_required
def forum_logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect('/forum')

@app.route('/forum/create', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        category = request.form.get('category', 'General')
        
        if title and content:
            post = Post(
                title=title,
                content=content,
                category=category,
                user_id=current_user.id
            )
            db.session.add(post)
            db.session.commit()
            flash('Post created successfully!', 'success')
            return redirect('/forum')
    
    categories = ['General', 'OSINT', 'Security', 'Programming', 'Off Topic']
    
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Create Post | VAHSET COMMUNITY</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --accent-green: #00ff00;
            --accent-cyan: #58a6ff;
            --text-primary: #f0f6fc;
            --text-secondary: #8b949e;
            --gradient-matrix: linear-gradient(90deg, #00ff00 0%, #00ff88 100%);
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'JetBrains Mono', monospace;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 20px;
        }
        
        .create-container {
            max-width: 800px;
            margin: 0 auto;
        }
        
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
        }
        
        .back-btn {
            background: rgba(88, 166, 255, 0.1);
            color: var(--accent-cyan);
            border: 1px solid rgba(88, 166, 255, 0.3);
            padding: 10px 20px;
            border-radius: 6px;
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .create-box {
            background: var(--bg-secondary);
            border: 1px solid rgba(0, 255, 0, 0.3);
            border-radius: 10px;
            padding: 30px;
            backdrop-filter: blur(10px);
        }
        
        .form-group {
            margin-bottom: 25px;
        }
        
        .form-label {
            display: block;
            margin-bottom: 10px;
            color: var(--accent-cyan);
            font-size: 1em;
            font-weight: 500;
        }
        
        .form-input {
            width: 100%;
            padding: 15px;
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(88, 166, 255, 0.3);
            border-radius: 8px;
            color: var(--text-primary);
            font-family: 'JetBrains Mono', monospace;
            font-size: 1em;
        }
        
        .form-input:focus {
            outline: none;
            border-color: var(--accent-green);
            box-shadow: 0 0 15px rgba(0, 255, 0, 0.2);
        }
        
        .form-textarea {
            width: 100%;
            padding: 15px;
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(88, 166, 255, 0.3);
            border-radius: 8px;
            color: var(--text-primary);
            font-family: 'JetBrains Mono', monospace;
            font-size: 1em;
            min-height: 300px;
            resize: vertical;
        }
        
        .form-select {
            width: 100%;
            padding: 15px;
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(88, 166, 255, 0.3);
            border-radius: 8px;
            color: var(--text-primary);
            font-family: 'JetBrains Mono', monospace;
            font-size: 1em;
        }
        
        .submit-btn {
            background: var(--gradient-matrix);
            color: #000;
            border: none;
            padding: 15px 30px;
            border-radius: 8px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 1em;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            width: 100%;
        }
        
        .submit-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(0, 255, 0, 0.3);
        }
        
        .emoji-hint {
            color: var(--text-secondary);
            font-size: 0.9em;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="create-container">
        <div class="header">
            <h1><i class="fas fa-edit"></i> CREATE NEW POST</h1>
            <a href="/forum" class="back-btn">
                <i class="fas fa-arrow-left"></i>
                Back to Forum
            </a>
        </div>
        
        <div class="create-box">
            <form method="POST">
                <div class="form-group">
                    <label class="form-label">Title</label>
                    <input type="text" name="title" class="form-input" required 
                           placeholder="Enter post title...">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Category</label>
                    <select name="category" class="form-select" required>
                        {% for category in categories %}
                        <option value="{{ category }}">{{ category }}</option>
                        {% endfor %}
                    </select>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Content</label>
                    <textarea name="content" class="form-textarea" required 
                              placeholder="Write your post here..."></textarea>
                    <div class="emoji-hint">
                        <i class="fas fa-lightbulb"></i> Tip: Press Ctrl + : to insert emojis
                    </div>
                </div>
                
                <button type="submit" class="submit-btn">
                    <i class="fas fa-paper-plane"></i>
                    PUBLISH POST
                </button>
            </form>
        </div>
    </div>
    
    <script>
        // Emoji picker
        document.querySelector('.form-textarea').addEventListener('keydown', function(e) {
            if (e.key === ':' && e.ctrlKey) {
                e.preventDefault();
                const emojis = ['😀', '😂', '🤔', '👏', '🔥', '💯', '🚀', '🎯', '⚡', '🔒', '💻', '🔍', '📡', '🔐'];
                const randomEmoji = emojis[Math.floor(Math.random() * emojis.length)];
                this.value += randomEmoji;
            }
        });
        
        // Auto-resize textarea
        const textarea = document.querySelector('.form-textarea');
        textarea.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        });
    </script>
</body>
</html>
''', categories=categories)

@app.route('/forum/post/<int:post_id>', methods=['GET', 'POST'])
@login_required  # Opsiyonel: sadece giriş yapanlar yorum yapabilsin
def view_post(post_id):
    post = Post.query.get_or_404(post_id)
    post.views += 1
    db.session.commit()

    if request.method == 'POST':
        content = request.form.get('content')
        if content and content.strip():
            comment = Comment(
                content=content.strip(),
                user_id=current_user.id,
                post_id=post.id
            )
            db.session.add(comment)
            db.session.commit()
            flash('Yorumunuz eklendi!', 'success')
            return redirect(url_for('view_post', post_id=post.id))

    # En yeni yorumlar üstte olsun
    comments = Comment.query.filter_by(post_id=post.id).order_by(desc(Comment.timestamp)).all()

    return render_template_string('''
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ post.title }} | VAHSET COMMUNITY</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --accent-green: #00ff00;
            --accent-cyan: #58a6ff;
            --accent-red: #ff3333;
            --text-primary: #f0f6fc;
            --text-secondary: #8b949e;
            --gradient-matrix: linear-gradient(90deg, #00ff00 0%, #00ff88 100%);
        }
        body { font-family: 'JetBrains Mono', monospace; background: var(--bg-primary); color: var(--text-primary); padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        .back-link { color: var(--accent-cyan); margin-bottom: 20px; display: inline-block; }
        .post-box {
            background: var(--bg-secondary);
            border: 1px solid rgba(0,255,0,0.3);
            border-radius: 10px;
            padding: 30px;
            margin-bottom: 30px;
        }
        .post-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid rgba(255,255,255,0.1); }
        .author-info { display: flex; align-items: center; gap: 15px; }
        .avatar { width: 50px; height: 50px; border-radius: 50%; background: var(--gradient-matrix); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #000; font-size: 1.3em; }
        .post-meta { color: var(--text-secondary); font-size: 0.9em; }
        .post-title { font-size: 1.8em; margin: 20px 0; color: var(--accent-cyan); }
        .post-content { line-height: 1.8; font-size: 1.1em; white-space: pre-wrap; }
        .post-stats { margin-top: 20px; display: flex; gap: 20px; color: var(--text-secondary); }
        .comments-section { margin-top: 40px; }
        .comment-form { margin-bottom: 30px; }
        .comment-textarea {
            width: 100%; padding: 15px; background: rgba(0,0,0,0.5); border: 1px solid rgba(88,166,255,0.3);
            border-radius: 8px; color: var(--text-primary); font-family: inherit; min-height: 120px;
        }
        .comment-textarea:focus { outline: none; border-color: var(--accent-green); }
        .submit-comment {
            margin-top: 10px; background: var(--gradient-matrix); color: #000; border: none;
            padding: 12px 25px; border-radius: 6px; cursor: pointer; font-weight: bold;
        }
        .comment-list { display: flex; flex-direction: column; gap: 20px; }
        .comment {
            background: rgba(22,27,34,0.6); padding: 20px; border-radius: 8px;
            border-left: 4px solid var(--accent-green);
        }
        .comment-header { display: flex; justify-content: space-between; margin-bottom: 10px; }
        .comment-author { display: flex; align-items: center; gap: 10px; }
        .comment-time { color: var(--text-secondary); font-size: 0.8em; }
        .no-comments { text-align: center; color: var(--text-secondary); padding: 40px; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/forum" class="back-link"><i class="fas fa-arrow-left"></i> Foruma Dön</a>

        <div class="post-box">
            <div class="post-header">
                <div class="author-info">
                    <div class="avatar">{{ post.author.username[0]|upper }}</div>
                    <div>
                        <strong>{{ post.author.username }}</strong><br>
                        <span class="post-meta">{{ post.timestamp.strftime('%d.%m.%Y %H:%M') }} • {{ post.category }}</span>
                    </div>
                </div>
                <div class="post-stats">
                    <span><i class="far fa-eye"></i> {{ post.views }}</span>
                    <span><i class="far fa-comment"></i> {{ post.comments|length }}</span>
                    <span><i class="far fa-heart"></i> {{ post.likes }}</span>
                </div>
            </div>

            <h1 class="post-title">{{ post.title }}</h1>
            <div class="post-content">{{ post.content }}</div>
        </div>

        <div class="comments-section">
            <h2><i class="far fa-comments"></i> Yorumlar ({{ comments|length }})</h2>

            {% if current_user.is_authenticated %}
            <form method="POST" class="comment-form">
                <textarea name="content" class="comment-textarea" placeholder="Yorumunuzu yazın..." required></textarea>
                <button type="submit" class="submit-comment"><i class="fas fa-paper-plane"></i> Yorum Gönder</button>
            </form>
            {% else %}
            <p style="color: var(--text-secondary);">Yorum yapabilmek için <a href="/forum/login" style="color: var(--accent-cyan);">giriş yapmalısınız</a>.</p>
            {% endif %}

            {% if comments %}
            <div class="comment-list">
                {% for comment in comments %}
                <div class="comment">
                    <div class="comment-header">
                        <div class="comment-author">
                            <div class="avatar" style="width:40px;height:40px;font-size:1em;">{{ comment.user.username[0]|upper }}</div>
                            <strong>{{ comment.user.username }}</strong>
                        </div>
                        <span class="comment-time">{{ comment.timestamp.strftime('%d.%m.%Y %H:%M') }}</span>
                    </div>
                    <div>{{ comment.content }}</div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="no-comments">
                <i class="far fa-comment" style="font-size: 3em; opacity: 0.4; margin-bottom: 15px;"></i>
                <p>Henüz yorum yok. İlk yorumu siz yapın!</p>
            </div>
            {% endif %}
        </div>
    </div>
</body>
</html>
    ''', post=post, comments=comments)


@app.route('/forum/profile')
@login_required
def profile():
    user = current_user
    user_posts = Post.query.filter_by(user_id=user.id).order_by(desc(Post.timestamp)).all()
    post_count = len(user_posts)
    comment_count = Comment.query.filter_by(user_id=user.id).count()
    join_date = user.join_date.strftime('%d.%m.%Y')

    return render_template_string('''
<!DOCTYPE html>
<html lang="tr">
<head>
                                  <div class="profile-header">
    <div class="profile-avatar">
        <img src="/static/uploads/profiles/{{ user.profile_pic }}" alt="Profil" style="width:100%;height:100%;border-radius:50%;object-fit:cover;"
             onerror="this.src='/static/default.png';">
    </div>
    <div class="profile-info">
        <h1>@{{ user.username }}</h1>
        <p style="font-size:1.1em; color:var(--accent-cyan); margin:15px 0;">
            {{ user.bio or 'Henüz biyo eklenmemiş.' }}
        </p>
        <a href="/forum/profile/edit" style="background:var(--gradient-matrix);color:#000;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:bold;">
            <i class="fas fa-edit"></i> Profili Düzenle
        </a>
        <!-- diğer bilgiler... -->
    </div>
</div>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Profil • {{ user.username }} | VAHSET COMMUNITY</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --accent-green: #00ff00;
            --accent-cyan: #58a6ff;
            --text-primary: #f0f6fc;
            --text-secondary: #8b949e;
            --gradient-matrix: linear-gradient(90deg, #00ff00 0%, #00ff88 100%);
        }
        body { font-family: 'JetBrains Mono', monospace; background: var(--bg-primary); color: var(--text-primary); padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        .profile-header {
            background: var(--bg-secondary);
            border: 1px solid rgba(0,255,0,0.3);
            border-radius: 10px;
            padding: 30px;
            display: flex;
            align-items: center;
            gap: 30px;
            margin-bottom: 30px;
        }
        .profile-avatar {
            width: 120px; height: 120px; border-radius: 50%;
            background: var(--gradient-matrix);
            display: flex; align-items: center; justify-content: center;
            font-size: 3.5em; font-weight: bold; color: #000;
        }
        .profile-info h1 { font-size: 2em; margin-bottom: 10px; }
        .profile-meta { color: var(--text-secondary); margin-bottom: 15px; }
        .stats { display: flex; gap: 30px; }
        .stat { text-align: center; }
        .stat-number { font-size: 1.8em; color: var(--accent-green); font-weight: bold; }
        .stat-label { font-size: 0.9em; color: var(--text-secondary); }
        .posts-section h2 { margin-bottom: 20px; color: var(--accent-cyan); }
        .user-posts {
            display: flex; flex-direction: column; gap: 15px;
        }
        .user-post-card {
            background: var(--bg-secondary);
            padding: 20px; border-radius: 8px;
            border-left: 4px solid var(--accent-green);
        }
        .user-post-title {
            font-size: 1.2em; color: var(--accent-cyan); text-decoration: none;
        }
        .user-post-title:hover { color: var(--accent-green); }
        .user-post-meta { color: var(--text-secondary); font-size: 0.9em; margin-top: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/forum" style="color: var(--accent-cyan); display: inline-block; margin-bottom: 20px;">
            <i class="fas fa-arrow-left"></i> Foruma Dön
        </a>

        <div class="profile-header">
            <div class="profile-avatar">{{ user.username[0]|upper }}</div>
            <div class="profile-info">
                <h1>@{{ user.username }}</h1>
                <div class="profile-meta">
                    <i class="fas fa-envelope"></i> {{ user.email }}<br>
                    <i class="fas fa-calendar-alt"></i> Katılım: {{ join_date }}
                </div>
                <div class="stats">
                    <div class="stat">
                        <div class="stat-number">{{ post_count }}</div>
                        <div class="stat-label">Gönderi</div>
                    </div>
                    <div class="stat">
                        <div class="stat-number">{{ comment_count }}</div>
                        <div class="stat-label">Yorum</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="posts-section">
            <h2><i class="fas fa-edit"></i> Gönderileri</h2>
            {% if user_posts %}
            <div class="user-posts">
                {% for post in user_posts %}
                <div class="user-post-card">
                    <a href="/forum/post/{{ post.id }}" class="user-post-title">{{ post.title }}</a>
                    <div class="user-post-meta">
                        {{ post.timestamp.strftime('%d.%m.%Y %H:%M') }} • 
                        {{ post.comments|length }} yorum • {{ post.views }} görüntülenme
                    </div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <p style="color: var(--text-secondary); text-align: center; padding: 40px;">
                Henüz gönderi yok.
            </p>
            {% endif %}
        </div>
    </div>
</body>
</html>
    ''', user=user, user_posts=user_posts, post_count=post_count, comment_count=comment_count, join_date=join_date)

# ==================== OTHER ROUTES ====================
@app.route('/forum/admin/ban/<int:user_id>')
@login_required
@admin_required
def admin_ban_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Kendinizi banlayamazsınız!', 'error')
    else:
        user.is_banned = True
        db.session.commit()
        flash(f'{user.username} banlandı.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/forum/admin/unban/<int:user_id>')
@login_required
@admin_required
def admin_unban_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_banned = False
    db.session.commit()
    flash(f'{user.username} banı kaldırıldı.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/forum/admin/make_admin/<int:user_id>')
@login_required
@admin_required
def admin_make_admin(user_id):
    user = User.query.get_or_404(user_id)
    user.is_admin = True
    db.session.commit()
    flash(f'{user.username} admin yapıldı.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/forum/admin/remove_admin/<int:user_id>')
@login_required
@admin_required
def admin_remove_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Kendi adminliğinizi alamazsınız!', 'error')
    else:
        user.is_admin = False
        db.session.commit()
        flash(f'{user.username} adminliği alındı.', 'success')
    return redirect(url_for('admin_panel'))
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/api/search/<user_id>')
def api_search(user_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_data = users_data.get(user_id)
    if user_data:
        return jsonify({
            'found': True,
            'user_id': user_id,
            'email': user_data['email'],
            'ip': user_data['ip']
        })
    else:
        return jsonify({
            'found': False,
            'user_id': user_id,
            'message': 'User not found'
        })

@app.template_filter('intcomma')
def intcomma_filter(value):
    try:
        return "{:,}".format(int(value))
    except:
        return value
    
@app.route('/forum/admin/delete_post/<int:post_id>')
@login_required
@admin_required
def admin_delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    flash('Gönderi silindi.', 'success')
    return redirect(url_for('forum_home'))

@app.route('/forum/admin/delete_comment/<int:comment_id>')
@login_required
@admin_required
def admin_delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    post_id = comment.post_id
    db.session.delete(comment)
    db.session.commit()
    flash('Yorum silindi.', 'success')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/forum/admin')
@login_required
@admin_required
def admin_panel():
    users = User.query.order_by(User.join_date.desc()).all()
    return render_template_string('''
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Paneli | VAHSET COMMUNITY</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root { --bg-primary: #0d1117; --bg-secondary: #161b22; --accent-green: #00ff00; --accent-red: #ff3333; --accent-cyan: #58a6ff; --text-primary: #f0f6fc; --text-secondary: #8b949e; }
        body { font-family: 'JetBrains Mono', monospace; background: var(--bg-primary); color: var(--text-primary); padding: 20px; }
        .container { max-width: 1100px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
        .back-btn { color: var(--accent-cyan); text-decoration: none; }
        table { width: 100%; border-collapse: collapse; background: var(--bg-secondary); border-radius: 10px; overflow: hidden; }
        th, td { padding: 15px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }
        th { background: rgba(0,255,0,0.1); color: var(--accent-green); }
        .btn { padding: 8px 15px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; text-decoration: none; display: inline-block; }
        .btn-ban { background: var(--accent-red); color: #000; }
        .btn-unban { background: var(--accent-green); color: #000; }
        .btn-admin { background: #bc8cff; color: #000; }
        .btn-remove-admin { background: #8b949e; color: #000; }
        .banned { opacity: 0.6; background: rgba(255,0,0,0.1); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-shield-alt"></i> ADMIN PANELİ</h1>
            <a href="/forum" class="back-btn"><i class="fas fa-arrow-left"></i> Foruma Dön</a>
        </div>

        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Kullanıcı Adı</th>
                    <th>E-posta</th>
                    <th>Katılım</th>
                    <th>Durum</th>
                    <th>İşlemler</th>
                </tr>
            </thead>
            <tbody>
                {% for user in users %}
                <tr {% if user.is_banned %}class="banned"{% endif %}>
                    <td>{{ user.id }}</td>
                    <td>{{ user.username }}</td>
                    <td>{{ user.email }}</td>
                    <td>{{ user.join_date.strftime('%d.%m.%Y') }}</td>
                    <td>
                        {% if user.is_banned %}BANLI{% else %}AKTİF{% endif %}
                        {% if user.is_admin %} | ADMIN{% endif %}
                    </td>
                    <td>
                        {% if not user.is_banned %}
                            <a href="/forum/admin/ban/{{ user.id }}" class="btn btn-ban">Banla</a>
                        {% else %}
                            <a href="/forum/admin/unban/{{ user.id }}" class="btn btn-unban">Banı Kaldır</a>
                        {% endif %}

                        {% if not user.is_admin %}
                            <a href="/forum/admin/make_admin/{{ user.id }}" class="btn btn-admin">Admin Yap</a>
                        {% else %}
                            {% if user.id != current_user.id %} {# Kendini adminlikten çıkarma izni yok #}
                                <a href="/forum/admin/remove_admin/{{ user.id }}" class="btn btn-remove-admin">Adminliği Al</a>
                            {% endif %}
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
    ''', users=users)  
@app.before_request
def restrict_banned_users():
    if request.endpoint and request.endpoint.startswith('forum_') and current_user.is_authenticated:
        if current_user.is_banned:
            flash('Hesabınız banlandığı için foruma erişiminiz engellenmiştir.', 'error')
            logout_user()
            return redirect(url_for('forum_home'))
        # ====================== DM (ÖZEL MESAJ) MODELLERİ VE ROUTES ======================
# Message modeli zaten tanımlı, ekstra bir şey gerekmiyor

@app.route('/forum/messages')
@login_required
def messages_inbox():
    # Gelen mesajlar (en yeni üstte)
    received = Message.query.filter_by(receiver_id=current_user.id)\
                .order_by(desc(Message.timestamp)).all()
    # Gönderilen mesajlar
    sent = Message.query.filter_by(sender_id=current_user.id)\
                .order_by(desc(Message.timestamp)).all()

    # Okunmamış mesaj sayısı
    unread_count = Message.query.filter_by(receiver_id=current_user.id, is_read=False).count()

    return render_template_string('''
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Özel Mesajlar | VAHSET COMMUNITY</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --accent-green: #00ff00;
            --accent-cyan: #58a6ff;
            --accent-red: #ff3333;
            --text-primary: #f0f6fc;
            --text-secondary: #8b949e;
            --gradient-matrix: linear-gradient(90deg, #00ff00 0%, #00ff88 100%);
        }
        body { font-family: 'JetBrains Mono', monospace; background: var(--bg-primary); color: var(--text-primary); padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; }
        .back-link { color: var(--accent-cyan); margin-bottom: 20px; display: inline-block; }
        .messages-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
        .new-msg-btn { background: var(--gradient-matrix); color: #000; padding: 10px 20px; border-radius: 6px; text-decoration: none; }
        .tabs { display: flex; gap: 20px; margin-bottom: 20px; }
        .tab { padding: 10px 20px; background: var(--bg-secondary); border-radius: 6px; cursor: pointer; }
        .tab.active { background: var(--gradient-matrix); color: #000; }
        .message-list { display: flex; flex-direction: column; gap: 15px; }
        .message-card {
            background: var(--bg-secondary);
            border-left: 4px solid var(--accent-green);
            padding: 20px;
            border-radius: 8px;
        }
        .message-header { display: flex; justify-content: space-between; margin-bottom: 10px; }
        .message-sender { font-weight: bold; color: var(--accent-cyan); }
        .message-time { color: var(--text-secondary); font-size: 0.8em; }
        .unread { font-weight: bold; color: var(--accent-green); }
        .no-messages { text-align: center; padding: 60px; color: var(--text-secondary); opacity: 0.7; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/forum" class="back-link"><i class="fas fa-arrow-left"></i> Foruma Dön</a>
        <div class="messages-header">
            <h1><i class="fas fa-envelope"></i> Özel Mesajlar</h1>
            <a href="/forum/messages/new" class="new-msg-btn"><i class="fas fa-plus"></i> Yeni Mesaj</a>
        </div>

        <div class="tabs">
            <div class="tab active" onclick="showTab('received')">Gelen Kutusu {% if unread_count > 0 %}({{ unread_count }} okunmamış){% endif %}</div>
            <div class="tab" onclick="showTab('sent')">Gönderilenler</div>
        </div>

        <div id="received" class="message-list">
            {% if received %}
                {% for msg in received %}
                <div class="message-card {% if not msg.is_read %}unread{% endif %}">
                    <div class="message-header">
                        <div class="message-sender">Gönderen: {{ msg.sender.username }}</div>
                        <div class="message-time">{{ msg.timestamp.strftime('%d.%m.%Y %H:%M') }}</div>
                    </div>
                    <div>{{ msg.content }}</div>
                    <div style="margin-top:10px;">
                        <a href="/forum/messages/reply/{{ msg.sender.id }}" style="color:var(--accent-cyan);font-size:0.9em;">Yanıtla</a>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <div class="no-messages"><i class="fas fa-envelope-open" style="font-size:3em;"></i><p>Gelen mesajınız yok.</p></div>
            {% endif %}
        </div>

        <div id="sent" class="message-list" style="display:none;">
            {% if sent %}
                {% for msg in sent %}
                <div class="message-card">
                    <div class="message-header">
                        <div class="message-sender">Alıcı: {{ msg.receiver.username }}</div>
                        <div class="message-time">{{ msg.timestamp.strftime('%d.%m.%Y %H:%M') }}</div>
                    </div>
                    <div>{{ msg.content }}</div>
                </div>
                {% endfor %}
            {% else %}
                <div class="no-messages"><i class="fas fa-paper-plane" style="font-size:3em;"></i><p>Gönderdiğiniz mesaj yok.</p></div>
            {% endif %}
        </div>
    </div>

    <script>
        function showTab(tab) {
            document.getElementById('received').style.display = tab === 'received' ? 'flex' : 'none';
            document.getElementById('sent').style.display = tab === 'sent' ? 'flex' : 'none';
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
        }

        // Okunmamış mesajları okundu olarak işaretle (sayfa yüklendiğinde)
        fetch('/forum/messages/mark_read', {method: 'POST'});
    </script>
</body>
</html>
    ''', received=received, sent=sent, unread_count=unread_count)

@app.route('/forum/messages/new', methods=['GET', 'POST'])
@login_required
def messages_new():
    if request.method == 'POST':
        username = request.form.get('username')
        content = request.form.get('content')

        receiver = User.query.filter_by(username=username).first()
        if not receiver:
            flash('Böyle bir kullanıcı bulunamadı!', 'error')
            return redirect(url_for('messages_new'))

        if not content.strip():
            flash('Mesaj içeriği boş olamaz!', 'error')
            return redirect(url_for('messages_new'))

        msg = Message(
            content=content.strip(),
            sender_id=current_user.id,
            receiver_id=receiver.id
        )
        db.session.add(msg)
        db.session.commit()
        flash('Mesaj gönderildi!', 'success')
        return redirect(url_for('messages_inbox'))

    return render_template_string('''
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Yeni Mesaj | VAHSET COMMUNITY</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root { --bg-primary: #0d1117; --bg-secondary: #161b22; --accent-green: #00ff00; --accent-cyan: #58a6ff; --text-primary: #f0f6fc; --gradient-matrix: linear-gradient(90deg, #00ff00 0%, #00ff88 100%); }
        body { font-family: 'JetBrains Mono', monospace; background: var(--bg-primary); color: var(--text-primary); padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; }
        .back-link { color: var(--accent-cyan); margin-bottom: 20px; display: inline-block; }
        .form-box { background: var(--bg-secondary); padding: 30px; border-radius: 10px; border: 1px solid rgba(0,255,0,0.3); }
        .form-group { margin-bottom: 20px; }
        .form-label { color: var(--accent-cyan); margin-bottom: 8px; display: block; }
        .form-input, .form-textarea {
            width: 100%; padding: 12px; background: rgba(0,0,0,0.5); border: 1px solid rgba(88,166,255,0.3);
            border-radius: 6px; color: var(--text-primary); font-family: inherit;
        }
        .form-textarea { min-height: 200px; resize: vertical; }
        .submit-btn { background: var(--gradient-matrix); color: #000; padding: 12px 25px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/forum/messages" class="back-link"><i class="fas fa-arrow-left"></i> Mesajlara Dön</a>
        <h1><i class="fas fa-paper-plane"></i> Yeni Mesaj Gönder</h1>
        <div class="form-box">
            <form method="POST">
                <div class="form-group">
                    <label class="form-label">Alıcı Kullanıcı Adı</label>
                    <input type="text" name="username" class="form-input" required placeholder="Kullanıcı adı girin">
                </div>
                <div class="form-group">
                    <label class="form-label">Mesaj</label>
                    <textarea name="content" class="form-textarea" required placeholder="Mesajınızı yazın..."></textarea>
                </div>
                <button type="submit" class="submit-btn"><i class="fas fa-paper-plane"></i> Gönder</button>
            </form>
        </div>
    </div>
</body>
</html>
    ''')

@app.route('/forum/messages/reply/<int:receiver_id>', methods=['GET', 'POST'])
@login_required
def messages_reply(receiver_id):
    receiver = User.query.get_or_404(receiver_id)

    if request.method == 'POST':
        content = request.form.get('content')
        if content.strip():
            msg = Message(content=content.strip(), sender_id=current_user.id, receiver_id=receiver.id)
            db.session.add(msg)
            db.session.commit()
            flash('Yanıt gönderildi!', 'success')
            return redirect(url_for('messages_inbox'))

    return render_template_string('''
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ receiver.username }}'a Yanıtla</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        /* Aynı stil yukarıdaki new mesaj ile */
        :root { --bg-primary: #0d1117; --bg-secondary: #161b22; --accent-green: #00ff00; --accent-cyan: #58a6ff; --text-primary: #f0f6fc; --gradient-matrix: linear-gradient(90deg, #00ff00 0%, #00ff88 100%); }
        body { font-family: 'JetBrains Mono', monospace; background: var(--bg-primary); color: var(--text-primary); padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; }
        .back-link { color: var(--accent-cyan); margin-bottom: 20px; display: inline-block; }
        .form-box { background: var(--bg-secondary); padding: 30px; border-radius: 10px; border: 1px solid rgba(0,255,0,0.3); }
        .form-group { margin-bottom: 20px; }
        .form-label { color: var(--accent-cyan); margin-bottom: 8px; display: block; }
        .form-textarea { width: 100%; padding: 12px; background: rgba(0,0,0,0.5); border: 1px solid rgba(88,166,255,0.3); border-radius: 6px; color: var(--text-primary); min-height: 200px; }
        .submit-btn { background: var(--gradient-matrix); color: #000; padding: 12px 25px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/forum/messages" class="back-link"><i class="fas fa-arrow-left"></i> Mesajlara Dön</a>
        <h1><i class="fas fa-reply"></i> {{ receiver.username }}'a Yanıtla</h1>
        <div class="form-box">
            <form method="POST">
                <div class="form-group">
                    <label class="form-label">Alıcı: {{ receiver.username }}</label>
                </div>
                <div class="form-group">
                    <label class="form-label">Mesaj</label>
                    <textarea name="content" class="form-textarea" required placeholder="Yanıtınızı yazın..."></textarea>
                </div>
                <button type="submit" class="submit-btn"><i class="fas fa-paper-plane"></i> Gönder</button>
            </form>
        </div>
    </div>
</body>
</html>
    ''', receiver=receiver)

@app.route('/forum/messages/mark_read', methods=['POST'])
@login_required
def messages_mark_read():
    Message.query.filter_by(receiver_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return '', 204
@app.route('/forum/profile/edit', methods=['GET', 'POST'])
@login_required
def profile_edit():
    user = current_user
    
    if request.method == 'POST':
        # Biyo güncelle
        bio = request.form.get('bio', '').strip()
        if len(bio) > 500:
            flash('Biyo en fazla 500 karakter olabilir!', 'error')
        else:
            user.bio = bio

        # Profil fotoğrafı yükleme
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename != '':
                # Dosya uzantısını kontrol et
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                    filename = f"user_{user.id}_{hashlib.md5(file.filename.encode()).hexdigest()[:8]}.{file.filename.rsplit('.', 1)[1].lower()}"
                    filepath = os.path.join('static/uploads/profiles', filename)
                    
                    # Klasör yoksa oluştur
                    os.makedirs('static/uploads/profiles', exist_ok=True)
                    
                    file.save(filepath)
                    user.profile_pic = filename
                    flash('Profil fotoğrafı ve biyo başarıyla güncellendi!', 'success')
                else:
                    flash('Geçersiz dosya türü! Sadece PNG, JPG, JPEG, GIF, WEBP kabul edilir.', 'error')
        
        db.session.commit()
        return redirect(url_for('profile'))

    return render_template_string('''
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Profil Düzenle • {{ user.username }} | VAHSET COMMUNITY</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --accent-green: #00ff00;
            --accent-cyan: #58a6ff;
            --text-primary: #f0f6fc;
            --text-secondary: #8b949e;
            --gradient-matrix: linear-gradient(90deg, #00ff00 0%, #00ff88 100%);
        }
        body { font-family: 'JetBrains Mono', monospace; background: var(--bg-primary); color: var(--text-primary); padding: 20px; }
        .container { max-width: 700px; margin: 0 auto; }
        .back-link { color: var(--accent-cyan); margin-bottom: 20px; display: inline-block; }
        .edit-box {
            background: var(--bg-secondary);
            border: 1px solid rgba(0,255,0,0.3);
            border-radius: 12px;
            padding: 30px;
        }
        .current-avatar {
            width: 120px; height: 120px; border-radius: 50%; object-fit: cover;
            border: 3px solid var(--accent-green);
            margin-bottom: 20px;
        }
        .form-group { margin-bottom: 25px; }
        .form-label { color: var(--accent-cyan); margin-bottom: 10px; display: block; font-weight: 500; }
        .form-textarea {
            width: 100%; padding: 15px; background: rgba(0,0,0,0.5); border: 1px solid rgba(88,166,255,0.3);
            border-radius: 8px; color: var(--text-primary); font-family: inherit; min-height: 150px; resize: vertical;
        }
        .form-textarea:focus { outline: none; border-color: var(--accent-green); box-shadow: 0 0 15px rgba(0,255,0,0.2); }
        .file-input {
            padding: 10px; background: rgba(0,0,0,0.5); border: 1px dashed rgba(88,166,255,0.5);
            border-radius: 8px; color: var(--text-primary); width: 100%;
        }
        .submit-btn {
            background: var(--gradient-matrix); color: #000; padding: 15px 30px; border: none;
            border-radius: 8px; font-weight: bold; cursor: pointer; width: 100%;
            font-size: 1.1em; transition: all 0.3s;
        }
        .submit-btn:hover { transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0,255,0,0.4); }
        .char-count { text-align: right; color: var(--text-secondary); font-size: 0.9em; margin-top: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/forum/profile" class="back-link"><i class="fas fa-arrow-left"></i> Profile Dön</a>
        <h1 style="text-align:center; margin-bottom:30px;"><i class="fas fa-user-edit"></i> PROFİL DÜZENLE</h1>
        
        <div class="edit-box" style="text-align:center;">
            <img src="/static/uploads/profiles/{{ user.profile_pic }}" alt="Profil Fotoğrafı" class="current-avatar"
                 onerror="this.src='/static/default.png';">
            
            <form method="POST" enctype="multipart/form-data">
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-image"></i> Profil Fotoğrafı Değiştir</label>
                    <input type="file" name="profile_pic" accept="image/*" class="file-input">
                    <p style="color:var(--text-secondary);font-size:0.9em;margin-top:8px;">
                        PNG, JPG, GIF, WEBP desteklenir (max 5MB önerilir)
                    </p>
                </div>
                
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-pen"></i> Biyo (Kendini Tanıt)</label>
                    <textarea name="bio" class="form-textarea" placeholder="Burada kendini anlatabilirsin... OSINT tutkunu, hacker, araştırmacı vs." 
                              maxlength="500">{{ user.bio }}</textarea>
                    <div class="char-count">{{ user.bio|length }}/500</div>
                </div>
                
                <button type="submit" class="submit-btn">
                    <i class="fas fa-save"></i> DEĞİŞİKLİKLERİ KAYDET
                </button>
            </form>
        </div>
    </div>

    <script>
        // Karakter sayacı canlı güncelleme
        document.querySelector('textarea[name="bio"]').addEventListener('input', function() {
            document.querySelector('.char-count').textContent = this.value.length + '/500';
        });
    </script>
</body>
</html>
    ''', user=user)
# ====================== ADMIN PANEL (Zaten var ama forum header'a link eklemek için forum_home'da küçük değişiklik) ======================
# forum_home route'undaki nav-buttons kısmına şu satırı ekle:
# {% if current_user.is_authenticated and current_user.is_admin %}
#     <a href="/forum/admin" class="nav-btn" style="background:#ff3333;color:#000;"><i class="fas fa-shield-alt"></i> ADMIN PANEL</a>
# {% endif %}

# Admin panel route'un zaten kodunda var, sadece yukarıdaki mesaj route'larından önce olduğundan emin ol.

# ====================== FORUM HEADER'A DM BUTONU EKLE ======================
# forum_home route'undaki nav-buttons içine şu satırı da ekle (admin butonunun yanına):
# {% if current_user.is_authenticated %}
#     <a href="/forum/messages" class="nav-btn btn-primary"><i class="fas fa-envelope"></i> Mesajlar</a>
# {% endif %}
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    print(f"\n{'='*80}")
    print("🚀 VAHSET TERMINAL OSINT v3.0 + FORUM")
    print(f"{'='*80}")
    print(f"🔧 Port: {port}")
    print(f"🔧 Debug: {debug}")
    print(f"👤 GitHub User: {GITHUB_USERNAME}")
    print(f"📦 Repository: {GITHUB_REPO}")
    print(f"📊 Loaded {len(users_data):,} OSINT records")
    print(f"👥 Forum Database: Ready")
    print(f"🛠️  Features: OSINT Terminal • Community Forum • User Profiles")
    print(f"{'='*80}\n")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
