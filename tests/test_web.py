import importlib.util, urllib.parse as up
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
H=srv.Handler
def t(text):
    a,r=H.explicit_web_request(text); return (a["url"],a.get("browser")) if a else None
cases={
 "open google chrome and search for cats":("https://www.google.com/search?q=cats","chrome"),
 "Open Edge and search for best pizza near me":("https://www.google.com/search?q=best+pizza+near+me","edge"),
 "please open firefox then look up python tutorials":("https://www.google.com/search?q=python+tutorials","firefox"),
 "search for cats on youtube":("https://www.youtube.com/results?search_query=cats",None),
 "search youtube for lofi music":("https://www.youtube.com/results?search_query=lofi+music",None),
 "open youtube and search for funny dogs":("https://www.youtube.com/results?search_query=funny+dogs",None),
 "can you search the web for rtx 2060 super price?":("https://www.google.com/search?q=rtx+2060+super+price",None),
 "google how to boil an egg":("https://www.google.com/search?q=how+to+boil+an+egg",None),
 "search for a good laptop":("https://www.google.com/search?q=a+good+laptop",None),
 "find videos about guitar":("https://www.youtube.com/results?search_query=guitar",None),
 "search wikipedia for Alan Turing":("https://en.wikipedia.org/w/index.php?search=Alan+Turing",None),
 "open stackoverflow":("https://stackoverflow.com/",None),
 "go to the bbc website":("https://www.bbc.com/",None),
 "go to reddit":("https://www.reddit.com/",None),
 "visit example.org":("https://example.org",None),
 "go to the nintendo website":("https://duckduckgo.com/?q=%21ducky+nintendo",None),
 "take me to wired":("https://duckduckgo.com/?q=%21ducky+wired",None),
 "open the cnn website":("https://www.cnn.com/",None),
 "open chrome and go to github":("https://github.com/","chrome"),
}
bad=0
for q,exp in cases.items():
    got=t(q)
    if got!=exp: bad+=1; print("FAIL",q,got,exp)
# must NOT be hijacked
for q in ["what is the meaning of life","open notepad","open chrome","open google chrome","open spotify","search my files for budget","search files named report","find files named report","search for files called x","google chrome","tell me a joke","what's the weather","open the calculator","make a picture of a cat","look up the capital of france"]:
    got=t(q)
    if got: bad+=1; print("HIJACKED",q,got)
print("web ok" if not bad else f"{bad} problems")
