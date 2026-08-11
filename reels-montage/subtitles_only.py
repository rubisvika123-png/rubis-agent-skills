#!/usr/bin/env python3
"""subtitles_only.py <video> <out.mp4> — burn RU subtitles ONLY (no speed/cut/
music/hook). Subtitles anchored to the LEFT column so they don't cover a
centered/right speaker. Reuses transcription from make_reel."""
import sys, subprocess, re
from make_reel import transcribe_words, GLOSSARY, ass_time

def probe_wh(p):
    o=subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0",
        "-show_entries","stream=width,height","-of","csv=p=0:s=x",p]).decode().strip()
    w,h=o.split("x"); return int(w),int(h)

def main():
    video,out = sys.argv[1], sys.argv[2]
    W,H = probe_wh(video)
    words = transcribe_words(video)          # real timestamps, whole video kept
    # narrow chunks (<=16 chars) so text stays in the left column
    chunks, cur, cs, ce, prev = [], [], None, None, None
    def flush():
        nonlocal cur,cs,ce
        if cur: chunks.append((cs,ce," ".join(cur)))
        cur,cs,ce=[],None,None
    for w in words:
        tok=w["text"].strip()
        if prev is not None and w["start"]-prev>0.6: flush()
        if cur and len(" ".join(cur)+" "+tok)>16: flush()
        if cs is None: cs=w["start"]
        cur.append(tok); ce=w["end"]; prev=w["end"]
    flush()
    # left column: usable width ~42% of frame; bottom-left, clear of the speaker
    colw=int(W*0.42); marginL=int(W*0.05); marginR=W-marginL-colw; marginV=int(H*0.12)
    fs=int(H*0.032)
    header=f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: L,Liberation Sans,{fs},&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3,2,1,{marginL},{marginR},{marginV},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines=[header]
    for cs,ce,txt in chunks:
        clean=txt.lstrip(" ,.—–-").strip().lower()
        for a,b in GLOSSARY.items():
            clean=re.sub(rf"\b{a}\b",b,clean,flags=re.IGNORECASE)
        lines.append(f"Dialogue: 0,{ass_time(cs)},{ass_time(ce)},L,,0,0,0,,{clean}")
    ass=video+".ass"; open(ass,"w").write("\n".join(lines))
    subprocess.run(["ffmpeg","-y","-i",video,"-vf",f"ass={ass}",
        "-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p",
        "-c:a","copy",out],check=True)
    print("DONE ->",out,"chunks:",len(chunks))

if __name__=="__main__": main()
