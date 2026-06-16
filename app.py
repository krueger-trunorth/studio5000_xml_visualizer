"""Plotly Dash app to browse the exploded/ XML tree and convert files to CSV.

Run with:  python app.py
"""

import io
import re
import xml.dom.minidom as minidom
import xml.etree.ElementTree as ET
from pathlib import Path

import dash
import dash_mantine_components as dmc
import pandas as pd
from dash import Input, Output, State, dash_table, dcc, html
from dash_iconify import DashIconify

from xml_to_csv import element_rows, recipe_rows, setting_rows

ROOT = (Path(__file__).parent / "exploded").resolve()
SETTINGS_REL = "RSLogix5000Content/Tags/Settings.xml"
RECIPE_REL = "RSLogix5000Content/Tags/Machine_Run_Recipe.xml"
PARAM_FIELDS = ["Parameter", "Description", "Unit", "Min", "Max"]
PREVIEW_LINE_LIMIT = 2000
MAX_SEARCH_RESULTS = 100
MAX_RECENT_SEARCHES = 10

# Content search ------------------------------------------------------------
# A separate directory (a sibling of `exploded/`, so it never shows up in the
# file tree) holds a single annotated "markup" file. Every exploded source
# file is concatenated into it, each chunk prefixed by an `@@FILE` comment that
# links the text back to the exploded file it came from. The index is built
# once, cached in memory, and rebuilt only when the exploded tree changes.
INDEX_DIR = (Path(__file__).parent / "search_index").resolve()
FILE_MARKER = "@@FILE"  # token used inside the markup comment, e.g. <!-- @@FILE rel -->
SEARCHABLE_EXTS = {".xml", ".st", ".yaml"}  # source files; derived csv/ is skipped
MAX_CONTENT_FILES = 100        # max files listed in the results dropdown
MAX_SNIPPETS_PER_FILE = 5      # max matching lines previewed per file
MAX_CONTENT_MATCHES = 2000     # global cap so a broad regex can't run away
MAX_SNIPPET_LEN = 200          # truncate long matching lines for display

# Cached index: {"signature": <tuple>, "files": [{"rel", "text"}, ...]}.
_CONTENT_INDEX: dict = {"signature": None, "files": []}

CHEVRON_OPEN = "\u25BE"   # down-pointing triangle
CHEVRON_CLOSED = "\u25B8" # right-pointing triangle
ICON_DIR = "\U0001F4C1"   # folder
ICON_FILE = "\U0001F4C4"  # page


def safe_resolve(rel_path: str) -> Path:
    """Resolve a user-supplied relative path against ROOT.

    Raises ValueError if the resolved path escapes ROOT (path traversal guard).
    """
    rel_path = (rel_path or "").strip().lstrip("/\\")
    candidate = (ROOT / rel_path).resolve()
    if candidate != ROOT and ROOT not in candidate.parents:
        raise ValueError(f"Path escapes browse root: {rel_path!r}")
    return candidate


def list_dir(rel_path: str):
    """Return (dirs, files) for the directory at rel_path, sorted by name.

    Each entry is a dict with 'name' and 'rel' (path relative to ROOT).
    """
    directory = safe_resolve(rel_path)
    dirs, files = [], []
    for entry in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        rel = entry.relative_to(ROOT).as_posix()
        item = {"name": entry.name, "rel": rel}
        if entry.is_dir():
            dirs.append(item)
        else:
            files.append(item)
    return dirs, files


def all_dirs() -> list[str]:
    """Every directory under ROOT (relative paths), for 'Expand all'."""
    return [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_dir()]


def all_files() -> list[str]:
    """Every file under ROOT (relative paths), used by the search index."""
    return sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file())


def ancestors_of(rel: str) -> list[str]:
    """Directory rel-paths that must be expanded to reveal `rel`."""
    parts = rel.split("/")
    return ["/".join(parts[: i + 1]) for i in range(len(parts) - 1)]


def build_tree_nodes(rel_path, expanded, selected, depth=0):
    """Recursively build indented tree rows.

    Only the children of directories present in `expanded` are rendered, so the
    tree is loaded lazily as the user expands folders.
    """
    nodes = []
    dirs, files = list_dir(rel_path)

    for d in dirs:
        is_open = d["rel"] in expanded
        chevron = CHEVRON_OPEN if is_open else CHEVRON_CLOSED
        nodes.append(
            html.Button(
                f"{chevron} {ICON_DIR} {d['name']}",
                id={"type": "tree-dir", "index": d["rel"]},
                n_clicks=0,
                className="tree-row tree-dir",
                style={"paddingLeft": f"{depth * 16 + 6}px"},
            )
        )
        if is_open:
            nodes.extend(build_tree_nodes(d["rel"], expanded, selected, depth + 1))

    for f in files:
        selected_cls = " tree-selected" if f["rel"] == selected else ""
        nodes.append(
            html.Button(
                f"{ICON_FILE} {f['name']}",
                id={"type": "tree-file", "index": f["rel"]},
                n_clicks=0,
                className=f"tree-row tree-file{selected_cls}",
                style={"paddingLeft": f"{depth * 16 + 22}px"},
            )
        )

    return nodes


def pretty_xml(path: Path) -> str:
    """Return indented XML text (falls back to raw text if it won't parse)."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"(could not read file: {exc})"

    try:
        dom = minidom.parseString(raw)
        pretty = dom.toprettyxml(indent="  ")
        text = "\n".join(line for line in pretty.splitlines() if line.strip())
    except Exception:
        text = raw

    lines = text.splitlines()
    if len(lines) > PREVIEW_LINE_LIMIT:
        lines = lines[:PREVIEW_LINE_LIMIT]
        lines.append(f"... (truncated at {PREVIEW_LINE_LIMIT} lines)")
    return "\n".join(lines)


def xml_to_dataframe(path: Path) -> pd.DataFrame:
    """Flatten XML to rows in memory (no file written to disk)."""
    tree = ET.parse(path)
    rows = list(element_rows(tree.getroot()))
    return pd.DataFrame(rows).fillna("")


def search_files(query: str) -> list[str]:
    """Return file rel-paths matching `query`.

    Tries `query` as a case-insensitive regex; if it is not valid regex, falls
    back to a plain case-insensitive substring match so partial input still works.
    """
    query = (query or "").strip()
    if not query:
        return []
    try:
        matcher = re.compile(query, re.IGNORECASE).search
    except re.error:
        needle = query.lower()
        matcher = lambda s: needle in s.lower()
    return [f for f in all_files() if matcher(f)][:MAX_SEARCH_RESULTS]


# ---------------------------------------------------------------------------
# Content search index
# ---------------------------------------------------------------------------
def iter_source_files():
    """Yield exploded source files worth searching, in stable order."""
    for path in sorted(ROOT.rglob("*"), key=lambda p: p.as_posix().lower()):
        if path.is_file() and path.suffix.lower() in SEARCHABLE_EXTS:
            yield path


def index_signature() -> tuple:
    """Cheap fingerprint of the exploded tree to detect when to rebuild.

    Uses (file count, newest mtime) so edits or re-explodes invalidate the
    cached index without us re-reading every file on each search.
    """
    count = 0
    newest = 0.0
    for path in iter_source_files():
        count += 1
        newest = max(newest, path.stat().st_mtime)
    return (count, newest)


def markup_name() -> str:
    """Name of the persisted markup file, derived from the exploded root."""
    top = next((p.name for p in ROOT.iterdir() if p.is_dir()), "exploded")
    return f"markup_{top}.xml"


def build_content_index() -> list[dict]:
    """Read every source file once and persist the annotated markup file.

    Returns the in-memory index (a list of {"rel", "text"}). Also writes a
    single `markup_{name}.xml` where each file's text is preceded by an
    `<!-- @@FILE rel -->` comment, so the same content can be regex-searched as
    one document and every hit traced back to its exploded file by its title.
    """
    files: list[dict] = []
    markup_parts: list[str] = []
    for path in iter_source_files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files.append({"rel": rel, "text": text})
        markup_parts.append(f"<!-- {FILE_MARKER} {rel} -->")
        markup_parts.append(text)

    try:
        INDEX_DIR.mkdir(exist_ok=True)
        (INDEX_DIR / markup_name()).write_text("\n".join(markup_parts), encoding="utf-8")
    except OSError:
        pass  # search still works from the in-memory index if the write fails

    return files


def get_content_index() -> list[dict]:
    """Return the cached index, rebuilding it if the exploded tree changed."""
    signature = index_signature()
    if _CONTENT_INDEX["signature"] != signature:
        _CONTENT_INDEX["files"] = build_content_index()
        _CONTENT_INDEX["signature"] = signature
    return _CONTENT_INDEX["files"]


def compile_query(query: str):
    """Compile `query` as case-insensitive regex, falling back to literal text."""
    try:
        return re.compile(query, re.IGNORECASE)
    except re.error:
        return re.compile(re.escape(query), re.IGNORECASE)


def search_content(query: str):
    """Search file contents for `query`.

    Returns (results, pattern) where results is a list of
    {"rel", "count", "hits": [(lineno, line), ...]} sorted by match count.
    The regex runs over the cached index (built once), so a search never has to
    re-read the exploded files from disk.
    """
    query = (query or "").strip()
    if not query:
        return [], None

    pattern = compile_query(query)
    results: list[dict] = []
    total = 0
    for entry in get_content_index():
        hits: list[tuple[int, str]] = []
        count = 0
        for lineno, line in enumerate(entry["text"].splitlines(), 1):
            if pattern.search(line):
                count += 1
                total += 1
                if len(hits) < MAX_SNIPPETS_PER_FILE:
                    hits.append((lineno, line.strip()[:MAX_SNIPPET_LEN]))
                if total >= MAX_CONTENT_MATCHES:
                    break
        if count:
            results.append({"rel": entry["rel"], "count": count, "hits": hits})
        if total >= MAX_CONTENT_MATCHES:
            break

    results.sort(key=lambda r: (-r["count"], r["rel"]))
    return results[:MAX_CONTENT_FILES], pattern


def highlight(line: str, pattern) -> list:
    """Split `line` into text + html.Mark spans around each regex match."""
    if pattern is None:
        return [line]
    parts: list = []
    last = 0
    for match in pattern.finditer(line):
        if match.start() == match.end():  # zero-width match: don't loop forever
            break
        parts.append(line[last:match.start()])
        parts.append(html.Mark(match.group(0)))
        last = match.end()
    parts.append(line[last:])
    return parts or [line]


def real_click(ctx) -> bool:
    """True only for a genuine click.

    When the tree (or tab strip) re-renders, recreated buttons reset n_clicks to
    0/None, which re-fires pattern-matching callbacks. Those spurious triggers
    carry a falsy value and must be ignored.
    """
    return bool(ctx.triggered and ctx.triggered[0].get("value"))


def add_tab(open_tabs, rel):
    """Return a new open-tabs list with `rel` appended if not already present."""
    tabs = list(open_tabs or [])
    if rel not in tabs:
        tabs.append(rel)
    return tabs


def render_file(rel: str):
    """Parse a file into the cache payload (xml markdown + csv data/columns)."""
    try:
        path = safe_resolve(rel)
    except ValueError as exc:
        return {"xml_md": f"```\n{exc}\n```", "csv_data": [], "csv_columns": [],
                "csv_count": "", "export": None}

    if path.suffix.lower() != ".xml":
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raw = f"(could not read file: {exc})"
        return {"xml_md": f"```\n{raw}\n```", "csv_data": [], "csv_columns": [],
                "csv_count": "(not an XML file)", "export": None}

    preview = f"```xml\n{pretty_xml(path)}\n```"
    try:
        df = xml_to_dataframe(path)  # parsed in memory, nothing saved
    except Exception as exc:  # surface parse errors to the user
        return {"xml_md": preview, "csv_data": [], "csv_columns": [],
                "csv_count": f"parse failed: {exc}", "export": None}

    columns = [{"name": c, "id": c} for c in df.columns]
    export = {"content": df.to_csv(index=False), "filename": f"{path.stem}.csv"}
    return {
        "xml_md": preview,
        "csv_data": df.to_dict("records"),
        "csv_columns": columns,
        "csv_count": f"({len(df)} rows)",
        "export": export,
    }


THEME = {
    "primaryColor": "blue",
    "fontFamily": "system-ui, -apple-system, 'Segoe UI', sans-serif",
    "fontFamilyMonospace": "'Cascadia Code', Consolas, 'Courier New', monospace",
}

NAVBAR_WIDTH = 320
NAVBAR_COLLAPSED_WIDTH = 48


app = dash.Dash(__name__)
app.title = "Studio5000 XML Viewer"


# ---------------------------------------------------------------------------
# Layout pieces
# ---------------------------------------------------------------------------
def header():
    return dmc.AppShellHeader(
        dmc.Group(
            [
                dmc.Group(
                    [
                        html.Img(
                            src=dash.get_asset_url("trunorth-logo.png"),
                            style={"height": "44px"},
                        ),
                        dmc.Title("Studio5000 XML Viewer", order=4),
                    ],
                    gap="sm",
                ),
                dmc.SegmentedControl(
                    id="view-mode",
                    value="xml",
                    data=[
                        {"label": "XML", "value": "xml"},
                        {"label": "CSV", "value": "csv"},
                    ],
                    size="sm",
                ),
            ],
            justify="space-between",
            align="center",
            h="100%",
            px="md",
        ),
    )


def navbar():
    return dmc.AppShellNavbar(
        [
            html.Div(
                dmc.Tooltip(
                    dmc.ActionIcon(
                        DashIconify(
                            id="nav-toggle-icon",
                            icon="tabler:layout-sidebar-left-collapse",
                        ),
                        id="nav-toggle",
                        n_clicks=0,
                        variant="subtle",
                        size="md",
                    ),
                    label="Toggle sidebar",
                    position="right",
                ),
                className="nav-toggle-row",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            dmc.Autocomplete(
                                id="search",
                                placeholder="Search files (regex)\u2026",
                                leftSection=DashIconify(icon="tabler:search"),
                                data=[],
                                comboboxProps={"withinPortal": False},
                                size="sm",
                            ),
                            html.Div(id="search-results", style={"display": "none"}),
                        ],
                        style={"position": "relative", "padding": "0 8px 6px 8px"},
                    ),
                    html.Div(
                        [
                            dmc.TextInput(
                                id="content-search",
                                placeholder="Search file contents (regex)\u2026",
                                leftSection=DashIconify(icon="tabler:file-search"),
                                size="sm",
                            ),
                            html.Div(
                                dmc.Button(
                                    "Open all matches",
                                    id="open-all-btn",
                                    n_clicks=0,
                                    leftSection=DashIconify(icon="tabler:folders"),
                                    variant="light",
                                    size="xs",
                                    fullWidth=True,
                                ),
                                id="open-all-wrap",
                                style={"display": "none"},
                            ),
                            html.Div(
                                id="content-search-results",
                                style={"display": "none"},
                            ),
                        ],
                        style={"position": "relative", "padding": "0 8px 6px 8px"},
                    ),
                    html.Div(
                        dmc.Button(
                            "SD Tables",
                            id="export-sd-tables-btn",
                            n_clicks=0,
                            leftSection=DashIconify(icon="tabler:table-export"),
                            variant="light",
                            size="xs",
                            fullWidth=True,
                        ),
                        style={"padding": "0 8px 6px 8px"},
                    ),
                    dmc.Group(
                        [
                            dmc.Tooltip(
                                dmc.ActionIcon(
                                    DashIconify(icon="tabler:layout-sidebar-right-collapse"),
                                    id="expand-all",
                                    variant="default",
                                    size="sm",
                                ),
                                label="Expand all",
                            ),
                            dmc.Tooltip(
                                dmc.ActionIcon(
                                    DashIconify(icon="tabler:layout-sidebar-left-collapse"),
                                    id="collapse-all",
                                    variant="default",
                                    size="sm",
                                ),
                                label="Collapse all",
                            ),
                        ],
                        gap="xs",
                        px="sm",
                        pb="xs",
                    ),
                    dmc.ScrollArea(
                        html.Div(id="tree", className="tree"),
                        style={"flex": "1 1 0", "minHeight": "0"},
                        type="auto",
                    ),
                ],
                id="nav-body",
                className="nav-body",
            ),
        ],
        style={"display": "flex", "flexDirection": "column", "minHeight": "0"},
        p=0,
    )


def xml_block():
    return html.Div(
        [
            html.Div(
                [
                    html.Span("XML", className="section-label"),
                    html.Span(id="xml-path", className="file-path"),
                ],
                className="section-title",
            ),
            dcc.Markdown(id="xml-preview", className="xml-view"),
        ],
        id="xml-block",
        className="preview-block",
    )


def csv_block():
    return html.Div(
        [
            html.Div(
                [
                    html.Span("CSV", className="section-label"),
                    html.Span(id="csv-path", className="file-path"),
                    html.Span(id="csv-count", className="csv-count"),
                    dmc.Button(
                        "Save CSV",
                        id="save-btn",
                        n_clicks=0,
                        disabled=True,
                        leftSection=DashIconify(icon="tabler:download"),
                        variant="default",
                        size="xs",
                        style={"marginLeft": "auto"},
                    ),
                ],
                className="section-title",
            ),
            html.Div(
                dash_table.DataTable(
                    id="csv-table",
                    page_action="native",
                    page_size=100,
                    sort_action="native",
                    filter_action="native",
                    fixed_rows={"headers": True},
                    style_table={"height": "100%", "overflowY": "auto"},
                    style_cell={
                        "textAlign": "left",
                        "fontSize": "12px",
                        "padding": "2px 6px",
                        "maxWidth": "320px",
                        "overflow": "hidden",
                        "textOverflow": "ellipsis",
                    },
                    style_header={"fontWeight": "600"},
                ),
                className="preview-body",
            ),
        ],
        id="csv-block",
        className="preview-block",
    )


def empty_state():
    return html.Div(
        dmc.Stack(
            [
                DashIconify(icon="tabler:file-text", width=56, color="#c0c7cf"),
                dmc.Text("No file open", fw=600, c="dimmed"),
                dmc.Text(
                    "Pick a file from the tree, or use search to open one.",
                    size="sm",
                    c="dimmed",
                ),
            ],
            align="center",
            gap=6,
        ),
        id="empty-state",
        className="empty-state",
    )


def main_panel():
    return dmc.AppShellMain(
        [
            dmc.Tabs(
                id="file-tabs",
                value=None,
                children=[],
                variant="outline",
                className="file-tabs",
            ),
            html.Div(
                [xml_block(), csv_block()],
                id="preview-container",
                className="view-xml",
            ),
            empty_state(),
        ],
        className="app-main",
    )


app.layout = dmc.MantineProvider(
    forceColorScheme="light",
    theme=THEME,
    children=dmc.AppShell(
        [
            dcc.Store(id="expanded", data=["RSLogix5000Content"]),
            dcc.Store(id="open-tabs", storage_type="local", data=[]),
            dcc.Store(id="active-tab", storage_type="local", data=None),
            dcc.Store(id="recent-searches", storage_type="local", data=[]),
            dcc.Store(id="content-search-rels", data=[]),
            dcc.Store(id="file-cache", storage_type="memory", data={}),
            dcc.Store(id="csv-export", data=None),
            dcc.Store(id="sidebar-open", storage_type="local", data=True),
            dcc.Download(id="download-csv"),
            dcc.Download(id="download-sd-tables"),
            dmc.Modal(
                id="open-all-modal",
                title="Open all matching files?",
                centered=True,
                children=[
                    dmc.Text(id="open-all-text"),
                    dmc.Group(
                        [
                            dmc.Button("Cancel", id="open-all-cancel", variant="default"),
                            dmc.Button("Open all", id="open-all-confirm", color="blue"),
                        ],
                        justify="flex-end",
                        mt="md",
                    ),
                ],
                opened=False,
            ),
            header(),
            navbar(),
            main_panel(),
        ],
        id="app-shell",
        header={"height": 56},
        navbar={
            "width": NAVBAR_WIDTH,
            "breakpoint": "sm",
            "collapsed": {"desktop": False, "mobile": False},
        },
        padding="md",
    ),
)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
@app.callback(
    Output("search", "data"),
    Input("recent-searches", "data"),
)
def sync_search_history(recent):
    return recent or []


@app.callback(
    Output("search-results", "children"),
    Output("search-results", "style"),
    Input("search", "value"),
)
def do_search(query):
    hidden = {"display": "none"}
    if not (query or "").strip():
        return [], hidden

    matches = search_files(query)
    shown = {
        "position": "absolute",
        "left": "8px",
        "right": "8px",
        "top": "100%",
        "zIndex": 50,
        "background": "#fff",
        "border": "1px solid #d0d7de",
        "borderRadius": "6px",
        "maxHeight": "55vh",
        "overflowY": "auto",
        "boxShadow": "0 6px 18px rgba(0,0,0,.12)",
    }
    if not matches:
        return [html.Div("No matches", className="search-empty")], shown

    results = [
        html.Button(
            [
                html.Div(rel.rsplit("/", 1)[-1], className="sr-name"),
                html.Div(rel, className="sr-path"),
            ],
            id={"type": "search-result", "index": rel},
            n_clicks=0,
            className="search-result",
        )
        for rel in matches
    ]
    return results, shown


@app.callback(
    Output("open-tabs", "data", allow_duplicate=True),
    Output("active-tab", "data", allow_duplicate=True),
    Output("recent-searches", "data", allow_duplicate=True),
    Output("search", "value"),
    Input({"type": "search-result", "index": dash.ALL}, "n_clicks"),
    State("open-tabs", "data"),
    State("recent-searches", "data"),
    State("search", "value"),
    prevent_initial_call=True,
)
def pick_search_result(_clicks, open_tabs, recent, query):
    ctx = dash.callback_context
    tid = ctx.triggered_id
    if not isinstance(tid, dict) or tid.get("type") != "search-result" or not real_click(ctx):
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    rel = tid["index"]
    query = (query or "").strip()
    recent = [q for q in (recent or []) if q != query]
    if query:
        recent.insert(0, query)
    recent = recent[:MAX_RECENT_SEARCHES]
    return add_tab(open_tabs, rel), rel, recent, ""


# ---------------------------------------------------------------------------
# Content search (search inside files)
# ---------------------------------------------------------------------------
DROPDOWN_STYLE = {
    "position": "absolute",
    "left": "8px",
    "right": "8px",
    "top": "100%",
    "zIndex": 50,
    "background": "#fff",
    "border": "1px solid #d0d7de",
    "borderRadius": "6px",
    "maxHeight": "55vh",
    "overflowY": "auto",
    "boxShadow": "0 6px 18px rgba(0,0,0,.12)",
}


@app.callback(
    Output("content-search-results", "children"),
    Output("content-search-results", "style"),
    Output("open-all-wrap", "style"),
    Output("open-all-btn", "children"),
    Output("content-search-rels", "data"),
    Input("content-search", "value"),
)
def do_content_search(query):
    hidden = {"display": "none"}
    btn_hidden = {"display": "none"}
    if not (query or "").strip():
        return [], hidden, btn_hidden, dash.no_update, []

    results, pattern = search_content(query)
    if not results:
        return [html.Div("No matches", className="search-empty")], DROPDOWN_STYLE, btn_hidden, dash.no_update, []

    rels = [r["rel"] for r in results]
    btn_shown = {"padding": "0 8px 6px 8px"}
    btn_label = f"Open all {len(rels)} file{'s' if len(rels) != 1 else ''}"

    total = sum(r["count"] for r in results)
    children = [
        html.Div(
            f"{total} match{'es' if total != 1 else ''} in {len(results)} file"
            f"{'s' if len(results) != 1 else ''}",
            className="cs-summary",
        )
    ]
    for r in results:
        rel = r["rel"]
        snippets = [
            html.Div(
                [
                    html.Span(f"{lineno}", className="cs-lineno"),
                    html.Span(highlight(line, pattern), className="cs-line"),
                ],
                className="cs-snippet",
            )
            for lineno, line in r["hits"]
        ]
        children.append(
            html.Button(
                [
                    html.Div(
                        [
                            html.Span(rel.rsplit("/", 1)[-1], className="sr-name"),
                            html.Span(str(r["count"]), className="cs-count"),
                        ],
                        className="cs-head",
                    ),
                    html.Div(rel, className="sr-path"),
                    html.Div(snippets, className="cs-snippets"),
                ],
                id={"type": "content-result", "index": rel},
                n_clicks=0,
                className="content-result",
            )
        )
    return children, DROPDOWN_STYLE, btn_shown, btn_label, rels


@app.callback(
    Output("open-tabs", "data", allow_duplicate=True),
    Output("active-tab", "data", allow_duplicate=True),
    Output("content-search", "value"),
    Input({"type": "content-result", "index": dash.ALL}, "n_clicks"),
    State("open-tabs", "data"),
    prevent_initial_call=True,
)
def pick_content_result(_clicks, open_tabs):
    ctx = dash.callback_context
    tid = ctx.triggered_id
    if not isinstance(tid, dict) or tid.get("type") != "content-result" or not real_click(ctx):
        return dash.no_update, dash.no_update, dash.no_update
    rel = tid["index"]
    return add_tab(open_tabs, rel), rel, ""


@app.callback(
    Output("open-all-modal", "opened"),
    Output("open-all-text", "children"),
    Input("open-all-btn", "n_clicks"),
    Input("open-all-confirm", "n_clicks"),
    Input("open-all-cancel", "n_clicks"),
    State("content-search-rels", "data"),
    prevent_initial_call=True,
)
def toggle_open_all_modal(_open, _confirm, _cancel, rels):
    ctx = dash.callback_context
    tid = ctx.triggered_id
    if tid == "open-all-btn" and real_click(ctx):
        count = len(rels or [])
        return True, (
            f"This will open {count} file{'s' if count != 1 else ''} in new tabs."
        )
    if tid in ("open-all-confirm", "open-all-cancel"):
        return False, dash.no_update
    return dash.no_update, dash.no_update


@app.callback(
    Output("open-tabs", "data", allow_duplicate=True),
    Output("active-tab", "data", allow_duplicate=True),
    Output("content-search", "value", allow_duplicate=True),
    Input("open-all-confirm", "n_clicks"),
    State("content-search-rels", "data"),
    State("open-tabs", "data"),
    prevent_initial_call=True,
)
def open_all_confirmed(_clicks, rels, open_tabs):
    ctx = dash.callback_context
    if not real_click(ctx):
        return dash.no_update, dash.no_update, dash.no_update
    rels = rels or []
    if not rels:
        return dash.no_update, dash.no_update, dash.no_update
    tabs = list(open_tabs or [])
    for rel in rels:
        if rel not in tabs:
            tabs.append(rel)
    return tabs, rels[0], ""


# ---------------------------------------------------------------------------
# Tree
# ---------------------------------------------------------------------------
@app.callback(
    Output("expanded", "data"),
    Input({"type": "tree-dir", "index": dash.ALL}, "n_clicks"),
    Input("expand-all", "n_clicks"),
    Input("collapse-all", "n_clicks"),
    State("expanded", "data"),
    prevent_initial_call=True,
)
def update_expanded(_dir_clicks, _expand, _collapse, expanded):
    ctx = dash.callback_context
    tid = ctx.triggered_id
    if tid == "expand-all":
        return all_dirs()
    if tid == "collapse-all":
        return []
    # A folder row toggle: ignore spurious re-render triggers (n_clicks reset).
    if not isinstance(tid, dict) or tid.get("type") != "tree-dir" or not real_click(ctx):
        return dash.no_update
    expanded = list(expanded or [])
    rel = tid["index"]
    if rel in expanded:
        expanded.remove(rel)
    else:
        expanded.append(rel)
    return expanded


@app.callback(
    Output("open-tabs", "data", allow_duplicate=True),
    Output("active-tab", "data", allow_duplicate=True),
    Input({"type": "tree-file", "index": dash.ALL}, "n_clicks"),
    State("open-tabs", "data"),
    prevent_initial_call=True,
)
def open_from_tree(_clicks, open_tabs):
    ctx = dash.callback_context
    tid = ctx.triggered_id
    if not isinstance(tid, dict) or tid.get("type") != "tree-file" or not real_click(ctx):
        return dash.no_update, dash.no_update
    rel = tid["index"]
    return add_tab(open_tabs, rel), rel


@app.callback(
    Output("tree", "children"),
    Input("expanded", "data"),
    Input("active-tab", "data"),
)
def render_tree(expanded, active):
    try:
        return build_tree_nodes("", set(expanded or []), active)
    except (ValueError, OSError) as exc:
        return html.Div(f"Error: {exc}", className="status-error")


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
@app.callback(
    Output("file-tabs", "children"),
    Output("file-tabs", "value"),
    Input("open-tabs", "data"),
    Input("active-tab", "data"),
)
def render_tabs(open_tabs, active):
    open_tabs = open_tabs or []
    tabs = [
        dmc.TabsTab(
            rel.rsplit("/", 1)[-1],
            value=rel,
            rightSection=dmc.ActionIcon(
                DashIconify(icon="tabler:x", width=12),
                id={"type": "tab-close", "index": rel},
                n_clicks=0,
                variant="subtle",
                color="gray",
                size="xs",
            ),
        )
        for rel in open_tabs
    ]
    return [dmc.TabsList(tabs)], active


@app.callback(
    Output("active-tab", "data", allow_duplicate=True),
    Input("file-tabs", "value"),
    State("active-tab", "data"),
    prevent_initial_call=True,
)
def switch_tab(value, active):
    if value == active:
        return dash.no_update
    return value


@app.callback(
    Output("open-tabs", "data", allow_duplicate=True),
    Output("active-tab", "data", allow_duplicate=True),
    Input({"type": "tab-close", "index": dash.ALL}, "n_clicks"),
    State("open-tabs", "data"),
    State("active-tab", "data"),
    prevent_initial_call=True,
)
def close_tab(_clicks, open_tabs, active):
    ctx = dash.callback_context
    tid = ctx.triggered_id
    if not isinstance(tid, dict) or tid.get("type") != "tab-close" or not real_click(ctx):
        return dash.no_update, dash.no_update
    rel = tid["index"]
    tabs = list(open_tabs or [])
    if rel not in tabs:
        return dash.no_update, dash.no_update
    idx = tabs.index(rel)
    tabs.remove(rel)
    if active != rel:
        return tabs, dash.no_update
    if not tabs:
        return tabs, None
    neighbor = tabs[idx - 1] if idx > 0 else tabs[0]
    return tabs, neighbor


# ---------------------------------------------------------------------------
# Active preview (cached)
# ---------------------------------------------------------------------------
@app.callback(
    Output("xml-preview", "children"),
    Output("csv-table", "data"),
    Output("csv-table", "columns"),
    Output("csv-count", "children"),
    Output("csv-export", "data"),
    Output("save-btn", "disabled"),
    Output("file-cache", "data"),
    Output("xml-path", "children"),
    Output("csv-path", "children"),
    Input("active-tab", "data"),
    State("file-cache", "data"),
)
def render_active(rel, cache):
    if not rel:
        return "", [], [], "", None, True, dash.no_update, "", ""

    cache = cache or {}
    hit = cache.get(rel)
    if hit is None:
        hit = render_file(rel)
        cache = {**cache, rel: hit}
        cache_out = cache
    else:
        cache_out = dash.no_update

    return (
        hit["xml_md"],
        hit["csv_data"],
        hit["csv_columns"],
        hit["csv_count"],
        hit["export"],
        hit["export"] is None,
        cache_out,
        rel,
        rel,
    )


@app.callback(
    Output("preview-container", "style"),
    Output("empty-state", "style"),
    Input("active-tab", "data"),
)
def toggle_empty(rel):
    """Show the preview panes when a file is open, the empty state otherwise."""
    if rel:
        return {"display": "flex"}, {"display": "none"}
    return {"display": "none"}, {"display": "flex"}


# ---------------------------------------------------------------------------
# View mode + sidebar + download
# ---------------------------------------------------------------------------
@app.callback(
    Output("preview-container", "className"),
    Input("view-mode", "value"),
)
def set_view(mode):
    return f"view-{mode}"


@app.callback(
    Output("app-shell", "navbar"),
    Output("nav-body", "style"),
    Output("nav-toggle-icon", "icon"),
    Output("sidebar-open", "data"),
    Input("nav-toggle", "n_clicks"),
    State("sidebar-open", "data"),
    prevent_initial_call=True,
)
def toggle_sidebar(_clicks, is_open):
    is_open = not is_open
    width = NAVBAR_WIDTH if is_open else NAVBAR_COLLAPSED_WIDTH
    body_style = {} if is_open else {"display": "none"}
    icon = (
        "tabler:layout-sidebar-left-collapse"
        if is_open
        else "tabler:layout-sidebar-left-expand"
    )
    navbar_prop = {
        "width": width,
        "breakpoint": "sm",
        "collapsed": {"desktop": False, "mobile": False},
    }
    return navbar_prop, body_style, icon, is_open


@app.callback(
    Output("download-csv", "data"),
    Input("save-btn", "n_clicks"),
    State("csv-export", "data"),
    prevent_initial_call=True,
)
def save_csv(_clicks, export):
    if not export:
        return dash.no_update
    return dict(content=export["content"], filename=export["filename"], type="text/csv")


def _params_dataframe(rel: str, row_func) -> pd.DataFrame | None:
    """Parse a tag file and extract parameter rows into a table."""
    try:
        path = safe_resolve(rel)
    except ValueError:
        return None
    if not path.is_file():
        return None

    tree = ET.parse(path)
    rows = list(row_func(tree.getroot()))
    return pd.DataFrame(rows, columns=PARAM_FIELDS)


@app.callback(
    Output("download-sd-tables", "data"),
    Input("export-sd-tables-btn", "n_clicks"),
    prevent_initial_call=True,
)
def export_sd_tables(_clicks):
    """Build one SD Tables workbook with each table on its own sheet."""
    tables = {
        "Settings": _params_dataframe(SETTINGS_REL, setting_rows),
        "Recipes": _params_dataframe(RECIPE_REL, recipe_rows),
    }
    if any(df is None for df in tables.values()):
        return dash.no_update

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for sheet_name, df in tables.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    return dcc.send_bytes(buffer.getvalue(), "sd_tables.xlsx")


if __name__ == "__main__":
    app.run(debug=True)
