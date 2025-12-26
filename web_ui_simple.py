import http.server
import socketserver
import threading
import json
import os
import base64
import subprocess
from urllib.parse import urlparse, parse_qs, unquote
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

from phone_agent.agent import PhoneAgent, AgentConfig
from phone_agent.model import ModelConfig

load_dotenv()

CONFIG_FILE = "ui_config.json"
# 强制本地不走代理
os.environ["NO_PROXY"] = "localhost,127.0.0.1"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "model_name": os.getenv("MODEL_NAME", "gpt-4o"),
        "api_type": "openai",
        "device_id": "",
        "lang": "cn",
        "max_steps": 15
    }

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

# 全局状态
state = {
    "history": [], # 存储步骤对象
    "running": False,
    "current_step": 0,
    "current_task": "",
    "config": load_config()
}

class SimpleHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(self.get_html().encode())
            
        elif parsed_path.path == '/state':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            # 只返回界面需要的状态，不包含巨大的图片数据
            self.wfile.write(json.dumps({
                "running": state["running"],
                "history": state["history"],
                "config": state["config"],
                "current_task": state["current_task"]
            }).encode())
            
        elif parsed_path.path == '/screenshot.png':
            if os.path.exists("latest_screenshot.png"):
                self.send_response(200)
                self.send_header('Content-type', 'image/png')
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.end_headers()
                with open("latest_screenshot.png", "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()

        elif parsed_path.path == '/refresh_screen':
            # 手动触发一次屏幕截图
            try:
                from phone_agent.device_factory import get_device_factory
                df = get_device_factory()
                # 尝试获取当前配置中的 device_id
                cfg = state["config"]
                screenshot = df.get_screenshot(cfg.get("device_id") if cfg.get("device_id") else None)
                if screenshot:
                    img_data = base64.b64decode(screenshot.base64_data)
                    with open("latest_screenshot.png", "wb") as f:
                        f.write(img_data)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"OK")
                else:
                    self.send_response(500)
                    self.end_headers()
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())

        elif parsed_path.path == '/start':
            query = parse_qs(parsed_path.query)
            # 更新并保存配置
            new_config = {
                "api_key": query.get('api_key', [''])[0],
                "base_url": query.get('base_url', [''])[0],
                "model_name": query.get('model_name', [''])[0],
                "api_type": query.get('api_type', ['openai'])[0],
                "device_id": query.get('device_id', [''])[0],
                "lang": query.get('lang', ['cn'])[0],
                "max_steps": int(query.get('max_steps', [15])[0])
            }
            state["config"] = new_config
            save_config(new_config)
            
            task = query.get('task', [''])[0]
            if task and not state['running']:
                # 设置为 daemon=True，确保主程序退出时子线程也随之停止
                t = threading.Thread(target=run_agent_thread, args=(task, new_config))
                t.daemon = True
                t.start()
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    def get_html(self):
        c = state["config"]
        # 使用三个单引号的 f-string 以减少双引号转义压力，但这里保持一致
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Open-AutoGLM Web Console</title>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
            <style>
                :root {{
                    --primary: #10a37f;
                    --primary-hover: #0d8a6a;
                    --bg-page: #f0f2f5;
                    --bg-card: #ffffff;
                    --text-main: #1a1a1a;
                    --text-muted: #666666;
                    --border: #e0e0e0;
                    --sidebar-bg: #202123;
                }}
                body {{ font-family: 'Inter', -apple-system, system-ui, sans-serif; margin: 0; background: var(--bg-page); color: var(--text-main); line-height: 1.5; }}
                .app {{ display: flex; flex-direction: column; height: 100vh; }}
                header {{ background: var(--sidebar-bg); color: white; padding: 0 24px; height: 60px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); z-index: 10; }}
                .header-title {{ font-size: 18px; font-weight: 700; display: flex; align-items: center; gap: 10px; }}
                .main {{ display: flex; flex: 1; overflow: hidden; }}
                .sidebar {{ width: 320px; background: var(--bg-card); border-right: 1px solid var(--border); padding: 24px; overflow-y: auto; flex-shrink: 0; display: flex; flex-direction: column; gap: 20px; }}
                .sidebar h3 {{ margin: 0 0 10px 0; font-size: 16px; display: flex; align-items: center; gap: 8px; color: var(--text-main); }}
                .field {{ margin-bottom: 0; }}
                .field label {{ display: block; margin-bottom: 6px; font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; }}
                .field input, .field select {{ width: 100%; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; box-sizing: border-box; font-size: 14px; transition: border-color 0.2s; }}
                .field input:focus {{ outline: none; border-color: var(--primary); }}
                .content {{ flex: 1; display: flex; flex-direction: column; padding: 24px; overflow-y: auto; gap: 24px; min-width: 0; }}
                .card {{ background: var(--bg-card); border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid var(--border); max-width: 100%; overflow: hidden; }}
                .task-card {{ padding: 20px; }}
                .task-row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
                .task-row input {{ flex: 1; min-width: 200px; padding: 12px 16px; border: 1px solid var(--border); border-radius: 10px; font-size: 15px; background: #f9f9f9; }}
                .btn-run {{ background: var(--primary); color: white; border: none; padding: 12px 24px; border-radius: 10px; cursor: pointer; font-weight: 600; font-size: 15px; transition: all 0.2s; display: flex; align-items: center; justify-content: center; gap: 8px; white-space: nowrap; }}
                .output-grid {{ display: grid; grid-template-columns: 380px 1fr; gap: 24px; flex: 1; min-height: 0; min-width: 0; }}
                .screen-box {{ display: flex; flex-direction: column; height: 100%; }}
                .box-header {{ padding: 12px 16px; border-bottom: 1px solid var(--border); font-weight: 600; display: flex; align-items: center; gap: 8px; }}
                .screen-container {{ flex: 1; padding: 16px; display: flex; align-items: center; justify-content: center; background: #2a2a2e; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; overflow: hidden; }}
                #screenshot {{ max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 4px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }}
                .log-box {{display: flex; flex-direction: column; height: 100%; overflow: hidden; }}
                #history_list {{ flex: 1; overflow-y: auto; padding: 0; }}
                .step-item {{ border-bottom: 1px solid var(--border); padding: 20px; transition: background 0.2s; }}
                .step-item:last-child {{ border-bottom: none; }}
                .step-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
                .step-num {{ background: #e7f6f2; color: var(--primary); padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 700; }}
                .step-status {{ font-size: 12px; }}
                .status-success {{ color: var(--primary); }}
                .status-fail {{ color: #dc3545; }}
                .thought-container {{ background: #f8f9fa; border-left: 4px solid #dee2e6; padding: 12px 16px; margin-bottom: 12px; border-radius: 0 8px 8px 0; }}
                .thought-label {{ font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px; display: block; }}
                .thought-text {{ font-size: 14px; color: #444; }}
                .action-info {{ display: flex; align-items: flex-start; gap: 10px; font-size: 14px; overflow: hidden; }}
                .action-tag {{ background: #e7f3ff; color: #007bff; padding: 4px 10px; border-radius: 6px; font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 13px; white-space: nowrap; }}
                .action-msg {{ color: var(--text-muted); margin-top: 4px; word-break: break-all; }}
                #status-badge {{ font-size: 13px; display: flex; align-items: center; gap: 6px; font-weight: 600; padding: 6px 12px; border-radius: 20px; background: rgba(255,255,255,0.1); white-space: nowrap; }}
                .current-task-display {{ margin-bottom: 24px; padding: 16px; background: #e7f6f2; border-radius: 10px; border: 1px solid #c3e6cb; word-break: break-all; }}
                .task-label {{ font-size: 12px; font-weight: 700; color: #0d8a6a; margin-bottom: 4px; text-transform: uppercase; }}
                .task-text {{ font-size: 16px; font-weight: 600; color: #155724; }}
                @media (max-width: 1024px) {{ .output-grid {{ grid-template-columns: 1fr; }} .sidebar {{ width: 280px; }} }}
                @media (max-width: 768px) {{ header {{ padding: 0 16px; }} .header-title {{ font-size: 16px; }} .content {{ padding: 16px; }} .main {{ flex-direction: column; overflow-y: auto; }} .sidebar {{ width: 100%; border-right: none; border-bottom: 1px solid var(--border); height: auto; overflow-y: visible; padding: 16px; box-sizing: border-box; }} .app {{ height: auto; min-height: 100vh; }} .main {{ overflow: visible; }} .output-grid {{ grid-template-columns: 1fr; }} .task-row {{ flex-direction: column; }} .btn-run {{ width: 100%; padding: 12px; }} .screen-container {{ min-height: 400px; }} }}
                ::-webkit-scrollbar {{ width: 8px; }} ::-webkit-scrollbar-track {{ background: transparent; }} ::-webkit-scrollbar-thumb {{ background: #ccc; border-radius: 4px; }} ::-webkit-scrollbar-thumb:hover {{ background: #bbb; }}
            </style>
        </head>
        <body>
            <div class="app">
                <header>
                    <div class="header-title"><i class="fas fa-robot"></i> Open-AutoGLM Console</div>
                    <div id="status-badge"><i class="fas fa-circle" id="status-dot" style="color: #10a37f; font-size: 8px;"></i> <span id="status-text">准备就绪</span></div>
                </header>
                <div class="main">
                    <div class="sidebar">
                        <div>
                            <h3><i class="fas fa-cog"></i> 模型设置</h3>
                            <div class="field"><label>API Key</label><input type="password" id="api_key" value="{c['api_key']}" placeholder="sk-..."></div>
                            <div style="margin-top: 12px;" class="field"><label>Base URL</label><input type="text" id="base_url" value="{c['base_url']}"></div>
                            <div style="margin-top: 12px;" class="field"><label>Model Name</label><input type="text" id="model_name" value="{c['model_name']}"></div>
                            <div style="margin-top: 12px;" class="field"><label>API Type</label><select id="api_type"><option value="openai" {"selected" if c['api_type']=='openai' else ""}>OpenAI</option><option value="gemini" {"selected" if c['api_type']=='gemini' else ""}>Gemini</option></select></div>
                        </div>
                        <div style="margin-top: 10px; padding-top: 20px; border-top: 1px solid var(--border);">
                            <h3><i class="fas fa-mobile-alt"></i> 设备设置</h3>
                            <div class="field"><label>Device ID</label><input type="text" id="device_id" value="{c['device_id']}" placeholder="ADB Serial (可选)"></div>
                            <div style="margin-top: 12px;" class="field"><label>最大步数</label><input type="number" id="max_steps" value="{c['max_steps']}"></div>
                        </div>
                        <div style="flex:1"></div>
                        <div style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 10px;">Powered by Open-AutoGLM</div>
                    </div>
                    <div class="content">
                        <div class="card task-card"><div class="task-row"><input type="text" id="task_input" placeholder="请输入指令..."><button class="btn-run" id="run_btn" onclick="startTask()"><i class="fas fa-play"></i> 开始运行</button></div></div>
                        <div id="current_task_box" class="current-task-display" style="display: none;"><div class="task-label">正在执行任务</div><div id="display_task_text" class="task-text"></div></div>
                        <div class="output-grid">
                            <div class="card screen-box"><div class="box-header"><i class="fas fa-desktop"></i> 实时画面</div><div class="screen-container"><img id="screenshot" src="/screenshot.png"></div></div>
                            <div class="card log-box"><div class="box-header"><i class="fas fa-list-ul"></i> 运行日志</div><div id="history_list"><div style="padding: 40px; text-align: center; color: var(--text-muted);"><i class="fas fa-terminal" style="font-size: 48px; margin-bottom: 16px; opacity: 0.2;"></i><p>等待任务开始...</p></div></div></div>
                        </div>
                    </div>
                </div>
            </div>

            <script>
                let lastHistoryLen = 0;
                let lastStatus = null; // 修改为 null 以确保第一次 update 时强制刷新画面

                // 页面加载时自动从 localStorage 恢复设置
                window.addEventListener('DOMContentLoaded', () => {{
                    const fields = ['api_key', 'base_url', 'model_name', 'api_type', 'device_id', 'max_steps'];
                    fields.forEach(id => {{
                        const saved = localStorage.getItem('autoglm_' + id);
                        if (saved) {{
                            document.getElementById(id).value = saved;
                        }}
                        
                        // 监听输入，实时保存到缓存
                        document.getElementById(id).addEventListener('input', (e) => {{
                            localStorage.setItem('autoglm_' + id, e.target.value);
                        }});
                    }});
                    
                    // 加载后立即尝试同步一次手机屏幕
                    fetch('/refresh_screen').then(() => {{
                        document.getElementById('screenshot').src = "/screenshot.png?t=" + Date.now();
                    }});
                }});

                function refreshScreen() {{
                    fetch('/refresh_screen').then(() => {{
                        document.getElementById('screenshot').src = "/screenshot.png?t=" + Date.now();
                    }});
                }}

                function startTask() {{
                    const task = document.getElementById('task_input').value;
                    if (!task) return alert('请输入任务指令');
                    
                    // 启动前先刷新一次屏幕，确保画面是最新的
                    refreshScreen();
                    
                    const params = new URLSearchParams({{
                        task: task,
                        api_key: document.getElementById('api_key').value,
                        base_url: document.getElementById('base_url').value,
                        model_name: document.getElementById('model_name').value,
                        api_type: document.getElementById('api_type').value,
                        device_id: document.getElementById('device_id').value,
                        max_steps: document.getElementById('max_steps').value,
                        lang: 'cn'
                    }});
                    
                    fetch('/start?' + params.toString());
                    document.getElementById('current_task_box').style.display = 'block';
                    document.getElementById('display_task_text').innerText = task;
                    document.getElementById('history_list').innerHTML = '<div style="text-align:center;padding:30px;"><i class="fas fa-spinner fa-spin"></i> 初始化中...</div>';
                    lastHistoryLen = 0;
                }}

                function update() {{
                    fetch('/state').then(r => r.json()).then(data => {{
                        const btn = document.getElementById('run_btn');
                        if (btn.disabled !== data.running) {{
                            btn.disabled = data.running;
                            document.getElementById('status-text').innerText = data.running ? "正在运行" : "准备就绪";
                            document.getElementById('status-dot').style.color = data.running ? "#f39c12" : "#10a37f";
                        }}
                        if (data.current_task) {{
                            document.getElementById('current_task_box').style.display = 'block';
                            document.getElementById('display_task_text').innerText = data.current_task;
                        }}
                        if (data.running || lastStatus !== data.running) {{
                            document.getElementById('screenshot').src = "/screenshot.png?t=" + Date.now();
                        }}
                        lastStatus = data.running;
                        if (data.history.length !== lastHistoryLen) {{
                            let html = "";
                            const history = [...data.history].reverse();
                            history.forEach((step, idx) => {{
                                const stepIdx = data.history.length - idx;
                                const isSuccess = step.success !== false;
                                const thinking = step.thinking || "";
                                const actionName = (step.action && step.action.action) ? step.action.action : (step.action && step.action._metadata === 'finish' ? 'Finish' : 'None');
                                const actionThought = (step.action && step.action.thought) ? step.action.thought : "";
                                
                                html += `
                                    <div class="step-item">
                                        <div class="step-header">
                                            <span class="step-num">STEP ${{stepIdx}}</span>
                                            <span class="step-status ${{isSuccess ? 'status-success' : 'status-fail'}}">
                                                <i class="fas ${{isSuccess ? 'fa-check-circle' : 'fa-exclamation-circle'}}"></i>
                                                ${{isSuccess ? '成功' : '失败'}}
                                            </span>
                                        </div>
                                        
                                        ${{thinking ? `
                                        <div class="thought-container">
                                            <div class="thought-text">${{thinking}}</div>
                                        </div>` : ""}}

                                        <div class="action-info">
                                            <div style="width: 100%;">
                                                <div style="display:flex; align-items:center; gap:8px; margin-bottom: 4px;">
                                                    <span class="action-tag" style="${{actionName === 'Finish' ? 'background:#10a37f;color:white;' : ''}}">${{actionName}}</span>
                                                    ${{actionThought ? `<span style="color: #10a37f; font-weight: 500; font-size: 13px;"><i class="fas fa-comment-dots"></i> ${{actionThought}}</span>` : ""}}
                                                </div>
                                                
                                                <div style="font-size: 12px; color: #666; margin-left: 2px;">
                                                    ${{step.action && step.action.text ? `<span><i class="fas fa-keyboard"></i> 内容: "${{step.action.text}}"</span>` : ""}}
                                                    ${{step.action && step.action.point ? `<span style="margin-left:8px;"><i class="fas fa-mouse-pointer"></i> 坐标: [${{step.action.point[0]}}, ${{step.action.point[1]}}]</span>` : ""}}
                                                </div>

                                                ${{step.message ? `<div class="action-msg" style="margin-top: 8px; padding: 8px; background: #f0f7ff; border-radius: 6px; color: #0056b3;">
                                                    <i class="fas fa-info-circle"></i> ${{step.message}}
                                                </div>` : ""}}
                                            </div>
                                        </div>
                                    </div>`;
                            }});
                            document.getElementById('history_list').innerHTML = html;
                            lastHistoryLen = data.history.length;
                        }}
                    }}).catch(e => console.error(e));
                }}
                setInterval(update, 2000);
            </script>
        </body>
        </html>
        """

def run_agent_thread(task, config):
    state['running'] = True
    state['history'] = []
    state['current_task'] = task
    
    try:
        model_cfg = ModelConfig(
            api_key=config['api_key'],
            base_url=config['base_url'],
            model_name=config['model_name'],
            api_type=config['api_type']
        )
        agent_cfg = AgentConfig(
            lang=config['lang'], 
            max_steps=config['max_steps'],
            device_id=config['device_id'] if config['device_id'] else None
        )
        
        agent = PhoneAgent(model_config=model_cfg, agent_config=agent_cfg)
        agent.reset()
        
        # 第一步
        result = agent.step(task)
        _update_step(result)
        
        while not result.finished and len(state['history']) < agent_cfg.max_steps:
            result = agent.step()
            _update_step(result)
            
    except Exception as e:
        state['history'].append({"thinking": f"错误: {str(e)}", "action": None, "message": "已停止", "success": False})
    
    state['running'] = False

def send_termux_notification(title, message):
    """通过 Termux:API 发送系统通知"""
    try:
        # 使用 termux-notification 命令
        subprocess.run([
            "termux-notification",
            "--title", title,
            "--content", message,
            "--id", "autoglm_notify",
            "--group", "autoglm"
        ], capture_output=True)
    except:
        pass

def _update_step(result):
    # 保存截图
    if result.screenshot:
        try:
            img_data = base64.b64decode(result.screenshot)
            with open("latest_screenshot.png", "wb") as f:
                f.write(img_data)
        except: pass
    
    # 添加到历史
    state['history'].append({
        "thinking": result.thinking,
        "action": result.action,
        "message": result.message,
        "success": result.success
    })

    # 发送通知到手机系统
    try:
        step_num = len(state['history'])
        action_desc = result.action.get('action', '进行中') if result.action else '思考中'
        notif_msg = f"Step {step_num}: {action_desc}\n{result.thinking[:60]}..."
        if result.finished:
            notif_msg = f"✅ 任务已完成!\n{result.message}"
        send_termux_notification("🤖 Open-AutoGLM", notif_msg)
    except:
        pass

if __name__ == "__main__":
    PORT = 7860
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("", PORT), SimpleHandler)
    
    print(f"🚀 全功能 Lite 版已启动!")
    print(f"📱 请访问: http://localhost:{PORT}")
    print(f"🛑 按下 Ctrl+C 可停止服务器")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n正在关闭服务器...")
        httpd.shutdown()
        httpd.server_close()
        print("已退出。")
