import cv2
import time
import torch
import edge_tts
import asyncio
import threading
import queue
import tempfile
import os
from playsound import playsound            
from ultralytics import YOLO
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

device = "cuda" if torch.cuda.is_available() else "cpu"
print("Running on:", device)

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://trash-iq-default-rtdb.firebaseio.com'
})
ref = db.reference("trash_iq/ai_result")


TTS_VOICE = "en-US-JennyNeural"

async def generate_audio(text, filepath):
    tts = edge_tts.Communicate(text, voice=TTS_VOICE)
    await tts.save(filepath)

def fetch_audio(text):
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)  # ✅ .mp3
        tmp.close()
        asyncio.run(generate_audio(text, tmp.name))
        return tmp.name
    except Exception as e:
        print(f"TTS generation failed: {e}")
        return None


speech_queue = queue.Queue()
is_speaking   = threading.Event()

def speech_worker():
    while True:
        text = speech_queue.get()

        if text is None:
            break

        is_speaking.set()
        filepath = fetch_audio(text)

        if filepath:
            try:
                playsound(filepath)          # ✅ plays MP3 correctly
            except Exception as e:
                print(f"Playback error: {e}")
            finally:
                try:
                    os.unlink(filepath)
                except:
                    pass

        is_speaking.clear()
        speech_queue.task_done()


speech_thread = threading.Thread(target=speech_worker, daemon=True)
speech_thread.start()


def speak_async(text):
    if not is_speaking.is_set() and speech_queue.empty():
        speech_queue.put(text)


waste_voice_messages = {
    "BIODEGRADABLE": "Biodegradable waste detected. Please dispose it in the biodegradable bin.",
    "CARDBOARD":     "Cardboard waste detected. Please dispose it in the biodegradable bin.",
    "GLASS":         "Glass waste detected. Please dispose it carefully in the glass bin.",
    "METAL":         "Metal waste detected. Please dispose it in the metal bin.",
    "PAPER":         "Paper waste detected. Please dispose it in the biodegradable bin.",
    "PLASTIC":       "Plastic waste detected. Please dispose it in the plastic bin.",
    "E-WASTE":       "Electronic waste detected. Please dispose it in the electronic waste bin.",
    "OTHERS":        "Unknown waste detected. Please dispose it in the general waste bin."
}

model = YOLO("C:/Users/pawan/runs/detect/train8/weights/best.pt")
model.to(device)

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 640)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

CONF_THRESHOLD  = 0.5
VOICE_DELAY     = 3
last_voice_time = {}

while True:

    ret, frame = cap.read()
    if not ret:
        break

    results = model(frame,
                    conf=CONF_THRESHOLD,
                    imgsz=640,
                    device=device,
                    stream=True)

    for r in results:
        for box in r.boxes:

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cls_id     = int(box.cls[0])
            conf       = float(box.conf[0])
            class_name = model.names[cls_id]
            label      = f"{class_name} {conf:.2f}"

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            current_time    = time.time()
            time_since_last = current_time - last_voice_time.get(class_name, 0)

            if time_since_last > VOICE_DELAY:

                voice_message = waste_voice_messages.get(class_name, "Waste detected.")
                speak_async(voice_message)

                data = {
                    "waste_type": class_name,
                    "confidence": conf,
                    "timestamp":  int(current_time)
                }
                ref.set(data)
                print(f"Detected: {class_name} ({conf:.2f}) | Sent to Firebase")

                last_voice_time[class_name] = current_time

    cv2.imshow("TrashIQ Smart Waste Detection", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break


# -----------------------------
# CLEANUP
# -----------------------------
speech_queue.put(None)
speech_thread.join()
cap.release()
cv2.destroyAllWindows()
print("Waste detection system stopped.")