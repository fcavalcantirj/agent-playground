// Package logging holds cross-cutting log infrastructure: writer
// wrappers, hooks, and helpers that every subsystem's zerolog instance
// plugs into. Phase 02.5 introduces the redaction writer as a defence-
// in-depth guard against BYOK key leakage (T-02.5-02).
package logging

import (
	"io"
	"regexp"
)

// redactionPatterns enumerates every secret shape the server must
// never emit into a log line. Each pattern is a standalone regex so
// additions are trivial. Adding a new pattern here is the ONLY way to
// extend redaction — there is no config knob and no run-time overlay.
//
//   - sk-ant-<alphanum+_-, 50+ chars>     Anthropic API key
//   - sk-or-v1-<hex, 64 chars>            OpenRouter API key
//   - ap_session=<value>                  Agent Playground session cookie
var redactionPatterns = []*regexp.Regexp{
	regexp.MustCompile(`sk-ant-[A-Za-z0-9_-]{50,}`),
	regexp.MustCompile(`sk-or-v1-[a-f0-9]{64}`),
	regexp.MustCompile(`ap_session=[A-Za-z0-9+/=_-]+`),
}

// redactionPlaceholder is the opaque string every regex match is
// rewritten to. Using a single constant makes the test matrix and the
// operational grep surface one thing to look for.
const redactionPlaceholder = "<REDACTED>"

// InstallRedactionHook returns an io.Writer wrapper that regex-scrubs
// every known secret shape before bytes reach the underlying sink.
//
// Implemented as a writer wrapper (NOT a zerolog.Hook) because zerolog
// Events are write-only once Msg() is called — wrapping the writer is
// the deterministic way to mutate log bytes before they hit stdout.
// Callers wire it as:
//
//	logger := zerolog.New(logging.InstallRedactionHook(os.Stdout))
//
// Correctness contract:
//   - The returned writer reports the LENGTH OF THE ORIGINAL INPUT p
//     on success, not the length of the post-redaction output. zerolog
//     (and many other loggers) will flag short writes as errors, and
//     redaction legitimately shortens the byte count.
//   - Redaction is applied per Write call. zerolog writes one complete
//     JSON object per call, so a pattern cannot be split across writes
//     by accident. If a future caller streams bytes without that
//     guarantee the wrapper would miss patterns straddling a boundary.
func InstallRedactionHook(w io.Writer) io.Writer {
	return &redactingWriter{inner: w}
}

// redactingWriter is the io.Writer returned by InstallRedactionHook.
// It intentionally has zero visible exports — callers use the Writer
// interface.
type redactingWriter struct {
	inner io.Writer
}

// Write runs every pattern in redactionPatterns against p, substitutes
// the placeholder for each match, and writes the resulting bytes to
// the inner sink. Returns the length of the ORIGINAL p on success so
// zerolog does not report a short write.
func (r *redactingWriter) Write(p []byte) (int, error) {
	out := p
	for _, re := range redactionPatterns {
		out = re.ReplaceAll(out, []byte(redactionPlaceholder))
	}
	if _, err := r.inner.Write(out); err != nil {
		return 0, err
	}
	return len(p), nil
}
