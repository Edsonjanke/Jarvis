"""Every element app.js reaches for must exist in index.html, and every CSS
class the new answer panel uses must be styled. Catches the typo class of bug
that a syntax check cannot see."""
import re
from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "ui"
html = (UI / "index.html").read_text(encoding="utf-8")
app = (UI / "app.js").read_text(encoding="utf-8")
css = (UI / "styles.css").read_text(encoding="utf-8")

ids_in_html = set(re.findall(r'\bid="([^"]+)"', html))
ids_used = sorted(set(re.findall(r'\$\("([^"]+)"\)', app)))

missing = [i for i in ids_used if i not in ids_in_html]
print(f"app.js reaches for {len(ids_used)} element ids; {len(missing)} missing")
for i in missing:
    print(f"    MISSING #{i}")
assert not missing, missing

# The classes the answer panel introduces.
new_classes = ["answer", "answer-head", "answer-meta", "answer-body",
               "answer-warn", "cites", "cite"]
unstyled = [c for c in new_classes if f".{c}" not in css]
print(f"new CSS classes: {len(new_classes)}; unstyled: {len(unstyled)}")
for c in unstyled:
    print(f"    UNSTYLED .{c}")
assert not unstyled, unstyled

# Stage gating: index declares 3, and the buttons declare what they need.
stage = re.search(r'data-stage="(\d+)"', html).group(1)
needs = dict(re.findall(r'id="(btn-[^"]+)"[^>]*data-stage-min="(\d+)"', html))
print(f"\ndata-stage={stage}")
for name, need in sorted(needs.items(), key=lambda kv: (kv[1], kv[0])):
    state = "enabled" if int(need) <= int(stage) else "greyed"
    print(f"    #{name:11} needs {need}  ->  {state}")
assert stage == "5"
assert needs["btn-brief"] == "3" and needs["btn-plan"] == "3"
assert needs["btn-mic"] == "4" and needs["btn-mute"] == "4"
assert needs["btn-memory"] == "5"

for name, route in (("btn-brief", "brief"), ("btn-plan", "plan")):
    assert re.search(rf'\$\("{name}"\)\.addEventListener\("click"', app), name
    assert f'think("{route}"' in app, route
assert 'think("ask"' in app
print("\nbrief / plan / ask handlers wired.")

# -- voice ------------------------------------------------------------------
for name in ("btn-mic", "btn-mute"):
    assert re.search(rf'\$\("{name}"\)\.addEventListener\("click"', app), name
print("mic / mute handlers wired.")

for fn in ("startListening", "stopListening", "encodeWav", "speak", "stopSpeaking"):
    assert f"function {fn}" in app or f"async function {fn}" in app, fn
print("capture, WAV encoding and speech functions present.")

# The recording must be released, or the tab keeps showing the mic indicator.
assert "getTracks().forEach" in app and ".stop()" in app, "microphone is never released"
print("microphone released on stop.")

# Speaking is local; nothing may post audio anywhere but our own /api/listen.
assert '"/api/listen"' in app
assert "elevenlabs.io" not in app.lower(), "the browser must never call ElevenLabs directly"
assert "webkitSpeechRecognition" not in app, "browser STT would send audio to Google"
print("audio only ever goes to our own server.")

# The health payload changed shape; nothing may read the old one.
assert "h.voice.available" not in app, "reads the removed voice.available"
assert "h.voice.listen" in app
print("reads the new voice capability shape.")

# -- memory -----------------------------------------------------------------
assert re.search(r'\$\("btn-memory"\)\.addEventListener\("click"', app), "memory button"
assert "async function showMemory" in app
print("memory panel wired.")

# Everything JARVIS writes must be visible and removable from the panel.
assert '"/api/memory"' in app and '"/api/forget"' in app
assert "Forget" in app, "no way to delete a remembered fact"
print("every remembered fact can be listed and deleted.")

for cls in ("fact", "fact-when", "fact-text", "fact-drop"):
    assert f".{cls}" in css, cls
print("memory panel styled.")

# -- the brain picker -------------------------------------------------------
assert "async function renderBrains" in app
assert "async function switchBrain" in app
assert '"/api/brain"' in app
assert "renderBrains()" in app, "the picker is never populated at boot"
for cls in ("brain-list", "brain-row", "brain-note"):
    assert f".{cls}" in css, cls
    assert cls in app, cls
print("brain picker wired and styled.")

# Switching must be one at a time, and must refresh what the sidebar claims.
assert "switchBrain.busy" in app, "nothing stops two switches racing"
assert "state.health.model.name" in app, "the model row would keep the old name"
print("switching is serialised and the sidebar follows.")

# -- tools ------------------------------------------------------------------
#
# If the model can reach outside your notes, that has to be visible on the
# page. A tools panel that exists only in the API is the same as no panel.
assert "async function renderTools" in app
assert '"/api/tools"' in app
assert "renderTools()" in app, "the tools panel is never populated at boot"
for element in ("tool-list", "tool-now", "tool-note"):
    assert f'id="{element}"' in html, element
assert ".tool-note" in css
assert "btn.disabled = !server.authenticated" in app, \
    "a server with no credential must not look switchable"
print("tools panel wired, and unauthenticated servers cannot be switched on.")

# -- always-on voice --------------------------------------------------------
for fn in ("detectSpeech", "freshVad", "afterWakeWord", "fold", "sendSegment"):
    assert f"function {fn}" in app or f"async function {fn}" in app, fn
assert re.search(r'\$\("btn-wake"\)\.addEventListener\("click"', app), "btn-wake"
assert 'id="btn-wake"' in html
# The two properties the whole feature rests on.
assert "speechSynthesis?.speaking" in app, "nothing stops it hearing its own answer"
assert "detectSpeech(rec.vad" in app, "audio would be uploaded without a speech check"
print("always-on listening: local detection, wake word, and no self-triggering.")

# -- reindex ----------------------------------------------------------------
assert re.search(r'\$\("btn-reindex"\)\.addEventListener\("click"', app), "btn-reindex"
assert '"/api/reindex"' in app
assert 'id="btn-reindex"' in html
print("reindex reachable from the page, so switching vaults needs no terminal.")

print("OK")
