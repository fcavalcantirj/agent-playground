package temporal

import (
	"fmt"

	"github.com/rs/zerolog"
	"go.temporal.io/sdk/client"
	tlog "go.temporal.io/sdk/log"
	"go.temporal.io/sdk/worker"
)

// Task-queue names are shared between the Go API (as worker pollers) and any
// workflow submission site. Exported so cmd/server/main.go, future handlers,
// and tctl verifications can all reference the same constants.
const (
	SessionQueue        = "session"
	BillingQueue        = "billing"
	ReconciliationQueue = "reconciliation"
)

// Workers bundles the Temporal client with its three workers so the caller
// (cmd/server/main.go) has a single object to Start, Stop, and hand to
// server.WithWorkers. Implements the server.Workers interface declared in
// api/internal/server/server.go (Start() error; Stop()).
type Workers struct {
	Client  client.Client
	workers []worker.Worker
	logger  zerolog.Logger
}

// NewWorkers dials the Temporal server at temporalHost within namespace and
// builds three workers: session / billing / reconciliation. Each worker is
// registered with the workflows and activities it owns. The returned Workers
// is ready to Start().
//
// Returns an error without leaking a partially-built client if the dial fails.
func NewWorkers(temporalHost, namespace string, logger zerolog.Logger) (*Workers, error) {
	c, err := client.Dial(client.Options{
		HostPort:  temporalHost,
		Namespace: namespace,
		Logger:    newZerologAdapter(logger),
	})
	if err != nil {
		return nil, fmt.Errorf("temporal client dial %q ns=%q: %w", temporalHost, namespace, err)
	}

	w := &Workers{
		Client: c,
		logger: logger.With().Str("component", "temporal-workers").Logger(),
	}

	// ---- Session worker: every workflow a user-facing session submits ----
	sessionWorker := worker.New(c, SessionQueue, worker.Options{})
	sessionWorker.RegisterWorkflow(PingPong)
	sessionWorker.RegisterWorkflow(SessionSpawn)
	sessionWorker.RegisterWorkflow(SessionDestroy)
	sessionWorker.RegisterWorkflow(RecipeInstall)
	sessionWorker.RegisterActivity(PingActivity)
	sessionWorker.RegisterActivity(SpawnContainerActivity)
	sessionWorker.RegisterActivity(DestroyContainerActivity)
	sessionWorker.RegisterActivity(InstallRecipeActivity)
	w.workers = append(w.workers, sessionWorker)

	// ---- Billing worker: credit ledger reconciliation ----
	billingWorker := worker.New(c, BillingQueue, worker.Options{})
	billingWorker.RegisterWorkflow(ReconcileBilling)
	w.workers = append(w.workers, billingWorker)

	// ---- Reconciliation worker: container state drift healing ----
	reconWorker := worker.New(c, ReconciliationQueue, worker.Options{})
	reconWorker.RegisterWorkflow(ReconcileContainers)
	w.workers = append(w.workers, reconWorker)

	return w, nil
}

// Start starts all registered workers. Each worker.Start is non-blocking and
// spawns its own background pollers. If any worker fails to start the method
// returns the first error without attempting to stop the already-started
// workers -- the caller is expected to treat that as fatal and exit the
// process, at which point the Temporal client cleanup happens in defer Stop().
func (w *Workers) Start() error {
	for i, wr := range w.workers {
		if err := wr.Start(); err != nil {
			return fmt.Errorf("temporal worker %d start: %w", i, err)
		}
	}
	w.logger.Info().
		Int("workers", len(w.workers)).
		Msg("temporal workers started")
	return nil
}

// Stop gracefully stops all workers and closes the Temporal client. Safe to
// call on a nil receiver's workers list: a freshly-built Workers whose Start
// has not yet been called can still be Stopped, and the client Close is the
// cleanup.
func (w *Workers) Stop() {
	for _, wr := range w.workers {
		wr.Stop()
	}
	if w.Client != nil {
		w.Client.Close()
	}
	w.logger.Info().Msg("temporal workers stopped")
}

// --- zerolog adapter for Temporal's log.Logger interface --------------------

// zerologAdapter implements go.temporal.io/sdk/log.Logger by delegating to
// zerolog. Temporal's interface passes alternating key/value pairs; we fan
// them out onto a zerolog event via the Fields helper.
type zerologAdapter struct {
	logger zerolog.Logger
}

// Compile-time assertion: the adapter must satisfy Temporal's Logger interface.
var _ tlog.Logger = (*zerologAdapter)(nil)

func newZerologAdapter(l zerolog.Logger) *zerologAdapter {
	return &zerologAdapter{
		logger: l.With().Str("component", "temporal").Logger(),
	}
}

func (z *zerologAdapter) Debug(msg string, keyvals ...interface{}) {
	z.logger.Debug().Fields(kvSlice(keyvals)).Msg(msg)
}

func (z *zerologAdapter) Info(msg string, keyvals ...interface{}) {
	z.logger.Info().Fields(kvSlice(keyvals)).Msg(msg)
}

func (z *zerologAdapter) Warn(msg string, keyvals ...interface{}) {
	z.logger.Warn().Fields(kvSlice(keyvals)).Msg(msg)
}

func (z *zerologAdapter) Error(msg string, keyvals ...interface{}) {
	z.logger.Error().Fields(kvSlice(keyvals)).Msg(msg)
}

// kvSlice normalizes the keyvals variadic into what zerolog.Event.Fields
// expects: either a map[string]interface{} or a []interface{}. We hand it the
// slice form, but only when the length is even -- an odd-length keyvals is a
// caller bug (Temporal SDK itself never emits one), so we pad with a
// placeholder key rather than panic.
func kvSlice(keyvals []interface{}) []interface{} {
	if len(keyvals)%2 == 1 {
		keyvals = append(keyvals, "(MISSING)")
	}
	return keyvals
}
