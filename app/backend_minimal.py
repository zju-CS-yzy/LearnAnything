from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def index():
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>LearnAnything - 验证页面</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; margin: 40px; background: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #2c3e50; }
        .status { display: inline-block; padding: 8px 16px; border-radius: 20px; background: #27ae60; color: white; font-weight: bold; }
        .card { margin: 20px 0; padding: 20px; border-left: 4px solid #3498db; background: #f8f9fa; border-radius: 4px; }
        .card h3 { margin-top: 0; color: #3498db; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎓 LearnAnything 桌面应用验证</h1>
        <p>状态: <span class="status">✅ 后端 + WebView 运行正常</span></p>
        
        <div class="card">
            <h3>后端服务</h3>
            <p>Flask 运行在 http://127.0.0.1:5000</p>
        </div>
        
        <div class="card">
            <h3>前端渲染</h3>
            <p>PyQt5 QWebEngineView 成功加载页面</p>
        </div>
        
        <div class="card">
            <h3>下一步</h3>
            <p>将前端代码接入此框架，实现完整的 RAG 学习系统界面。</p>
        </div>
        
        <p><small>验证时间: <span id="time"></span></small></p>
    </div>
    <script>
        document.getElementById('time').textContent = new Date().toLocaleString();
    </script>
</body>
</html>
    """

@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "service": "learnanything-backend"})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
