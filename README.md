# E57 Building Model

`e57-building-model` is a [Codex skill](https://learn.chatgpt.com/docs/build-skills) for turning E57 laser-scan point clouds into documented 3D deliverables. It analyses scan density, estimates dominant building axes, recommends detail levels, creates reference meshes, and registers user-provided plans as explicit geometric constraints.

It is designed for a careful workflow: a scan mesh is treated as measurement evidence, while a clean architectural model is a separate, constraint-based interpretation.

## What it does

- Reads E57 point-cloud metadata and samples Cartesian scan data.
- Estimates point spacing, scene size, memory requirements, planes, and dominant axes.
- Recommends light, balanced, detailed, or custom mesh profiles.
- Creates PLY, OBJ, STL, and COLLADA/DAE reference meshes.
- Registers a site plan or floor plan to scan coordinates using control points.
- Records hard, soft, and evidence-based facts in a JSON constraint manifest.
- Provides an optional SketchUp Ruby importer for saving a native `.skp` file.

## Important limits

This project does not turn a scan into a legally authoritative survey, cadastral determination, or a fully semantic building model by itself. Surface reconstruction can fill gaps where nothing was measured. A plan, photograph, or user fact only controls the attributes explicitly assigned to it.

Always verify scale, orientation, known dimensions, and any locked footprint before relying on output. Do not upload or include private scans, plans, addresses, or credentials in bug reports.

## Prerequisites

| Requirement | Status | Why |
| --- | --- | --- |
| Python 3.11 or 3.12 with `venv` and `pip` | Required | Runs the E57, analysis, and meshing tools. |
| Bash-compatible shell | Required for helper scripts | Tested on macOS and Linux. |
| 8 GB RAM; 16 GB recommended | Recommended | Dense scans and Poisson reconstruction are memory intensive. |
| CloudCompare | Optional | Useful fallback for very large or unusual E57 files. |
| SketchUp Desktop | Optional | Required only to turn DAE into a native SKP. |

The runtime installs `numpy`, `scipy`, `pye57`, `open3d`, and `psutil` into an isolated virtual environment. No scan data is uploaded by these scripts.

Windows is not currently supported by the shell helpers. The Python core may work in WSL, but that path is untested. Contributions for native Windows support are welcome.

## Install as a Codex skill

```bash
git clone https://github.com/YOUR-ACCOUNT/e57-building-model.git
cp -R e57-building-model ~/.codex/skills/e57-building-model
~/.codex/skills/e57-building-model/scripts/run.sh doctor
```

Restart or start a new Codex task after installation. Then use it with:

```text
Use $e57-building-model to analyse this E57 scan and recommend a constrained SketchUp-ready model.
```

## Configuration

The scripts discover standard commands and macOS application locations automatically. Set these variables only when detection is insufficient:

```bash
export E57_MODEL_PYTHON=/path/to/python3.12
export E57_MODEL_VENV=/path/to/isolated/venv
export E57_MODEL_CLOUDCOMPARE=/path/to/CloudCompare
export E57_MODEL_SKETCHUP=/path/to/SketchUp
```

`CloudCompare` and `SketchUp` are optional; `doctor` reports them when found but does not fail if they are missing.

## Quick start

Analyse an E57 before requesting a full model:

```bash
scripts/run.sh analyze scan.e57 \
  --output analysis.json \
  --markdown analysis.md
```

Create a reference mesh after selecting a profile:

```bash
scripts/run.sh mesh scan.e57 \
  --analysis analysis.json \
  --profile balanced \
  --output-base ./output/site-model
```

Start a constraint manifest for an architectural model:

```bash
scripts/run.sh init-constraints \
  --analysis analysis.json \
  --output constraints.json
```

Add control points to a reference plan and calculate its scan transform:

```bash
scripts/run.sh register-plan constraints.json \
  --plan-index 0 \
  --output constraints-registered.json
```

See [SKILL.md](SKILL.md) and the files in [references](references/) for the full evidence, validation, and SketchUp workflows.

## SketchUp

DAE is the portable interchange file. To create an SKP, open SketchUp Desktop, set the input and output paths in its Ruby console, and load [`scripts/sketchup_import.rb`](scripts/sketchup_import.rb). The script deliberately requires explicit input/output paths so it cannot silently write into a user-specific location.

## Development

Run the unit tests after installing runtime dependencies:

```bash
python -m unittest discover -s tests -v
```

The test suite uses synthetic numeric inputs only. Do not commit real E57 scans or project deliverables.

## Publish to GitHub

Before the first push, inspect the repository for private data and configure a public-safe Git author email, such as a GitHub no-reply address. Then create an empty public repository and push this directory:

```bash
git add .
git commit -m "Initial open-source release"
git remote add origin https://github.com/YOUR-ACCOUNT/e57-building-model.git
git push -u origin main
```

Do not add a remote or push until the repository owner, visibility, and Git author email have been checked.

## License

MIT. See [LICENSE](LICENSE).

## Contributing and support

Bug reports and pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) first.
