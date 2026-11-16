"""Render the original 90s film, independent stems, captions and engine media.

Requires ffmpeg/ffprobe, Pillow, numpy, scipy. All source media belongs to this run.
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile
from PIL import Image
from opening_plan import ROOT, SHOTS, LINES

FFMPEG=shutil.which('ffmpeg')
FFPROBE=shutil.which('ffprobe')
SR=48000
DURATION=90
TAKES={'s02':2,'s04':2,'s05':2,'s06':2,'s07':2,'s08':1,'s09':1}

def run(args):
    p=subprocess.run([str(x) for x in args],capture_output=True,text=True,encoding='utf8',errors='replace')
    if p.returncode:raise RuntimeError(p.stderr[-7000:])
    return p.stdout

def ff(*args):return run([FFMPEG,'-hide_banner','-loglevel','error','-nostdin','-y',*args])

def probe(path):return json.loads(run([FFPROBE,'-v','error','-show_format','-show_streams','-of','json',path]))

def save_wav(path,audio):
    wavfile.write(path,SR,(np.clip(audio,-0.98,0.98)*32767).astype(np.int16))

def srt_time(t):
    ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'

def captions(lines):
    events=[]
    for line in lines:
        # Keep captions short; actual line timing follows the fitted narration stem.
        words=re.findall(r'[^，。？！；]+[，。？！；]?',line['text'])
        groups=[];current=''
        for word in words:
            if current and len(current)+len(word)>19:groups.append(current);current=''
            current+=word
        if current:groups.append(current)
        start=line['start'];duration=line.get('fitted_duration',line['end']-line['start'])
        weights=[len(x) for x in groups];total=sum(weights)
        for text,weight in zip(groups,weights):
            end=start+duration*weight/total
            events.append({'start':round(start,3),'end':round(end,3),'text':text});start=end
    (ROOT/'opening_zh.srt').write_text('\n\n'.join(f"{i+1}\n{srt_time(e['start'])} --> {srt_time(e['end'])}\n{e['text']}" for i,e in enumerate(events))+'\n',encoding='utf8')
    (ROOT/'opening_subtitles.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf8')
    # ASS in 1080p coordinates. Warm moon-blue with 60% indigo backing.
    def ass_time(t):return f'{int(t)//3600}:{int(t)//60%60:02}:{t%60:05.2f}'
    ass='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Narration,Noto Serif SC,40,&H00D6C4B8,&H00D6C4B8,&H661A1414,&H661A1414,0,0,0,0,100,100,1,0,3,12,0,2,100,100,92,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    ass+='\n'.join(f"Dialogue: 0,{ass_time(e['start'])},{ass_time(e['end'])},Narration,,0,0,0,,{{\\fad(100,120)}}{e['text']}" for e in events)
    (ROOT/'opening_zh.ass').write_text(ass,encoding='utf8')
    return events

def audio():
    out=ROOT/'audio';out.mkdir(exist_ok=True)
    count=SR*DURATION;rng=np.random.default_rng(20261107)
    music=np.zeros((count,2),np.float32);foley=np.zeros_like(music);voice=np.zeros_like(music)
    def add(buf,start,wave,gain=1.,pan=0.):
        i=round(start*SR);w=np.asarray(wave,np.float32)
        if w.ndim==1:w=np.column_stack((w*np.sqrt((1-pan)/2),w*np.sqrt((1+pan)/2)))
        n=min(len(w),len(buf)-i)
        if n>0:buf[i:i+n]+=w[:n]*gain
    def tone(freq,dur=3.5,vel=.04):
        t=np.arange(round(dur*SR))/SR
        env=(1-np.exp(-t*90))*np.exp(-t/1.05)
        # Original struck-glass/wood musical timbre; no sampled instrument.
        wave=np.sin(2*np.pi*freq*t)+.24*np.sin(2*np.pi*freq*2.003*t)*np.exp(-t/.4)+.11*np.sin(2*np.pi*freq*3.99*t)*np.exp(-t/.16)
        return vel*env*wave
    # A sparse newly composed five-note motif; harmonic rhythm leaves room for speech.
    notes=[(0.7,62),(4.8,69),(8.0,72),(12.1,74),(15.8,69),(19.0,65),(22.0,64),
           (25.4,62),(44.0,62),(47.3,69),(50.5,72),(53.4,74),(56.4,77),(59.4,74),
           (62.0,72),(73.8,69),(76.6,74),(79.3,77),(82.3,81),(85.0,77),(87.0,74)]
    for i,(at,midi) in enumerate(notes):add(music,at,tone(440*2**((midi-69)/12),vel=.04 if at<26 else .052),pan=.22*np.sin(i))
    for at,root in [(0,38),(18,41),(43,38),(53,46),(73,38),(84,41)]:
        dur=min(11,90-at);t=np.arange(round(dur*SR))/SR;env=np.sin(np.pi*np.minimum(t/dur,1))**2
        pad=sum(np.sin(2*np.pi*440*2**((root+n-69)/12)*t+.012*np.sin(2*np.pi*.17*t)) for n in [0,7,12])/3
        add(music,at,.022*env*pad)
    # Rain and tape hiss, newly synthesized from seeded filtered noise.
    noise=rng.standard_normal(count).astype(np.float32)
    rain=signal.sosfilt(signal.butter(2,[700,6000],btype='bandpass',fs=SR,output='sos'),noise).astype(np.float32)
    t=np.arange(count)/SR
    rainenv=np.where(t<35,.012,np.where(t<43,.008,.003))
    add(foley,0,rain*rainenv,pan=-.25)
    hiss=signal.sosfilt(signal.butter(1,2600,btype='highpass',fs=SR,output='sos'),rng.standard_normal(count)).astype(np.float32)
    add(foley,0,hiss*.0024,pan=.05)
    for at in [0.9,8.9,43.3,88.2]:
        n=round(.09*SR);tt=np.arange(n)/SR
        click=rng.standard_normal(n)*np.exp(-tt*110)*.08+np.sin(2*np.pi*145*tt)*np.exp(-tt*60)*.035
        add(foley,at,click,pan=-.3)
    # Ceramic scrape/impact and a short trickle at the spill.
    tt=np.arange(round(.8*SR))/SR
    add(foley,29.3,.035*np.sin(2*np.pi*270*tt)*np.exp(-tt*12),pan=.2)
    for at in [30.0,30.18,30.41,30.8,31.25,35.6,37.8]:
        tt=np.arange(round(.13*SR))/SR
        add(foley,at,.018*np.sin(2*np.pi*(650*tt+1400*tt**2))*np.exp(-tt*40),pan=.2)
    add(foley,54.8,tone(1320,2,.022),pan=-.3)
    add(foley,74.0,tone(880,3,.05),pan=.4)
    # Soft vapor hiss for purification; no gunshot or blast.
    n=round(3.5*SR);tt=np.arange(n)/SR
    vapor=signal.sosfilt(signal.butter(2,[1000,5000],btype='bandpass',fs=SR,output='sos'),rng.standard_normal(n))
    add(foley,76,.012*vapor*np.sin(np.pi*tt/3.5)**2,pan=.25)
    manifest=json.loads((out/'voice_manifest.json').read_text(encoding='utf8'))
    fitted=[]
    for i,line in enumerate(manifest['lines']):
        source=out/line['file'];target=out/f'voice_fitted_{i+1:02}.wav'
        slot=line['end']-line['start'];raw=float(probe(source)['format']['duration'])
        # Never truncate speech; speed up only if a line exceeds its allocated time.
        speed=max(.86,raw/(slot-.12))
        chain=f'atempo={speed:.6f},highpass=f=95,lowpass=f=7600,acompressor=threshold=0.13:ratio=2:attack=10:release=120,loudnorm=I=-19:TP=-3:LRA=8'
        ff('-i',source,'-af',chain,'-ar',SR,'-ac',1,target)
        rate,data=wavfile.read(target);data=data.astype(np.float32)/32768
        # Tiny speed wander and a trace of saturation provide this film's tape timbre.
        samples=np.arange(len(data));wander=6*np.sin(2*np.pi*.47*samples/SR)
        data=np.interp(np.clip(samples+wander,0,len(data)-1),samples,data).astype(np.float32)
        data=np.tanh(data*1.07)/1.07
        add(voice,line['start'],data,gain=1.32)
        fitted.append({**line,'fitted_duration':len(data)/SR,'tempo':speed})
    # Duck score under spoken sentences.
    gain=np.ones(count,np.float32)
    for line in fitted:
        i=max(0,int((line['start']-.25)*SR));j=min(count,int((line['start']+line['fitted_duration']+.2)*SR))
        gain[i:j]=.48
    gain=signal.sosfilt(signal.butter(1,3,fs=SR,output='sos'),gain).astype(np.float32)
    music*=gain[:,None]
    fade=np.minimum(t/1.5,1)*np.minimum((90-t)/1.4,1)
    music*=fade[:,None];foley*=fade[:,None];voice*=fade[:,None]
    save_wav(out/'music_original.wav',music);save_wav(out/'foley_original.wav',foley);save_wav(out/'narration_tape.wav',voice)
    save_wav(out/'mix_pre.wav',music+foley+voice)
    # Two-pass normalization: preserves dynamics while controlling true peak.
    first=subprocess.run([FFMPEG,'-hide_banner','-i',str(out/'mix_pre.wav'),'-af','loudnorm=I=-18:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True)
    measurement=json.loads(first.stderr[first.stderr.rfind('{'):first.stderr.rfind('}')+1])
    filt='loudnorm=I=-18:TP=-1.5:LRA=11:linear=true:'+':'.join(f'{k}={measurement[v]}' for k,v in [('measured_I','input_i'),('measured_TP','input_tp'),('measured_LRA','input_lra'),('measured_thresh','input_thresh'),('offset','target_offset')])
    ff('-i',out/'mix_pre.wav','-af',filt,'-ar',SR,'-ac',2,out/'opening_mix.wav')
    (out/'mix_measurement.json').write_text(json.dumps(measurement,indent=2))
    captions(fitted)
    print('Original music, Foley, narration and timed captions complete',flush=True)

def lut():
    path=ROOT/'luminance_cap.cube'
    with path.open('w',encoding='ascii') as f:
        f.write('TITLE "Paper Lantern City original CG luminance cap"\nLUT_3D_SIZE 33\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n')
        for b in np.linspace(0,1,33):
            for g in np.linspace(0,1,33):
                for r in np.linspace(0,1,33):
                    y=.299*r+.587*g+.114*b;scale=min(1,.742/max(y,.00001))
                    f.write(f'{r*scale:.8f} {g*scale:.8f} {b*scale:.8f}\n')

def normalize():
    # Overlay filters may inherit a 25fps still-image clock. Normalize every shot
    # to the exact timeline frame count and one common MP4 timebase before concat.
    norm=ROOT/'build/normalized';norm.mkdir(exist_ok=True)
    for s in SHOTS:
        src=ROOT/'build'/f"{s['id']}.mp4";dst=norm/src.name
        if dst.exists() and dst.stat().st_mtime>src.stat().st_mtime:continue
        temp=norm/f"{s['id']}.tmp.mp4"
        frames=s['duration']*30
        ff('-i',src,'-vf',f'fps=30,tpad=stop_mode=clone:stop_duration=1,trim=end_frame={frames},setpts=N/(30*TB),setsar=1',
           '-frames:v',frames,'-an','-c:v','libx264','-preset','fast','-crf','16','-threads','4','-video_track_timescale','90000',temp)
        info=next(x for x in probe(temp)['streams'] if x['codec_type']=='video')
        assert int(info['nb_frames'])==frames and info['r_frame_rate']=='30/1'
        temp.replace(dst)
        print('Normalized',s['id'],frames,'frames',flush=True)

def export_game():
    # Windows 8.1.1 failed encoding; Windows 7.1 encoded but failed full decoding.
    # Use the installed native WSL encoder, then strictly decode before promotion.
    game_ffmpeg=os.environ.get('GUNFORGE_THEORA_FFMPEG','/usr/local/bin/ffmpeg')
    prefix=['wsl','-d',os.environ.get('GUNFORGE_WSL_DISTRO','Ubuntu-22.04'),'--',game_ffmpeg] if os.name=='nt' else [game_ffmpeg]
    def native_path(p):
        value=str(p.resolve()).replace('\\','/')
        return '/mnt/'+value[0].lower()+value[2:] if re.match(r'^[A-Za-z]:/',value) else value
    target=ROOT/'paper_lantern_city_opening_game.ogv'
    temporary=ROOT/'paper_lantern_city_opening_game.tmp.ogv'
    run(prefix+['-hide_banner','-loglevel','error','-nostdin','-y','-i',native_path(ROOT/'paper_lantern_city_opening_clean.mp4'),
       '-vf','fps=30,scale=1776:936:force_original_aspect_ratio=increase,crop=1776:936,setsar=1',
       '-r','30','-c:v','libtheora','-q:v','6','-pix_fmt','yuv420p','-c:a','libvorbis','-q:a','5',native_path(temporary)])
    decoded=run(prefix+['-v','error','-xerror','-err_detect','explode','-i',native_path(temporary),'-vf','fps=30','-progress','pipe:1','-f','null','-'])
    frame_counts=re.findall(r'^frame=(\d+)',decoded,re.MULTILINE)
    assert frame_counts and int(frame_counts[-1])==2700
    p=probe(temporary)
    v=next(s for s in p['streams'] if s['codec_type']=='video')
    a=next(s for s in p['streams'] if s['codec_type']=='audio')
    assert (v['width'],v['height'])==(1776,936) and v['r_frame_rate']=='30/1'
    assert abs(float(p['format']['duration'])-90)<.12
    assert abs(float(a['duration'])-90)<.12
    temporary.replace(target)
    print('Game Theora export validated',flush=True)

def video(shots_only=False,only=None):
    lut();build=ROOT/'build';build.mkdir(exist_ok=True)
    os.chdir(ROOT)
    selected_path=ROOT/'selected_sources.json'
    selected=json.loads(selected_path.read_text()) if selected_path.exists() else {}
    for s in SHOTS:
        if only and s['id'] not in only.split(','):continue
        sid=s['id'];dur=s['duration'];target=build/f'{sid}.mp4'
        if target.exists():continue
        base='scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1'
        if sid=='s04':
            # Keep only the ordinary nudge before H3 invents extra lamp illumination.
            # An authored dissolve completes the spill into our explicit continuity keyframe.
            src=ROOT/'sources/s04_take2.mp4'
            selected[sid]='s04_take2.mp4 0-1.35s + original spill_end.png authored dissolve'
            fc=f'[0:v]trim=duration=1.35,setpts=PTS-STARTPTS,{base},fps=30,tpad=start_mode=clone:start_duration=1.25:stop_mode=clone:stop_duration=8[begin];[1:v]{base},format=rgba,fade=t=in:st=2.35:d=0.6:alpha=1[end];[begin][end]overlay=0:0:shortest=1,lut3d=luminance_cap.cube,format=yuv420p[v]'
            ff('-i',src,'-loop','1','-i',ROOT/'keyframes/spill_end.png','-filter_complex',fc,'-map','[v]','-t',dur,'-an','-c:v','libx264','-preset','fast','-crf','17','-threads','6',target)
            print('Rendered authored spill',flush=True)
            continue
        if sid=='s07':
            # Lock the upper paper town to the newly painted background. H3 repeatedly
            # invented a sun despite endpoint conditioning; keep only the lower puppet stage.
            src=ROOT/'sources/s07_take2.mp4'
            if not src.exists():raise RuntimeError('Missing new resident motion take')
            native=float(probe(src)['format']['duration'])
            selected[sid]='s07_take2.mp4 lower puppet stage over this run\'s city.png; generated sun excluded'
            fc=f"[0:v]setpts=(PTS-STARTPTS)*{dur/native:.9f},scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,{base},tpad=stop_mode=clone:stop_duration=0.5,crop=1920:500:0:580,format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='255*min(1,Y/120)'[puppets];[1:v]{base}[bg];[bg][puppets]overlay=0:580:shortest=1,lut3d=luminance_cap.cube,fade=t=out:st={dur-.2}:d=0.2,format=yuv420p[v]"
            ff('-i',src,'-loop','1','-i',ROOT/'keyframes/city.png','-filter_complex',fc,'-map','[v]','-t',dur,'-an','-c:v','libx264','-preset','fast','-crf','17','-threads','6',target)
            print('Rendered locked paper stage',flush=True)
            continue
        if s['kind']=='h3':
            take=TAKES[sid];name=sid+(f'_take{take}' if take>1 else '')+'.mp4'
            src=ROOT/'sources'/name
            if not src.exists():raise RuntimeError(f'Missing selected shot {name}; rejected takes cannot be substituted')
            selected[sid]=src.name
            native=float(probe(src)['format']['duration'])
            trim=''
            if sid=='s08':
                # Cut before the bird leaves frame, so the following beam shot has continuity.
                native=4.75;trim='trim=duration=4.75,'
            # Optical flow at 720p avoids held frames when retiming. Upscale after interpolation.
            vf=f'{trim}setpts=(PTS-STARTPTS)*{dur/native:.9f},scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,{base},tpad=stop_mode=clone:stop_duration=0.5'
            inputs=['-i',src]
        else:
            src=ROOT/'keyframes'/f"{s['frame']}.png";selected[sid]=src.name
            # A slow, deterministic camera move over newly drawn artwork.
            vf=f"scale=2304:1296:force_original_aspect_ratio=increase,crop=2304:1296,zoompan=z='1.015+0.045*on/{dur*30}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={dur*30}:s=1920x1080:fps=30,setsar=1"
            inputs=['-loop','1','-i',src]
        if s['kind']=='title':
            # Title PNG is original generated calligraphy with genuine alpha.
            vf+=',eq=brightness=-0.12:saturation=0.75,gblur=sigma=1.3'
            fc=f'[0:v]{vf}[bg];[1:v]scale=1152:-1,format=rgba,fade=t=in:st=0.5:d=1.5:alpha=1[title];[bg][title]overlay=(W-w)/2:(H-h)/2-20:shortest=1,lut3d=luminance_cap.cube,fade=t=out:st=5:d=1,format=yuv420p[v]'
            ff(*inputs,'-loop','1','-i',ROOT/'keyframes/title.png','-filter_complex',fc,'-map','[v]','-t',dur,'-an','-c:v','libx264','-preset','fast','-crf','17','-threads','6',target)
        else:
            vf+=',lut3d=luminance_cap.cube'
            if sid=='s01':vf+=',fade=t=in:st=0:d=1.2'
            # Restrained short dips between chapters avoid white transition flashes.
            if sid in ['s03','s05','s07']:vf+=f',fade=t=out:st={dur-.2}:d=0.2'
            vf+=',format=yuv420p'
            ff(*inputs,'-vf',vf,'-t',dur,'-r',30,'-an','-c:v','libx264','-preset','fast','-crf','17','-threads','6',target)
        print('Rendered',sid,flush=True)
    (ROOT/'selected_sources.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2))
    if shots_only:return
    normalize()
    (build/'concat.txt').write_text(''.join(f"file 'normalized/{s['id']}.mp4'\n" for s in SHOTS))
    ff('-f','concat','-safe','0','-i',build/'concat.txt','-c','copy',build/'picture.mp4')
    ff('-i',build/'picture.mp4','-i',ROOT/'audio/opening_mix.wav','-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-b:a','256k','-t',90,'-movflags','+faststart',ROOT/'paper_lantern_city_opening_clean.mp4')
    ff('-i',ROOT/'paper_lantern_city_opening_clean.mp4','-vf','ass=opening_zh.ass,lut3d=luminance_cap.cube','-c:v','libx264','-preset','fast','-crf','18','-threads','6','-c:a','copy','-movflags','+faststart',ROOT/'paper_lantern_city_opening.mp4')
    # Content-area ratio for the planned game; no baked outer tracking frame.
    export_game()
    print('Final film exports complete',flush=True)

def audit():
    qa=ROOT/'qa';qa.mkdir(exist_ok=True)
    final=ROOT/'paper_lantern_city_opening.mp4';p=probe(final)
    v=next(s for s in p['streams'] if s['codec_type']=='video');a=next(s for s in p['streams'] if s['codec_type']=='audio')
    assert (v['width'],v['height'])==(1920,1080)
    assert v['r_frame_rate']=='30/1'
    assert int(v['nb_frames'])==2700,'Film must contain exactly 90 seconds at 30fps'
    assert abs(float(v['duration'])-90)<.04,'Picture duration must match audio and subtitles'
    assert abs(float(p['format']['duration'])-90)<.12
    events=json.loads((ROOT/'opening_subtitles.json').read_text(encoding='utf8'))
    assert all(0<=e['start']<e['end']<=84 for e in events)
    assert all(events[i]['end']<=events[i+1]['start']+.01 for i in range(len(events)-1))
    samples=[]
    for s in SHOTS:
        at=s['start']+s['duration']*.58;frame=qa/f"final_{s['id']}.png"
        ff('-ss',at,'-i',final,'-frames:v',1,frame)
        rgb=np.asarray(Image.open(frame).convert('RGB'),np.float32)
        y=rgb@np.array([.299,.587,.114])
        samples.append({'shot':s['id'],'time':at,'mean_Yprime':float(y.mean()/255),'max_Yprime':float(y.max()/255),'over_75_fraction':float((y>191.25).mean())})
    # Scan every second of the clean film for luminance and black-frame anomalies.
    data=subprocess.run([FFMPEG,'-v','error','-i',str(ROOT/'paper_lantern_city_opening_clean.mp4'),'-vf','fps=1,scale=320:180','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True).stdout
    frames=np.frombuffer(data,np.uint8).reshape(-1,180,320,3)
    y=frames.astype(np.float32)@np.array([.299,.587,.114])/255
    report={'duration':p['format']['duration'],'resolution':[v['width'],v['height']],'fps':v['r_frame_rate'],'video_frames':int(v['nb_frames']),'audio_codec':a['codec_name'],'caption_events':len(events),'samples':samples,
        'one_second_scan':{'frames':len(frames),'max_Yprime':float(y.max()),'over_75_fraction':float((y>.75).mean()),'dark_frames_seconds':[i for i,x in enumerate(y) if x.mean()<.012]},
        'limits':['AI-generated original shots require human aesthetic review.','Game engine and actual light-gun validation are not performed.','H3 source resolution is 1152x640; 1080p delivery is upscaled.']}
    loud=subprocess.run([FFMPEG,'-hide_banner','-i',str(final),'-af','loudnorm=I=-18:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True)
    report['final_audio_measurement']=json.loads(loud.stderr[loud.stderr.rfind('{'):loud.stderr.rfind('}')+1])
    assert float(report['final_audio_measurement']['input_tp'])<=-1.0,'Audio true peak too high'
    assert -20<=float(report['final_audio_measurement']['input_i'])<=-16,'Unexpected mix loudness'
    game=ROOT/'paper_lantern_city_opening_game.ogv'
    gp=probe(game);gv=next(x for x in gp['streams'] if x['codec_type']=='video')
    ga=next(x for x in gp['streams'] if x['codec_type']=='audio')
    assert gv['codec_name']=='theora' and ga['codec_name']=='vorbis'
    assert (gv['width'],gv['height'])==(1776,936) and gv['r_frame_rate']=='30/1'
    count=json.loads(run([FFPROBE,'-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=nb_read_frames','-of','json',game]))
    # Theora legitimately omits identical displayed frames. Decode strictly and
    # reconstruct the 30fps presentation clock to check the whole 90s timeline.
    decoded=run([FFMPEG,'-v','error','-xerror','-err_detect','explode','-i',game,'-vf','fps=30','-progress','pipe:1','-f','null','-'])
    presentation=re.findall(r'^frame=(\d+)',decoded,re.MULTILINE)
    assert presentation and int(presentation[-1])==2700
    report['game_export']={'resolution':[gv['width'],gv['height']],'fps':gv['r_frame_rate'],'decoded_distinct_frames':int(count['streams'][0]['nb_read_frames']),'presentation_frames':2700,'strict_decode_errors':0,'video_codec':gv['codec_name'],'audio_codec':ga['codec_name'],'duration':gp['format']['duration']}
    (qa/'technical_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    # Provenance includes new media only, with no copied historical assets.
    audio_files = sorted((ROOT / 'audio').glob('*.wav'))
    audio_files = [path for path in audio_files if path.name != 'mix_pre.wav' and not path.name.startswith('voice_fitted_')]
    files=list((ROOT/'keyframes').glob('*.png'))+list((ROOT/'sources').glob('*.mp4'))+audio_files+[ROOT/'opening_zh.srt',ROOT/'opening_subtitles.json',final,ROOT/'paper_lantern_city_opening_clean.mp4',ROOT/'paper_lantern_city_opening_game.ogv']
    manifest={'original_media_only':True,'external_media_inputs':[],'files':[{'path':str(x.relative_to(ROOT)).replace('\\','/'),'bytes':x.stat().st_size,'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in files]}
    (ROOT/'asset_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('step',choices=['audio','video','shots','normalize','game','audit','all']);ap.add_argument('--only');args=ap.parse_args()
    if args.step=='game':export_game()
    if args.step=='normalize':normalize()
    if args.step in ['audio','all']:audio()
    if args.step in ['video','shots','all']:video(args.step=='shots',args.only)
    if args.step in ['audit','all']:audit()
