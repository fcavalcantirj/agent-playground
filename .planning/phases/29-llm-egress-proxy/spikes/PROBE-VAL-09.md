# PROBE-VAL-09

## PROBE-VAL-09: idempotency_keys table shape (current + AMD-03 delta)

### Columns
```json
[
  {
    "column_name": "id",
    "data_type": "uuid",
    "is_nullable": "NO",
    "column_default": "gen_random_uuid()"
  },
  {
    "column_name": "user_id",
    "data_type": "uuid",
    "is_nullable": "NO",
    "column_default": null
  },
  {
    "column_name": "key",
    "data_type": "text",
    "is_nullable": "NO",
    "column_default": null
  },
  {
    "column_name": "run_id",
    "data_type": "text",
    "is_nullable": "YES",
    "column_default": null
  },
  {
    "column_name": "verdict_json",
    "data_type": "jsonb",
    "is_nullable": "NO",
    "column_default": null
  },
  {
    "column_name": "request_body_hash",
    "data_type": "text",
    "is_nullable": "NO",
    "column_default": null
  },
  {
    "column_name": "created_at",
    "data_type": "timestamp with time zone",
    "is_nullable": "NO",
    "column_default": "now()"
  },
  {
    "column_name": "expires_at",
    "data_type": "timestamp with time zone",
    "is_nullable": "NO",
    "column_default": null
  }
]
```

### Indexes
```json
[
  {
    "indexname": "idempotency_keys_pkey",
    "indexdef": "CREATE UNIQUE INDEX idempotency_keys_pkey ON public.idempotency_keys USING btree (id)"
  },
  {
    "indexname": "uq_idempotency_keys_user_key",
    "indexdef": "CREATE UNIQUE INDEX uq_idempotency_keys_user_key ON public.idempotency_keys USING btree (user_id, key)"
  },
  {
    "indexname": "idx_idempotency_expires",
    "indexdef": "CREATE INDEX idx_idempotency_expires ON public.idempotency_keys USING btree (expires_at)"
  }
]
```

### Constraints
```json
[
  {
    "conname": "idempotency_keys_pkey",
    "def": "PRIMARY KEY (id)"
  },
  {
    "conname": "uq_idempotency_keys_user_key",
    "def": "UNIQUE (user_id, key)"
  },
  {
    "conname": "idempotency_keys_user_id_fkey",
    "def": "FOREIGN KEY (user_id) REFERENCES users(id)"
  }
]
```

### Phase 29 proxy column requirements
- user_id present: **True**
- key present: **True**
- request_body_hash present: **True**
- verdict_json present: **True** (nullable: NO)
- expires_at present: **True** (24h TTL slot)

### Migration-013 delta (AMD-03 reserved-row strategy)
Required additions to support the in-flight reservation pattern:

- ADD `status` column (text) with CHECK constraint allowing
  values: `'in_flight' | 'success' | 'failed'`. Default: `'in_flight'`.
  Currently present: **False** (must be added by migration 013)
- ALTER `verdict_json` to NULLABLE (placeholder rows store NULL
  until the upstream call lands).
  Current nullability: **NO** (currently NOT NULL → must be relaxed)

- Optional but recommended index on `status` for the watchdog
  cleanup task (`SELECT ... WHERE status='in_flight' AND expires_at < NOW()`).

### Verdict reasoning
- Phase-29 base columns present: **True**
- Migration-013 delta enumerated (status column + verdict_json NULLABLE).

VERDICT: PASS
