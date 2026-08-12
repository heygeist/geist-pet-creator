#!/bin/sh
# Run a command with OPENROUTER_API_KEY resolved from the macOS Keychain.
#
#   ./with_openrouter_key.sh python3 eval_providers.py --out provider-eval
#
# The key is read at exec time and exported into the child only. It is never
# written to a dotfile, never placed in the environment of every command the
# shell runs, and never passed as an argument -- argv is world-readable via ps,
# so the value is exported rather than handed to `env`.
#
# Why /usr/bin/security specifically: a keychain item created by `security` has
# that binary on its ACL, which is what lets this read return without a GUI
# prompt from a non-interactive shell. A language binding that links
# Security.framework directly (Python `keyring`, say) executes as a different
# binary, misses the ACL, and would prompt. Do not "simplify" this into Python.
#
# Honest boundary: this means the key never has to be handed to an agent. It is
# not a sandbox. The key is in the child's environment for the length of the
# run, and anything running as this user could read it there. What it buys is
# that a cooperative agent cannot leak a value it never receives.

set -eu

SERVICE="${OPENROUTER_KEYCHAIN_SERVICE:-openrouter-geist}"
ACCOUNT="${OPENROUTER_KEYCHAIN_ACCOUNT:-$(id -un)}"

usage() {
    cat >&2 <<USAGE
usage: with_openrouter_key.sh <command> [args...]
       with_openrouter_key.sh --check

Reads the OpenRouter key from the login keychain (service "$SERVICE",
account "$ACCOUNT") and execs <command> with OPENROUTER_API_KEY set.

Override the item with OPENROUTER_KEYCHAIN_SERVICE / OPENROUTER_KEYCHAIN_ACCOUNT.
USAGE
    exit 64
}

missing() {
    cat >&2 <<MISSING
with_openrouter_key.sh: no keychain item for service "$SERVICE", account "$ACCOUNT".

Create it, omitting the value so the terminal prompts for it -- passing -w with
the key inline would put the key in your shell history:

    security add-generic-password -a "$ACCOUNT" -s "$SERVICE" -w

Mint the key itself at https://openrouter.ai/settings/keys with a credit limit
set. The limit is server-enforced before requests reach a provider and is the
only spend control outside this machine's reach.
MISSING
    exit 69
}

[ "$#" -ge 1 ] || usage

if [ "$1" = "--check" ]; then
    # Confirm the item resolves without ever printing the value.
    if /usr/bin/security find-generic-password -a "$ACCOUNT" -s "$SERVICE" -w >/dev/null 2>&1; then
        printf 'ok: keychain item "%s" for account "%s" resolves\n' "$SERVICE" "$ACCOUNT"
        exit 0
    fi
    missing
fi

case "$1" in
    -h | --help) usage ;;
esac

key=$(/usr/bin/security find-generic-password -a "$ACCOUNT" -s "$SERVICE" -w 2>/dev/null) || missing
[ -n "$key" ] || missing

# A missing item exits above rather than falling through to whatever
# OPENROUTER_API_KEY the caller happened to export. Silently dropping from the
# hardened path onto the plain one is the failure this whole arrangement exists
# to prevent, so it is an error, not a fallback.
#
# The marker lets the generator name which path supplied the credential. It
# carries no service name or account: a candidate packet travels between
# machines, and where this machine keeps its key is nobody else's business.
export GEIST_CREDENTIAL_SOURCE="keychain"
export OPENROUTER_API_KEY="$key"
unset key
exec "$@"
