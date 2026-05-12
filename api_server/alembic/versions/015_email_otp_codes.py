"""Magic-link OTP store (2026-05-12).

Adds ``email_otp_codes`` — the at-rest table backing
``POST /v1/auth/email/request`` (insert a hashed code, send raw via
Resend) and ``POST /v1/auth/email/verify`` (look up by (email, code_hash),
check expiry + attempts + consumed_at, mint session on hit).

Schema:

  email           TEXT NOT NULL          — case-normalized lowercase
  code_hash       TEXT NOT NULL          — sha256 hex of the 6-digit code
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
  expires_at      TIMESTAMPTZ NOT NULL   — created_at + 10 min
  consumed_at     TIMESTAMPTZ NULL       — set on first successful verify
  attempts        INT NOT NULL DEFAULT 0 — incremented on every wrong-code
  PRIMARY KEY (email, code_hash)

Indexes:

  PK on (email, code_hash) — hot-path verify lookup (request also queries
  by email-prefix for cooldown; the PK's leading-column prefix covers it).
  Sweeping expired rows is a maintenance concern (cron / future phase);
  no time-based index needed for MVP.

Revision ID: 015_email_otp_codes
Revises: 014_phase_b_ledger_and_tier
Create Date: 2026-05-12
"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "015_email_otp_codes"
down_revision = "014_phase_b_ledger_and_tier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_otp_codes",
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.PrimaryKeyConstraint("email", "code_hash"),
    )
    # Secondary index on (email, created_at DESC) — supports the cooldown
    # check on request (find the most recent code for this email and gate
    # if `created_at > now - 60s`). The PK alone doesn't sort by
    # created_at, so a plain index pays for itself on every request.
    op.create_index(
        "ix_email_otp_codes_email_created",
        "email_otp_codes",
        ["email", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_otp_codes_email_created", table_name="email_otp_codes",
    )
    op.drop_table("email_otp_codes")
