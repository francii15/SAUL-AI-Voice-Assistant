from pathlib import Path
import time

import numpy as np
import sounddevice as sd
from openwakeword.model import Model


MODEL_PATH = Path(__file__).parent / "hey_saul.onnx"
SAMPLE_RATE = 16000
CHUNK_SIZE = 1280
THRESHOLD = 0.50

if not MODEL_PATH.exists():
    raise FileNotFoundError(f"Model not found: {MODEL_PATH}")

wake_model = Model(
    wakeword_models=[str(MODEL_PATH)],
    inference_framework="onnx"
)

print("Listening for your wake word...")
print("Say: Hey Saul")
print("Press Ctrl+C to stop.")

last_detection = 0

try:
    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=CHUNK_SIZE,
        dtype="int16",
        channels=1
    ) as microphone:

        while True:
            audio_bytes, overflowed = microphone.read(CHUNK_SIZE)

            if overflowed:
                continue

            audio = np.frombuffer(audio_bytes, dtype=np.int16)
            scores = wake_model.predict(audio)

            score = max(scores.values())

            if score >= THRESHOLD and time.time() - last_detection > 2:
                print(f"Wake word detected! Score: {score:.3f}")
                last_detection = time.time()

except KeyboardInterrupt:
    print("\nTest stopped.")