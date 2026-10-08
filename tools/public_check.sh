#!/usr/bin/env bash
# Is this repository safe to publish?
#
#   bash tools/public_check.sh             by hand, `make public-check`: this checkout — what is staged, the
#                                          tracked files as they stand, and all the history here;
#   bash tools/public_check.sh --pushed    as git's pre-push hook, the refs being pushed on stdin as git hands
#                                          them to it: each commit the push would publish, and nothing of the
#                                          checkout — a run landed on a remote is pushed as a commit this
#                                          checkout never held;
#   bash tools/public_check.sh --commit C  one commit, as a push of it would be judged;
#   bash tools/public_check.sh --install   `make hooks`: have this clone's git run that hook.
#
#   1. nothing private is tracked — .env, secrets/, runtime state, keys, your own descriptors;
#   2. no secret is anywhere in the files or in the history that a push would carry,
#      according to Gitleaks, pinned to one version and run from its own image;
#   3. the scanner is actually working — a control it must reject is fed to it every time, from a
#      temporary directory, so no credential-shaped string is ever committed to prove the point.
#
# The script that judges and the scanner's configuration are this checkout's own: a commit is what is
# judged, never what judges it.
#
# It exits non-zero on the first failure and says what to do. Nothing here is a substitute for
# reading `AGENTS.md`: a gate that is bypassed is not a gate.
set -uo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO="$(cd -- "$HERE/.." && pwd -P)"
SELF="$HERE/${BASH_SOURCE[0]##*/}"
GITLEAKS_VERSION="v8.29.0"
GITLEAKS_IMAGE="ghcr.io/gitleaks/gitleaks:$GITLEAKS_VERSION"
MODE="${1:-}"
COMMIT=""
SHORT=""
FAILED=0

say() { printf '%s %s\n' "$1" "$2"; }
fail() { say "FAIL" "$1"; FAILED=1; }
pass() { say "ok  " "$1"; }
verdict() {
    echo
    if [ "$FAILED" -eq 0 ]; then
        echo "PUBLIC CHECK PASSED${SHORT:+ for commit $SHORT}"
    else
        echo "PUBLIC CHECK FAILED${SHORT:+ for commit $SHORT} - do not push"
    fi
    exit "$FAILED"
}

cd "$REPO" || exit 2

# Git hands a hook the remote's name and URL after its own arguments; nothing here reads them.
if [ "$MODE" = --pushed ]; then set -- --pushed; fi

# Git for Windows runs a hook in its own shell, where the Docker this script needs is as a rule not
# running: the check is handed whole — its arguments and its stdin — to WSL, where the rest of this
# repository's tooling runs. It is handed over in this script's own checkout, named outright: git runs a
# hook at the top of whichever worktree is pushed from, and that worktree's copy of this script judges
# nothing.
case "$(uname -s)" in
    MINGW*|MSYS*)
        if ! command -v wsl.exe >/dev/null 2>&1; then
            fail "on Windows the public check runs in WSL, and wsl.exe is not to be found"
            verdict
        fi
        exec wsl.exe --cd "$(cd "$REPO" && pwd -W)" -e bash tools/public_check.sh "$@" ;;
esac

# ---- the hook, and what it is handed --------------------------------------------------------

if [ "$MODE" = --install ]; then
    # Stated in the clone's git configuration, not written as a file under hooks/. Git runs a hook's file
    # only where it is executable, and a Windows drive that WSL mounts without file modes holds no
    # executable file: measured there, git passes the file by with a hint and pushes. The configuration
    # is read by every git that pushes from the clone, and a hook's file there, if any, still runs.
    #
    # The check it runs is the main checkout's, found through the clone's git directory: a run's
    # worktree holds a copy of its own, and no run judges its own landing.
    command='bash "$(git rev-parse --git-common-dir)/../tools/public_check.sh" --pushed'
    if git config --local --replace-all hook.public-check.event pre-push &&
       git config --local --replace-all hook.public-check.command "$command" &&
       git hook list pre-push 2>/dev/null | grep -q -x public-check; then
        pass "git judges every push from this clone by the public check (hook.public-check, pre-push)"
        exit 0
    fi
    # Git itself was asked whether it would run it: a hook only believed to be there is worse than none.
    git config --local --remove-section hook.public-check 2>/dev/null
    fail "this git runs no hook from its configuration (git 2.54 and later do), so nothing was installed"
    exit 1
fi

if [ "$MODE" = --pushed ]; then
    # One line a ref: <local ref> <local commit> <remote ref> <remote commit>. Each commit is judged by
    # this script run again for it, so one commit's verdict stands apart from the next. Only what failed
    # and the verdict are said, and on stderr, beside git's own words about the push: whoever pushed —
    # a person, or the controller landing a run — reads the refusal first there.
    status=0
    while read -r name commit _; do
        # A ref being deleted publishes nothing.
        [ "$name" = "(delete)" ] && continue
        bash "$SELF" --commit "$commit" </dev/null | grep -v '^ok  ' >&2
        [ "${PIPESTATUS[0]}" -eq 0 ] || status=1
    done
    exit "$status"
fi

SCRATCH="$(mktemp -d)" || exit 2
trap 'rm -rf "$SCRATCH"' EXIT

if [ "$MODE" = --commit ]; then
    if ! COMMIT="$(git rev-parse --verify --quiet "${2:-}^{commit}" 2>/dev/null)"; then
        fail "'${2:-}' is no commit this repository can read, so nothing is known of what it would publish"
        verdict
    fi
    SHORT="${COMMIT:0:12}"
    # The commit's tree, read into an index of its own. Whatever is asked of the index below — what is
    # tracked, and its bytes — is then answered for this commit, and the checkout's own index is neither
    # read nor written.
    export GIT_INDEX_FILE="$SCRATCH/commit-index"
    if ! git read-tree "$COMMIT"; then
        fail "could not read the files of commit $SHORT"
        verdict
    fi
elif [ -n "$MODE" ]; then
    fail "unknown argument: $MODE"
    verdict
fi

# ---- 1. what is tracked ---------------------------------------------------------------------

tracked() { git ls-files -- "$@" 2>/dev/null; }

for path in .env secrets tmp .orchestra/settings.local.json; do
    if [ -n "$(tracked "$path" "$path/**")" ]; then
        fail "$path is tracked; it is private to a machine or generated by a run"
    else
        pass "$path is not tracked"
    fi
done

# Your own repositories, wherever a descriptor file sits: `.orchestra/`, or the root it moved from.
own="$(tracked ':(glob)**/repos.json' || true)"
if [ -n "$own" ]; then
    fail "a repos.json is tracked, and it names your own repositories: $(echo "$own" | tr '\n' ' ')"
else
    pass "no repos.json is tracked"
fi

keys="$(tracked '*.pem' '*.key' '*.p12' '*.pfx' '*.token' | grep -v '^app/interfaces/workbench/static/vendor/' || true)"
if [ -n "$keys" ]; then
    fail "key or token files are tracked: $(echo "$keys" | tr '\n' ' ')"
else
    pass "no key or token files are tracked"
fi

runtime="$(tracked '*.out' '*.err' '*.prompt' '*.events' '*.pid' '*.log' || true)"
if [ -n "$runtime" ]; then
    fail "run artefacts are tracked: $(echo "$runtime" | tr '\n' ' ')"
else
    pass "no run artefacts are tracked"
fi

# Debris of local acceptance: a throwaway repository or probe that must never be committed.
debris="$(tracked '*orchestra-accept*' '*trustprobe*' '*acceptance-*' || true)"
if [ -n "$debris" ]; then
    fail "acceptance debris is tracked: $(echo "$debris" | tr '\n' ' ')"
else
    pass "no acceptance debris is tracked"
fi

# ---- 2. the scanner, and proof that it is working -------------------------------------------

if ! command -v docker >/dev/null 2>&1; then
    fail "docker is needed to run Gitleaks $GITLEAKS_VERSION; install it or run the scanner yourself"
    verdict
fi

# Uncoloured: what it says is read in a terminal, and in a refusal the controller relays to a page.
gitleaks() { docker run --rm -v "$1:/scan:ro" -w /scan "$GITLEAKS_IMAGE" "${@:2}" --no-color; }

control="$SCRATCH/control"
mkdir "$control"

# A credential shape the scanner must recognise, assembled here so the string exists only in a
# temporary directory — never in a commit, and never usable. Neither a documented example key nor an
# obvious placeholder: measured, the scanner allowlists both, and a control it ignores proves nothing.
printf 'token = "ghp_%s"\n' "a1b2c3d4e5a1b2c3d4e5a1b2c3d4e5abcdef" > "$control/control.txt"
if gitleaks "$control" detect --no-git --no-banner --redact >/dev/null 2>&1; then
    fail "the control was not rejected: Gitleaks is not scanning, so its silence means nothing"
else
    pass "the scanner rejects a known-bad control"
fi

# The index is a separate snapshot: a staged secret can differ from a clean or deleted worktree file.
# Export it without changing the index, and fail if any entry cannot be exported or scanned. For a
# commit the index is that commit's files, and the scanner's configuration this checkout's.
index_dir="$SCRATCH/index"
held="the staged index"
if [ -n "$COMMIT" ]; then held="commit $SHORT"; fi
if mkdir "$index_dir" && git checkout-index --all --ignore-skip-worktree-bits --prefix="$index_dir/"; then
    if [ -n "$COMMIT" ]; then
        rm -f "$index_dir/.gitleaks.toml"
        cp "$REPO/.gitleaks.toml" "$index_dir/" 2>/dev/null || true
    fi
    if gitleaks "$index_dir" detect --no-git --no-banner --redact --exit-code 1 >"$control/gitleaks-index.txt" 2>&1; then
        pass "no secret in $held"
    else
        fail "Gitleaks found something in $held:"
        sed 's/^/     /' "$control/gitleaks-index.txt" | head -40
    fi
else
    fail "could not export $held for the secret scan"
fi

# Tracked files still present in the working tree, exported to a directory of their own. Scanning
# the checkout itself would scan `.env`, `secrets/` and `tmp/` — ignored files that hold real
# credentials by design, and whose absence from the push is checked above. A push of a commit carries
# none of them.
if [ -z "$COMMIT" ]; then
    export_dir="$SCRATCH/export"
    mkdir "$export_dir"
    worktree_exported=true
    if git ls-files -z > "$control/candidate-paths"; then
        while IFS= read -r -d "" file; do
            # An unstaged deletion has no working-tree bytes to export; its old content remains in history.
            [ -e "$file" ] || continue
            if ! mkdir -p "$export_dir/$(dirname "$file")" || ! cp -- "$file" "$export_dir/$file"; then
                fail "could not export $file for the secret scan"
                worktree_exported=false
            fi
        done < "$control/candidate-paths"
    else
        fail "could not list files for the secret scan"
        worktree_exported=false
    fi
    cp "$REPO/.gitleaks.toml" "$export_dir/" 2>/dev/null || true
    if [ "$worktree_exported" = true ]; then
        if gitleaks "$export_dir" detect --no-git --no-banner --redact --exit-code 1 >"$control/gitleaks-tracked.txt" 2>&1; then
            pass "no secret in the tracked files still present"
        else
            fail "Gitleaks found something in a tracked file:"
            sed 's/^/     /' "$control/gitleaks-tracked.txt" | head -40
        fi
    fi
fi

# By hand, every ref's history; for a commit, the history a push of it carries — all it descends from,
# whatever the remote holds already.
history="the history"
carried="the history a push would carry"
if [ -n "$COMMIT" ]; then history="the history of commit $SHORT"; carried="$history"; fi
if [ -d "$REPO/.git" ]; then
    if gitleaks "$REPO" detect --no-banner --redact --exit-code 1 ${COMMIT:+"--log-opts=$COMMIT"} >"$control/gitleaks-history.txt" 2>&1; then
        pass "no secret in $carried"
    else
        fail "Gitleaks found something in $history:"
        sed 's/^/     /' "$control/gitleaks-history.txt" | head -40
    fi
elif [ -n "$COMMIT" ]; then
    fail "$history cannot be scanned from a worktree: run this from the clone's main checkout"
fi

# ---- 3. the working tree itself --------------------------------------------------------------

if [ -z "$COMMIT" ]; then
    if git diff --check >/dev/null 2>&1; then
        pass "git diff --check is clean"
    else
        fail "git diff --check reports whitespace errors"
    fi
fi

verdict
