"""Hardware-free regression checks against the actual assistant.py functions.
Uses AST loading to avoid Windows/ML imports; audio, GUI and cloud are simulated.
Run: python test_regression.py [--source path/to/assistant.py]
"""
import argparse
import ast
import contextlib
from collections import deque
from datetime import datetime
from difflib import SequenceMatcher
import io
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import threading
import time
import types
import unittest
from unittest.mock import patch
import urllib
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import numpy as np
SOURCE = Path(__file__).with_name('assistant.py')

def load_functions():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.Assign))]
    env = dict(globals())
    env.update(__file__=str(SOURCE), nullcontext=contextlib.nullcontext)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), env)
    return env

class Regression(unittest.TestCase):

    def setUp(self):
        self.g = load_functions()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.g['__file__'] = str(Path(self.temp.name) / 'assistant.py')
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def test_question_followups_and_sources(self):
        g = self.g
        for phrase in ['Can you explain it briefly?', 'Could you give me an example?', 'Tell me more', 'Explain it in detail', 'Make it simpler', 'Show me sources', 'What is machine learning?']:
            self.assertTrue(g['question_request'](phrase), phrase)
            self.assertIsNone(g['command_intent'](phrase), phrase)
        self.assertFalse(g['question_request']('open something strange'))
        calls = []

        class Graph:

            def invoke(self, state):
                calls.append(state)
                return {'answer': 'An explanation.'}
        g['language_graph'] = lambda: Graph()
        g['question_reading_links'] = lambda topic: 'Related link for ' + topic
        g['answer_general_question']('What is machine learning?')
        g['execute_command']('Can you explain it briefly?')
        self.assertIn('machine learning', calls[-1]['context'])
        self.assertEqual(len(list((Path(self.temp.name) / 'questions').glob('*.txt'))), 2)
        g['answer_general_question']('What is India?')
        self.assertEqual(calls[-1]['text'], 'What is India?')
        g['language_graph'] = lambda: (_ for _ in ()).throw(RuntimeError())
        before = list(g['_QA_HISTORY'])
        g['answer_general_question']('Explain it briefly')
        self.assertEqual(before, g['_QA_HISTORY'])

    def test_question_source_failure_fallback(self):
        with patch.object(urllib.request, 'urlopen', side_effect=OSError('offline')):
            result = self.g['question_reading_links']('machine learning')
        self.assertIn('not a verified source', result)
        self.assertIn('search=machine%20learning', result)

    def test_saved_knowledge_lifecycle(self):
        base = Path(self.temp.name)
        folder = base / 'summaries'
        folder.mkdir()
        path = folder / 'ACID_20260919_120000_transcript.txt'
        path.write_text('Atomicity means a transaction completes entirely or not at all. ' * 400, encoding='utf-8')
        (folder / 'Movies_summary.txt').write_text('Cinema budgets and audience ratings.', encoding='utf-8')
        (base / '.env').write_text('Atomicity PRIVATE_SECRET', encoding='utf-8')
        hits = self.g['retrieve_saved_knowledge']('What did my saved lecture say about atomicity?')
        self.assertEqual(len(hits), 1)
        self.assertLessEqual(len(hits[0]['excerpt'].split()), 220)
        self.assertNotIn('PRIVATE_SECRET', str(hits))
        self.assertTrue((base / 'saul_knowledge.sqlite3').exists())
        fresh = load_functions()
        fresh['__file__'] = self.g['__file__']
        self.assertEqual(len(fresh['retrieve_saved_knowledge']('atomicity')), 1)
        path.write_text('Durability preserves committed transactions.', encoding='utf-8')
        self.assertEqual(self.g['retrieve_saved_knowledge']('atomicity'), [])
        self.assertEqual(len(self.g['retrieve_saved_knowledge']('durability')), 1)
        path.unlink()
        self.assertEqual(self.g['retrieve_saved_knowledge']('durability'), [])
        self.assertEqual(self.g['retrieve_saved_knowledge']('what did my lecture say'), [])

    def test_five_exchanges_and_retrieval_context(self):
        g = self.g
        calls = []

        class Graph:

            def invoke(self, state):
                calls.append(state)
                return {'answer': 'A useful answer.'}
        g['language_graph'] = lambda: Graph()
        g['question_reading_links'] = lambda topic: 'Search link'
        g['retrieve_saved_knowledge'] = lambda query: []
        for i in range(7):
            g['answer_general_question'](f'What is topic {i}?')
        self.assertEqual(len(g['_QA_HISTORY']), 5)
        g['answer_general_question']('Explain it briefly')
        self.assertEqual(len(json.loads(calls[-1]['context'])), 5)
        previous = len(calls)
        self.assertIn("couldn't find", g['answer_general_question']('What did my saved lecture say about acid?'))
        self.assertEqual(len(calls), previous)
        g['retrieve_saved_knowledge'] = lambda query: [{'source': 'summaries/ACID.txt', 'excerpt': 'Atomicity', 'kind': 'lecture transcript'}]
        g['answer_general_question']('What did my saved lecture say about acid?')
        self.assertIn('[S1]', calls[-1]['memory'])
        self.assertIn('Atomicity', calls[-1]['memory'])

    def test_natural_followups_resolved_topic_and_clarification(self):
        g = self.g
        calls, topics = ([], [])

        class Graph:

            def invoke(self, state):
                calls.append(state)
                return {'answer': 'Topic: Machine learning\nHere are the types and an explanation.'}
        g['language_graph'] = lambda: Graph()
        g['question_reading_links'] = lambda topic: topics.append(topic) or 'Related reading'
        g['retrieve_saved_knowledge'] = lambda text: self.fail('General Q&A should not retrieve unrelated files')
        for phrase in ['what is machine learning?', 'can you brief it and explain what are the types of machine learning?', 'can you breathe it?', 'explain in detail', 'I am confused; walk me through that with a practical example']:
            reply, leave = g['execute_command'](phrase)
            self.assertIn('types', reply)
            self.assertFalse(leave)
        self.assertEqual(len(calls), 5)
        self.assertIn('Machine learning', calls[-1]['context'])
        self.assertEqual(set(topics), {'Machine learning'})
        self.assertNotIn('Topic:', reply)
        before = list(g['_QA_HISTORY'])
        g['language_graph'] = lambda: types.SimpleNamespace(invoke=lambda state: {'answer': 'CLARIFY: Which topic do you mean?'})
        self.assertEqual(g['answer_general_question']('something unclear'), 'Which topic do you mean?')
        self.assertEqual(before, g['_QA_HISTORY'])

    def test_qa_identical_timestamp_saves(self):
        g = self.g
        fixed = datetime(2026, 9, 19, 17, 47, 50)
        g['datetime'] = types.SimpleNamespace(now=lambda: fixed)
        g['language_graph'] = lambda: types.SimpleNamespace(invoke=lambda state: {'answer': 'Topic: Machine learning\nAnswer for ' + state['text']})
        g['question_reading_links'] = lambda topic: 'Related reading'
        g['answer_general_question']('What is machine learning?')
        g['execute_command']('Can you explain it briefly?')
        files = list((Path(self.temp.name) / 'questions').glob('*.txt'))
        self.assertEqual(len(files), 2)
        contents = [p.read_text(encoding='utf-8') for p in files]
        self.assertTrue(any(('Question: What is machine learning?' in c for c in contents)))
        self.assertTrue(any(('Question: Can you explain it briefly?' in c for c in contents)))

    def test_general_answer_interruptible_playback(self):
        g = self.g
        g['answer_general_question'] = lambda text: 'An answer about machine learning.'
        reply, leave = g['execute_command']('What is machine learning?')
        self.assertTrue(g['_REPLY_INTERRUPTIBLE'])
        calls = []
        engine = types.SimpleNamespace(say=lambda *args, **kwargs: calls.append((args, kwargs)))
        with patch.object(time, 'sleep'):
            g['speak'](engine, reply, interruptible=g['_REPLY_INTERRUPTIBLE'], device=3)
        self.assertEqual(calls[0][1], {'interruptible': True, 'device': 3})
        for phrase in ['stop', 'enough', 'pause it', 'can you stop answering', 'please stop talking', "that's enough", 'no need to continue']:
            self.assertTrue(g['is_reading_stop'](phrase), phrase)
        for phrase in ['do not stop', "don't stop talking", 'the bus stop is ahead']:
            self.assertFalse(g['is_reading_stop'](phrase), phrase)

    def test_close_commands_and_target_scope(self):
        g = self.g
        for text, intent in [('quit Chrome', 'close_chrome'), ('shut the browser', 'close_chrome'), ("I'm done with YouTube", 'close_youtube'), ('please close the YouTube tab in Chrome', 'close_youtube')]:
            self.assertEqual(g['command_intent'](text), intent)
        for text in ['do not close Chrome', "don't close YouTube", 'how do I close Chrome', 'close it']:
            self.assertIsNone(g['close_command_intent'](text))
        g['os'] = types.SimpleNamespace(name='nt')
        g['chrome_windows'] = lambda: [(1, 'Docs - Google Chrome'), (2, 'Music - YouTube - Google Chrome')]
        closed = []
        g['close_visible_youtube_tab'] = lambda hwnd: closed.append(hwnd) or True
        self.assertIn('requested', g['close_browser_target']('close_youtube'))
        self.assertEqual(closed, [2])
        g['request_chrome_window_close'] = lambda hwnd: closed.append(hwnd) or True
        g['close_browser_target']('close_chrome')
        self.assertEqual(closed, [2, 1, 2])
        g['chrome_windows'] = lambda: [(1, 'Docs - Google Chrome')]
        self.assertIn('Select the YouTube tab', g['close_browser_target']('close_youtube'))
        self.assertEqual(closed, [2, 1, 2])

    def test_background_model_load_reuses_first_model(self):
        g=self.g
        entered=threading.Event()
        release=threading.Event()
        builds=[]
        def fake_model(*args,**kwargs):
            builds.append(1)
            entered.set()
            self.assertTrue(release.wait(2))
            return object()
        with patch.dict(sys.modules,{'faster_whisper':types.SimpleNamespace(WhisperModel=fake_model)}):
            worker=g['warm_models_in_background'](False)
            self.assertTrue(entered.wait(2))
            result=[]
            second=threading.Thread(target=lambda:result.append(g['fast_asr_model']()))
            second.start()
            release.set()
            worker.join(2);second.join(2)
            self.assertFalse(worker.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(len(builds),1)
            self.assertIs(result[0],g['fast_asr_model']())

    def test_voice_energy_uses_output_audio(self):
        energy=self.g['voice_energy']
        self.assertEqual(energy(np.zeros(1600)),0)
        self.assertEqual(energy(np.array([])),0)
        self.assertGreater(energy(np.full((1600,2),.1)),energy(np.full(1600,.01)))
        self.assertEqual(energy(np.ones(1600)),1)
        with patch.dict(os.environ,{'SAUL_DESKTOP_EVENTS':'1'}):
            events=[]
            self.g['ui_event']=lambda kind,**data:events.append((kind,data))
            meter=self.g['start_voice_meter'](np.ones(1600)*.1,16000)
            meter[1].join(timeout=1)
            self.g['finish_voice_meter'](meter)
            self.assertTrue(events)
            self.assertTrue(all(e[1]['level']==.5 for e in events))
            self.assertFalse(meter[1].is_alive())

    def test_desktop_voice_cancel_and_reuse(self):
        g=self.g
        calls=[]
        g['sd']=types.SimpleNamespace(stop=lambda:calls.append('stop'))
        g['cancel_desktop_voice']()
        self.assertEqual(calls,[])
        speaker=object.__new__(g['Speaker'])
        def cancelled(*args):
            self.assertTrue(g['_VOICE_ACTIVE'].is_set())
            g['cancel_desktop_voice']()
            return g['_VOICE_CANCEL'].is_set()
        speaker._say_audio=cancelled
        self.assertTrue(speaker.say('An answer'))
        self.assertEqual(calls,['stop'])
        self.assertFalse(g['_VOICE_ACTIVE'].is_set())
        speaker._say_audio=lambda *args:g['_VOICE_CANCEL'].is_set()
        self.assertFalse(speaker.say('Next answer'))
        def failed(*args):raise RuntimeError('audio unavailable')
        speaker._say_audio=failed
        with self.assertRaises(RuntimeError):speaker.say('Failure')
        self.assertFalse(g['_VOICE_ACTIVE'].is_set())

    def test_desktop_clean_events_and_hyperlinks(self):
        from urllib.parse import urlparse
        source = Path(__file__).with_name('saul_desktop.py')
        tree = ast.parse(source.read_text(encoding='utf-8'))
        env = dict(re=re, json=json, urlparse=urlparse, webbrowser=webbrowser, tk=types.SimpleNamespace(Canvas=object))
        nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), env)
        for line in ['Loading model weights...', 'Timing | LLM request: 2s', 'Matched action: time', 'Traceback: detail']:
            self.assertIsNone(env['read_ui_event'](line))
        self.assertIsNone(env['read_ui_event']('SAUL_EVENT:broken'))
        event = env['read_ui_event']('SAUL_EVENT:' + json.dumps({'kind': 'answer', 'text': 'Answer', 'reading': 'https://example.org'}))
        self.assertEqual(event['text'], 'Answer')
        self.assertFalse(env['safe_web_link']('javascript:alert(1)'))
        ui = object.__new__(env['Desktop'])
        ui.link_count = 0

        class Text:

            def __init__(self):
                self.content = ''
                self.bindings = []

            def insert(self, position, text, *args):
                self.content += text

            def tag_configure(self, *args, **kwargs):
                pass

            def tag_bind(self, tag, event, callback):
                self.bindings.append((event, callback))
        ui.log = Text()
        ui.insert_links('Read [Machine learning](https://example.org/ml) next.')
        self.assertEqual(ui.log.content, 'Read Machine learning next.')
        click = next((callback for event, callback in ui.log.bindings if event == '<Button-1>'))
        with patch.object(webbrowser, 'open_new_tab') as open_tab:
            click(None)
            open_tab.assert_called_once_with('https://example.org/ml')

    def test_phrase_catalog_and_routing(self):
        self.g['_READ_PROGRESS'] = {'index': 1}
        for intent in self.g['COMMAND_BASES']:
            phrases = self.g['command_examples'](intent)
            self.assertEqual(len(set(phrases)), 100)
            if intent == 'stop_reading':
                continue
            for phrase in phrases:
                with self.subTest(intent=intent, phrase=phrase):
                    self.assertEqual(self.g['command_intent'](phrase), intent)

    def test_user_reported_commands(self):
        self.g['_READ_PROGRESS'] = {'index': 1}
        self.g['_READ_CHOICES'] = [1, 2, 3]
        cases = {'pick up where you left': 'resume_explanation', 'keep option 3': 'read_explanation', 'the third one': 'read_explanation', 'please start the lecture for me': 'lecture', 'read healing of tuba colossus patient through prayer and positive thinking': 'read_explanation', 'take a photograph': 'photo'}
        for text, expected in cases.items():
            self.assertEqual(self.g['command_intent'](text), expected, text)
        for text in ['do not open chrome', "don't resume reading", 'never take a photo']:
            self.assertIsNone(self.g['command_intent'](text), text)
        self.assertIsNone(self.g['command_intent']('unrelated nonsense zebra'))

    def test_songs_and_explanations(self):
        for text, expected in [('open youtube and play the song called Yellow by Coldplay', 'Yellow by Coldplay'), ('please open YouTube in Chrome and then play Yesterday', 'Yesterday'), ("play Don't Stop Me Now", "Don't Stop Me Now")]:
            self.assertEqual(self.g['command_intent'](text), 'song')
            self.assertEqual(self.g['song_request'](text), expected)
        self.assertIsNone(self.g['command_intent']('do not play Yesterday'))
        self.assertEqual(self.g['command_intent']('play the explanation about India'), 'read_explanation')
        self.assertEqual(self.g['command_intent']('open youtube'), 'youtube')

    def test_stop_phrases_and_negations(self):
        for text in ['Salt, stop.', 'Pause it.', 'Enough', 'stop stop', 'hold on', 'no more reading']:
            self.assertTrue(self.g['is_reading_stop'](text), text)
        for text in ["don't stop", 'keep reading', 'the bus stop is ahead', 'salt', 'never stop reading']:
            self.assertFalse(self.g['is_reading_stop'](text), text)

    def test_wake_alias_scope(self):
        for phrase, expected in [('Hey, so', ''), ('Hey, sal', ''), ('Hey Saul.', ''), ('Okay so resume', 'resume'), ('Hey Saul, open Chrome', 'open Chrome')]:
            self.assertEqual(self.g['strip_wake_phrase'](phrase, True), expected)
            self.assertEqual(self.g['strip_wake_phrase'](phrase, False), phrase)

    def test_audio_endpoint_and_wake_preroll(self):
        g = self.g

        class Stream:

            def __init__(self, frames):
                self.frames = iter(frames)
                self.reads = 0
                self.closed = False

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.closed = True

            def read(self, size):
                self.reads += 1
                return (next(self.frames, np.zeros(size, dtype=np.int16).tobytes()), False)

        class Wake:

            def reset(self):
                pass

            def predict(self, block):
                return {'wake': np.array([0.9])}
        speech = (np.ones(1280, dtype=np.int16) * 800).tobytes()
        for ongoing in [True, False]:
            stream = Stream([speech] * (7 if ongoing else 2))
            g['sd'] = types.SimpleNamespace(RawInputStream=lambda **kw: stream)
            audio, heard = g['wait_for_wake'](Wake(), None)
            self.assertEqual(heard, ongoing)
            self.assertTrue(stream.closed)
            self.assertLess(stream.reads, 45)
            self.assertGreaterEqual(len(audio), 2560)
        stream = Stream([speech] * 4)
        g['sd'] = types.SimpleNamespace(RawInputStream=lambda **kw: stream)
        audio, heard = g['record_command'](None)
        self.assertTrue(heard)
        self.assertLess(len(audio) / 16000, 2)

    def test_playback_stop_releases_devices(self):
        g = self.g

        class Mic:
            closed = False
            stopped = False

            def __init__(self, **kw):
                self.callback = kw['callback']

            def start(self):
                for _ in range(12):
                    self.callback((np.ones(1600, dtype=np.int16) * 800).tobytes(), 1600, None, None)

            def stop(self):
                self.stopped = True

            def close(self):
                self.closed = True
        mic = Mic(callback=lambda *a: None)

        def make_mic(**kw):
            mic.callback = kw['callback']
            return mic
        stops = []
        g['sd'] = types.SimpleNamespace(RawInputStream=make_mic, play=lambda *a, **kw: None, get_stream=lambda: types.SimpleNamespace(active=True), stop=lambda: stops.append(True))
        g['CommandRecognizer'] = lambda: types.SimpleNamespace(transcribe=lambda *a, **kw: {'text': 'pause it', 'segments': [{'no_speech_prob': 0.05}]})
        self.assertTrue(g['play_with_stop_listener'](np.zeros(1000), 16000, None))
        self.assertTrue(mic.closed and mic.stopped and stops)

    def test_pause_resume_and_topic_switch(self):
        g = self.g
        path = Path(self.temp.name) / 'lecture.txt'
        path.write_text(' '.join((f'Concept {i} explains an important part of the lecture.' for i in range(25))), encoding='utf-8')
        calls = []

        def say(text, **kw):
            calls.append(text)
            return len(calls) == 2
        g['read_saved_explanation'](types.SimpleNamespace(say=say), path)
        self.assertEqual(g['_READ_PROGRESS']['index'], 1)
        resumed = []
        g['read_saved_explanation'](types.SimpleNamespace(say=lambda t, **kw: resumed.append(t) or False), path, resume=True)
        self.assertEqual(resumed[0], calls[1])
        self.assertNotIn(calls[0], resumed)
        self.assertIsNone(g['_READ_PROGRESS'])
        g['read_saved_explanation'](types.SimpleNamespace(say=lambda *a, **kw: True), path)
        other = Path(self.temp.name) / 'other.txt'
        other.write_text('Topic: Movies. A different topic.', encoding='utf-8')
        selected = []
        g['read_saved_explanation'](types.SimpleNamespace(say=lambda t, **kw: selected.append(t) or False), other)
        self.assertTrue(selected[0].startswith('Topic: Movies'))

    def test_saved_topic_fuzzy_lookup_and_choices(self):
        g = self.g
        folder = Path(self.temp.name) / 'summaries'
        folder.mkdir()
        title = 'Healing of a Tuberculosis Patient Through Prayer and Positive Thinking'
        first = folder / 'prayer_summary.txt'
        first.write_text('Topic: ' + title + '\nMain idea: a personal account.', encoding='utf-8')
        chosen = []
        g['read_saved_explanation'] = lambda engine, path, device: chosen.append(path) or ''
        g['read_latest_explanation'](object(), 'read healing of tuba colossus patient through prayer and positive thinking')
        self.assertEqual(chosen, [first])
        second = folder / 'another_summary.txt'
        second.write_text('Topic: ' + title + '\nA second account.', encoding='utf-8')
        result = g['read_latest_explanation'](object(), 'read prayer positive thinking')
        self.assertIn('Possible matching', result)
        g['read_latest_explanation'](object(), 'keep option 2')
        self.assertEqual(len(chosen), 2)
        self.assertEqual(g['_READ_CHOICES'], [])

    def test_topic_save_collision_and_failure(self):
        g = self.g
        folder = Path(self.temp.name)
        source = folder / 'raw.txt'
        source.write_text('all lecture details', encoding='utf-8')
        target, summary = g['save_topic_files'](source, 'Topic: India / Geography\nAll points', 'stamp')
        self.assertEqual(target.read_text(encoding='utf-8'), 'all lecture details')
        self.assertFalse(source.exists())
        source.write_text('another lecture', encoding='utf-8')
        target2, summary2 = g['save_topic_files'](source, 'Topic: India / Geography\nNew points', 'stamp')
        self.assertNotEqual(target, target2)
        self.assertEqual(target.read_text(encoding='utf-8'), 'all lecture details')
        source.write_text('keep this transcript', encoding='utf-8')
        original = Path.open

        def failing_open(path, *a, **kw):
            if path.name.endswith('_summary.txt') and a and (a[0] == 'x'):
                raise OSError('simulated disk error')
            return original(path, *a, **kw)
        with patch.object(Path, 'open', failing_open):
            with self.assertRaises(OSError):
                g['save_topic_files'](source, 'Topic: Failure\nPoints', 'stamp2')
        self.assertEqual(source.read_text(encoding='utf-8'), 'keep this transcript')

    def test_notes_recorder_tuple_integration(self):
        g = self.g

        class Widget:

            def __init__(self, *a, **kw):
                pass

            def __getattr__(self, name):
                return lambda *a, **kw: None
        tk = types.SimpleNamespace(Tk=Widget, Text=Widget)
        messages = iter(['Remember the milk', 'stop taking notes'])
        recognizer = types.SimpleNamespace(transcribe=lambda *a, **kw: {'text': next(messages), 'segments': [{'no_speech_prob': 0.01}]})
        g['record_command'] = lambda *a: (np.ones(1600, dtype=np.float32) * 0.1, True)
        g['speak'] = lambda *a: None
        with patch.dict(sys.modules, {'tkinter': tk}):
            g['take_notes'](object(), recognizer, None)
        files = list((Path(self.temp.name) / 'notes').glob('*.txt'))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_text(encoding='utf-8').strip(), 'Remember the milk')

    def test_speech_cleanup_and_unknown_reply(self):
        cleaned = self.g['format_for_speech']('### 1. India\n**Main idea:** Geography\n- **Takeaway:** Learn more.')
        self.assertIn('Point 1.', cleaned)
        self.assertNotIn('**', cleaned)
        self.assertNotIn('###', cleaned)
        self.g['language_graph'] = lambda: types.SimpleNamespace(invoke=lambda state: {'answer': 'UNRECOGNIZED'})
        reply, leave = self.g['execute_command']('unrelated nonsense zebra')
        self.assertEqual(reply, "I didn't catch that. Please try again.")
        self.assertFalse(leave)
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=SOURCE)
    options, remaining = parser.parse_known_args()
    SOURCE = options.source.resolve()
    unittest.main(argv=[sys.argv[0]] + remaining, verbosity=2)
