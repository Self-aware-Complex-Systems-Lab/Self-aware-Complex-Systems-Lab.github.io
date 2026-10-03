import sys, json
from playwright.sync_api import sync_playwright
url=sys.argv[1]
JS=r"""() => {
 const res=[]; const imgs=[...document.querySelectorAll('img')].filter(i=>!i.closest('header'));
 for (const img of imgs){
   let el=img, steps=0, txt='';
   while(el && el!==document.body){ el=el.parentElement; steps++; const t=(el.innerText||'').trim(); if(t){txt=t;break;} }
   const sec=img.closest('section'); const r=img.getBoundingClientRect();
   res.push({src:img.src.slice(45,75), nat:[img.naturalWidth,img.naturalHeight], y:Math.round(r.top+scrollY), x:Math.round(r.left), w:Math.round(r.width), steps, cls:el&&el.className, txt:txt.slice(0,70).replace(/\n/g,' | '), secText:(sec?sec.innerText:'').slice(0,50).replace(/\n/g,' | ')});
 } return res;}"""
with sync_playwright() as pw:
    b=pw.chromium.launch(); p=b.new_page(viewport={"width":1440,"height":1000})
    p.goto(url,wait_until="networkidle")
    h=p.evaluate("document.body.scrollHeight")
    for y in range(0,h+1000,500): p.evaluate(f"scrollTo(0,{y})"); p.wait_for_timeout(150)
    p.wait_for_timeout(1500)
    for r in p.evaluate(JS): print(r)
    b.close()
