from flask import Flask, request, render_template_string, session, redirect, url_for, jsonify, g
import os
import re
import base64
import json
from datetime import datetime

app = Flask(__name__)

# Render için güvenli ayarlar
app.secret_key = os.environ.get('SECRET_KEY', 'vahset_render_2025_secure_key')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 dakika

CORRECT_KEY = os.environ.get('ACCESS_KEY', 'vahset2025')

# Global değişken
users_data = {}

class TerminalStyle:
    """Terminal stili sabitler"""
    COLORS = {
        'black': '#0a0a0a',
        'dark': '#111111',
        'gray': '#1a1a1a',
        'light_gray': '#2a2a2a',
        'red': '#ff3333',
        'green': '#00ff88',
        'cyan': '#00ffff',
        'yellow': '#ffff00',
        'orange': '#ff9900',
        'purple': '#cc33ff',
        'pink': '#ff66cc',
        'white': '#ffffff'
    }
    
    GRADIENTS = {
        'terminal': 'linear-gradient(135deg, #0a0a0a 0%, #111111 50%, #1a1a1a 100%)',
        'button': 'linear-gradient(90deg, #ff3333 0%, #ff6666 100%)',
        'success': 'linear-gradient(90deg, #00ff88 0%, #00ccaa 100%)',
        'warning': 'linear-gradient(90deg, #ff9900 0%, #ffcc00 100%)',
        'header': 'linear-gradient(90deg, #111111 0%, #222222 100%)'
    }

def load_all_data():
    """Verileri yükle - Render uyumlu"""
    global users_data
    
    print("=" * 70)
    print("🚀 vahset ıd query v2.0 - MODERN TERMINAL STYLE")
    print("=" * 70)
    
    all_users = {}
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    print(f"📁 Script Directory: {script_dir}")
    print(f"📁 Current Directory: {os.getcwd()}")
    
    # Dosya listesi
    data_files = []
    
    # Önce data_part dosyalarını ara
    for i in range(1, 6):
        filename = f"data_part{i}.txt"
        paths_to_check = [
            os.path.join(script_dir, filename),
            os.path.join(os.getcwd(), filename),
            filename
        ]
        
        for path in paths_to_check:
            if os.path.exists(path):
                data_files.append(path)
                print(f"✅ Found: {filename} at {path}")
                break
        else:
            print(f"⚠️  Not found: {filename}")
    
    # Alternatif dosyalar
    if not data_files:
        print("🔍 Searching for alternative data files...")
        for file in os.listdir(script_dir):
            if file.endswith('.txt') and 'data' in file.lower():
                data_files.append(os.path.join(script_dir, file))
                print(f"📄 Using: {file}")
    
    if not data_files:
        print("❌ No data files found!")
        return {}
    
    # Dosyaları oku
    total_loaded = 0
    
    for file_path in data_files:
        filename = os.path.basename(file_path)
        print(f"\n📖 Reading: {filename}")
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            lines = content.strip().split('\n')
            print(f"   📊 Lines: {len(lines):,}")
            
            file_count = 0
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Satır formatını parse et
                if line.startswith('(') and line.endswith('),'):
                    line = line[:-1]
                
                if line.startswith('(') and line.endswith(')'):
                    line = line[1:-1]
                    
                    # Değerleri ayır
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
                    
                    # Verileri çıkar
                    if len(values) >= 9:
                        user_id = values[0].strip().strip("'\"")
                        
                        # Email decode
                        email_encoded = values[1].strip().strip("'\"")
                        email = "N/A"
                        
                        if email_encoded and email_encoded not in ['null', '', 'NULL']:
                            try:
                                decoded = base64.b64decode(email_encoded)
                                email = decoded.decode('utf-8', errors='ignore')
                            except:
                                email = email_encoded
                        
                        # IP adresi
                        ip = values[8].strip().strip("'\"") if len(values) > 8 else "N/A"
                        if ip in ['null', 'NULL']:
                            ip = "N/A"
                        
                        # Kaydet
                        all_users[user_id] = {
                            'email': email,
                            'ip': ip,
                            'encoded': email_encoded
                        }
                        
                        file_count += 1
                        total_loaded += 1
            
            print(f"   ✅ Loaded: {file_count:,} records")
            
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
    
    print(f"\n🎯 TOTAL LOADED: {len(all_users):,} users")
    
    # Örnekler göster
    if all_users:
        print("\n📊 SAMPLE RECORDS:")
        sample_ids = list(all_users.keys())[:3]
        for uid in sample_ids:
            data = all_users[uid]
            print(f"   📍 ID: {uid}")
            print(f"      📧 Email: {data['email'][:50]}...")
            print(f"      🌐 IP: {data['ip']}")
            print()
    
    users_data = all_users
    return all_users

# Verileri uygulama başladığında yükle
with app.app_context():
    print("📦 Loading data on startup...")
    users_data = load_all_data()

@app.before_request
def before_request():
    """Her request öncesi çalışır"""
    g.users_data = users_data

# ==================== ROUTES ====================

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
        <title>VAHSET ID QUERY | ACCESS</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Roboto+Mono:wght@300;400;500&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-primary: {{ colors.black }};
                --bg-secondary: {{ colors.dark }};
                --bg-tertiary: {{ colors.gray }};
                --accent-red: {{ colors.red }};
                --accent-green: {{ colors.green }};
                --accent-cyan: {{ colors.cyan }};
                --text-primary: {{ colors.white }};
                --text-secondary: #aaaaaa;
                --gradient-terminal: {{ gradients.terminal }};
                --gradient-button: {{ gradients.button }};
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
                overflow-x: hidden;
                position: relative;
            }
            
            .scan-line {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 2px;
                background: linear-gradient(90deg, transparent, var(--accent-green), transparent);
                z-index: 1000;
                animation: scan 3s linear infinite;
                opacity: 0.3;
            }
            
            @keyframes scan {
                0% { top: 0%; }
                100% { top: 100%; }
            }
            
            .terminal-grid {
                display: grid;
                place-items: center;
                min-height: 100vh;
                padding: 20px;
                position: relative;
                overflow: hidden;
            }
            
            .terminal-grid::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: 
                    radial-gradient(circle at 20% 30%, rgba(255, 51, 51, 0.05) 0%, transparent 50%),
                    radial-gradient(circle at 80% 70%, rgba(0, 255, 136, 0.05) 0%, transparent 50%);
                z-index: -1;
            }
            
            .login-container {
                background: rgba(17, 17, 17, 0.95);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 51, 51, 0.3);
                border-radius: 16px;
                padding: 50px 40px;
                width: 100%;
                max-width: 480px;
                text-align: center;
                position: relative;
                overflow: hidden;
                box-shadow: 
                    0 20px 40px rgba(0, 0, 0, 0.5),
                    0 0 60px rgba(255, 51, 51, 0.2),
                    inset 0 1px 0 rgba(255, 255, 255, 0.1);
            }
            
            .login-container::before {
                content: '';
                position: absolute;
                top: -2px;
                left: -2px;
                right: -2px;
                bottom: -2px;
                background: linear-gradient(45deg, 
                    {{ colors.red }}, 
                    {{ colors.purple }}, 
                    {{ colors.cyan }}, 
                    {{ colors.red }});
                border-radius: 18px;
                z-index: -1;
                opacity: 0.3;
                animation: borderGlow 3s linear infinite;
            }
            
            @keyframes borderGlow {
                0% { filter: hue-rotate(0deg); }
                100% { filter: hue-rotate(360deg); }
            }
            
            .brand-header {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 15px;
                margin-bottom: 30px;
            }
            
            .logo {
                font-size: 2.5em;
                color: var(--accent-red);
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.1); }
            }
            
            .brand-text {
                font-size: 1.8em;
                font-weight: 700;
                background: linear-gradient(90deg, {{ colors.red }}, {{ colors.purple }}, {{ colors.cyan }});
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                letter-spacing: 1px;
            }
            
            .title {
                font-size: 2.2em;
                font-weight: 600;
                margin-bottom: 10px;
                background: linear-gradient(90deg, {{ colors.white }}, {{ colors.cyan }});
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            
            .subtitle {
                color: var(--text-secondary);
                margin-bottom: 40px;
                font-size: 0.95em;
                letter-spacing: 0.5px;
            }
            
            .input-group {
                position: relative;
                margin-bottom: 30px;
            }
            
            .access-input {
                background: rgba(26, 26, 26, 0.8);
                border: 1px solid rgba(255, 51, 51, 0.4);
                border-radius: 10px;
                color: var(--text-primary);
                font-family: 'JetBrains Mono', monospace;
                padding: 18px 20px;
                width: 100%;
                font-size: 16px;
                transition: all 0.3s ease;
                letter-spacing: 1px;
            }
            
            .access-input:focus {
                outline: none;
                border-color: {{ colors.red }};
                box-shadow: 0 0 20px rgba(255, 51, 51, 0.3);
                background: rgba(26, 26, 26, 0.9);
            }
            
            .input-label {
                position: absolute;
                left: 20px;
                top: -10px;
                background: var(--bg-secondary);
                padding: 0 10px;
                color: var(--accent-cyan);
                font-size: 0.9em;
                letter-spacing: 0.5px;
            }
            
            .access-btn {
                background: var(--gradient-button);
                border: none;
                border-radius: 10px;
                color: #000;
                font-family: 'JetBrains Mono', monospace;
                font-weight: 600;
                padding: 18px;
                width: 100%;
                font-size: 16px;
                cursor: pointer;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                letter-spacing: 1px;
                text-transform: uppercase;
            }
            
            .access-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 25px rgba(255, 51, 51, 0.4);
            }
            
            .access-btn:active {
                transform: translateY(0);
            }
            
            .error-message {
                background: rgba(255, 51, 51, 0.1);
                border: 1px solid rgba(255, 51, 51, 0.3);
                border-radius: 8px;
                padding: 15px;
                margin-top: 25px;
                color: {{ colors.red }};
                font-size: 0.95em;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                animation: shake 0.5s;
            }
            
            @keyframes shake {
                0%, 100% { transform: translateX(0); }
                10%, 30%, 50%, 70%, 90% { transform: translateX(-5px); }
                20%, 40%, 60%, 80% { transform: translateX(5px); }
            }
            
            .terminal-footer {
                margin-top: 40px;
                color: var(--text-secondary);
                font-size: 0.8em;
                border-top: 1px solid rgba(255, 255, 255, 0.1);
                padding-top: 20px;
            }
            
            .powered-by {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 5px;
                margin-top: 10px;
            }
            
            @media (max-width: 600px) {
                .login-container {
                    padding: 40px 25px;
                    margin: 20px;
                }
                
                .title {
                    font-size: 1.8em;
                }
                
                .brand-text {
                    font-size: 1.5em;
                }
            }
        </style>
    </head>
    <body>
        <div class="scan-line"></div>
        <div class="terminal-grid">
            <div class="login-container">
                <div class="brand-header">
                    <div class="logo"><i class="fas fa-terminal"></i></div>
                    <div class="brand-text">VAHSET ID QUERY BY CAPPY</div>
                </div>
                
                <div class="title">🔐 Secure Access</div>
                <div class="subtitle">Enter your access key to continue</div>
                
                <form id="loginForm" method="POST">
                    <div class="input-group">
                        <div class="input-label">ACCESS KEY</div>
                        <input type="password" name="access_key" class="access-input" 
                               placeholder="••••••••••••" required autofocus>
                    </div>
                    
                    <button type="submit" class="access-btn">
                        <i class="fas fa-lock-open"></i>
                        UNLOCK TERMINAL
                    </button>
                    
                    {% if error %}
                    <div class="error-message">
                        <i class="fas fa-exclamation-triangle"></i>
                        {{ error }}
                    </div>
                    {% endif %}
                </form>
                
                <div class="terminal-footer">
                    <div>v2.0 | Modern Terminal Interface</div>
                    <div class="powered-by">
                        <i class="fas fa-code"></i>
                        <span>Powered by Flask & Render</span>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            document.getElementById('loginForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const formData = new FormData(this);
                const button = this.querySelector('.access-btn');
                const originalText = button.innerHTML;
                
                // Loading state
                button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> AUTHENTICATING...';
                button.disabled = true;
                
                try {
                    const response = await fetch('/login', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        // Success animation
                        button.innerHTML = '<i class="fas fa-check"></i> ACCESS GRANTED';
                        button.style.background = '{{ gradients.success }}';
                        
                        setTimeout(() => {
                            window.location.href = data.redirect;
                        }, 1000);
                    } else {
                        // Error state
                        button.innerHTML = originalText;
                        button.disabled = false;
                        
                        // Show error
                        const errorDiv = document.createElement('div');
                        errorDiv.className = 'error-message';
                        errorDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Invalid access key!';
                        
                        const existingError = document.querySelector('.error-message');
                        if (existingError) {
                            existingError.remove();
                        }
                        
                        document.getElementById('loginForm').appendChild(errorDiv);
                        
                        // Shake animation
                        errorDiv.style.animation = 'none';
                        setTimeout(() => {
                            errorDiv.style.animation = 'shake 0.5s';
                        }, 10);
                    }
                } catch (error) {
                    button.innerHTML = originalText;
                    button.disabled = false;
                    alert('Network error. Please try again.');
                }
            });
            
            // Add some terminal-like effects
            document.addEventListener('DOMContentLoaded', function() {
                const inputs = document.querySelectorAll('.access-input');
                inputs.forEach(input => {
                    input.addEventListener('focus', function() {
                        this.parentElement.style.transform = 'scale(1.02)';
                    });
                    
                    input.addEventListener('blur', function() {
                        this.parentElement.style.transform = 'scale(1)';
                    });
                });
            });
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
    
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        search_time = datetime.now().strftime("%H:%M:%S")
        
        if user_id:
            user_data = users_data.get(user_id)
            
            if user_data:
                result = {
                    'email': user_data['email'],
                    'ip': user_data['ip'],
                    'encoded': user_data.get('encoded', ''),
                    'status': 'success'
                }
            else:
                # Benzer ID'leri bul
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
    
    # Örnek ID'ler
    sample_ids = list(users_data.keys())[:8] if users_data else []
    
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>VAHSET ID QUERY | Dashboard</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-primary: {{ colors.black }};
                --bg-secondary: {{ colors.dark }};
                --bg-tertiary: {{ colors.gray }};
                --accent-red: {{ colors.red }};
                --accent-green: {{ colors.green }};
                --accent-cyan: {{ colors.cyan }};
                --accent-yellow: {{ colors.yellow }};
                --accent-purple: {{ colors.purple }};
                --text-primary: {{ colors.white }};
                --text-secondary: #aaaaaa;
                --gradient-header: {{ gradients.header }};
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
            
            .terminal-interface {
                display: flex;
                flex-direction: column;
                min-height: 100vh;
                position: relative;
            }
            
            /* Header */
            .terminal-header {
                background: var(--gradient-header);
                border-bottom: 1px solid rgba(255, 51, 51, 0.3);
                padding: 20px 30px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: sticky;
                top: 0;
                z-index: 100;
                backdrop-filter: blur(10px);
            }
            
            .header-left {
                display: flex;
                align-items: center;
                gap: 20px;
            }
            
            .logo-terminal {
                font-size: 1.8em;
                color: var(--accent-red);
                animation: glow 2s infinite alternate;
            }
            
            @keyframes glow {
                from { text-shadow: 0 0 5px var(--accent-red); }
                to { text-shadow: 0 0 20px var(--accent-red), 0 0 30px var(--accent-red); }
            }
            
            .brand-terminal {
                font-size: 1.5em;
                font-weight: 700;
                background: linear-gradient(90deg, var(--accent-red), var(--accent-purple));
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            
            .header-stats {
                display: flex;
                gap: 25px;
            }
            
            .stat-item {
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            
            .stat-value {
                font-size: 1.2em;
                font-weight: 600;
                color: var(--accent-cyan);
            }
            
            .stat-label {
                font-size: 0.8em;
                color: var(--text-secondary);
                margin-top: 5px;
            }
            
            .header-right {
                display: flex;
                align-items: center;
                gap: 15px;
            }
            
            .user-info {
                background: rgba(255, 51, 51, 0.1);
                padding: 8px 15px;
                border-radius: 20px;
                border: 1px solid rgba(255, 51, 51, 0.3);
                font-size: 0.9em;
            }
            
            .logout-btn {
                background: rgba(255, 51, 51, 0.2);
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
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(255, 51, 51, 0.4);
            }
            
            /* Main Content */
            .terminal-main {
                flex: 1;
                padding: 30px;
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 30px;
                max-width: 1400px;
                margin: 0 auto;
                width: 100%;
            }
            
            @media (max-width: 1024px) {
                .terminal-main {
                    grid-template-columns: 1fr;
                }
            }
            
            /* Left Panel - Search */
            .search-panel {
                background: rgba(26, 26, 26, 0.8);
                border: 1px solid rgba(255, 51, 51, 0.2);
                border-radius: 15px;
                padding: 30px;
                backdrop-filter: blur(10px);
            }
            
            .panel-title {
                font-size: 1.3em;
                font-weight: 600;
                margin-bottom: 25px;
                color: var(--accent-cyan);
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .search-form {
                display: flex;
                flex-direction: column;
                gap: 20px;
            }
            
            .input-wrapper {
                position: relative;
            }
            
            .terminal-input {
                background: rgba(10, 10, 10, 0.8);
                border: 1px solid rgba(255, 51, 51, 0.4);
                border-radius: 10px;
                color: var(--text-primary);
                font-family: 'JetBrains Mono', monospace;
                padding: 18px 20px;
                width: 100%;
                font-size: 16px;
                transition: all 0.3s ease;
            }
            
            .terminal-input:focus {
                outline: none;
                border-color: var(--accent-red);
                box-shadow: 0 0 20px rgba(255, 51, 51, 0.3);
            }
            
            .search-btn {
                background: linear-gradient(90deg, var(--accent-red), #ff6666);
                border: none;
                border-radius: 10px;
                color: #000;
                font-family: 'JetBrains Mono', monospace;
                font-weight: 600;
                padding: 18px;
                font-size: 16px;
                cursor: pointer;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            
            .search-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 25px rgba(255, 51, 51, 0.4);
            }
            
            .sample-ids {
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            .sample-title {
                color: var(--text-secondary);
                margin-bottom: 15px;
                font-size: 0.9em;
            }
            
            .id-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
                gap: 10px;
            }
            
            .id-chip {
                background: rgba(255, 51, 51, 0.1);
                border: 1px solid rgba(255, 51, 51, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 0.8em;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s ease;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            
            .id-chip:hover {
                background: rgba(255, 51, 51, 0.2);
                transform: translateY(-2px);
            }
            
            /* Right Panel - Results */
            .results-panel {
                background: rgba(26, 26, 26, 0.8);
                border: 1px solid rgba(255, 51, 51, 0.2);
                border-radius: 15px;
                padding: 30px;
                backdrop-filter: blur(10px);
            }
            
            .results-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 25px;
            }
            
            .search-time {
                color: var(--text-secondary);
                font-size: 0.9em;
            }
            
            .results-content {
                min-height: 300px;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }
            
            .no-search {
                text-align: center;
                color: var(--text-secondary);
                padding: 50px 20px;
            }
            
            .no-search i {
                font-size: 3em;
                margin-bottom: 20px;
                color: var(--accent-purple);
                opacity: 0.5;
            }
            
            .result-card {
                background: rgba(10, 10, 10, 0.9);
                border: 1px solid rgba(255, 51, 51, 0.3);
                border-radius: 12px;
                padding: 25px;
                animation: fadeIn 0.5s ease;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            .result-status {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            .status-success {
                color: var(--accent-green);
            }
            
            .status-error {
                color: var(--accent-red);
            }
            
            .status-icon {
                font-size: 1.5em;
            }
            
            .result-grid {
                display: grid;
                gap: 15px;
            }
            
            .result-row {
                display: flex;
                align-items: center;
                gap: 15px;
                padding: 12px;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 8px;
                transition: all 0.3s ease;
            }
            
            .result-row:hover {
                background: rgba(255, 255, 255, 0.08);
                transform: translateX(5px);
            }
            
            .row-label {
                min-width: 100px;
                color: var(--accent-cyan);
                font-weight: 500;
            }
            
            .row-value {
                flex: 1;
                word-break: break-all;
                font-family: 'Courier New', monospace;
            }
            
            .similar-results {
                margin-top: 25px;
                padding-top: 20px;
                border-top: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            .similar-title {
                color: var(--accent-yellow);
                margin-bottom: 15px;
                font-size: 0.9em;
            }
            
            .similar-list {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
            }
            
            .similar-id {
                background: rgba(255, 153, 0, 0.1);
                border: 1px solid rgba(255, 153, 0, 0.3);
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 0.8em;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            
            .similar-id:hover {
                background: rgba(255, 153, 0, 0.2);
                transform: translateY(-2px);
            }
            
            /* Footer */
            .terminal-footer {
                background: var(--gradient-header);
                border-top: 1px solid rgba(255, 51, 51, 0.3);
                padding: 20px 30px;
                text-align: center;
                color: var(--text-secondary);
                font-size: 0.9em;
            }
            
            .footer-links {
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-top: 10px;
            }
            
            .footer-link {
                color: var(--accent-cyan);
                text-decoration: none;
                transition: all 0.3s ease;
            }
            
            .footer-link:hover {
                color: var(--accent-red);
                text-decoration: underline;
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
                    padding: 20px;
                    gap: 20px;
                }
                
                .search-panel, .results-panel {
                    padding: 20px;
                }
                
                .id-grid {
                    grid-template-columns: repeat(2, 1fr);
                }
            }
        </style>
    </head>
    <body>
        <div class="terminal-interface">
            <!-- Header -->
            <header class="terminal-header">
                <div class="header-left">
                    <div class="logo-terminal">
                        <i class="fas fa-terminal"></i>
                    </div>
                    <div class="brand-terminal">VAHSET ID QUERY</div>
                </div>
                
                <div class="header-stats">
                    <div class="stat-item">
                        <div class="stat-value">{{ total_users|intcomma }}</div>
                        <div class="stat-label">USERS</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">v2.0</div>
                        <div class="stat-label">VERSION</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="liveTime">--:--:--</div>
                        <div class="stat-label">TIME</div>
                    </div>
                </div>
                
                <div class="header-right">
                    <div class="user-info">
                        <i class="fas fa-user-shield"></i>
                        ADMIN ACCESS
                    </div>
                    <a href="/logout" class="logout-btn">
                        <i class="fas fa-sign-out-alt"></i>
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
                        USER ID SEARCH
                    </div>
                    
                    <form method="POST" class="search-form">
                        <div class="input-wrapper">
                            <input type="text" 
                                   name="user_id" 
                                   class="terminal-input"
                                   placeholder="Enter User ID (e.g., 1379557223096914020)..."
                                   value="{{ user_id if user_id }}"
                                   required
                                   autofocus>
                        </div>
                        
                        <button type="submit" class="search-btn">
                            <i class="fas fa-bolt"></i>
                            EXECUTE QUERY
                        </button>
                    </form>
                    
                    <div class="sample-ids">
                        <div class="sample-title">
                            <i class="fas fa-lightbulb"></i>
                            SAMPLE USER IDs:
                        </div>
                        <div class="id-grid">
                            {% for sample_id in sample_ids %}
                            <div class="id-chip" onclick="document.querySelector('.terminal-input').value='{{ sample_id }}'">
                                {{ sample_id[:10] }}...
                            </div>
                            {% endfor %}
                        </div>
                    </div>
                </div>
                
                <!-- Right Panel - Results -->
                <div class="results-panel">
                    <div class="results-header">
                        <div class="panel-title">
                            <i class="fas fa-database"></i>
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
                            <i class="fas fa-terminal"></i>
                            <h3>No Query Executed</h3>
                            <p>Enter a User ID and click "Execute Query" to search the database</p>
                        </div>
                        {% else %}
                        <div class="result-card">
                            <div class="result-status">
                                <div class="status-icon">
                                    {% if result.status == 'success' %}
                                    <i class="fas fa-check-circle status-success"></i>
                                    {% else %}
                                    <i class="fas fa-times-circle status-error"></i>
                                    {% endif %}
                                </div>
                                <div>
                                    {% if result.status == 'success' %}
                                    <h3 class="status-success">USER FOUND</h3>
                                    {% else %}
                                    <h3 class="status-error">USER NOT FOUND</h3>
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
                                    <div class="row-label">BASE64:</div>
                                    <div class="row-value" style="font-size: 0.85em; opacity: 0.8;">
                                        {{ result.encoded }}
                                    </div>
                                </div>
                                {% endif %}
                            </div>
                            {% else %}
                            <div class="result-grid">
                                <div class="result-row">
                                    <div class="row-label">STATUS:</div>
                                    <div class="row-value">{{ result.message }}</div>
                                </div>
                                <div class="result-row">
                                    <div class="row-label">SEARCHED:</div>
                                    <div class="row-value">{{ user_id }}</div>
                                </div>
                            </div>
                            
                            {% if result.similar %}
                            <div class="similar-results">
                                <div class="similar-title">
                                    <i class="fas fa-random"></i>
                                    SIMILAR IDs FOUND:
                                </div>
                                <div class="similar-list">
                                    {% for similar_id in result.similar %}
                                    <div class="similar-id" 
                                         onclick="document.querySelector('.terminal-input').value='{{ similar_id }}'">
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
                <div>VAHSET ID QUERY v2.0 | Modern Terminal Interface</div>
                <div class="footer-links">
                    <a href="#" class="footer-link"><i class="fas fa-shield-alt"></i> Secure</a>
                    <a href="#" class="footer-link"><i class="fas fa-bolt"></i> Fast</a>
                    <a href="#" class="footer-link"><i class="fas fa-database"></i> Reliable</a>
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
            
            setInterval(updateTime, 1000);
            updateTime();
            
            // Terminal effects
            document.addEventListener('DOMContentLoaded', function() {
                // Input focus effect
                const inputs = document.querySelectorAll('.terminal-input');
                inputs.forEach(input => {
                    input.addEventListener('focus', function() {
                        this.parentElement.style.transform = 'scale(1.02)';
                    });
                    
                    input.addEventListener('blur', function() {
                        this.parentElement.style.transform = 'scale(1)';
                    });
                });
                
                // Sample ID click effect
                const idChips = document.querySelectorAll('.id-chip, .similar-id');
                idChips.forEach(chip => {
                    chip.addEventListener('click', function() {
                        this.style.animation = 'none';
                        setTimeout(() => {
                            this.style.animation = 'fadeIn 0.3s ease';
                        }, 10);
                    });
                });
                
                // Form submission
                const form = document.querySelector('form');
                if (form) {
                    form.addEventListener('submit', function() {
                        const button = this.querySelector('.search-btn');
                        const originalHTML = button.innerHTML;
                        
                        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> SEARCHING...';
                        button.disabled = true;
                        
                        setTimeout(() => {
                            button.innerHTML = originalHTML;
                            button.disabled = false;
                        }, 2000);
                    });
                }
                
                // Terminal typing effect for placeholder
                const input = document.querySelector('.terminal-input');
                if (input && !input.value) {
                    const placeholder = input.getAttribute('placeholder');
                    let i = 0;
                    
                    function typeWriter() {
                        if (i < placeholder.length) {
                            input.setAttribute('placeholder', placeholder.substring(0, i + 1));
                            i++;
                            setTimeout(typeWriter, 50);
                        }
                    }
                    
                    setTimeout(typeWriter, 1000);
                }
            });
            
            // Auto-focus input on page load
            window.onload = function() {
                const input = document.querySelector('.terminal-input');
                if (input) {
                    input.focus();
                }
            };
        </script>
    </body>
    </html>
    ''', result=result, user_id=user_id, total_users=total_users, 
         sample_ids=sample_ids, search_time=search_time,
         colors=TerminalStyle.COLORS, gradients=TerminalStyle.GRADIENTS)

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

# Custom filter for number formatting
@app.template_filter('intcomma')
def intcomma_filter(value):
    try:
        return "{:,}".format(int(value))
    except:
        return value

# Render için gerekli
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Render'da debug mode kapalı olmalı
    debug = os.environ.get('FLASK_ENV') == 'development'
    print(f"\n{'='*70}")
    print("🚀 VAHSET ID QUERY v2.0 - MODERN TERMINAL INTERFACE")
    print(f"🔧 Port: {port}")
    print(f"🔧 Debug: {debug}")
    print(f"📊 Loaded {len(users_data):,} users")
    print(f"{'='*70}\n")
    app.run(host='0.0.0.0', port=port, debug=debug)
