#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill_dir="$(cd "${script_dir}/.." && pwd)"
venv_dir="${E57_MODEL_VENV:-${skill_dir}/.venv}"
python_bin="${venv_dir}/bin/python"

if [[ ! -x "${python_bin}" ]]; then
  "${script_dir}/setup_runtime.sh"
fi

exec "${python_bin}" "${script_dir}/e57_model.py" "$@"
