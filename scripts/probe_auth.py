#!/usr/bin/env python3
"""probe_auth.py — one-shot probe of chat.z.ai auth state in the replay browser.
Prints JSON: agentNav / signinVisible / composer / hasToken + quick verdict."""
import json, urllib.request, sys, time
sys.path.insert(0, "/home/z/replay2/scripts")
import channel

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=10))
cands = [t for t in tabs if t.get('type') == 'page' and 'chat.z.ai' in t.get('url', '')]
if not cands:
    print(json.dumps({"error": "no chat.z.ai tab"}))
    sys.exit(1)
tab = cands[0]
c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)

JS = r"""(() => {
  try {
    const nav = [...document.querySelectorAll('a, button, [role=button], span, div')].filter(x => /^(Agent|Agents)$/i.test((x.innerText||'').trim()) && x.children.length===0).length;
    const signin = [...document.querySelectorAll('button, a')].filter(x => /sign in|log in/i.test((x.innerText||''))).length;
    const composer = document.querySelector('textarea, [contenteditable=true]');
    const token = !!(localStorage.getItem('token'));
    return JSON.stringify({agentNav: nav>0, signinVisible: signin>0, composer: !!composer, hasToken: token, url: location.href, title: document.title});
  } catch(e) { return 'ERR:' + e.message; }
})()"""
for attempt in range(3):
    r = c.call("Runtime.evaluate", {"expression": JS, "returnByValue": True}, timeout=30)
    v = r.get('result', {}).get('value')
    if v:
        print(v)
        break
    time.sleep(4)
else:
    print(json.dumps({"error": "eval returned nothing (page loading?)"}))
