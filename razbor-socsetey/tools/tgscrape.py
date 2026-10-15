import re,html,subprocess,sys,os
CH=sys.argv[1]; OUT=sys.argv[2]; before=int(sys.argv[3]) if len(sys.argv)>3 else 0; pages=int(sys.argv[4]) if len(sys.argv)>4 else 25
def get(u): return subprocess.run(['curl','-s','--max-time','10','-A','Mozilla/5.0',u],capture_output=True,text=True).stdout
def clean(s): return html.unescape(re.sub(r'<br\s*/?>','\n',re.sub(r'<(?!br)[^>]+>','',s))).strip()
posts={}
for n in range(pages):
    p=get(f'https://t.me/s/{CH}'+(f'?before={before}' if before else ''))
    if n==0 and not before:
        t=re.search(r'tgme_channel_info_header_title[^>]*>(.*?)</div>',p,re.S); d=re.search(r'tgme_channel_info_description[^>]*>(.*?)</div>',p,re.S)
        print('TITLE',clean(t.group(1)) if t else None); print('DESC',clean(d.group(1)) if d else None)
        print('COUNTERS',re.findall(r'counter_value">([^<]+)</span> <span class="counter_type">([^<]+)',p))
    for b in re.split(r'<div class="tgme_widget_message_wrap',p)[1:]:
        i=re.search(r'data-post="'+CH+r'/(\d+)"',b)
        if not i: continue
        dt=re.search(r'datetime="([^"]+)"',b); v=re.search(r'tgme_widget_message_views">([^<]+)',b)
        tx=re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>',b,re.S)
        media='video' if 'message_video' in b else ('photo' if 'message_photo' in b else ('voice' if 'message_voice' in b else ''))
        posts[int(i.group(1))]=(dt.group(1)[:10] if dt else '',v.group(1) if v else '',media,clean(tx.group(1)) if tx else '')
    ids=[int(x) for x in re.findall(r'data-post="'+CH+r'/(\d+)"',p)]
    if not ids or min(ids)<=1: before=0; break
    before=min(ids)
old=open(OUT).read() if os.path.exists(OUT) else ''
open(OUT,'w').write('\n\n'.join(f'#{k} {a} views={b} {c}\n{d}' for k,(a,b,c,d) in sorted(posts.items()))+('\n\n'+old if old else ''))
print('POSTS',len(posts),'NEXT_BEFORE',before)
