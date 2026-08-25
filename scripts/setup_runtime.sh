#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill_dir="$(cd "${script_dir}/.." && pwd)"
venv_dir="${E57_MODEL_VENV:-${skill_dir}/.venv}"

if [[ -x "${venv_dir}/bin/python" ]]; then
  if "${venv_dir}/bin/python" -c 'import numpy, scipy, pye57, open3d, psutil'; then
    exit 0
  fi
fi

python_bin="${E57_MODEL_PYTHON:-}"
if [[ -n "${python_bin}" ]]; then
  if ! command -v "${python_bin}" >/dev/null 2>&1 && [[ ! -x "${python_bin}" ]]; then
    printf 'E57_MODEL_PYTHON does not point to an executable: %s\n' "${python_bin}" >&2
    exit 2
  fi
else
  for candidate in python3.12 python3.11; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      python_bin="$(command -v "${candidate}")"
      break
    fi
  done
fi

if [[ -z "${python_bin}" ]]; then
  printf 'Python 3.11 or 3.12 is required. Set E57_MODEL_PYTHON if it is not on PATH.\n' >&2
  exit 2
fi

if ! "${python_bin}" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 12) else 1)'; then
  printf 'Python 3.11 or 3.12 is required; found: ' >&2
  "${python_bin}" --version >&2
  exit 2
fi

"${python_bin}" -m venv "${venv_dir}"
"${venv_dir}/bin/python" -m pip install --upgrade pip
"${venv_dir}/bin/python" -m pip install -r "${script_dir}/requirements.txt"
"${venv_dir}/bin/python" -c 'import numpy, scipy, pye57, open3d, psutil'
