import re
import subprocess
from pathlib import Path

OLLAMA_PATH = Path(r"C:\Users\SINCHANA P\AppData\Local\Programs\Ollama\ollama.exe")
OLLAMA_MODEL = "qwen2.5:7b"


def check_ollama():
    if not OLLAMA_PATH.is_file():
        return False, "Ollama executable was not found."
    try:
        result = subprocess.run([str(OLLAMA_PATH), "list"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False, "Ollama is unavailable."
    if result.returncode != 0 or OLLAMA_MODEL not in result.stdout:
        return False, f"Ollama model {OLLAMA_MODEL} is unavailable."
    return True, "Ollama is ready."


def format_response(response):
    response = re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", response or "")
    response = re.sub(r"[\x00-\x08\x0B-\x1F\x7F]", "", response)
    response = re.sub(r"^\s*(>>>|>)\s*", "", response, flags=re.MULTILINE)
    response = re.sub(r"\s+", " ", response).strip()
    return response or "I'm here to support you."


def generate_response(conversation):
    if not str(conversation).strip():
        return "Please share the counselling conversation first."
    available, message = check_ollama()
    if not available:
        return message
    prompt = f"""You are a compassionate college counsellor. Provide practical, concise support for academic, career, or college-related personal concerns. Do not mention AI.\n\nConversation:\n{conversation}\n\nResponse:"""
    try:
        result = subprocess.run([str(OLLAMA_PATH), "run", OLLAMA_MODEL], input=prompt, text=True, capture_output=True, encoding="utf-8", timeout=90)
        if result.returncode != 0:
            return "Unable to generate a response right now."
        return format_response(result.stdout)
    except subprocess.TimeoutExpired:
        return "Response generation timed out. Please try again."
    except OSError:
        return "Unable to connect to Ollama."
