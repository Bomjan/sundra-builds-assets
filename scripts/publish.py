"""Daily Sundra Builds graphic generator and Facebook publisher.
Requires OPENAI_API_KEY and UPLOAD_POST_API_KEY GitHub Actions secrets.
Fails closed on uncertain image validation or ambiguous publishing results.
"""
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
TODAY = dt.datetime.now(dt.timezone(dt.timedelta(hours=6))).date().isoformat()
TOPICS = [
    ("java-dsa", "Why binary search needs sorted data", "Binary search halves the search range only because sorted order tells us which half can be discarded."),
    ("go-backend", "Timeouts are part of API design", "In Go, propagate request context so downstream operations can be cancelled when clients disconnect."),
    ("software-engineering", "Indexes trade writes for reads", "Database indexes speed up selective queries but add storage and write maintenance."),
    ("one-minute-curiosity", "Why hashes change drastically", "The avalanche effect means changing one input bit can change many output hash bits."),
]
FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
def font(size, bold=False):
    return ImageFont.truetype(FONTS[int(bold)], size)

def get_content(topic):
    category, headline, fact = topic
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY secret is required")
    prompt = ("You write for Sundra Builds. Return ONLY JSON with keys headline, insight, takeaway, caption. "
              "Headline <= 48 chars; insight <= 100; takeaway <= 95. "
              "Use precise natural English, no emojis. Caption 90-150 words. "
              "Be technically correct, avoid unverified statistics. "
              "Topic: " + headline + ". Ground truth: " + fact)
    r = requests.post("https://api.openai.com/v1/chat/completions",
        headers={"Authorization": "Bearer " + key},
        json={"model":"gpt-4.1-mini","messages":[{"role":"user","content":prompt}],
              "response_format":{"type":"json_object"},"temperature":0.35}, timeout=60)
    r.raise_for_status()
    content = json.loads(r.json()["choices"][0]["message"]["content"])
    if any(not isinstance(content.get(k),str) or not content[k].strip()
           for k in ("headline","insight","takeaway","caption")):
        raise ValueError("Incomplete generated content")
    if len(content["headline"]) > 48 or len(content["insight"]) > 100 or len(content["takeaway"]) > 95:
        raise ValueError("Generated content exceeds design limits")
    if any(ord(c)>0xFFFF for c in json.dumps(content)):
        raise ValueError("Unsupported symbol")
    return content

def wrap(draw, text, f, max_width):
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = (current + " " + word).strip()
        if draw.textbbox((0,0),trial,font=f)[2] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = trial
    if current: lines.append(current)
    return lines

def render(content, topic, output):
    im = Image.new("RGB",(1080,1350),"#F5F3EE")
    d = ImageDraw.Draw(im)
    black, grey, accent = "#101114", "#64666A", "#B8E986"
    d.rectangle((0,0,1080,16),fill=accent)
    d.text((76,70),"FIELD NOTES   /   " + topic[0].upper(),font=font(23,True),fill=grey)
    y=205
    for line in wrap(d,content["headline"],font(74,True),920):
        d.text((76,y),line,font=font(74,True),fill=black)
        y+=98
    if y>510: raise ValueError("Headline overflows")
    d.line((76,530,1004,530),fill=black,width=3)
    d.text((76,583),"THE IDEA",font=font(25,True),fill=grey)
    y=648
    for line in wrap(d,content["insight"],font(40),910):
        d.text((76,y),line,font=font(40),fill=black)
        y+=62
    if y>930: raise ValueError("Insight overflows")
    # Meaningful conceptual diagram: shrinking search-space / request boundaries / index lookup.
    d.rounded_rectangle((76,947,1004,1100),radius=18,fill=black)
    if topic[0]=="java-dsa":
        for i,w in enumerate((800,400,200,100)):
            d.rounded_rectangle((112,972+i*29,112+w,988+i*29),radius=4,fill=accent if i==3 else "#90929A")
    else:
        for i in range(4):
            d.rounded_rectangle((120+i*220,995,270+i*220,1052),radius=10,outline=accent,width=3)
            if i<3:d.line((273+i*220,1023,330+i*220,1023),fill=accent,width=4)
    d.text((76,1145),"TAKEAWAY",font=font(22,True),fill=grey)
    for i,line in enumerate(wrap(d,content["takeaway"],font(28,True),920)):
        d.text((76,1180+i*36),line,font=font(28,True),fill=black)
    if i>1: raise ValueError("Takeaway overflows")
    d.line((76,1281,1004,1281),fill="#CCCCCC",width=2)
    d.text((76,1297),"Sundra Builds",font=font(23,True),fill=black)
    output.parent.mkdir(parents=True,exist_ok=True)
    im.save(output,optimize=True)
    with Image.open(output) as check:
        assert check.size==(1080,1350) and check.format=="PNG"

def main():
    idx=(dt.date.fromisoformat(TODAY)-dt.date(2026,10,26)).days % len(TOPICS)
    topic=TOPICS[idx]
    slug=re.sub(r"[^a-z0-9]+","-",topic[1].lower()).strip("-")
    target=ROOT/"posts"/f"{TODAY}-{slug}.png"
    record=ROOT/"records"/f"{TODAY}.json"
    if record.exists() or target.exists():
        print("Already generated for this date; refusing duplicate")
        return
    content=get_content(topic)
    render(content,topic,target)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    record.parent.mkdir(exist_ok=True)
    payload={"date":TODAY,"topic":topic[1],"image":str(target.relative_to(ROOT)),
             "sha256":digest,"caption":content["caption"],"status":"prepared"}
    record.write_text(json.dumps(payload,indent=2)+"\n")
    # Commit and push BEFORE passing the public raw GitHub URL to Upload-Post.
    subprocess.run(["git","config","user.name","sundra-builds-bot"],check=True)
    subprocess.run(["git","config","user.email","41898282+github-actions[bot]@users.noreply.github.com"],check=True)
    subprocess.run(["git","add",str(target.relative_to(ROOT)),str(record.relative_to(ROOT))],check=True)
    subprocess.run(["git","commit","-m",f"Prepare Sundra Builds {TODAY}"],check=True)
    subprocess.run(["git","push","origin","HEAD:main"],check=True)
    repo=os.environ["GITHUB_REPOSITORY"]
    url=f"https://raw.githubusercontent.com/{repo}/main/{target.relative_to(ROOT)}"
    response=requests.get(url,timeout=30)
    response.raise_for_status()
    if hashlib.sha256(response.content).hexdigest()!=digest:
        raise RuntimeError("Public image does not match committed PNG")
    key=os.environ.get("UPLOAD_POST_API_KEY")
    if not key: raise RuntimeError("UPLOAD_POST_API_KEY secret is required")
    # Upload-Post photo API: multipart fields, remote image URL.
    # Non-2xx or ambiguous results are NOT automatically retried.
    result=requests.post("https://api.upload-post.com/api/upload_photos",
        headers={"Authorization":"Apikey "+key},
        data={"user":os.getenv("UPLOAD_POST_PROFILE","default"),
              "platform[]":"facebook","title":content["caption"],
              "facebook_page_id":os.environ["FACEBOOK_PAGE_ID"],
              "async_upload":"false"},
        files={"photos[]":("image-url.txt",url.encode(),"text/plain")},
        timeout=120)
    response_body=result.text[:5000]
    payload.update({"status":"submitted_unverified","public_image_url":url,
                    "upload_http_status":result.status_code,"upload_response":response_body})
    if result.ok:
        try:
            data=result.json()
            if data.get("success") is True and (data.get("results") or data.get("post_url")):
                payload["status"]="published_reported"
        except ValueError: pass
    record.write_text(json.dumps(payload,indent=2)+"\n")
    if payload["status"]!="published_reported":
        raise RuntimeError("Publication not verified; inspect records before retrying")
if __name__=="__main__":
    main()
