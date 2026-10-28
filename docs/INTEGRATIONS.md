# Integrations: sending messages into SchoolConnect

Other systems, such as an email forwarder or a WhatsApp Business gateway, can create tickets
by calling one endpoint. A ticket created this way takes **exactly the same path** as a message
from the web form:

1. personal data masked before any AI sees it
2. classification
3. child-safety guardrails
4. audit row
5. auto-assignment
6. staff notifications

```
POST /integrations/inbound-message
Content-Type: application/json
X-Timestamp: <Unix seconds, now>
X-Signature: sha256=<hex HMAC-SHA256 of "<X-Timestamp>.<raw body>" using INBOUND_SECRET>
```

## Body

| Field            | Required | Notes                                                            |
|------------------|----------|------------------------------------------------------------------|
| `channel`        | yes      | `email` or `whatsapp` (stored on the ticket)                     |
| `message`        | yes      | 1 to 4000 characters, exactly as the parent wrote it             |
| `sender_name`    | no       | Seen by staff only; **never** sent to an AI                      |
| `sender_contact` | no       | Email address or phone number. Replies go here (email only for now) |
| `learner_grade`  | no       | `R`, `1` … `12`                                                  |

## Security

- **Shared secret.** Set `INBOUND_SECRET` in `.env` on the server and give the same value to the
  sending system. If it is empty, the endpoint answers `503` and stays disabled.
  To generate one: `python -c "import secrets; print(secrets.token_hex(32))"`.
- **Signature.** HMAC-SHA256 over `"<timestamp>.<raw body bytes>"`.
  - The signature covers the *exact* bytes sent. Re-formatting the JSON after signing breaks it.
  - The timestamp is part of what is signed. So an old signature cannot be reused with a new
    timestamp.
  - Signatures are compared with `hmac.compare_digest`, which takes the same time whichever byte
    differs, so timing does not leak anything.
- **Replay window.** A request whose `X-Timestamp` is more than **5 minutes** from the server
  clock is rejected. This works in both directions, so a fast clock on the sender is also caught.
- **Responses.**

  | Code  | Meaning                                                          |
  |-------|------------------------------------------------------------------|
  | `201` | Created. Returns `reference`, `channel`, `category`, `urgency`, `assigned`. No personal data is echoed back. |
  | `401` | Missing, invalid or old signature                                |
  | `422` | The signature is valid but the body is invalid                   |
  | `503` | No secret is configured                                          |

## Example: signing a request in Python

```python
"""Send one signed message to SchoolConnect. Usage: python send_inbound.py"""
import hashlib
import hmac
import json
import os
import time

import requests

URL = os.environ.get("SCHOOLCONNECT_URL", "http://localhost:8000") + "/integrations/inbound-message"
SECRET = os.environ["INBOUND_SECRET"]          # the same value as on the SchoolConnect server

payload = {"channel": "whatsapp", "message": "Good day, when do Grade 1 applications open?",
           "sender_contact": "parent@example.com"}
body = json.dumps(payload).encode("utf-8")     # sign the EXACT bytes you send
timestamp = str(int(time.time()))
signature = "sha256=" + hmac.new(SECRET.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()

response = requests.post(URL, data=body, timeout=10, headers={
    "Content-Type": "application/json", "X-Timestamp": timestamp, "X-Signature": signature})
print(response.status_code, response.json())
```

## Test vector

Use this to check your own signing code. With:

- secret `demo-secret`
- timestamp `1772438400`
- body `{"channel":"email","message":"Hello"}`, with no spaces

the header must be:

```
X-Signature: sha256=03c4483688681215892e2a9589fba7f7a374bd305aef255767e3d114415a336b
```

`tests/test_inbound.py` checks the same calculation.

## Limitations

- **Exact repeats.** A request repeated unchanged *within* the 5-minute window would create a
  second ticket. A gateway that retries should wait for our `201` first. A list of signatures
  already seen would close this gap (Week 8 backlog).
- **Replies by email only.** Replies go out by email. WhatsApp or SMS contacts are recorded as
  `not_supported` in the outbox, and staff phone the parent instead.
