"""Recorded audit walkthrough: actual proof artifacts, no simulated live counts."""
import csv
import html
import json
import math
import shutil
import struct
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ASSETS = HERE / "assets"
SCENES = HERE / "compositions"
DURATION = 54
escape = lambda value: html.escape(str(value))

CSS = """
@font-face{font-family:"ZC Inter";src:url("assets/fonts/Inter-400.woff2") format("woff2");font-weight:400}
@font-face{font-family:"ZC Inter";src:url("assets/fonts/Inter-700.woff2") format("woff2");font-weight:700}
*{box-sizing:border-box}#root{position:absolute;inset:0;overflow:hidden;background:#f8f8f2;color:#202820;font-family:"ZC Inter",sans-serif}
.scene-shell{position:absolute;inset:0}.step{position:absolute;left:192px;top:88px;font-size:28px;font-weight:700;letter-spacing:2px;color:#5a6c44}
.title{position:absolute;left:192px;top:137px;right:192px;margin:0;font-size:72px;line-height:1.08;letter-spacing:-2.8px;font-weight:700}
.subtitle{position:absolute;left:192px;top:235px;right:192px;margin:0;font-size:30px;line-height:1.4;color:#536149}
.viewport{position:absolute;left:192px;top:315px;width:1536px;height:580px;overflow:hidden;border:2px solid #d9e3c9;border-radius:14px;background:#edf2df}
.world{position:absolute;left:0;top:0;width:1440px;height:1080px;transform-origin:0 0;will-change:transform}
.world img{display:block;width:1440px;height:1080px}
.disclosure{position:absolute;left:192px;top:930px;margin:0;font-size:32px;line-height:1.2;letter-spacing:.4px;color:#667254}
.proof-panel{position:absolute;left:192px;top:325px;width:1536px;height:555px;border:2px solid #dce7ca;border-radius:14px;background:#fff;padding:46px}
.proof-head{font-size:30px;color:#5f7147;margin:0 0 30px;font-weight:700}
.fact{font-size:58px;line-height:1.16;font-weight:700;letter-spacing:-1.8px;margin:0 0 22px}
.proof-note{font-size:28px;line-height:1.45;color:#536149;margin:0}
.export-table{border-collapse:collapse;width:100%;font-size:28px;text-align:left}
.export-table th{color:#5f7147;font-weight:700;padding:18px 12px;background:#f2f7e7;border-bottom:2px solid #e0e8d5}
.export-table td{padding:19px 12px;border-bottom:1px solid #e5ecda;vertical-align:top;color:#46533c;line-height:1.35}
.export-table td:first-child{width:46%}.export-table td:last-child{width:23%}.export-table tr:last-child td{border-bottom:0}
.final-line{position:absolute;left:192px;top:885px;font-size:37px;font-weight:700;letter-spacing:-.8px;margin:0}
"""

def make_audio():
    rate = 44100
    chords = ((146.832,174.614,220.0),(130.813,164.814,196.0),(174.614,220.0,261.626),(164.814,196.0,246.942))
    marks = (.2,4.15,12.15,22.15,33.15,42.15,49.0)
    with wave.open(str(ASSETS / "bed.wav"),"wb") as output:
        output.setparams((1,2,rate,0,"NONE","not compressed"))
        buffer=bytearray()
        for i in range(DURATION*rate):
            t=i/rate
            chord=chords[int(t/6)%len(chords)]
            gain=min(1,t/1.1,(DURATION-t)/2.2)
            value=sum(math.sin(2*math.pi*f*t) for f in chord)*.010
            value+=math.sin(2*math.pi*chord[0]*.5*t)*.012
            value*=gain*(.82+.18*math.sin(2*math.pi*.30*t))
            for mark in marks:
                age=t-mark
                if 0<=age<.4:
                    value+=.06*math.exp(-age*16)*math.sin(2*math.pi*(660+120*age)*age)
            buffer.extend(struct.pack("<h",max(-32767,min(32767,int(value*32767)))))
            if len(buffer)>rate*2:
                output.writeframes(buffer)
                buffer.clear()
        output.writeframes(buffer)

def scene_html(name,duration,title,subtitle,content,camera=None):
    animation=f"""
      const tl=gsap.timeline({{paused:true}});
      tl.fromTo("#{name}-title",{{x:70,opacity:0}},{{x:0,opacity:1,duration:.6,ease:"power3.out"}},.05);
      tl.fromTo("#{name}-subtitle",{{opacity:0}},{{opacity:1,duration:.5,ease:"power2.out"}},.42);
    """
    if camera:
        start,end=camera
        animation+=(f'tl.fromTo("#{name}-world",{{x:{start[0]},y:{start[1]},scale:{start[2]}}},'
                    f'{{x:{end[0]},y:{end[1]},scale:{end[2]},duration:{duration-1.7},ease:"power2.inOut"}},.7);')
    else:
        animation+=f'tl.fromTo("#{name}-panel",{{y:40,opacity:0}},{{y:0,opacity:1,duration:.7,ease:"power3.out"}},.6);'
    if name=="resume":
        animation+='tl.fromTo("#resume-final",{opacity:0},{opacity:1,duration:.5,ease:"power2.out"},7.5);'
    animation+=f'window.__timelines["{name}"]=tl;'
    return f"""<!doctype html><html><body><template><style>{CSS}</style>
      <div id="root" data-composition-id="{name}" data-width="1920" data-height="1080" data-duration="{duration}">
      <div class="scene-shell"><div class="step">{escape(name.upper())} / RECORDED RUN</div>
      <h1 id="{name}-title" class="title">{escape(title)}</h1>
      <p id="{name}-subtitle" class="subtitle">{escape(subtitle)}</p>{content}
      <p class="disclosure" data-hold="true">Walkthrough of recorded audit • Counts are saved results</p>
      </div></div><script>{animation}</script></template></body></html>"""

def screenshot_content(name,file):
    return (f'<div class="viewport" data-layout-allow-overflow="true"><div id="{name}-world" class="world">'
            f'<img id="{name}-shot" src="assets/{file}" alt="Actual recorded Zombie Check interface"></div></div>')

def main():
    ASSETS.mkdir(exist_ok=True)
    SCENES.mkdir(exist_ok=True)
    for origin,target in ((ROOT/"artifacts/jobs-run-report.json",ASSETS/"audit-report.json"),
                         (ROOT/"artifacts/jobs-resume-proof.json",ASSETS/"resume-proof.json"),
                         (ROOT/"artifacts/jobs-audited.csv",ASSETS/"export.csv"),
                         (ROOT/"examples/jobs-500.csv",ASSETS/"input.csv")):
        shutil.copy2(origin,target)
    audit=json.loads((ASSETS/"audit-report.json").read_text())
    resume=json.loads((ASSETS/"resume-proof.json").read_text())
    assert audit["submission_ready"] and audit["input_rows"]>=500
    assert resume["pass"] and resume["completed_results_unchanged"] and resume["original_rows_unchanged"]
    with (ASSETS/"export.csv").open(encoding="utf-8-sig",newline="") as handle:
        exported=list(csv.DictReader(handle))
    assert len(exported)==audit["output_rows"]
    assert all(row["verdict"] in ("alive","slowing down","zombie") for row in exported)
    (HERE/"facts.json").write_text(json.dumps({"audit":audit,"resume":resume,"duration_seconds":DURATION,
      "source_scope":"Actual recorded audit; screenshot pixels and counts are not simulated."},indent=2))
    make_audio()
    table="".join("<tr><td>"+escape(row["title"])+"</td><td>"+escape(row["verdict"])+"</td><td>"+
                  escape(row["latest_activity_date"] or "Not established")+"</td></tr>" for row in exported[:3])
    output=f"""<div id="export-panel" class="proof-panel"><p class="proof-head">ACTUAL EXPORTED CSV / {audit['input_rows']} original rows retained</p>
      <table class="export-table"><thead><tr><th>Original job title</th><th>New verdict</th><th>Evidence date</th></tr></thead><tbody>{table}</tbody></table>
      <p class="proof-note" style="margin-top:24px">Original columns + verdict + activity date + evidence URLs</p></div>"""
    comparison=f"""<div id="resume-panel" class="proof-panel"><p class="proof-head">ACTUAL SAVED RESUME COMPARISON / jobs-resume-proof.json</p>
      <p class="fact">{resume['baseline_completed']} finished results unchanged</p><p class="fact">{resume['now_completed']} rows complete after resume</p>
      <p class="proof-note">Original rows unchanged: true</p><p class="proof-note">Progress after resume: true</p></div>
      <p id="resume-final" class="final-line">Audit. Inspect. Export.</p>"""
    scenes=[
      ("proof",0,4,f"{audit['input_rows']} job posts. Every row checked.","A real completed run — evidence stays attached.",
       screenshot_content("proof","ui-desktop-ledger.png"),((-130,-245,1.20),(-280,-315,1.42))),
      ("mapping",4,8,"Map the list you already have.","Original titles, employer names, and exact listing URLs.",
       screenshot_content("mapping","ui-desktop-import-preview.png"),((-25,-210,1.00),(-150,-425,1.26))),
      ("signals",12,10,"Five live checks for every posting.","TinySet researches employers; each job is checked independently.",
       screenshot_content("signals","ui-desktop-ledger.png"),((-170,-260,1.22),(-240,-420,1.36))),
      ("evidence",22,11,"Follow each verdict to its sources.","Posting health is checked. Hiring intent remains unverified.",
       screenshot_content("evidence","ui-desktop-evidence.png"),((-1490,-270,2.18),(-1560,-1010,2.27))),
      ("export",33,9,f"{audit['input_rows']} rows in. {audit['output_rows']} rows out.","This preview comes directly from the returned CSV.",output,None),
      ("resume",42,12,"Resume without repeating finished work.","The saved checkpoint was compared with the completed run.",comparison,None)]
    hosts=[]
    for name,start,duration,title,subtitle,content,camera in scenes:
        (SCENES/(name+".html")).write_text(scene_html(name,duration,title,subtitle,content,camera))
        hosts.append(f'<div id="{name}" class="clip" data-composition-id="{name}" data-composition-src="compositions/{name}.html" data-start="{start}" data-duration="{duration}" data-track-index="0" data-track-kind="graphics" data-width="1920" data-height="1080"></div>')
    main_html=f"""<!doctype html><html lang="en" data-composition-variables='[{{"id":"film_title","type":"string","label":"Film title","default":"Zombie Check recorded audit"}}]'>
      <head><meta charset="utf-8"><meta name="viewport" content="width=1920, height=1080"><title>Zombie Check / recorded audit walkthrough</title>
      <script src="assets/gsap.min.js"></script><style>html,body{{margin:0;width:1920px;height:1080px;overflow:hidden;background:#f8f8f2}}
      #root{{position:relative;width:100%;height:100%;overflow:hidden}}.clip{{position:absolute;inset:0}}</style></head>
      <body><div id="root" data-composition-id="main" data-start="0" data-duration="{DURATION}" data-width="1920" data-height="1080">{''.join(hosts)}
      <audio id="recorded-demo-bed" class="clip" src="assets/bed.wav" data-start="0" data-duration="{DURATION}" data-track-index="4" data-volume="1"></audio>
      </div><script>window.__timelines["main"]=gsap.timeline({{paused:true}});</script></body></html>"""
    (HERE/"index.html").write_text(main_html)
    print(json.dumps({"duration":DURATION,"scenes":len(scenes),"input_rows":audit["input_rows"],
      "output_rows":audit["output_rows"],"resume_comparison":resume["pass"]}))

if __name__=="__main__":
    main()
