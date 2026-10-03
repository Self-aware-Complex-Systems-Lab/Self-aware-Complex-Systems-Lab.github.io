import sys
from playwright.sync_api import sync_playwright
url=sys.argv[1]
with sync_playwright() as pw:
    b=pw.chromium.launch(); p=b.new_page(viewport={"width":1440,"height":1000})
    p.goto(url,wait_until="networkidle"); p.wait_for_timeout(4000)
    for f in p.frames:
        try: t=f.evaluate("document.body?document.body.innerText:''")
        except Exception as e: t=repr(e)
        print("FRAME",f.url[:150],len(t)); print(t[:1500])
    b.close()
