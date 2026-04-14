// Package docker — naming.go
//
// Deterministic container naming for Agent Playground sessions.
// Format: playground-<user_uuid>-<session_uuid>
//
// Phase 5's reconciliation loop will derive container names from DB rows
// alone: SELECT id, user_id FROM sessions → BuildContainerName → docker ps.
// SBX-09: containers are named deterministically so reconciliation is
// idempotent (CONTEXT D-26).

package docker

import (
	"fmt"
	"strings"

	"github.com/google/uuid"
)

const containerNamePrefix = "playground-"

// BuildContainerName returns the deterministic Docker container name for a
// given (userID, sessionID) pair. Both must be valid RFC-4122 UUIDs.
// Output is exactly 84 characters: 11 prefix + 36 + 1 separator + 36.
func BuildContainerName(userID, sessionID uuid.UUID) string {
	return fmt.Sprintf("%s%s-%s", containerNamePrefix, userID.String(), sessionID.String())
}

// ParseContainerName extracts (userID, sessionID) from a deterministic name.
// Returns an error if the name does not match the expected format.
// Tolerates a leading "/" (Docker Inspect prefixes container names with /).
func ParseContainerName(name string) (userID, sessionID uuid.UUID, err error) {
	name = strings.TrimPrefix(name, "/")
	if !strings.HasPrefix(name, containerNamePrefix) {
		return uuid.Nil, uuid.Nil, fmt.Errorf("docker name: missing prefix in %q", name)
	}
	rest := strings.TrimPrefix(name, containerNamePrefix)
	if len(rest) != 36+1+36 || rest[36] != '-' {
		return uuid.Nil, uuid.Nil, fmt.Errorf("docker name: bad shape %q", name)
	}
	userID, err = uuid.Parse(rest[:36])
	if err != nil {
		return uuid.Nil, uuid.Nil, fmt.Errorf("docker name: bad user uuid: %w", err)
	}
	sessionID, err = uuid.Parse(rest[37:])
	if err != nil {
		return uuid.Nil, uuid.Nil, fmt.Errorf("docker name: bad session uuid: %w", err)
	}
	return userID, sessionID, nil
}

// IsPlaygroundContainerName returns true if the given Docker name belongs
// to the agent-playground (used by Phase 5 reconciliation to filter
// `docker ps`). Tolerates leading "/" from Docker Inspect.
func IsPlaygroundContainerName(name string) bool {
	return strings.HasPrefix(strings.TrimPrefix(name, "/"), containerNamePrefix)
}
