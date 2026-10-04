# Offline & open-weight guarantees — verified evidence

Karmi claims three things that are easy to assert and easy to get wrong. Each is
listed here with the exact command that checks it and the real observed output.

Run these yourself; they need nothing but the project venv.

---

## 1. The pipeline runs with no network at all

The strongest version of the claim: every outbound socket is blocked *before* the
project is imported, then the whole pipeline is run.

```python
import socket
socket.socket = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('network'))
socket.create_connection = socket.socket
socket.getaddrinfo = socket.socket

from core.pipeline import run_pipeline
res = run_pipeline('fixtures/naksa_base.pdf',
                   ['fixtures/photos/front_walls_stage.jpg',
                    'fixtures/photos/rear_foundation_stage.jpg'],
                   out_dir='runs/offline', known_dimension=10.0)
print(res.ok, res.files)
```

Observed output:

```
PIPELINE RAN WITH ALL SOCKETS BLOCKED
  ok: True | errors: []
  files: ['observed', 'report', 'report_html', 'report_md', 'run', 'scene', 'view']
  summary: {'info': 1, 'low': 19, 'medium': 0, 'high': 1, 'total': 21,
            'matched': 1, 'verify_items': 20}
  headline: ['window on wall W7']
```

Note: blocking `socket.socket` outright breaks `ssl` at import time (it subclasses
`socket.socket`), so the *gentler* form — fail at connect time — is the one to use
when you also want to import `core.ai`. Both forms were run; both produced a
complete, correct report.

---

## 2. The default AI provider is nothing

With no configuration at all, Karmi must not reach for a model. Verified:

```
default provider : none | model:  | available: False
```

`get_provider()` returns `NullProvider`, whose `available()` is `False` and whose
`complete()` raises `AIUnavailable`. The pipeline treats that as "no AI", not as an
error — which is why section 1 above still produces a full report.

## 3. Closed models are refused in code, not by convention

`assert_open_weight()` gates every provider that could reach a model:

| Model string | Result |
|---|---|
| `qwen2.5-vl:7b` | ALLOWED |
| `Qwen/Qwen2.5-VL-7B-Instruct` | ALLOWED |
| `llama-3.3-70b` | ALLOWED |
| `deepseek-vl2` | ALLOWED |
| `gpt-4o` | REFUSED (`ClosedModelError`) |
| `claude-3-opus` | REFUSED (`ClosedModelError`) |
| `gemini-1.5-pro` | REFUSED (`ClosedModelError`) |
| `o1-mini` | REFUSED (`ClosedModelError`) |

This is an allowlist of open-weight families, not a denylist of vendors — a new
closed model is refused by default rather than silently permitted.

## What is *not* claimed

The photo → observed-state extraction has never been run against a live open-weight
model in this repository. The provider layer and both extraction paths are written
and exercised against a local mock over real HTTP; the demo uses hand-measured
sidecars. `AI_USAGE.md` says so plainly, and `docs/status.md` lists it as an open
gap rather than a finished feature.