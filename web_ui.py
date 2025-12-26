import gradio as gr
import os
import time
import base64
import json
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

# 修复代理导致的 502 错误
os.environ["NO_PROXY"] = "localhost,127.0.0.1"

from phone_agent.agent import PhoneAgent, AgentConfig
from phone_agent.model import ModelConfig
from phone_agent.device_factory import get_device_factory

load_dotenv()

CONFIG_FILE = "ui_config.json"

def load_ui_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_ui_config(config_dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)
    except:
        pass

def base64_to_pil(base64_str):
    if not base64_str:
        return None
    image_data = base64.b64decode(base64_str)
    return Image.open(BytesIO(image_data))

class WebUI:
    def __init__(self):
        self.agent = None
        self.history = []

    def start_agent(self, task, api_key, base_url, model_name, api_type, device_id, lang, max_steps):
        # Save config for next time
        save_ui_config({
            "api_key": api_key,
            "base_url": base_url,
            "model_name": model_name,
            "api_type": api_type,
            "device_id": device_id,
            "lang": lang,
            "max_steps": max_steps
        })

        # Initialize Config
        model_config = ModelConfig(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            api_type=api_type
        )
        agent_config = AgentConfig(
            device_id=device_id if device_id else None,
            lang=lang,
            max_steps=int(max_steps),
            verbose=True
        )
        
        self.agent = PhoneAgent(model_config=model_config, agent_config=agent_config)
        self.agent.reset()
        
        step_idx = 0
        self.history = []
        
        yield (
            gr.update(value="### 🔄 正在初始化设备...", visible=True),
            None,
            gr.update(value=self._format_history(), visible=True)
        )

        try:
            # First step
            result = self.agent.step(task)
            img = base64_to_pil(result.screenshot)
            self._add_to_history(step_idx, result)
            
            yield (
                gr.update(value=f"### 🚀 第 {step_idx+1} 步执行中..."),
                img,
                gr.update(value=self._format_history())
            )

            while not result.finished and step_idx < agent_config.max_steps:
                step_idx += 1
                result = self.agent.step()
                img = base64_to_pil(result.screenshot)
                self._add_to_history(step_idx, result)
                
                yield (
                    gr.update(value=f"### 🚀 第 {step_idx+1} 步执行中..."),
                    img,
                    gr.update(value=self._format_history())
                )
                
            final_msg = result.message if result.message else "任务完成"
            yield (
                gr.update(value=f"### ✅ 任务结束: {final_msg}"),
                img,
                gr.update(value=self._format_history())
            )

        except Exception as e:
            yield (
                gr.update(value=f"### ❌ 运行出错: {str(e)}"),
                None,
                gr.update(value=self._format_history())
            )

    def _add_to_history(self, step, result):
        self.history.append({
            "step": step + 1,
            "thinking": result.thinking,
            "action": result.action,
            "message": result.message
        })

    def _format_history(self):
        md = ""
        for item in reversed(self.history):
            md += f"### 📍 Step {item['step']}\n"
            md += f"**🤔 思考:** {item['thinking']}\n\n"
            if item['action']:
                md += f"**🎯 动作:** `{item['action'].get('action')}`\n"
                md += f"```json\n{json.dumps(item['action'], ensure_ascii=False, indent=2)}\n```\n"
            if item['message']:
                md += f"**💬 结果:** {item['message']}\n"
            md += "---\n"
        return md

def create_ui():
    ui_logic = WebUI()
    cached_config = load_ui_config()
    
    # 修复 Gradio 6.0 警告：将 theme 移至 launch
    js_load_localstorage = """
    function() {
        const fields = ['api_key', 'base_url', 'model_name', 'api_type', 'device_id', 'lang', 'max_steps'];
        fields.forEach(id => {
            const saved = localStorage.getItem('autoglm_gradio_' + id);
            if (saved) {
                const el = document.querySelector(`#${id} textarea, #${id} input, #${id} select`);
                if (el) {
                    // 模拟输入触发 Gradio 后端更新
                    el.value = saved;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }
            
            // 监听变化并保存
            document.querySelector(`#${id}`).addEventListener('input', (e) => {
                const val = e.target.value;
                if (val !== undefined) {
                    localStorage.setItem('autoglm_gradio_' + id, val);
                }
            }, true);
        });
    }
    """
    with gr.Blocks(title="Open-AutoGLM Web UI", js=js_load_localstorage) as demo:
        gr.Markdown("# 📱 Open-AutoGLM 智能手机助手")
        
        with gr.Row():
            # Sidebar for configuration
            with gr.Column(scale=1):
                gr.Markdown("### ⚙️ 配置中心")
                api_key = gr.Textbox(
                    label="API Key", 
                    value=cached_config.get("api_key", os.getenv("OPENAI_API_KEY", "")),
                    type="password",
                    elem_id="api_key"
                )
                base_url = gr.Textbox(
                    label="Base URL", 
                    value=cached_config.get("base_url", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")),
                    elem_id="base_url"
                )
                model_name = gr.Textbox(
                    label="Model Name", 
                    value=cached_config.get("model_name", os.getenv("MODEL_NAME", "gpt-4o")),
                    elem_id="model_name"
                )
                api_type = gr.Dropdown(
                    choices=["openai", "gemini"], 
                    value=cached_config.get("api_type", "openai"), 
                    label="API Type",
                    elem_id="api_type"
                )
                device_id = gr.Textbox(
                    label="Device ID (Optional)", 
                    value=cached_config.get("device_id", ""),
                    placeholder="ADB/HDC 设备 ID",
                    elem_id="device_id"
                )
                lang = gr.Radio(
                    choices=["cn", "en"], 
                    value=cached_config.get("lang", "cn"), 
                    label="语言 / Language",
                    elem_id="lang"
                )
                max_steps = gr.Slider(
                    minimum=1, 
                    maximum=50, 
                    value=cached_config.get("max_steps", 15), 
                    step=1, 
                    label="最大步数",
                    elem_id="max_steps"
                )
            
            # Main area
            with gr.Column(scale=2):
                task_input = gr.Textbox(
                    label="📝 任务描述", 
                    placeholder="请输入你想让 Agent 完成的任务，例如：'查看今天的天气'",
                    lines=3
                )
                run_btn = gr.Button("🚀 开始运行", variant="primary")
                
                status_md = gr.Markdown("### ⏳ 等待任务开始...", visible=True)
                
                with gr.Row():
                    with gr.Column(scale=1):
                        screen_output = gr.Image(label="实时画面", type="pil")
                    with gr.Column(scale=1):
                        history_output = gr.Markdown("### 📜 运行日志", visible=True)
                        
        run_btn.click(
            ui_logic.start_agent,
            inputs=[task_input, api_key, base_url, model_name, api_type, device_id, lang, max_steps],
            outputs=[status_md, screen_output, history_output]
        )

    return demo

if __name__ == "__main__":
    demo = create_ui()
    # 允许外部访问，theme 参数移到了这里
    demo.launch(
        server_name="0.0.0.0", 
        server_port=7860, 
        share=False,
        theme=gr.themes.Soft()
    )
