"""Optionally make Pages an entry to a complete, same-origin application.

The backend serves the app and owns its HttpOnly login cookies. No credentials
or OAuth callback parameters are relayed through GitHub Pages.
"""
import html
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

origin = os.environ.get('ARENA_APP_ORIGIN', '').rstrip('/')
if origin:
    url = urlsplit(origin)
    if (url.scheme != 'https' or not url.netloc or
            any([url.path, url.query, url.fragment, url.username, url.password])):
        raise ValueError('ARENA_APP_ORIGIN must be an HTTPS origin')
    target = origin + '/'
    encoded = json.dumps(target).replace('<', '\\u003c')
    Path('web/dist/index.html').write_text('''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>Fly Arena · 进入竞技场</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#eeeae1;color:#24372b;font:18px/1.7 system-ui,sans-serif}
main{max-width:36rem;padding:3rem}small{letter-spacing:.2em}h1{font-size:clamp(2rem,7vw,4rem);line-height:1.15}
a{display:inline-block;padding:.8rem 1.5rem;border-radius:2rem;background:#24372b;color:#fff;text-decoration:none}
</style></head><body><main><small>FLY ARENA · OPEN PLAYGROUND</small>
<h1>设计一只果蝇，<br>观察一个生命。</h1>
<p>正在进入试玩竞技场。你可以设计大脑、运行模拟，并通过 NyxID 登录保存自己的果蝇。</p>
<a id="enter" href="''' + html.escape(target, quote=True) + '''">进入竞技场 / Enter arena</a>
</main><script>
const target = ''' + encoded + ''' + window.location.hash;
document.getElementById('enter').href = target;
window.location.replace(target);
</script></body></html>
''')
