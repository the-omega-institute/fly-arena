"""Write-only-new, payload-preserving presentation patch of frozen r2 HTML."""
from pathlib import Path
import hashlib
import json
import re
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "var/contact-v8"
OUT = ROOT / "var/presentation-correction-v8"
ORIGINAL_SHA = "cf0f827afd81faab3898bff211ce501ff89b05a726633ebab9b6aed94e808212"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def payload(raw):
    start = raw.index(b"<script>const data=") + len(b"<script>const data=")
    end = raw.index(b";\nconst legs=", start)
    return raw[start:end]


def transform(raw):
    if sha(raw) != ORIGINAL_SHA:
        raise ValueError("r2 viewer does not match the reviewed original")
    original_payload = payload(raw)
    text = raw.decode("utf-8")
    replacements = [
        ("<title>Actual contact phenotype · v8</title>",
         "<title>Actual contact phenotype · v8 presentation r3</title>"),
        ("<h1>Actual WT / official / submitted contact phenotype</h1>",
         '<h1>Actual WT / official / submitted contact phenotype</h1>'
         '<p>Presentation r3 · held-input timing and neutral-only phenotype labels. '
         '<a href="correction-manifest.json">Correction provenance</a>.</p>'),
        ("Endpoint traces: 101 frames over 1 s. Input/current read starts every 10 ms;",
         "Endpoint plots retain 101 recorded frames over 1 s. Engineered "
         "voltage-equivalent held input (mV) uses 100 intervals: recorded "
         "current[k+1] from input_time[k] to time[k+1], including paired-control "
         "differences on the same clock, with no interpolation across switches. "
         "Input read starts every 10 ms;"),
        ("<h2>Actual paired subject phenotypes</h2>",
         "<h2>Neutral-only paired subject phenotypes · odor (.55,.55), both states</h2>"
         "<p>Independent of selected plot context. Official/submitted odor OFF "
         "NOT RUN; no OFF A/B/C comparison.</p>"),
        ('href="joint-phenotype-r2.png"', 'href="../contact-v8/joint-phenotype-r2.png"'),
        ('href="verification.json"', 'href="../contact-v8/verification.json"'),
        ('href="registration.json"', 'href="../contact-v8/registration.json"'),
        ("s.y.map((v,k)=>(k?'L':'M')+x(s.t[k]).toFixed(3)+','+y(v).toFixed(3)).join(' ')",
         "s.y.map((v,k)=>s.end?'M'+x(s.t[k]).toFixed(3)+','+y(v).toFixed(3)"
         "+'H'+x(s.end[k]).toFixed(3):(k?'L':'M')+x(s.t[k]).toFixed(3)"
         "+','+y(v).toFixed(3)).join(' ')"),
        ("function render(){", """function heldInput(a,b,i,ch){
if(a.input_time.length!==100||a.time.length!==101||a.current.length!==101)throw Error('Invalid held input lengths');
if(b&&(b.input_time.length!==100||b.time.length!==101||b.current.length!==101))throw Error('Invalid paired lengths');
for(let k=0;k<100;k++){
if(a.input_time[k]!==a.time[k]||!(a.time[k+1]>a.input_time[k]))throw Error('Invalid interval support');
if(b&&(a.input_time[k]!==b.input_time[k]||a.time[k]!==b.time[k]||a.time[k+1]!==b.time[k+1]))throw Error('Paired clock mismatch');
}
return {i,t:a.input_time,end:a.time.slice(1),y:a.current.slice(1).map((v,k)=>v[ch]-(b?b.current[k+1][ch]:0))};
}
function render(){"""),
        ("['current','Afferent external current','mV']",
         "['current','Engineered held input (voltage-equivalent)','mV']"),
        ("active.map(({a,b,i})=>({i,t:a.time,y:a[key].map((v,k)=>v[ch]-(b?b[key][k][ch]:0))}))",
         "active.map(({a,b,i})=>key==='current'?heldInput(a,b,i,ch):"
         "({i,t:a.time,y:a[key].map((v,k)=>v[ch]-(b?b[key][k][ch]:0))}))"),
    ]
    # Validate all anchors before one substitution pass. Payload cannot be an anchor.
    changes = {}
    for old, new in replacements:
        if text.count(old) != 1 or old.encode() in original_payload:
            raise ValueError("Missing, repeated or payload-overlapping anchor: " + old)
        changes[old] = new
    pattern = re.compile("|".join(re.escape(old) for old in changes))
    corrected = pattern.sub(lambda m: changes[m.group()], text).encode("utf-8")
    if payload(corrected) != original_payload:
        raise ValueError("Embedded scientific payload changed")
    return corrected, [{"old": old, "new": new} for old, new in replacements]


def main():
    original = (BASE / "viewer-r2.html").read_bytes()
    corrected, replacements = transform(original)
    # Exclusive directory and files prevent a second pass from overwriting evidence.
    OUT.mkdir()
    intent = {"schema": "contact-v8/presentation-correction-r3", "recorded_utc":
              datetime.now(timezone.utc).isoformat(), "scientific_deviations": [],
              "scope": "Display timing/context and exact-test resource portability only",
              "old_viewer_sha256": sha(original), "exact_replacements": replacements}
    with (OUT / "correction-intent.json").open("x") as f:
        json.dump(intent, f, indent=2)
    with (OUT / "viewer-r3.html").open("xb") as f:
        f.write(corrected)
    sources = [Path(__file__), ROOT / "scripts/validate_contact_v8_r3.cjs",
               ROOT / "tests/conftest.py", ROOT / "docs/CONTACT_PRESENTATION_V8_R3.md"]
    preserved = ["viewer-r2.html", "derived-r2.json", "joint-phenotype-r2.png",
                 "registration.json", "delivery-manifest.json"]
    manifest = {**intent, "entrypoint": "viewer-r3.html", "new_viewer_sha256": sha(corrected),
                "payload_byte_identical": True, "embedded_payload_sha256": sha(payload(original)),
                "embedded_payload_bytes": len(payload(original)),
                "source_sha256": {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sources},
                "preserved_sha256": {"../contact-v8/" + p: sha((BASE / p).read_bytes()) for p in preserved},
                "old_reporters_sha256": {str(p.relative_to(ROOT)): sha(p.read_bytes())
                    for p in (ROOT / "scripts").glob("report_contact_v8*.py") if p != Path(__file__)},
                "frozen_test_sha256": sha((ROOT / "tests/test_contact_v8.py").read_bytes()),
                "validation_entrypoint": "validation.json", "browser_qa": "NOT RUN",
                "figure": "Original neutral PNG unaffected; linked without rerendering"}
    with (OUT / "correction-manifest.json").open("x") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps({"viewer_sha256": sha(corrected), "payload_sha256": sha(payload(corrected)),
                      "replacement_count": len(replacements)}))


if __name__ == "__main__":
    main()
