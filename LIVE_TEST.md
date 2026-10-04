# Aura acceptance check

1. Deploy the extracted package, then launch Start_Saul_Floating.cmd.
2. Click Listen, wait for the listening status, say Hey Saul and ask a question.
3. Check the question and answer cards; open a further-reading hyperlink.
4. During the answer click Stop speaking. Audio must stop and the answer remain.
5. Say Hey Saul again: Saul must still accept a new question.
6. Read a saved explanation, stop it with the button, then request resume reading.
7. Click Float, drag the orb, then click it to expand. Check at your display scale.
8. Click Saved: the summaries folder should open.
9. Record a short lecture. It should save silently; request reading explicitly.
10. Close the window. Confirm no Saul process remains before relaunching.

Voice recognition interruption remains dependent on microphone quality; the
button uses a separate local signal and does not require speech transcription.

Latency check: after a fresh app launch, click Listen and time until Listening · say Hey Saul. Wait 45 seconds for background warmup; then try Hey Saul, close Chrome. Compare Timing | Command capture, Command transcription, Command action, and Voice preparation in the terminal diagnostic launch. If the first command is slow but later ones are fast, model warmup is responsible.
