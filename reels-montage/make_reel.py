#!/usr/bin/env python3
"""make_reel.py — assemble Vika's Reels per locked settings.

Usage: make_reel.py "<hook text>" clip1.mov [clip2.mov ...] -o out.mp4
Self-check (no ffmpeg): make_reel.py --selfcheck

Pipeline: concat+normalize 1080x1920 -> transcribe once (faster-whisper,
word timestamps) -> SPEECH-AWARE cut (drop retakes + pauses on WORD
boundaries, never clipping a finished word) -> speed 1.2x -> styled ASS
subtitles remapped from the same words (no 2nd transcription) -> red-block
hook overlay (first HOOK_SECS) -> ducked music -> H.264 export.
"""
import subprocess, sys, os, tempfile, glob, re, shutil

W, H = 1080, 1920
FPS = 30
SPEED = 1.2
HOOK_SECS = 4.0
CREAM = (241, 236, 226)
RED   = (214, 33, 51)

# Bigger model = far better RU accuracy (esp. loanwords like "рилс").
WHISPER_MODEL = "large-v3"
WHISPER_PROMPT = ("Рилс, рилсом, рилсы, сторис, эфир, ИИ-агенты, ассистент, "
                  "автоматизация, Телеграм, монтаж, контент, нейросеть.")
GLOSSARY = {"рюсом": "рилсом", "рюс": "рилс", "рюсы": "рилсы", "рюсе": "рилсе"}

# Speech-aware cut knobs (Vika's locked rules):
#  - never clip a finished word  -> WORD_PAD kept around every word, incl. the last.
#  - cut pauses hard             -> gaps longer than MAX_PAUSE collapse to 2*WORD_PAD.
#  - cut stumble/retakes         -> see drop_retakes().
WORD_PAD  = 0.10   # sec kept before/after each speech run (protects word edges)
MAX_PAUSE = 0.35   # sec: gap longer than this between words is a "pause" -> cut

# IG safe zones (px)
TOP_SAFE, BOTTOM_SAFE, RIGHT_COL, SIDE = 220, 450, 250, 60

HERE = os.path.dirname(os.path.abspath(__file__))

def run(cmd):
    print("+", " ".join(cmd[:6]), "..." if len(cmd) > 6 else "")
    subprocess.run(cmd, check=True)

def ffprobe_dur(path):
    out = subprocess.check_output(["ffprobe","-v","error","-show_entries",
        "format=duration","-of","default=nw=1:nk=1", path])
    return float(out.strip())

# ---------- 1. concat + normalize ----------
def concat(clips, dst):
    inputs = []
    for c in clips: inputs += ["-i", c]
    fc = ""
    for i in range(len(clips)):
        fc += (f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
               f"crop={W}:{H},setsar=1,fps={FPS}[v{i}];"
               f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo[a{i}];")
    fc += "".join(f"[v{i}][a{i}]" for i in range(len(clips)))
    fc += f"concat=n={len(clips)}:v=1:a=1[v][a]"
    run(["ffmpeg","-y",*inputs,"-filter_complex",fc,"-map","[v]","-map","[a]",
         "-c:v","libx264","-preset","medium","-crf","18","-c:a","aac","-b:a","192k",dst])

# ---------- 2. transcribe ONCE (word level) ----------
def _norm(tok):
    return re.sub(r"[^\wа-яё]", "", tok.lower(), flags=re.IGNORECASE)

def transcribe_words(video):
    from faster_whisper import WhisperModel
    wav = video + ".wav"
    run(["ffmpeg","-y","-i",video,"-ar","16000","-ac","1",wav])
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments,_ = model.transcribe(wav, language="ru", word_timestamps=True,
                                  initial_prompt=WHISPER_PROMPT)
    words = []
    for seg in segments:
        for w in (seg.words or []):
            tok = w.word.strip()
            if tok and _norm(tok):
                words.append({"start": float(w.start), "end": float(w.end), "text": tok})
    return words

# ---------- 3a. drop stumble/retakes ----------
def drop_retakes(words, max_n=6, max_gap=4):
    """Remove a botched first attempt when a phrase is restarted.

    Detects: a run of n>=2 words that reappears (normalized) shortly after,
    possibly separated by a few aborted words (the trailing "я про..."). The
    FIRST occurrence + the aborted words in between are cut; the clean restart
    stays. ponytail: exact-match heuristic, n>=2 to avoid nuking intentional
    single-word repeats ("да да"); tune max_n/max_gap on real videos, may miss
    non-verbatim restarts.
    """
    norm = [_norm(w["text"]) for w in words]
    keep = [True]*len(words)
    i = 0
    while i < len(words):
        if not keep[i]:
            i += 1; continue
        cut_to = None
        for n in range(max_n, 1, -1):
            if i + 2*n > len(words): continue
            a = norm[i:i+n]
            for gap in range(0, max_gap+1):
                j = i + n + gap
                if j + n > len(words): break
                if a == norm[j:j+n]:
                    cut_to = j; break
            if cut_to is not None: break
        if cut_to is not None:
            for k in range(i, cut_to): keep[k] = False
            i = cut_to
        else:
            i += 1
    out = [w for w,k in zip(words, keep) if k]
    return out or words   # never return empty

# ---------- 3b. plan keep-spans (pause cutting on word boundaries) ----------
def plan_keep_spans(words, pad=WORD_PAD, max_pause=MAX_PAUSE):
    spans = []
    start = max(0.0, words[0]["start"] - pad)
    prev_end = words[0]["end"]
    for w in words[1:]:
        if w["start"] - prev_end > max_pause:
            spans.append([start, prev_end + pad])   # close: +pad protects last word of run
            start = max(0.0, w["start"] - pad)
        prev_end = w["end"]
    spans.append([start, prev_end + pad])            # final +pad protects the very last word
    return spans

def _kept_offsets(spans):
    off, acc = [], 0.0
    for s,e in spans:
        off.append(acc); acc += (e - s)
    return off, acc

def map_time(t, spans, offsets, speed):
    """Original time -> output time after cuts + speed."""
    for (s,e),o in zip(spans, offsets):
        if t < s: return o / speed          # inside a cut gap: snap to next kept start
        if t <= e: return (o + (t - s)) / speed
    s,e = spans[-1]; return (offsets[-1] + (e - s)) / speed

# ---------- 3c. apply cuts ----------
def apply_cuts(src, spans, dst):
    fc = ""
    for i,(s,e) in enumerate(spans):
        fc += f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[v{i}];"
        fc += f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS[a{i}];"
    n = len(spans)
    fc += "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
    run(["ffmpeg","-y","-i",src,"-filter_complex",fc,"-map","[v]","-map","[a]",
         "-c:v","libx264","-preset","medium","-crf","18","-c:a","aac","-b:a","192k",dst])

# ---------- 4. speed ----------
def speed_up(src, dst):
    run(["ffmpeg","-y","-i",src,"-filter:v",f"setpts=PTS/{SPEED}",
         "-filter:a",f"atempo={SPEED}","-c:v","libx264","-preset","medium",
         "-crf","18","-c:a","aac","-b:a","192k",dst])

# ---------- 5. subtitles (remapped from the same words) ----------
def ass_time(t):
    h=int(t//3600); m=int((t%3600)//60); s=t%60
    return f"{h}:{m:02d}:{s:05.2f}"

def build_ass(words, spans, ass_path, speed=SPEED, max_pause=MAX_PAUSE):
    # group surviving words into <=20-char chunks; also break at a cut pause so
    # a chunk never straddles a removed gap.
    chunks, cur, cs, ce = [], [], None, None
    prev_end = None
    def flush():
        nonlocal cur, cs, ce
        if cur: chunks.append((cs, ce, " ".join(cur)))
        cur, cs, ce = [], None, None
    for w in words:
        tok = w["text"].strip()
        if prev_end is not None and w["start"] - prev_end > max_pause:
            flush()
        if cur and len(" ".join(cur)+" "+tok) > 20:
            flush()
        if cs is None: cs = w["start"]
        cur.append(tok); ce = w["end"]; prev_end = w["end"]
    flush()

    offsets, _ = _kept_offsets(spans)
    marginL = marginR = 110
    marginV = BOTTOM_SAFE + 30
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Liberation Sans,52,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,4,3,2,{marginL},{marginR},{marginV},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for cs,ce,txt in chunks:
        clean = txt.lstrip(" ,.—–-").strip().lower()
        for a,b in GLOSSARY.items():
            clean = re.sub(rf"\b{a}\b", b, clean, flags=re.IGNORECASE)
        a = map_time(cs, spans, offsets, speed)
        b = map_time(ce, spans, offsets, speed)
        lines.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Sub,,0,0,0,,{clean}")
    open(ass_path,"w").write("\n".join(lines))
    return len(chunks)

# ---------- 6. hook overlay PNG (variant 2: ruby marker — brandbook, Vika 2026-08-01) ----------
def _find_chrome():
    for name in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
        path = shutil.which(name)
        if path: return path
    hits = glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome"))
    if hits: return sorted(hits)[-1]
    sys.exit("no Chrome/Chromium found for hook rendering — install one "
             "(apt install chromium-browser, or: npx playwright install chromium)")

FONTS_DIR = os.path.join(HERE, "fonts")   # Oswald + IBM Plex Mono (bundled with this skill)
def make_hook_png(text, png_path):
    # Split into a plain cream top line + the KEY phrase (price/number, with any
    # leading prepositions) which gets the ruby marker. Same split as before.
    # Vika marks WHICH part to highlight per reel by wrapping it in [brackets]
    # (I insert them from her "выделить: …" instruction). The bracketed span gets
    # the ruby marker; everything else is plain cream. If no brackets are given,
    # fall back to auto-detecting the price/number phrase.
    t = text.upper()
    mono = lambda s: re.sub(r"\d+", lambda m: f'<span class="num">{m.group(0)}</span>', s)
    if "[" in t and "]" in t:
        raw = t.replace("[", "\x01").replace("]", "\x02")
    else:
        words = t.split()
        PREP = {"ЗА","В","ВО","НА","С","СО","К","КО","О","ОБ","ОТ","ДО","ПО","У","ИЗ",
                "НАД","ПОД","ПРИ","ПРО","БЕЗ","И","А","НО"}
        idx = next((i for i,w in enumerate(words) if any(c.isdigit() for c in w)), None)
        if idx is None:
            idx = max(0, len(words)-2)
        else:
            while idx > 0 and words[idx-1] in PREP:
                idx -= 1
        raw = " ".join(words[:idx]) + " \x01" + " ".join(words[idx:]) + "\x02"
    body = mono(raw).replace("\x01", '<span class="mark">').replace("\x02", "</span>")
    # Rendered via HTML+chromium (Oswald + Plex Mono can't be drawn by PIL cleanly).
    # Safe band [245,585]: JS shrinks the font until the hook fits (no IG-UI / no
    # forehead overlap). Transparent PNG -> overlaid on the video by compose().
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:'Oswald';src:url('file://{FONTS_DIR}/Oswald.ttf');font-weight:200 700;}}
@font-face{{font-family:'Plex';src:url('file://{FONTS_DIR}/PlexMono-SmBd.ttf');font-weight:600;}}
*{{margin:0;box-sizing:border-box;}}
html,body{{width:{W}px;height:{H}px;background:transparent;}}
.hook{{position:absolute;left:84px;top:245px;right:110px;font-family:'Oswald';font-weight:600;
  text-transform:uppercase;line-height:1.05;letter-spacing:.5px;color:#F2EFE8;font-size:62px;
  text-shadow:0 3px 18px rgba(10,8,6,.55),0 1px 3px rgba(10,8,6,.75);}}
.num{{font-family:'Plex';font-weight:600;letter-spacing:-1px;}}
.mark{{background:linear-gradient(to top,#9E2233 34%,transparent 34%);padding:0 6px;
  box-decoration-break:clone;-webkit-box-decoration-break:clone;}}
</style></head><body>
<div class="hook">{body}</div>
<script>window.onload=function(){{var h=document.querySelector('.hook'),fs=62;
while(h.offsetHeight>340&&fs>34){{fs-=2;h.style.fontSize=fs+'px';}}}};</script>
</body></html>"""
    png_path = os.path.abspath(png_path)
    htmlpath = png_path + ".html"
    open(htmlpath, "w").write(html)
    run([_find_chrome(),"--headless=new","--no-sandbox","--hide-scrollbars",
         "--force-device-scale-factor=1","--default-background-color=00000000",
         "--virtual-time-budget=1500",f"--window-size={W},{H}",
         f"--screenshot={png_path}", f"file://{htmlpath}"])

# ---------- 7. final compose ----------
def compose(video, ass, hook_png, music, dst):
    dur = ffprobe_dur(video)
    inputs = ["-i",video,"-i",hook_png]
    if music: inputs += ["-i",music]
    vf = (f"[0:v][1:v]overlay=0:0:enable='between(t,0,{HOOK_SECS})'[vh];"
          f"[vh]ass={ass}[v]")
    if music:
        af = (f"[2:a]aloop=loop=-1:size=2e9,volume=0.12[bg];"
              f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[a]")
        maps = ["-map","[v]","-map","[a]"]
    else:
        af = "anull"
        maps = ["-map","[v]","-map","0:a"]
    fc = vf + (";"+af if music else "")
    run(["ffmpeg","-y",*inputs,"-filter_complex",fc,*maps,"-t",f"{dur}",
         "-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p",
         "-c:a","aac","-b:a","192k",dst])

def _selfcheck():
    # retake: "фраза раз" started, aborted ("э"), restarted clean
    w = lambda t,s,e: {"text":t,"start":s,"end":e}
    words = [w("привет",0,.4), w("это",.5,.7), w("тест",.8,1.1),
             # long pause here (1.1 -> 3.0) must be cut
             w("в",3.0,3.1), w("пятницу",3.1,3.5), w("я",3.5,3.6), w("про",3.6,3.8),
             w("в",3.9,4.0), w("пятницу",4.0,4.4), w("я",4.4,4.5), w("прочитаю",4.5,5.0)]
    kept = drop_retakes(words)
    txt = [x["text"] for x in kept]
    assert "прочитаю" in txt and txt.count("пятницу")==1, txt   # first attempt dropped
    assert "про" not in txt, txt                                # aborted word dropped
    spans = plan_keep_spans(words)
    assert spans[0][0]==0.0, spans                              # starts at 0 (pad clamped)
    assert abs(spans[-1][1]-(5.0+WORD_PAD))<1e-6, spans         # last word protected by +pad
    assert len(spans)>=2, spans                                 # the big pause split it
    offs,total = _kept_offsets(spans)
    # a cut pause shrinks output below original span
    assert map_time(5.0,spans,offs,1.0) < 5.0, map_time(5.0,spans,offs,1.0)
    # speed halves mapped time
    assert abs(map_time(5.0,spans,offs,2.0)*2 - map_time(5.0,spans,offs,1.0)) < 1e-6
    print("selfcheck OK:", txt)

def main():
    args = sys.argv[1:]
    if args == ["--selfcheck"]:
        _selfcheck(); return
    # --recompose: reuse the last render's cut+subtitles (skip the costly
    # transcription/cut) and only rebuild the hook + music + final compose.
    # For fast hook/style tweaks. ponytail: single-slot cache, last render only.
    recompose = "--recompose" in args
    if recompose: args.remove("--recompose")
    out = "out.mp4"
    if "-o" in args:
        i=args.index("-o"); out=args[i+1]; args=args[:i]+args[i+2:]
    hook, clips = args[0], args[1:]
    tmp = tempfile.mkdtemp(dir=HERE)
    cache_fast = os.path.join(HERE,"out","_last_fast.mp4")
    cache_ass  = os.path.join(HERE,"out","_last.ass")
    fast=f"{tmp}/fast.mp4"; ass=f"{tmp}/subs.ass"; hookpng=f"{tmp}/hook.png"
    if recompose:
        if not (os.path.exists(cache_fast) and os.path.exists(cache_ass)):
            sys.exit("no cached render to recompose from — run a full render first")
        fast, ass = cache_fast, cache_ass
        print("recompose: reusing cached cut + subtitles")
    else:
        joined=f"{tmp}/joined.mp4"; cut=f"{tmp}/cut.mp4"
        concat(clips, joined)
        words = transcribe_words(joined)
        words = drop_retakes(words)
        print(f"words kept after retake removal: {len(words)}")
        spans = plan_keep_spans(words)
        print(f"keep-spans: {len(spans)}")
        apply_cuts(joined, spans, cut)
        speed_up(cut, fast)
        n = build_ass(words, spans, ass)
        print(f"subtitles: {n} chunks")
        shutil.copy(fast, cache_fast); shutil.copy(ass, cache_ass)  # cache for --recompose
    make_hook_png(hook, hookpng)
    mp3s = sorted(glob.glob(os.path.join(HERE,"music","*.mp3")))
    music = mp3s[0] if mp3s and os.path.getsize(mp3s[0])>100000 else None
    print("music:", music or "none (skipped)")
    compose(fast, ass, hookpng, music, out)
    print("DONE ->", out)

if __name__ == "__main__":
    main()
