"""System prompts and tool descriptions for the AI agent."""

from datetime import datetime
from phone_agent.config.prompts_zh import SYSTEM_PROMPT as SYSTEM_PROMPT_ZH
from phone_agent.config.prompts_en import SYSTEM_PROMPT as SYSTEM_PROMPT_EN

# Extract tool descriptions to separate strings to keep prompts clean
TOOL_DESCRIPTIONS_ZH = """
操作指令及其作用如下：
- do(action="Tap", element=[x,y])
    点击屏幕上的特定点。坐标系统从左上角 (0,0) 开始到右下角（999,999)。
- do(action="Launch", app="xxx")
    启动目标app的操作。
- do(action="Type", text="xxx")  
    在当前聚焦的输入框中输入文本。
- do(action="Type_Name", text="xxx")  
    输入人名的操作，基本功能同Type。
- do(action="Interact")  
    当有多个满足条件的选项时而触发的交互操作，询问用户如何选择。
- do(action="Swipe", start=[x1,y1], end=[x2,y2])  
    滑动操作，通过从起始坐标拖动到结束坐标来执行滑动手势。
- do(action="Note", message="True")  
    记录当前页面内容以便后续总结。
- do(action="Call_API", instruction="xxx")  
    总结或评论内容。
- do(action="Long Press", element=[x,y])  
    长按操作。
- do(action="Double Tap", element=[x,y])  
    双击操作。
- do(action="Take_over", message="xxx")  
    接管操作，验证阶段需要用户协助。
- do(action="Back")  
    返回操作。
- do(action="Home") 
    回到系统桌面的操作。
- do(action="Wait", duration="x seconds")  
    等待页面加载。
- finish(message="xxx")  
    结束任务的操作。
"""

TOOL_DESCRIPTIONS_EN = """
Available actions:
- do(action="Tap", element=[x,y])
- do(action="Launch", app="Settings")
- do(action="Type", text="Hello")
- do(action="Swipe", start=[x1,y1], end=[x2,y2])
- do(action="Back")
- do(action="Home")
- finish(message="Task completed.")
"""

# Format instructions for non-native tool calling models
FORMAT_INSTRUCTIONS_ZH = """
你必须严格按照要求输出以下格式：
<think>{think}</think>
<answer>{action}</answer>

其中：
- {think} 是对你为什么选择这个操作的简短推理说明。
- {action} 是本次执行的具体操作指令。
"""

FORMAT_INSTRUCTIONS_EN = """
# Output Format
Your response format must be structured as follows:

Think first: Use <think>...</think> to analyze the current screen, identify key elements, and determine the most efficient action.
Provide the action: Use <answer>...</answer> to return a single line of pseudo-code representing the operation.

Your output should STRICTLY follow the format:
<think>
[Your thought]
</think>
<answer>
[Your operation code]
</answer>
"""

def get_system_prompt(lang: str = "cn", api_type: str = "openai") -> str:
    """Get the system prompt for the specified language."""
    prompt = SYSTEM_PROMPT_ZH if lang == "cn" else SYSTEM_PROMPT_EN
    
    # Gemini uses native Tool Calling and native Thought, so we don't need text descriptions.
    if api_type == "gemini":
        return prompt
        
    tools = TOOL_DESCRIPTIONS_ZH if lang == "cn" else TOOL_DESCRIPTIONS_EN
    formats = FORMAT_INSTRUCTIONS_ZH if lang == "cn" else FORMAT_INSTRUCTIONS_EN
    return prompt + "\n" + formats + "\n" + tools

def get_messages(lang: str = "cn") -> dict[str, str]:
    """Get UI messages for the specified language."""
    if lang == "cn":
        return {
            "thinking": "思考过程",
            "action": "执行动作",
            "task_completed": "任务完成",
            "done": "完成",
        }
    return {
        "thinking": "Thinking Process",
        "action": "Executing Action",
        "task_completed": "Task Completed",
        "done": "Done",
    }
