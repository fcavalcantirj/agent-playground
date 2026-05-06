# PROBE-VAL-10

## PROBE-VAL-10: Docker bridge IP refresh strategy

- network used: `deploy_default`

- initial IP on `deploy_default`: `172.18.0.9`
- IP after restart on `deploy_default`: `172.18.0.9`
- IP changed on restart: **False**
- restart wall-time: 0.228s

### Events observed during restart window
- count: 4
```json
[
  {
    "Action": "start",
    "id_short": "30eec330f213",
    "from": "nginx:alpine"
  },
  {
    "Action": "stop",
    "id_short": "30eec330f213",
    "from": "nginx:alpine"
  },
  {
    "Action": "die",
    "id_short": "30eec330f213",
    "from": "nginx:alpine"
  },
  {
    "Action": "start",
    "id_short": "30eec330f213",
    "from": "nginx:alpine"
  }
]
```

### Strategy decision
- **DECISION: events() subscription** is viable on this platform (events arrived in real-time during the restart window). The proxy should subscribe to `start`/`die`/`destroy` events and refresh the IP→user map on every event — no 60s polling fallback needed.

### Verdict reasoning
- IP behavior documented: **True**
- events() viability empirically established: **True** (4 events observed)

VERDICT: PASS
