package session

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Session lifecycle status constants. These values are the domain
// vocabulary the 002_sessions.sql partial unique index uses for its
// "active" predicate: pending, provisioning, running. A session in any
// of those three states counts against the 1-active-per-user cap.
const (
	StatusPending      = "pending"
	StatusProvisioning = "provisioning"
	StatusRunning      = "running"
	StatusStopping     = "stopping"
	StatusStopped      = "stopped"
	StatusFailed       = "failed"
)

// ErrConflictActive is returned by Store.Create when the Postgres
// partial unique index idx_sessions_one_active_per_user fires. The
// handler layer (Plan 05) translates this to HTTP 409 Conflict.
var ErrConflictActive = errors.New("user already has an active session")

// pgUniqueViolation is the Postgres SQLSTATE code for unique constraint
// violations. Store.Create inspects pgconn.PgError for this value to
// distinguish "concurrent double-create" from "unrelated DB error".
const pgUniqueViolation = "23505"

// Session is the in-memory mirror of a row in the sessions table. It
// deliberately does NOT include every column the 002_sessions.sql
// migration declares — Phase 5 will bring ExpiresAt / HeartbeatAt /
// BillingMode into scope. Phase 2 only needs what the session
// lifecycle state machine reads and writes.
type Session struct {
	ID            uuid.UUID
	UserID        uuid.UUID
	RecipeName    string
	ModelProvider string
	ModelID       string
	ContainerID   *string
	Status        string
	CreatedAt     time.Time
	UpdatedAt     time.Time
}

// Store is a thin CRUD layer over the sessions table. It is NOT a
// DAO/repository with business logic — lifecycle transitions and
// one-active enforcement live in the handler + bridge layer (Plan 05).
// This struct exists only so handler code never touches SQL directly.
type Store struct {
	db *pgxpool.Pool
}

// NewStore returns a Store backed by the given pgxpool. The pool must
// already be open and have survived the migrator run (Phase 1 handles
// that during server startup).
func NewStore(db *pgxpool.Pool) *Store {
	return &Store{db: db}
}

// Create inserts a new session row with status='pending' and returns
// the populated Session. If the partial unique index fires (the user
// already has an active session), Create returns ErrConflictActive.
//
// The RETURNING clause fetches the server-generated id, created_at,
// and updated_at so callers never have to round-trip.
func (s *Store) Create(ctx context.Context, userID uuid.UUID, recipe, provider, modelID string) (*Session, error) {
	const q = `
		INSERT INTO sessions (user_id, recipe_name, model_provider, model_id, status)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING id, created_at, updated_at
	`
	var sess = Session{
		UserID:        userID,
		RecipeName:    recipe,
		ModelProvider: provider,
		ModelID:       modelID,
		Status:        StatusPending,
	}
	err := s.db.QueryRow(ctx, q, userID, recipe, provider, modelID, StatusPending).
		Scan(&sess.ID, &sess.CreatedAt, &sess.UpdatedAt)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == pgUniqueViolation {
			return nil, ErrConflictActive
		}
		return nil, fmt.Errorf("session store: create: %w", err)
	}
	return &sess, nil
}

// Get returns the session row for the given id, or (nil, nil) if no
// such row exists. Callers must NOT treat a nil result as an error —
// 404 is a handler-layer concern.
func (s *Store) Get(ctx context.Context, id uuid.UUID) (*Session, error) {
	const q = `
		SELECT id, user_id, recipe_name, model_provider, model_id,
		       container_id, status, created_at, updated_at
		FROM sessions
		WHERE id = $1
	`
	var sess Session
	err := s.db.QueryRow(ctx, q, id).Scan(
		&sess.ID,
		&sess.UserID,
		&sess.RecipeName,
		&sess.ModelProvider,
		&sess.ModelID,
		&sess.ContainerID,
		&sess.Status,
		&sess.CreatedAt,
		&sess.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, nil
		}
		return nil, fmt.Errorf("session store: get %s: %w", id, err)
	}
	return &sess, nil
}

// UpdateStatus transitions a session to a new status value and bumps
// updated_at. It does NOT validate the state machine — the handler
// layer owns that. Returns an error if the row does not exist or the
// query fails.
func (s *Store) UpdateStatus(ctx context.Context, id uuid.UUID, status string) error {
	const q = `UPDATE sessions SET status = $1, updated_at = NOW() WHERE id = $2`
	tag, err := s.db.Exec(ctx, q, status, id)
	if err != nil {
		return fmt.Errorf("session store: update status %s: %w", id, err)
	}
	if tag.RowsAffected() == 0 {
		return fmt.Errorf("session store: update status %s: no such session", id)
	}
	return nil
}

// UpdateContainer writes both the container_id and a new status in a
// single UPDATE. Plan 05's handler uses this right after the docker
// runner returns a container ID so the transition from 'provisioning'
// to 'running' is atomic with the ID assignment.
func (s *Store) UpdateContainer(ctx context.Context, id uuid.UUID, containerID, status string) error {
	const q = `
		UPDATE sessions
		SET container_id = $1, status = $2, updated_at = NOW()
		WHERE id = $3
	`
	tag, err := s.db.Exec(ctx, q, containerID, status, id)
	if err != nil {
		return fmt.Errorf("session store: update container %s: %w", id, err)
	}
	if tag.RowsAffected() == 0 {
		return fmt.Errorf("session store: update container %s: no such session", id)
	}
	return nil
}
