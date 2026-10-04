"""Small always-on-top Windows controller for the existing Saul voice backend."""
import os
import math
import json
import re
import webbrowser
from urllib.parse import urlparse
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import scrolledtext

ROOT = Path(__file__).resolve().parent


def status_for_line(line):
    if 'Waiting for "Hey Saul"' in line: return 'Listening · say Hey Saul'
    if line.startswith('Ready.'): return 'Listening · say Hey Saul'
    if 'Speak now' in line or 'Listening for command' in line: return 'Listening to you'
    if 'Recording continuously' in line: return 'Recording your lecture'
    if line.startswith('Speaking.') or line.startswith('Saul:'): return 'Speaking · say stop to interrupt'
    if 'already running' in line: return 'Saul is already open elsewhere'
    return None


def read_ui_event(line):
    if not line.startswith('SAUL_EVENT:'): return None
    try:
        event = json.loads(line[len('SAUL_EVENT:'):])
        if event.get('kind') in {'question', 'answer', 'voice', 'voice_level'} and isinstance(event.get('text'), str):
            return event
    except (ValueError, AttributeError):
        pass
    return None


def clean_display(text):
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.M)
    text = text.replace('**', '').replace('__', '').replace('`', '')
    return text.strip()


def safe_web_link(address):
    parsed = urlparse(address)
    return parsed.scheme in {'https', 'http'} and bool(parsed.hostname)


class SoftButton(tk.Canvas):
    """Rounded, keyboard-operable button using native Tk drawing."""
    def __init__(self,parent,text,command,accent=False):
        self.label=text;self.action=command;self.disabled=False;self.hover=False;self.accent=accent
        super().__init__(parent,width=108 if text=='Stop speaking' else 78,height=38,
                         bg='#101829',highlightthickness=0,takefocus=True,cursor='hand2')
        self.bind('<Enter>',lambda e:self.paint(True))
        self.bind('<Leave>',lambda e:self.paint(False))
        self.bind('<Button-1>',lambda e:self.invoke())
        self.bind('<Return>',lambda e:self.invoke())
        self.bind('<space>',lambda e:self.invoke())
        self.bind('<FocusIn>',lambda e:self.paint(True))
        self.bind('<FocusOut>',lambda e:self.paint(False))
        self.paint()
    def configure(self,cnf=None,**kw):
        if 'state' in kw:self.disabled=kw.pop('state')=='disabled'
        if 'text' in kw:self.label=kw.pop('text')
        result=super().configure(cnf,**kw) if cnf or kw else None
        self.paint();return result
    config=configure
    def invoke(self):
        if not self.disabled:self.action()
    def paint(self,hover=False):
        self.delete('all');w=int(self['width']);h=38
        fill=('#345571' if hover else '#27465e') if self.accent else ('#29344e' if hover else '#202c42')
        if self.disabled:fill='#182235'
        rounded(self,1,1,w-1,h-1,11,fill=fill,outline='')
        self.create_text(w/2,h/2,text=self.label,fill='#708098' if self.disabled else '#e1edf9',font=('Segoe UI',9))


def rounded(canvas,x1,y1,x2,y2,r,**kw):
    return canvas.create_polygon(x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,
        x2-r,y2,x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1,smooth=True,splinesteps=24,**kw)


def configure_windows(root):
    if os.name!='nt':return
    try:
        import ctypes
        root.update_idletasks()
        hwnd=ctypes.windll.user32.GetParent(root.winfo_id())
        for attribute,value in [(20,1),(33,2)]:
            setting=ctypes.c_int(value)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd,attribute,ctypes.byref(setting),4)
    except (OSError,AttributeError):pass


class Desktop:
    def __init__(self, root):
        self.root, self.process = root, None
        self.events = queue.Queue()
        self.control = None
        self.voice_control = None
        self.speaking = False
        self.voice_level=0.0
        self.visual_level=0.0
        self.level_at=0.0
        self.cards = []
        self.closing = False
        self.stopping = False
        self.compact = False
        self.link_count = 0
        self.phase = 0.0
        self.orb_small=tk.PhotoImage(file=str(ROOT/'aura_float.png'))
        self.orb_large=tk.PhotoImage(file=str(ROOT/'aura_hero.png'))
        self.expanded_geometry = '480x660'
        root.title('Saul · Aura')
        if os.name == 'nt':
            try:
                root.iconbitmap(default=str(ROOT/'saul.ico'))
            except (OSError, tk.TclError):
                pass
        root.geometry(self.expanded_geometry)
        root.minsize(450, 520)
        root.attributes('-topmost', True)
        root.configure(bg='#0c1425')
        self.panel = tk.Frame(root, bg='#101829', highlightbackground='#26334a', highlightthickness=0)
        self.panel.pack(fill='both', expand=True, padx=5,pady=5)
        header = tk.Frame(self.panel,bg='#101829'); header.pack(fill='x',padx=24,pady=(18,0))
        tk.Label(header,text='Saul',bg='#101829',fg='#f2f4ff',font=('Segoe UI',21,'bold')).pack(side='left')
        tk.Button(header,text='◌',command=self.toggle,bg='#101829',fg='#a9c9f5',activebackground='#253552',
                  relief='flat',bd=0,font=('Segoe UI',19),cursor='hand2',takefocus=True).pack(side='right')
        tk.Label(self.panel,text='Your AI companion',anchor='w',bg='#101829',fg='#98abc8',font=('Segoe UI',10)).pack(fill='x',padx=25)
        self.hero = tk.Canvas(self.panel,height=114,bg='#101829',highlightthickness=0)
        self.hero.pack(fill='x',padx=20)
        self.status = tk.StringVar(value='A little help, whenever you need it')
        tk.Label(self.panel,textvariable=self.status,bg='#101829',fg='#b7dfff',font=('Segoe UI',10)).pack(pady=(0,12))
        self.feed = tk.Canvas(self.panel, bg='#101829', highlightthickness=0)
        self.feed.pack(fill='both', expand=True, padx=20, pady=(0,14))
        self.card_stack = tk.Frame(self.feed, bg='#101829')
        self.feed_window = self.feed.create_window(0,0,window=self.card_stack,anchor='nw')
        self.card_stack.bind('<Configure>',lambda e:self.feed.configure(scrollregion=self.feed.bbox('all')))
        self.feed.bind('<Configure>',lambda e:self.feed.itemconfigure(self.feed_window,width=e.width))
        root.bind('<MouseWheel>',lambda e:self.feed.yview_scroll(-int(e.delta/120),'units'))
        dock=tk.Frame(self.panel,bg='#101829');dock.pack(fill='x',padx=20,pady=(0,12))
        def button(label,action,accent=False):
            return SoftButton(dock,label,action,accent)
        self.start_button=button('Listen',self.start,True);self.start_button.pack(side='left',padx=(0,7))
        self.stop_button=button('Stop speaking',self.stop_voice);self.stop_button.pack(side='left',padx=(0,7));self.stop_button.configure(state='disabled')
        button('Saved',self.open_files).pack(side='left')
        self.compact_button=button('Float ↗',self.toggle);self.compact_button.pack(side='right')
        tk.Label(self.panel,text='A little clarity, whenever you need it.',bg='#101829',fg='#7188ac',font=('Segoe UI',9)).pack(pady=(0,14))
        self.bubble=tk.Canvas(root,width=48,height=48,bg='#0c1425',highlightthickness=0,cursor='hand2')
        self.bubble.bind('<ButtonPress-1>',self.begin_drag)
        self.bubble.bind('<B1-Motion>',self.drag)
        self.bubble.bind('<ButtonRelease-1>',self.release_drag)
        menu=tk.Menu(root,tearoff=False)
        menu.add_command(label='Open Saul',command=self.toggle)
        menu.add_command(label='Start listening',command=self.start)
        menu.add_command(label='Stop speaking',command=self.stop_voice)
        menu.add_command(label='Stop Saul',command=self.stop)
        menu.add_separator();menu.add_command(label='Exit',command=self.close)
        self.bubble.bind('<Button-3>',lambda event:menu.tk_popup(event.x_root,event.y_root))
        root.bind('<Escape>',lambda event:self.toggle() if self.compact else None)
        self.message('answer','A calm presence, always with you.\n\nClick Listen, say “Hey Saul”, and ask what’s on your mind.')
        configure_windows(root)
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(100,self.poll)
        root.after(80,self.animate_orb)

    def animate_orb(self):
        if self.closing and self.process is None:return
        self.phase+=.10
        target=self.voice_level if self.speaking and time.monotonic()-self.level_at<.3 else 0.0
        self.visual_level+=(target-self.visual_level)*(.55 if target>self.visual_level else .24)
        if self.compact:
            canvas=self.bubble;cx=cy=24;radius=16.8;step=1.05;amplitude=2.4
            if not canvas.find_withtag('orb'):canvas.create_image(cx,cy,image=self.orb_small,tags='orb')
        else:
            canvas=self.hero;cx=max(200,canvas.winfo_width())/2;cy=54;radius=37;step=2.1;amplitude=6
            canvas.delete('orb')
            canvas.create_image(cx,cy,image=self.orb_large,tags='orb')
        canvas.delete('voice_wave')
        if self.visual_level>.015:
            for layer,color in enumerate(('#76e1ed','#88bcfa','#b59cf2')):
                points=[]
                for j in range(121):
                    a=j/120*math.tau
                    wave=math.sin(a*5-self.phase*2+layer)*.65+math.sin(a*9+self.phase)*.35
                    r=radius+layer*step+self.visual_level*amplitude*wave
                    points.extend((cx+math.cos(a)*r,cy+math.sin(a)*r))
                canvas.create_line(*points,fill=color,width=1 if self.compact else 1.5,
                                   smooth=True,tags='voice_wave')
        self.root.after(33,self.animate_orb)

    def begin_drag(self,event):
        self.drag_origin=(event.x_root,event.y_root,self.root.winfo_x(),self.root.winfo_y())
        self.was_dragged=False

    def drag(self,event):
        x,y,wx,wy=self.drag_origin
        dx,dy=event.x_root-x,event.y_root-y
        if abs(dx)+abs(dy)>5:self.was_dragged=True
        self.root.geometry(f'+{max(0,wx+dx)}+{max(0,wy+dy)}')

    def release_drag(self,event):
        if not self.was_dragged:self.toggle()

    def append(self, text):
        # Internal process messages intentionally do not enter the conversation.
        pass

    def insert_links(self, text):
        pattern = r'\[([^\]]+)\]\((https?://[^\s)]+)\)|(https?://[^\s<>]+)'
        offset = 0
        for match in re.finditer(pattern, text):
            self.log.insert('end', text[offset:match.start()], 'body')
            address = (match.group(2) or match.group(3)).rstrip('.,;')
            label = match.group(1) or 'Open reading page ↗'
            if safe_web_link(address):
                tag = 'link_' + str(self.link_count); self.link_count += 1
                self.log.tag_configure(tag, foreground='#8abaff', underline=True)
                self.log.tag_bind(tag, '<Button-1>', lambda event, url=address: webbrowser.open_new_tab(url))
                self.log.tag_bind(tag, '<Enter>', lambda event, widget=self.log: widget.configure(cursor='hand2'))
                self.log.tag_bind(tag, '<Leave>', lambda event, widget=self.log: widget.configure(cursor='arrow'))
                self.log.insert('end', label, tag)
            offset = match.end()
        self.log.insert('end', text[offset:], 'body')

    def message(self, kind, text, reading=''):
        color='#202c45' if kind=='question' else '#19263a'
        shell=tk.Canvas(self.card_stack,bg='#101829',highlightthickness=0,height=100)
        shell.pack(fill='x',pady=(0,12),padx=(36,0) if kind=='question' else (0,0))
        card=tk.Frame(shell,bg=color)
        window=shell.create_window(10,10,window=card,anchor='nw')
        def layout(event=None):
            width=max(80,shell.winfo_width())
            shell.itemconfigure(window,width=width-20)
            height=card.winfo_reqheight()+20
            if int(shell['height'])!=height:shell.configure(height=height)
            shell.delete('surface')
            item=rounded(shell,0,0,width,height,18,fill=color,outline='')
            shell.itemconfigure(item,tags='surface');shell.tag_lower(item)
        shell.bind('<Configure>',layout)
        card.bind('<Configure>',layout)
        tk.Label(card,text='YOU' if kind=='question' else 'SAUL',anchor='w',
                 bg=card['bg'],fg='#b5b7ff' if kind=='question' else '#85dfff',
                 font=('Segoe UI',9,'bold')).pack(fill='x',padx=16,pady=(12,5))
        self.log=tk.Text(card,wrap='word',bg=card['bg'],fg='#e5edfc',font=('Segoe UI',11),
                         relief='flat',bd=0,padx=16,pady=8,height=3,highlightthickness=0)
        self.log.pack(fill='x',pady=(0,10))
        self.log.tag_configure('body',spacing3=9)
        self.log.tag_configure('reading',foreground='#90a8c9',spacing1=12,spacing3=8)
        self.insert_links(clean_display(text))
        if reading:
            self.log.insert('end','\n\nEXPLORE MORE\n','reading')
            self.insert_links(clean_display(reading))
        widget=self.log
        def resize(event=None):
            count=widget.count('1.0','end','displaylines')
            widget.configure(height=max(2,(count[0] if count else 2)+1))
        widget.bind('<Configure>',resize)
        widget.configure(state='disabled')
        self.cards.append(shell)
        if len(self.cards)>30:self.cards.pop(0).destroy()
        self.root.after_idle(lambda:self.feed.yview_moveto(1))

    def stop_voice(self):
        if self.process is not None and self.voice_control is not None:
            self.voice_control.touch()
            self.speaking=False
            self.voice_level=0.0
            self.status.set('Voice stopped · answer stays here')

    def start(self):
        if self.process is not None: return
        fd, name = tempfile.mkstemp(prefix='saul-stop-', suffix='.signal')
        os.close(fd); Path(name).unlink()
        self.control = Path(name)
        self.voice_control = Path(name + ".voice")
        env = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8', SAUL_DESKTOP_EVENTS='1')
        try:
            self.process = subprocess.Popen(
                [sys.executable, '-u', str(ROOT/'run_saul.py'), '--semantic-commands', '--further-reading', '--control-file', name, '--voice-control-file', str(self.voice_control)],
                cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except OSError as error:
            self.status.set('Could not start Saul'); self.append(str(error)+'\n'); return
        self.status.set('Getting ready…')
        self.start_button.configure(state='disabled',text='Starting'); self.stop_button.configure(state='disabled')
        process = self.process
        def read_output():
            # Capture only startup diagnostics; never log conversation events.
            log_path=ROOT/'saul-startup.log'
            try:
                startup_log=log_path.open('w',encoding='utf-8')
            except OSError:
                startup_log=None
            try:
                with process.stdout:
                    for line in process.stdout:
                        if startup_log is not None:
                            if line.startswith('Ready.'):
                                startup_log.write('Startup ready.\n')
                                startup_log.close();startup_log=None
                            elif not line.startswith('SAUL_EVENT:'):
                                startup_log.write(line);startup_log.flush()
                        self.events.put(line)
            finally:
                if startup_log is not None:startup_log.close()
        threading.Thread(target=read_output, daemon=True).start()

    def stop(self):
        if self.process is None or self.stopping: return
        self.stopping = True
        self.status.set('Stopping Saul…')
        self.stop_button.configure(state='disabled')
        self.control.touch()
        process = self.process
        def stop_worker():
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.events.put('Saul did not exit within 10 seconds; closing its process tree.\n')
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    process.terminate()
        threading.Thread(target=stop_worker, daemon=True).start()

    def poll(self):
        for _ in range(100):
            try: line = self.events.get_nowait()
            except queue.Empty: break
            event = read_ui_event(line)
            if event:
                if event['kind']=='voice_level':
                    try:self.voice_level=max(0.0,min(1.0,float(event.get('level',0))))
                    except (ValueError,TypeError):self.voice_level=0.0
                    self.level_at=time.monotonic()
                elif event['kind']=='voice':
                    self.speaking=event['text']=='speaking'
                    if not self.speaking:self.voice_level=0.0
                    self.stop_button.configure(state='normal' if event['text']!='idle' else 'disabled')
                    self.status.set('Speaking · interrupt anytime' if self.speaking else 'Here with you')
                else:
                    self.message(event['kind'], event['text'], event.get('reading', ''))
            status = status_for_line(line)
            if status and not self.stopping:
                self.status.set(status)
                if line.startswith('Ready.'): self.start_button.configure(text='Listening')
        if self.process is not None and self.process.poll() is not None:
            code = self.process.returncode
            self.process = None; self.stopping = False
            if self.control: self.control.unlink(missing_ok=True)
            if self.voice_control: self.voice_control.unlink(missing_ok=True)
            self.speaking=False
            self.start_button.configure(state='normal',text='Listen'); self.stop_button.configure(state='disabled')
            if code==0:self.status.set('Stopped')
            elif code==2:self.status.set('Saul is already running in another window')
            else:
                self.status.set('Could not start listening · see saul-startup.log')
                self.message('answer','I could not start listening. Startup details are saved in C:\\Orynth\\saul-startup.log. Please share that file to diagnose the issue.')
        if self.closing and self.process is None:
            self.root.destroy(); return
        self.root.after(100, self.poll)

    def toggle(self):
        self.compact=not self.compact
        if self.compact:
            self.expanded_geometry=self.root.geometry()
            x,y=self.root.winfo_x(),self.root.winfo_y()
            self.panel.pack_forget()
            self.root.overrideredirect(True)
            self.root.minsize(48,48)
            self.root.geometry(f'48x48+{x}+{y}')
            self.bubble.pack(fill='both',expand=True)
            if os.name=='nt': self.root.wm_attributes('-transparentcolor','#0c1425')
        else:
            if os.name=='nt': self.root.wm_attributes('-transparentcolor','')
            self.bubble.pack_forget()
            x,y=self.root.winfo_x(),self.root.winfo_y()
            self.root.overrideredirect(False)
            self.root.minsize(450,520)
            size=self.expanded_geometry.split('+')[0]
            width,height=map(int,size.split('x'))
            x=max(0,min(x,self.root.winfo_screenwidth()-width))
            y=max(0,min(y,self.root.winfo_screenheight()-height-50))
            self.root.geometry(f'{size}+{x}+{y}')
            self.panel.pack(fill='both',expand=True,padx=5,pady=5)
        self.root.attributes('-topmost',True)

    def open_files(self):
        folder=ROOT / "summaries"
        folder.mkdir(exist_ok=True)
        os.startfile(str(folder))

    def close(self):
        self.closing = True
        self.stop()


if __name__ == '__main__':
    if os.name=='nt':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Orynth.Saul.Aura')
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (OSError,AttributeError):pass
    app = tk.Tk()
    app.tk.call('tk','scaling',96/72)
    Desktop(app)
    app.mainloop()
