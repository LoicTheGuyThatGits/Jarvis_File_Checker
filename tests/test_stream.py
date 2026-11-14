import json, random, importlib.util, sys
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
R=srv.ReplyStreamer
cases=[
 {"reply":"Good day, sir.","action":None},
 {"reply":"Line1\nLine \"quoted\" \\ back/slash\ttab 😀 emoji é ü 日本語","action":{"type":"open_url","url":"https://x.com"}},
 {"action":{"type":"save_code","filename":"a.py","code":"print(\"{\\\"reply\\\": 1}\")\n"},"reply":"Saved after action, sir."},
 {"reply":"","action":None},
 {"reply":"x"*500,"action":None},
]
random.seed(1)
for ensure in (True,False):
  for c in cases:
    full=json.dumps(c,ensure_ascii=ensure)
    for trial in range(300):
        st=R(); out=""; i=0
        while i<len(full):
            k=random.randint(1,7); out+=st.feed(full[i:i+k]); i+=k
        assert out==c["reply"],(ensure,c["reply"][:30],out[:60])
# pretty-printed / spaced JSON
full=json.dumps({"action":None,"reply":"hi there"},indent=2)
st=R();out="".join(st.feed(ch) for ch in full);assert out=="hi there",out
# non-JSON never emits
st=R();assert "".join(st.feed(ch) for ch in "Sure thing, sir.")==""
print("streamer OK")
