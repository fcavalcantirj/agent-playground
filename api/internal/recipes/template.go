// Package recipes template.go — hardened filesystem template registry.
//
// TemplateRegistry implements the Plan 02.5-02 contract: Render loads
// agents/<recipeID>/templates/<name>.tmpl, rejects every template SSTI /
// path-traversal / DoS vector from 02.5-RESEARCH.md §Pattern 6 & Pitfall 2,
// caches parsed templates by mtime, and renders inside a 5s timeout with a
// 64 KiB output cap.
//
// Threat register: T-02.5-02 (secret leak routing is the caller's
// responsibility), T-02.5-03 (SSTI — closed FuncMap of exactly 5 safe
// functions), T-02.5-03a (path traversal — regex + symlink + prefix check),
// T-02.5-06 (DoS — timeout + limitedWriter cap).
//
// We explicitly do NOT import sprig or any other FuncMap provider — the
// allowlist below is the complete set of helpers available to template
// authors. Adding a sixth function requires a code change and a plan amend.
package recipes

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"text/template"
	"time"
)

// Sentinel errors — callers use errors.Is to distinguish rejection class.
var (
	// ErrTemplatePath signals the template reference failed name-allowlist,
	// symlink, or absolute-prefix validation.
	ErrTemplatePath = errors.New("template path rejected")
	// ErrTemplateSize signals the rendered output would exceed the hard cap.
	ErrTemplateSize = errors.New("template output exceeds cap")
	// ErrTemplateTimeout signals the render wall-clock deadline expired.
	ErrTemplateTimeout = errors.New("template render timeout")
)

// templateNameRE is the on-disk filename allowlist. Lowercase + digits +
// dash + underscore + dot only, must start with a lowercase letter or
// digit (never a dot, so `..` and `.hidden` are rejected), and must end
// in `.tmpl`. No path separators, no uppercase, no shell metacharacters.
//
// Dots inside the stem are allowed so that recipe templates can follow
// the "<config>.yml.tmpl" convention (e.g. security.yml.tmpl). The
// leading-char constraint keeps `../traversal` out because `.` is not in
// the first character class.
//
// This regex is the first of three defense-in-depth path checks; see
// Render for the symlink + absolute-prefix checks.
var templateNameRE = regexp.MustCompile(`^[a-z0-9][a-z0-9._-]*\.tmpl$`)

const (
	// templateMaxBytes is the hard cap on a single rendered output
	// (64 * 1024 = 65536 bytes). Exceeding it returns ErrTemplateSize.
	templateMaxBytes = 64 * 1024
	// templateMaxDuration is the wall-clock timeout for a single render.
	templateMaxDuration = 5 * time.Second
)

// safeFuncs is the CLOSED FuncMap for template rendering. Exactly five
// functions, all string-pure, no I/O, no reflection, no format-string
// surface. Adding a function here is a security review, not a drive-by.
//
// Explicitly absent (for grep-gate auditability): exec, include, printf,
// js, html, readFile, env. The sprig library is NOT imported anywhere
// in this package.
var safeFuncs = template.FuncMap{
	"default": func(def, v any) any {
		if v == nil {
			return def
		}
		if s, ok := v.(string); ok && s == "" {
			return def
		}
		return v
	},
	"quote": func(s string) string { return strconv.Quote(s) },
	"lower": strings.ToLower,
	"upper": strings.ToUpper,
	"trim":  strings.TrimSpace,
}

// TemplateRegistry renders filesystem-backed agent templates. It is
// safe for concurrent use; parsed templates are cached behind an
// RWMutex keyed by absolute path + file mtime.
type TemplateRegistry struct {
	root string // points at "agents/" (or a temp dir in tests)

	mu    sync.RWMutex
	cache map[string]cachedTmpl

	// parseCount is a test-only counter. It is incremented every time the
	// registry re-parses a template from disk (cache miss or mtime bump).
	// Exposed via ParseCountForTest so TestCache_MtimeInvalidates can
	// assert the cache actually invalidates.
	parseCount int
}

type cachedTmpl struct {
	mtime time.Time
	tmpl  *template.Template
}

// NewTemplateRegistry returns a registry rooted at `root`, where each
// recipe lives under `root/<recipeID>/templates/`. `root` is typically
// the repo `agents/` directory but tests pass a t.TempDir().
func NewTemplateRegistry(root string) *TemplateRegistry {
	return &TemplateRegistry{
		root:  root,
		cache: make(map[string]cachedTmpl),
	}
}

// ParseCountForTest returns the number of times the registry re-parsed a
// template from disk. This is the ONLY test-only surface — production
// callers MUST NOT depend on it.
func (r *TemplateRegistry) ParseCountForTest() int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.parseCount
}

// Render resolves `name` (base filename WITHOUT the `.tmpl` suffix, per
// the RecipeAuthFileDecl.Template convention) to an on-disk template
// under agents/<recipeID>/templates/, validates every security check,
// executes the template with `data` in a bounded goroutine, and returns
// the rendered string.
//
// Errors are wrapped with one of three sentinels that callers can
// type-assert with errors.Is: ErrTemplatePath, ErrTemplateSize,
// ErrTemplateTimeout. All other errors (parse, stat, execute) are
// returned as regular wrapped errors.
func (r *TemplateRegistry) Render(
	ctx context.Context,
	recipeID, name string,
	data any,
) (string, error) {
	filename := name + ".tmpl"
	if !templateNameRE.MatchString(filename) {
		return "", fmt.Errorf("%w: %q", ErrTemplatePath, filename)
	}

	dir := filepath.Join(r.root, recipeID, "templates")
	path := filepath.Join(dir, filename)

	// Defense-in-depth check #2: reject symlinks. Lstat (not Stat) so the
	// link itself is inspected, not its target.
	info, err := os.Lstat(path)
	if err != nil {
		return "", fmt.Errorf("template stat: %w", err)
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return "", fmt.Errorf("%w: symlink forbidden: %s", ErrTemplatePath, path)
	}

	// Defense-in-depth check #3: the resolved absolute path must still live
	// inside the absolute template dir. The regex already catches `..`
	// sequences, but keeping this belt-and-suspenders means a future regex
	// loosening cannot introduce a traversal by itself.
	absDir, err := filepath.Abs(dir)
	if err != nil {
		return "", fmt.Errorf("template abs dir: %w", err)
	}
	absPath, err := filepath.Abs(path)
	if err != nil {
		return "", fmt.Errorf("template abs path: %w", err)
	}
	if !strings.HasPrefix(absPath, absDir+string(os.PathSeparator)) {
		return "", fmt.Errorf("%w: path escape: %s", ErrTemplatePath, path)
	}

	// Cache lookup — key is absolute path, invalidation on any mtime
	// change (not just "newer than"; user may revert).
	r.mu.RLock()
	cached, ok := r.cache[absPath]
	r.mu.RUnlock()

	var tmpl *template.Template
	if ok && cached.mtime.Equal(info.ModTime()) {
		tmpl = cached.tmpl
	} else {
		raw, err := os.ReadFile(absPath)
		if err != nil {
			return "", fmt.Errorf("template read: %w", err)
		}
		parsed, err := template.New(filename).
			Funcs(safeFuncs).
			Option("missingkey=error").
			Parse(string(raw))
		if err != nil {
			return "", fmt.Errorf("template parse: %w", err)
		}
		tmpl = parsed
		r.mu.Lock()
		if r.cache == nil {
			r.cache = make(map[string]cachedTmpl)
		}
		r.cache[absPath] = cachedTmpl{mtime: info.ModTime(), tmpl: tmpl}
		r.parseCount++
		r.mu.Unlock()
	}

	// Execute under a hard deadline. text/template.Execute cannot be
	// cancelled mid-run, so we execute on a goroutine and select on the
	// deadline. A malicious template can still burn the goroutine, but the
	// v0.1 trust model (code-reviewed repo recipes only) accepts that; the
	// limitedWriter bounds memory damage regardless.
	execCtx, cancel := context.WithTimeout(ctx, templateMaxDuration)
	defer cancel()

	type result struct {
		s   string
		err error
	}
	ch := make(chan result, 1)
	go func() {
		var buf bytes.Buffer
		lw := &limitedWriter{w: &buf, max: templateMaxBytes}
		err := tmpl.Execute(lw, data)
		ch <- result{s: buf.String(), err: err}
	}()

	select {
	case <-execCtx.Done():
		return "", fmt.Errorf("%w: %v", ErrTemplateTimeout, execCtx.Err())
	case res := <-ch:
		if res.err != nil {
			// If the underlying cause is ErrTemplateSize (from limitedWriter),
			// keep the sentinel intact so callers can errors.Is against it.
			if errors.Is(res.err, ErrTemplateSize) {
				return "", res.err
			}
			return "", fmt.Errorf("template execute: %w", res.err)
		}
		return res.s, nil
	}
}

// limitedWriter wraps an io.Writer and hard-caps cumulative bytes written.
// The first Write that would cross the cap returns (0, ErrTemplateSize);
// no partial write is issued, which keeps the inner buffer clean.
type limitedWriter struct {
	w   io.Writer
	max int
	n   int
}

func (l *limitedWriter) Write(p []byte) (int, error) {
	if l.n+len(p) > l.max {
		return 0, fmt.Errorf("%w: %d bytes", ErrTemplateSize, l.max)
	}
	n, err := l.w.Write(p)
	l.n += n
	return n, err
}
