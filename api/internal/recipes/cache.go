package recipes

import (
	"context"
	"os"
	"os/signal"
	"syscall"

	"github.com/rs/zerolog"
)

// StartSIGHUPWatcher installs a signal handler on SIGHUP and calls
// Loader.Reload on every delivery, returning immediately. The watcher
// goroutine exits when ctx is cancelled; the caller owns ctx lifetime.
//
// Rationale (D-35): ops wants to push a new recipe YAML to the box and
// reload the catalog without bouncing the API process. SIGHUP is the
// conventional Unix signal for "reread config", and since the Loader
// already supports atomic swap under a write lock, wiring a signal
// handler is the smallest possible plumbing.
//
// The handler is deliberately never the primary reload path — callers
// can also call Loader.Reload directly (e.g. from a tests, a future
// admin HTTP endpoint, or a filesystem watcher). SIGHUP is the
// lowest-friction escape hatch and nothing else.
func StartSIGHUPWatcher(ctx context.Context, l *Loader, logger zerolog.Logger) {
	ch := make(chan os.Signal, 1)
	signal.Notify(ch, syscall.SIGHUP)
	go func() {
		defer signal.Stop(ch)
		for {
			select {
			case <-ctx.Done():
				return
			case <-ch:
				if err := l.Reload(ctx); err != nil {
					logger.Error().Err(err).Msg("recipes: SIGHUP reload failed — keeping previous catalog")
				} else {
					logger.Info().Msg("recipes: SIGHUP reload ok")
				}
			}
		}
	}()
}
