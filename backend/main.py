import os
import sys
import time
import subprocess
import webbrowser
import datetime
import urllib.parse
import threading
import asyncio
import json

try:
    import pyttsx3
    import speech_recognition as sr
    import webview
except ImportError:
    print("Missing dependencies. Please run 'pip install -r requirements.txt'")
    sys.exit(1)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from config_manager import load_config
from diagnostics import run_diagnostics

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables to track state
connected_clients = []
assistant_state = {
    "status": "Initializing...",
    "last_command": ""
}
desktop_window = None

async def broadcast_state(status_update=None, last_command=None):
    if status_update:
        assistant_state["status"] = status_update
    if last_command is not None:
        assistant_state["last_command"] = last_command

    message = json.dumps(assistant_state)
    for client in connected_clients:
        try:
            await client.send_text(message)
        except:
            pass

def broadcast_sync(status_update=None, last_command=None):
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast_state(status_update, last_command))
    except RuntimeError:
        pass # No event loop

# Initialize TTS
try:
    tts_engine = pyttsx3.init()
except Exception as e:
    print(f"Failed to initialize TTS engine: {e}")
    sys.exit(1)

def speak(text):
    """Speaks the given text using pyttsx3."""
    print(f"Sundar: {text}")
    broadcast_sync(status_update=f"Speaking: {text}")
    try:
        tts_engine.say(text)
        tts_engine.runAndWait()
    except Exception as e:
        print(f"TTS Error: {e}")
    broadcast_sync(status_update="Listening...")

def listen(recognizer, microphone):
    """Listens to microphone and returns transcribed text."""
    try:
        with microphone as source:
            print("Listening...")
            broadcast_sync(status_update="Listening...")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
        
        print("Recognizing...")
        broadcast_sync(status_update="Transcribing...")
        text = recognizer.recognize_google(audio)
        print(f"User: {text}")
        broadcast_sync(last_command=text)
        return text.lower()
    except sr.WaitTimeoutError:
        return ""
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        speak("I'm having trouble connecting to the speech service.")
        print(f"Speech Recognition Error: {e}")
        return ""
    except Exception as e:
        print(f"Microphone Error: {e}")
        return ""

def handle_open_app(command, config):
    apps = config.get("applications", {})
    app_to_open = None
    app_name_spoken = None
    
    for app_name, app_path in apps.items():
        if app_name.lower() in command:
            app_to_open = app_path
            app_name_spoken = app_name
            break
            
    if app_to_open:
        try:
            subprocess.Popen(app_to_open)
            speak(f"Opening {app_name_spoken}.")
        except Exception as e:
            speak(f"I couldn't open {app_name_spoken}.")
    else:
        speak("I couldn't find that application in your configuration.")

def handle_open_file(command):
    target = ""
    if "open" in command:
        target = command.split("open", 1)[1].strip()
    elif "show" in command:
        target = command.split("show", 1)[1].strip()
        
    if not target:
        speak("I am not sure what file to open.")
        return

    try:
        os.startfile(target)
        speak(f"Opening {target}.")
    except Exception as e:
        speak(f"I encountered an error trying to open {target}.")

def handle_play_music(command):
    query = command.split("play", 1)[1].strip()
    if not query:
        speak("I am not sure what to play.")
        return
        
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.youtube.com/results?search_query={encoded_query}"
        webbrowser.open(url)
        speak(f"Playing {query} on YouTube.")
    except Exception as e:
        speak("I encountered an error trying to search YouTube.")

def handle_time_date(command):
    now = datetime.datetime.now()
    if "time" in command:
        time_str = now.strftime("%I:%M %p").replace("AM", "in the morning").replace("PM", "in the afternoon")
        speak(f"It is {time_str}.")
    elif "date" in command:
        date_str = now.strftime("%A, %B %d, %Y")
        speak(f"Today is {date_str}.")

def handle_diagnostics():
    speak("Running system diagnostics.")
    messages = run_diagnostics()
    for msg in messages:
        speak(msg)

def voice_assistant_loop():
    config = load_config()
    wake_word = config.get("preferences", {}).get("wake_word", "sundar").lower()
    
    try:
        import pyaudio
    except ImportError:
        print("pyaudio is not installed.")
        broadcast_sync(status_update="Microphone dependencies missing.")
        return

    recognizer = sr.Recognizer()
    try:
        microphone = sr.Microphone()
    except Exception as e:
        print(f"Could not initialize microphone: {e}")
        broadcast_sync(status_update="Could not connect to microphone.")
        return

    # Wait for the server to be ready before speaking
    time.sleep(2)
    speak("Sundar is online and ready.")
    
    while True:
        command = listen(recognizer, microphone)
        
        if not command:
            continue
            
        if wake_word not in command:
            continue
            
        command = command.replace(wake_word, "").strip()
        
        if not command:
            speak("Yes?")
            continue
            
        # Intent Dispatcher
        if any(word in command for word in ["exit", "quit", "goodbye", "bye"]):
            speak("Goodbye.")
            if desktop_window:
                desktop_window.destroy()
            os._exit(0)
            
        elif any(phrase in command for phrase in ["open interface", "show interface", "open frontend"]):
            speak("The interface is already running.")
            if desktop_window:
                desktop_window.restore()
            
        elif "play" in command:
            handle_play_music(command)
            
        elif "time" in command or "date" in command:
            handle_time_date(command)
            
        elif any(phrase in command for phrase in ["scan", "security check", "check my system"]):
            handle_diagnostics()
            
        elif "open" in command and any(app in command for app in config.get("applications", {})):
            handle_open_app(command, config)
            
        elif "open" in command or "show" in command:
            handle_open_file(command)
            
        else:
            speak("I'm not sure how to handle that yet.")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        # Send initial state
        await websocket.send_text(json.dumps(assistant_state))
        while True:
            data = await websocket.receive_text()
            pass
    except WebSocketDisconnect:
        connected_clients.remove(websocket)

# Serve the static files from frontend/dist
dist_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(dist_dir):
    app.mount("/", StaticFiles(directory=dist_dir, html=True), name="static")

def run_fastapi_server():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

if __name__ == "__main__":
    # 1. Start FastAPI server in a background thread
    server_thread = threading.Thread(target=run_fastapi_server, daemon=True)
    server_thread.start()

    # 2. Start Voice Assistant in a background thread
    voice_thread = threading.Thread(target=voice_assistant_loop, daemon=True)
    voice_thread.start()

    # 3. Start PyWebview GUI on the main thread
    # Wait a tiny bit to ensure FastAPI is listening before loading the URL
    time.sleep(1)
    desktop_window = webview.create_window(
        title="Sundar AI",
        url="http://127.0.0.1:8000",
        width=450,
        height=550,
        resizable=False,
        frameless=False,
        background_color='#0f172a'
    )
    # Start the desktop app loop (blocking)
    webview.start()
