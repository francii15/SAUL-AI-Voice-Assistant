"""Local deployment preflight. Never prints API keys or sends transcripts.
--models may download/cache models; --online sends one small test question to Groq.
--camera briefly opens the camera and discards a single test frame.
"""
import argparse
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', action='store_true')
    parser.add_argument('--online', action='store_true')
    parser.add_argument('--camera', action='store_true')
    parser.add_argument('--device', type=int)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    results = []
    def report(name, ok, detail=''):
        results.append({'check': name, 'passed': bool(ok), 'detail': detail})
        print(('PASS' if ok else 'FAIL') + ' | ' + name + (': '+detail if detail else ''), flush=True)
    report('Windows', os.name == 'nt', sys.platform)
    report('Python 3.11', sys.version_info[:2] == (3, 11), sys.version.split()[0])
    try:
        compile((root/'assistant.py').read_text(encoding='utf-8'), 'assistant.py', 'exec')
        report('Source syntax', True)
    except Exception as error:
        report('Source syntax', False, type(error).__name__)
    modules = [('numpy','numpy'), ('torch','torch'), ('sounddevice','sounddevice'),
               ('comtypes','comtypes'), ('openwakeword','openwakeword'), ('onnxruntime','onnxruntime'),
               ('faster_whisper','faster-whisper'), ('silero_vad','silero-vad'),
               ('sentence_transformers','sentence-transformers'), ('dotenv','python-dotenv'),
               ('langchain_groq','langchain-groq'), ('langgraph.graph','langgraph'),
               ('groq','groq'), ('yt_dlp','yt-dlp'), ('cv2','opencv-python'), ('tkinter',None)]
    for module, distribution in modules:
        try:
            importlib.import_module(module)
            version = importlib.metadata.version(distribution) if distribution else 'built in'
            report('Import '+module, True, version)
        except Exception as error:
            report('Import '+module, False, type(error).__name__)
    wake = root/'hey_saul.onnx'
    report('Custom wake model file', wake.is_file() and wake.stat().st_size > 0,
           'hey_saul.onnx (retain your existing trained file)')
    try:
        from dotenv import dotenv_values
        config = dotenv_values(root/'.env', encoding='utf-8-sig')
        key = (config.get('GROQ_API_KEY') or os.environ.get('GROQ_API_KEY') or '').strip()
        report('Groq key configured', bool(key), 'value not displayed')
    except Exception as error:
        report('Groq key configured', False, type(error).__name__)
    try:
        for name in ['summaries','notes','photos']:
            folder = root/name
            folder.mkdir(exist_ok=True)
            with tempfile.TemporaryFile(dir=folder) as probe: probe.write(b'test')
        report('Output folders writable', True)
    except Exception as error:
        report('Output folders writable', False, type(error).__name__)
    if os.name == 'nt':
        try:
            import assistant
            import numpy as np
            import sounddevice as sd
            sd.check_input_settings(device=args.device, channels=1, dtype='int16', samplerate=16000)
            sd.check_output_settings(channels=1, dtype='float32', samplerate=22050)
            report('Audio device settings', True, 'device settings checked; no audio recorded')
            voices = assistant.available_voices()
            report('Default George voice', any('george' in name.lower() for name,_ in voices),
                   'Use assistant.py --list-voices for alternatives')
            if wake.is_file():
                model = assistant.Model(wakeword_models=[str(wake)], inference_framework='onnx')
                prediction = model.predict(np.zeros(1280, dtype=np.int16))
                report('Wake model inference', bool(prediction), 'synthetic silence only')
            if args.models:
                assistant.torch.set_num_threads(2)
                assistant.fast_asr_model()
                assistant.lecture_models()
                assistant.init_semantic_matcher()
                report('Speech and semantic models loaded', assistant._SEMANTIC is not None)
            if args.online:
                answer = assistant.language_graph().invoke({'mode':'question','text':'Reply with the word READY.'})['answer']
                report('Groq generation through LangGraph', isinstance(answer,str) and bool(answer.strip()))
            if args.camera:
                import cv2
                camera = cv2.VideoCapture(0)
                try:
                    ok, frame = camera.read()
                    report('Camera test frame', ok and frame is not None, 'test frame discarded')
                finally:
                    camera.release()
        except Exception as error:
            report('Runtime smoke check', False, type(error).__name__)
    path = root/'preflight-results.json'
    path.write_text(json.dumps({'checks':results, 'live_voice_acceptance':'pending manual check'}, indent=2), encoding='utf-8')
    if all(item['passed'] for item in results):
        # Record installed names/versions only: never pip-freeze URLs or credentials.
        versions = sorted({f"{d.metadata['Name']}=={d.version}" for d in importlib.metadata.distributions() if d.metadata['Name']})
        (root/'environment-snapshot.txt').write_text('\n'.join(versions)+'\n', encoding='utf-8')
        print('Preflight passed. Complete LIVE_TEST.md before marking the release accepted.')
        return 0
    print('Preflight failed. Review the FAIL lines before the live test.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
