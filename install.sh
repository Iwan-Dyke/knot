#!/usr/bin/env bash
set -euo pipefail

knot_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
knot_bin_dir="$HOME/bin"
if [[ $# -eq 2 && $1 == --bin-dir ]]; then
    knot_bin_dir="$2"
elif [[ $# -ne 0 ]]; then
    echo 'Usage: ./install.sh [--bin-dir DIRECTORY]' >&2
    exit 2
fi

if [[ ! -x "$knot_root/.venv/bin/python" || ! -x "$knot_root/knot" ]]; then
    echo 'The project launcher and .venv must be set up first; see README.md.' >&2
    exit 1
fi

mkdir -p -- "$knot_bin_dir"
knot_bin_dir="$(cd -- "$knot_bin_dir" && pwd)"
knot_target="$knot_bin_dir/knot"
knot_temporary="$(mktemp "$knot_bin_dir/.knot-install.XXXXXX")"
trap 'rm -f -- "$knot_temporary"' EXIT

# A wrapper preserves the checkout path; a symlink would change launcher discovery.
printf '#!/usr/bin/env bash\nexec %q "$@"\n' "$knot_root/knot" > "$knot_temporary"
chmod 755 "$knot_temporary"
if [[ -e "$knot_target" || -L "$knot_target" ]]; then
    if [[ -L "$knot_target" || ! -f "$knot_target" ]] || ! cmp -s -- "$knot_temporary" "$knot_target"; then
        echo "Refusing to replace an existing command: $knot_target" >&2
        exit 1
    fi
    if [[ ! -x "$knot_target" ]]; then
        echo "Existing launcher is not executable: $knot_target" >&2
        exit 1
    fi
else
    mv -T -n -- "$knot_temporary" "$knot_target"
    if [[ -e "$knot_temporary" ]]; then
        echo "Installation destination changed; inspect $knot_target before retrying." >&2
        exit 1
    fi
fi

echo "Installed: $knot_target"
case ":$PATH:" in
    *":$knot_bin_dir:"*) echo 'Run: knot add' ;;
    *) printf 'Open a new terminal if this directory is already configured, or add this to your shell profile:\nexport PATH=%q:"$PATH"\n' "$knot_bin_dir" ;;
esac
