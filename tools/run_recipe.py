#!/usr/bin/env python3
"""Minimal Agent Playground recipe runner.

Usage:
    python3 tools/run_recipe.py <recipe.yaml> <prompt> <model>

Reads a recipe in the ap.recipe/v0 format, builds the upstream Dockerfile
if the image is missing, runs the non-interactive invocation with
substituted $PROMPT and $MODEL, applies the stdout filter, and evaluates
the smoke pass_if rule.

This is a minimal, iterative runner. It will grow every time a new agent's
recipe reveals a gap in the format. Today it supports exactly what hermes
needs; tomorrow it may need to support file-backed secrets (picoclaw),
REPL-pty invocation, or other shapes.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


def run(cmd, check=True, capture=False, stream_label=None):
    """Run a command. Returns (rc, stdout, stderr) if capture else rc."""
    if stream_label:
        print(f"  [{stream_label}] $ {' '.join(cmd)}", flush=True)
    result = subprocess.run(
        cmd,
        check=False,
        capture_output=capture,
        text=True,
    )
    if check and result.returncode != 0:
        if capture:
            sys.stderr.write(result.stderr or "")
        raise SystemExit(f"ERROR: command failed (exit {result.returncode}): {' '.join(cmd)}")
    if capture:
        return result.returncode, result.stdout, result.stderr
    return result.returncode


def load_dotenv(path: Path) -> dict:
    """Naive .env parser — KEY=VALUE, ignores comments."""
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def resolve_api_key(recipe: dict, repo_root: Path) -> tuple[str, str]:
    """Return (env_var_name, value). Falls back to .env and common aliases."""
    var_name = recipe["runtime"]["process_env"]["api_key"]
    dotenv = load_dotenv(repo_root / ".env")

    aliases = [var_name, "OPEN_ROUTER_API_TOKEN", "OPENROUTER_API_KEY"]
    for alias in aliases:
        val = os.environ.get(alias) or dotenv.get(alias)
        if val:
            return var_name, val
    raise SystemExit(
        f"ERROR: no API key — set {var_name} (or one of {aliases}) "
        f"in process env or {repo_root}/.env"
    )


def substitute_argv(argv: list[str], prompt: str, model: str) -> list[str]:
    """Replace $PROMPT and $MODEL tokens inside each argv element."""
    subs = {"$PROMPT": prompt, "$MODEL": model}
    out = []
    for arg in argv:
        if arg in subs:
            out.append(subs[arg])
        else:
            # also handle embedded substitution like "prefix-$MODEL-suffix"
            s = arg
            for k, v in subs.items():
                s = s.replace(k, v)
            out.append(s)
    return out


def apply_stdout_filter(raw: str, awk_program: str) -> str:
    """Run the raw stdout through the recipe's awk filter program."""
    proc = subprocess.run(
        ["awk", awk_program],
        input=raw,
        capture_output=True,
        text=True,
    )
    return proc.stdout


def evaluate_pass_if(rule: str, payload: str, name: str, case_insensitive: bool) -> str:
    """Return PASS or FAIL for a given smoke.pass_if rule."""
    if rule == "response_contains_name":
        needle = name
        hay = payload
        if case_insensitive:
            needle = needle.lower()
            hay = hay.lower()
        return "PASS" if needle in hay else "FAIL"
    return f"UNKNOWN(pass_if={rule})"


def main():
    if len(sys.argv) != 4:
        sys.stderr.write(
            "usage: run_recipe.py <recipe.yaml> <prompt> <model>\n"
            "  e.g. run_recipe.py recipes/hermes.yaml 'who are you?' 'openai/gpt-4o-mini'\n"
        )
        return 2

    recipe_path = Path(sys.argv[1]).resolve()
    prompt = sys.argv[2]
    model = sys.argv[3]

    # Repo root = parent of `recipes/` or `tools/`
    repo_root = recipe_path.parent.parent

    recipe = yaml.safe_load(recipe_path.read_text())
    name = recipe["name"]

    # Only `upstream_dockerfile` build mode is supported today.
    build_mode = recipe["build"].get("mode", "upstream_dockerfile")
    if build_mode != "upstream_dockerfile":
        raise SystemExit(f"ERROR: unsupported build.mode: {build_mode}")

    repo_url = recipe["source"]["repo"]
    ref = recipe["source"]["ref"]
    dockerfile = recipe["build"].get("dockerfile", "Dockerfile")
    context_dir = recipe["build"].get("context", ".")

    api_key_var, api_key_val = resolve_api_key(recipe, repo_root)

    image_tag = f"ap-recipe-{name}"
    clone_dir = Path(f"/tmp/ap-recipe-{name}-clone")
    data_dir = Path(tempfile.mkdtemp(prefix=f"ap-recipe-{name}-data-"))

    print(f"=== ap-recipe-runner :: {name} ===", flush=True)
    print(f"  recipe:     {recipe_path}", flush=True)
    print(f"  prompt:     {prompt!r}", flush=True)
    print(f"  model:      {model}", flush=True)
    print(f"  image:      {image_tag}", flush=True)
    print(f"  clone:      {clone_dir}", flush=True)
    print(f"  data_dir:   {data_dir}", flush=True)
    print(f"  api_key:    {api_key_var}=<{len(api_key_val)} chars>", flush=True)

    try:
        # 1. Clone (cached between runs)
        if not clone_dir.exists():
            print("\n--- step 1: clone ---", flush=True)
            run(["git", "clone", "--depth=1", repo_url, str(clone_dir)])
            # Try to pin to the exact ref; fail-soft if shallow clone can't reach it
            if ref:
                print(f"  attempting to pin to {ref[:12]}...", flush=True)
                rc = run(
                    ["git", "-C", str(clone_dir), "fetch", "--depth=1", "origin", ref],
                    check=False,
                )
                if rc == 0:
                    run(["git", "-C", str(clone_dir), "checkout", "FETCH_HEAD"], check=False)
                else:
                    print(f"  WARN: could not fetch pinned ref {ref}, using shallow HEAD", flush=True)
        else:
            print("\n--- step 1: clone (cached) ---", flush=True)

        # 2. Build (cached by image tag)
        rc, _, _ = run(
            ["docker", "image", "inspect", image_tag],
            check=False,
            capture=True,
        )
        if rc != 0:
            print("\n--- step 2: build (image missing, building cold) ---", flush=True)
            print(f"  NOTE: hermes cold build ~7 min. Streaming...", flush=True)
            run([
                "docker", "build",
                "--progress=plain",
                "-t", image_tag,
                "-f", str(clone_dir / dockerfile),
                str(clone_dir / context_dir),
            ])
        else:
            print("\n--- step 2: build (image cached) ---", flush=True)

        # 3. Substitute variables in argv
        print("\n--- step 3: substitute argv ---", flush=True)
        raw_argv = recipe["invoke"]["spec"]["argv"]
        argv = substitute_argv(raw_argv, prompt, model)
        print(f"  raw argv:    {raw_argv}", flush=True)
        print(f"  subbed argv: {argv}", flush=True)

        # 4. Build docker run command
        vol = recipe["runtime"]["volumes"][0]
        container_mount = vol["container"]
        entrypoint = recipe["invoke"]["spec"].get("entrypoint")
        docker_cmd = [
            "docker", "run", "--rm",
            "-e", f"{api_key_var}={api_key_val}",
            "-v", f"{data_dir}:{container_mount}",
        ]
        if entrypoint:
            docker_cmd += ["--entrypoint", entrypoint]
        docker_cmd += [image_tag] + argv

        # 5. Run
        print("\n--- step 4: run ---", flush=True)
        safe_cmd = [a if not a.startswith(f"{api_key_var}=") else f"{api_key_var}=<REDACTED>" for a in docker_cmd]
        print(f"  $ {' '.join(safe_cmd)}", flush=True)
        import time
        t0 = time.time()
        rc, stdout, stderr = run(docker_cmd, check=False, capture=True)
        wall = time.time() - t0
        print(f"  exit: {rc}  wall: {wall:.1f}s", flush=True)

        # 6. Apply stdout_filter
        print("\n--- step 5: stdout_filter ---", flush=True)
        awk_program = recipe["invoke"]["spec"]["stdout_filter"]["program"]
        filtered = apply_stdout_filter(stdout, awk_program)
        print(f"  raw stdout bytes:      {len(stdout)}", flush=True)
        print(f"  filtered payload bytes: {len(filtered)}", flush=True)

        # 7. Evaluate pass_if
        print("\n--- step 6: evaluate ---", flush=True)
        pass_if = recipe["smoke"]["pass_if"]
        case_insensitive = recipe["smoke"].get("case_insensitive", False)
        verdict = evaluate_pass_if(pass_if, filtered, name, case_insensitive)

        # 8. Report
        print()
        print("=" * 70)
        print(f"  VERDICT: {verdict}")
        print(f"  pass_if: {pass_if} (case_insensitive={case_insensitive}, needle={name!r})")
        print(f"  model:   {model}")
        print(f"  exit:    {rc}")
        print(f"  wall:    {wall:.1f}s")
        print("=" * 70)
        print("FILTERED PAYLOAD:")
        print(filtered)
        print("=" * 70)
        if rc != 0 or verdict != "PASS":
            print("RAW STDOUT (last 40 lines):")
            print("\n".join(stdout.splitlines()[-40:]))
            print("-" * 70)
            print("RAW STDERR (last 20 lines):")
            print("\n".join(stderr.splitlines()[-20:]))

        return 0 if verdict == "PASS" else 1

    finally:
        # Teardown: only data_dir. Keep clone + image cached between runs.
        if data_dir.exists():
            run(["rm", "-rf", str(data_dir)], check=False)
        print(f"\n[teardown] cached: image={image_tag} clone={clone_dir}", flush=True)
        print(f"[teardown] removed: data_dir={data_dir}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
