# PROBE-VAL-15

## PROBE-VAL-15: bridge IP uniqueness scope (`container_status='running'`)

- network used: `deploy_default`
- container A initial IP: `172.18.0.9`
- container B IP (after A stopped): `172.18.0.9`
- IP reuse observed: **True**

### SQL scope filter on `container_status='running'`
- query: `SELECT ... WHERE bridge_ip=$1 AND container_status='running'`
- rows returned: 1
- correct user (B, the running one): **True**
- partial unique index blocks 2nd `running` row with same IP: **True**

### Verdict reasoning
- IP reuse documented (running scope is REAL — empirical test): observed = True
- `container_status='running'` scope filter empirically validated: **True**
- partial unique index `ix_agent_containers_bridge_ip_running` enforces uniqueness among only `running` rows: **True**

### Implication for Plan 29-02 (migration 013) + Plan 29-08 (proxy IP map)
- Migration 013 MUST add `bridge_ip` column to `agent_containers` (INET) AND a partial unique index `ix_agent_containers_bridge_ip_running` on (bridge_ip) WHERE container_status='running'. The proxy's IP→user lookup MUST scope to `WHERE container_status='running'` always — without this, a freshly-stopped user A's IP could be mis-attributed to a freshly-started user B.

VERDICT: PASS
