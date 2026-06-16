# Studio5000 XML Viewer

A Plotly Dash app for browsing, searching, and exporting from Studio 5000 /
Logix Designer projects. Import an `.ACD` directly: the app converts it to L5X,
explodes it into a multi-file XML tree, and lets you browse, search, and export
SD/DV tables. Multiple imported projects are cached side by side and selectable
from a switcher.

## Prerequisites

- **Python 3.10+** and the packages in `requirements.txt`.
- **.NET SDK 10** to build the `l5xgit` CLI from `L5xCmd.sln`.
- **Studio 5000 / Logix Designer SDK** installed on the host. ACD -> L5X
  conversion calls `RockwellAutomation.LogixDesigner.CSClient`, which only runs
  where the SDK is present (Windows).

The `l5xgit.exe` used by the import pipeline is built to
`artifacts/bin/Release/l5xgit.exe`. The app builds it automatically on first
import if it's missing; you can also build it ahead of time:

```bash
dotnet build L5xCmd.sln -c Release
```

## Run

```bash
pip install -r requirements.txt
python app.py
```

Open the app, drop an `.ACD` into the **Import .ACD** box in the sidebar, and
wait for the conversion to finish (it can take a few minutes). The tree opens at
the new project; use the project switcher to move between imported projects.

## Cache layout

Each imported ACD lands in its own folder under `cache/` (git-ignored):

```
cache/
  {project}/
    {project}.acd          # copy of the imported ACD
    {project}.l5x          # intermediate conversion output
    markup_{project}.xml   # content-search index
    exploded/              # browse root
      RSLogix5000Content/...
```

`{project}` is the imported ACD filename without its extension. The exploded
tree is the file root the app browses, searches, and exports from.

## Import workflow

1. Decode the uploaded `.acd` and copy it to `cache/{project}/{project}.acd`.
2. `l5xgit acd2l5x` -> `cache/{project}/{project}.l5x`.
3. `l5xgit explode` -> `cache/{project}/exploded/RSLogix5000Content/...`
   (retried with `--unsafe-skip-dependency-check` if a dependency error occurs).
4. Build `markup_{project}.xml` for content search and activate the project.
