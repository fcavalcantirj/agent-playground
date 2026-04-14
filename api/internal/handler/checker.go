// Package handler hosts the API's HTTP handlers and the small interfaces
// they depend on (HealthChecker, SessionProvider).
package handler

import "context"

// DBPinger is the minimum surface a Postgres handle must expose to satisfy the
// health checker. Both *database.DB (and any test double) implements it.
type DBPinger interface {
	Ping(ctx context.Context) error
}

// RedisPinger is the minimum surface a Redis client must expose to satisfy the
// health checker.
type RedisPinger interface {
	Ping(ctx context.Context) error
}

// HealthChecker abstracts the dependencies the /healthz handler needs. The
// concrete InfraChecker delegates to a real DB + Redis; tests can pass a fake.
type HealthChecker interface {
	PingDB(ctx context.Context) error
	PingRedis(ctx context.Context) error
}

// InfraChecker is the production HealthChecker. It owns nothing -- callers
// inject the pingers so the same struct works in main.go and in tests.
type InfraChecker struct {
	DB    DBPinger
	Redis RedisPinger
}

// NewInfraChecker wires a DB and Redis pinger into a HealthChecker.
func NewInfraChecker(db DBPinger, rdb RedisPinger) *InfraChecker {
	return &InfraChecker{DB: db, Redis: rdb}
}

// PingDB delegates to the wrapped DB pinger.
func (ic *InfraChecker) PingDB(ctx context.Context) error {
	return ic.DB.Ping(ctx)
}

// PingRedis delegates to the wrapped Redis pinger.
func (ic *InfraChecker) PingRedis(ctx context.Context) error {
	return ic.Redis.Ping(ctx)
}
