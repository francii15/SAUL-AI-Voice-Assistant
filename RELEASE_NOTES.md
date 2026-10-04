# Saul 1.0.0-rc8 — Aura desktop

Aura now uses separate question and answer cards, clickable further-reading links,
a draggable floating orb with a transparent Windows backdrop, and a speaking waveform.
Listen starts the existing wake-word assistant; it is not a microphone mute toggle.
Stop speaking cancels voice output without exiting Saul. It also cancels pending
speech after voice preparation completes. Stop Saul is available in the floating
orb right-click menu; closing the window exits the backend.
Saved opens the summaries folder. Explanations remain saved after playback stops.
The desktop renders user messages and answers, not technical logs.

The native Tkinter design adapts the preview; it does not implement glass blur.
Windows display scaling, microphone playback, and actual stop latency must be
checked on the target laptop. No new UI dependency is required.

## Aura polish update
- 48 x 48 pixel floating control with no caption.
- Smooth pre-rendered orb assets; no extra runtime image dependency.
- Compact header, rounded cards and keyboard-operable rounded controls.
- DPI-aware startup and dark native Windows title bar where supported.
- Interface remains a native desktop adaptation, without glass blur.

## Voice-reactive orb
Cyan/violet ripples in both views follow RMS loudness of outgoing speech PCM on the playback timeline, not microphone input. This is an amplitude-reactive visual, not a frequency spectrum. Stops and silence settle the motion. The 48px float stays unchanged. No new dependencies.

## Desktop startup fix
Launcher now activates Conda through its full path even when launched outside Anaconda Prompt. Startup-only diagnostics go to saul-startup.log; duplicate-instance exit has a distinct status. Windows launch validation is still required.

## Latency update
Wake listening starts before the shared CPU speech model and semantic matcher finish warming in the background. Speech recognition loads first; if a command arrives before it is ready, that first command waits for it. Existing models and matching thresholds are unchanged. Console diagnostics now separate command capture, transcription, dispatch and speech preparation. No background recording begins before the Listen button.

## Desktop presentation update
A high resolution Windows .ico matching the Aura orb is included at multiple taskbar sizes. The GUI sets the window icon and app identity. Deploy creates a hidden-launch Saul Aura desktop shortcut with an icon and leaves existing unrelated shortcuts alone. If Windows disallows shortcut creation, the application installation still succeeds and the command launcher remains usable. This is a desktop release; Windows taskbar appearance and shortcut creation require on-device confirmation.
