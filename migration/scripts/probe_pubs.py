from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b=pw.chromium.launch(); p=b.new_page(viewport={"width":1440,"height":1000})
    p.goto("https://sites.google.com/view/scslab-isu/publications",wait_until="networkidle"); p.wait_for_timeout(4000)
    f=[f for f in p.frames if f.url=="about:blank"][0]
    html=f.evaluate("document.documentElement.outerHTML")
    open("migration/archive/publications/embed.html","w").write(html)
    print(len(html)); print(html[:3000])
    b.close()
