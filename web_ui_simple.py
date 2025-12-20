import http.server
import socketserver
import threading
import json
import os
import base64
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv
from phone_agent.agent import PhoneAgent, AgentConfig
from phone_agent.model import ModelConfig

load_dotenv()

# 全局状态存储
state = {
    "log": "等待任务开始...",
    "running": False,
    "task": ""
}

class SimpleHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            html = f"""
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Open-AutoGLM Lite</title>
                <style>
                    body {{ font-family: sans-serif; margin: 20px; background: #f0f0f0; }}
                    .container {{ max-width: 600px; margin: auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                    img {{ width: 100%; border: 1px solid #ccc; margin-top: 10px; }}
                    pre {{ background: #333; color: #eee; padding: 10px; white-space: pre-wrap; word-wrap: break-word; font-size: 12px; height: 200px; overflow-y: auto; }}
                    input[type="text"] {{ width: 70%; padding: 10px; }}
                    button {{ padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; }}
                    .status {{ color: #666; font-size: 14px; margin-bottom: 10px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>🤖 Open-AutoGLM Lite</h2>
                    <div class="status" id="status">状态: 准备就绪</div>
                    <form action="/start" method="post" id="taskForm">
                        <input type="text" name="task" id="taskInput" placeholder="输入任务，如：打开微信">
                        <button type="submit">开始</button>
                    </form>
                    <div id="log_container">
                        <strong>运行日志:</strong>
                        <pre id="log">等待开始...</pre>
                    </div>
                    <strong>当前画面:</strong>
                    <img id="screenshot" src="/screenshot.png" onerror="this.style.display='none'">
                </div>
                <script>
                    function update() {{
                        fetch('/state').then(r => r.json()).then(data => {{
                            document.getElementById('log').innerText = data.log;
                            document.getElementById('status').innerText = "状态: " + (data.running ? "正在执行..." : "空闲");
                            document.getElementById('screenshot').src = "/screenshot.png?t=" + Date.now();
                            document.getElementById('screenshot').style.display = 'block';
                            // 自动滚动日志到底部
                            var logObj = document.getElementById('log');
                            logObj.scrollTop = logObj.scrollHeight;
                        }});
                    }}
                    setInterval(update, 1500);
                    
                    document.getElementById('taskForm').onsubmit = function(e) {{
                        e.preventDefault();
                        const task = document.getElementById('taskInput').value;
                        fetch('/start?task=' + encodeURIComponent(task));
                        document.getElementById('log').innerText = "正在启动 Agent...";
                    }};
                </script>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
            
        elif self.path == '/state':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(state).encode())
            
        elif self.path.startswith('/screenshot.png'):
            if os.path.exists("latest_screenshot.png"):
                self.send_response(200)
                self.send_header('Content-type', 'image/png')
                self.end_headers()
                with open("latest_screenshot.png", "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
        
        elif self.path.startswith('/start'):
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            task = query.get('task', [''])[0]
            if task and not state['running']:
                threading.Thread(target=run_agent, args=(task,)).start()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

def run_agent(task_desc):
    state['running'] = True
    state['log'] = f"🚀 任务开始: {task_desc}\n"
    
    try:
        model_config = ModelConfig(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
            model_name=os.getenv("MODEL_NAME", "gpt-4o")
        )
        agent_config = AgentConfig(lang="cn", max_steps=15)
        agent = PhoneAgent(model_config=model_config, agent_config=agent_config)
        
        step_count = 0
        result = agent.step(task_desc)
        
        while True:
            step_count += 1
            # 更新日志
            state['log'] += f"\n--- Step {step_count} ---\n"
            state['log'] += f"🤔 思考: {result.thinking}\n"
            if result.action:
                state['log'] += f"🎯 动作: {result.action.get('action')}\n"
            
            # 保存截图供网页显示
            if result.screenshot:
                img_data = base64.b64decode(result.screenshot)
                with open("latest_screenshot.png", "wb") as f:
                    f.write(img_data)
            
            if result.finished:
                state['log'] += f"\n✅ 任务完成: {result.message}\n"
                break
                
            if step_count >= agent_config.max_steps:
                state['log'] += f"\n⚠️ 已达到最大步数\n"
                break
                
            result = agent.step()
            
    except Exception as e:
        state['log'] += f"\n❌ 出错: {str(e)}\n"
    
    state['running'] = False

if __name__ == "__main__":
    PORT = 7860
    handler = SimpleHandler
    # 允许端口复用
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        print(f"🚀 轻量版 UI 已启动!")
        print(f"📱 请在手机浏览器访问: http://localhost:{PORT}")
        httpd.serve_forever()
