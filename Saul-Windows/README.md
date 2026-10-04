# Saul Aura for Windows

Saul is your floating, voice controlled assistant. The desktop icon opens Aura without starting Anaconda Prompt. Click **Listen**, say **Hey Saul**, and speak naturally. **Float** shrinks Aura to a draggable orb. During speech, **Stop speaking** silences Saul while leaving the answer visible; it does not stop the assistant. Close the Aura window to exit. **Saved** opens your explanations folder.

## Install on your existing laptop

You need your existing `C:\Orynth` installation, Python 3.11 `orynth` environment, `hey_saul.onnx`, and your own `.env` API key. The ZIP contains no key or trained wake model. Stop any running Saul instance, then extract the ZIP into `C:\Orynth\Saul-Windows`, replacing older package files. In Anaconda Prompt, run once:

```bat
conda activate orynth
cd /d C:\Orynth\Saul-Windows
Deploy_Saul.cmd
```

The installer checks file hashes, runs the regression suite, backs up existing managed files, then creates **Saul Aura** on your Windows desktop. It preserves your API key, wake model, transcripts, answers, and notes. If shortcut creation is blocked by your Windows settings, you can still open `C:\Orynth\Start_Saul_Floating.cmd` or run `C:\Orynth\Create_Saul_Shortcut.ps1` later. Existing personal shortcuts are not overwritten.

Double-click **Saul Aura** on the desktop and click **Listen**. To pin to the taskbar, right-click the **running Saul window's taskbar icon** and select **Pin to taskbar**. There is no need to open Anaconda Prompt for everyday use. For debugging, launch `Start_Saul_Floating.cmd` from Anaconda Prompt or inspect `C:\Orynth\saul-startup.log` for startup errors.

The first voice command may take longer while local speech models warm. Answers and lecture explanations may use Groq over the network; Chrome, notes, wake listening, and speech transcription are local. `LIVE_TEST.md` contains the Windows audio acceptance checks. This is a Python desktop application, not a self-contained EXE or a phone app.

## Roll back

The deployment prints its backup location. Stop Saul, then use `python deploy.py --rollback "C:\Orynth\backups\BACKUP_FOLDER"` from the extracted release folder. Your saved content and credentials are not changed. A desktop shortcut created by this version may be removed manually after a rollback if you no longer want it.
