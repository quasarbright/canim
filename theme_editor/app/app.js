/* The page holds no colour maths and no lexer. Both live in canim and are
   asked for over the API, so what you see is what a render produces rather
   than a second implementation that drifts. Colours still apply instantly,
   because that part is only CSS custom properties. */

(() => {
"use strict";

const TOKEN_ROLES = ["identifier", "keyword", "builtin", "operator", "literal",
                     "delimiter", "punctuation", "string", "comment"];
const CHROME_ROLES = ["surface", "surface_stroke", "frame", "frame_stroke",
                      "muted", "subtle", "danger"];

const SAMPLES = {
  lisp: `; swap two places without colliding with the use site
(defmacro swap (x y)
  (let ((tmp (gensym)))
    \`(let ((,tmp ,x))
       (setf ,x ,y
             ,y ,tmp))))

(defvar a 1)
(swap a b)          ; => "done", #t, 42`,
  python: `import ast

def state_machine(source: str) -> type:
    # every branch of the parser lands somewhere
    tree = ast.parse(source)
    if tree is None or len(tree.body) == 0:
        raise ValueError(f"nothing to build: {source!r}")
    return ClassDef(name="VendingMachine", bases=[], body=[...])`,
  javascript: `// every branch of the parser lands somewhere
const stateMachine = (source) => {
  const tree = JSON.parse(source);
  if (tree === null || tree.states.length === 0) {
    throw new Error(\`nothing to build: \${source}\`);
  }
  return { name: "VendingMachine", states: [...tree.states], count: 42 };
};`,
};

const state = {
  theme: null,
  path: null,
  saved: null,      // the JSON of the last saved state, to detect edits
  analysis: { contrast: {}, warnings: {}, oklch: {} },
  compare: null,    // the theme being compared against
  mode: "side",
  showing: "a",     // which theme the single pane shows in toggle mode
  cvd: "",
};

const history = { past: [], future: [] };

const $ = (sel) => document.querySelector(sel);
const el = (tag, props = {}) => Object.assign(document.createElement(tag), props);

// --- talking to canim -------------------------------------------------------

async function api(path, body) {
  const options = body === undefined
    ? {}
    : { method: "POST", body: JSON.stringify(body) };
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

// --- history ----------------------------------------------------------------

/* Every change goes through here, so undo covers generating a palette and
   opening a preset as well as nudging one swatch. */
function change(mutate) {
  history.past.push(JSON.stringify(state.theme));
  history.future.length = 0;
  mutate(state.theme);
  render();
}

function undo() {
  if (!history.past.length) return;
  history.future.push(JSON.stringify(state.theme));
  state.theme = JSON.parse(history.past.pop());
  render();
}

function redo() {
  if (!history.future.length) return;
  history.past.push(JSON.stringify(state.theme));
  state.theme = JSON.parse(history.future.pop());
  render();
}

const dirty = () => JSON.stringify(state.theme) !== state.saved;

// --- rows -------------------------------------------------------------------

function colorRow(role, { chrome = false } = {}) {
  const key = chrome ? `chrome_${role}` : role;
  const pinned = !chrome || key in state.theme;
  const value = state.theme[key] ?? derivedValue(role);

  const row = el("div", { className: "row" + (chrome && pinned ? " pinned" : "") });
  row.dataset.key = key;

  const swatch = el("input", { type: "color", value });
  swatch.setAttribute("aria-label", role);
  // `input`, not `change`: this is what makes the preview follow the cursor
  // around the picker rather than waiting for the mouse to come up.
  swatch.addEventListener("input", (e) => setColor(key, e.target.value));

  const label = el("span", { className: "label" });
  label.append(el("span", { textContent: role }));
  const warnings = state.analysis.warnings[key];
  if (warnings) {
    label.append(el("span", {
      className: "warn", textContent: "⚠️", title: warnings.join("\n"),
    }));
  }

  const hex = el("input", { className: "hex" + (pinned ? "" : " derived"), value });
  hex.addEventListener("input", (e) => {
    if (/^#[0-9a-fA-F]{6}$/.test(e.target.value.trim())) {
      setColor(key, e.target.value.trim().toLowerCase());
    }
  });

  const unpin = el("button", { className: "unpin", textContent: "×", title: "back to derived" });
  unpin.addEventListener("click", () => change((t) => { delete t[key]; }));

  row.append(swatch, label, hex);
  if (chrome) row.append(unpin);

  const ratio = state.analysis.contrast[key];
  if (ratio !== undefined && role !== "background") {
    row.after();
    const readout = el("div", { className: "readout" });
    const track = el("div", { className: "track" });
    const fill = el("div", {
      className: "fill" + (ratio < 4.5 ? " low" : ""),
    });
    fill.style.width = `${Math.min(100, (ratio / 21) * 100)}%`;
    track.append(fill);
    readout.append(track, el("span", { className: "value", textContent: `${ratio.toFixed(1)}:1` }));
    const wrap = el("div");
    wrap.append(row, readout);
    return wrap;
  }
  return row;
}

/* What an unpinned chrome field currently resolves to. The server already
   worked it out when it opened the theme, so this only has to read it back
   off the rendered custom property. */
function derivedValue(role) {
  const name = `--${role.replace(/_/g, "-")}`;
  return getComputedStyle($("#pane-a .surface")).getPropertyValue(name).trim() || "#000000";
}

function setColor(key, value) {
  change((theme) => { theme[key] = value; });
}

// --- painting ---------------------------------------------------------------

function paint(surface, theme) {
  const style = surface.style;
  style.setProperty("--bg", theme.background);
  for (const role of TOKEN_ROLES) style.setProperty(`--k-${role}`, theme[role]);
  for (const role of CHROME_ROLES) {
    const value = theme[`chrome_${role}`];
    if (value) style.setProperty(`--${role.replace(/_/g, "-")}`, value);
    else style.removeProperty(`--${role.replace(/_/g, "-")}`);
  }
}

/* Unpinned chrome has to be resolved somewhere, and the server is the only
   thing that knows the derivation. Opening or generating fills these in; this
   keeps the preview honest in between by asking for a full theme. */
async function resolveChrome(theme) {
  const missing = CHROME_ROLES.filter((r) => !(`chrome_${r}` in theme));
  if (!missing.length) return theme;
  const derived = await api("/api/generate/chrome", {
    background: theme.background, identifier: theme.identifier,
  });
  return { ...derived, ...theme };
}

async function renderCode() {
  const language = $("#language").value;
  const source = $("#source").value;
  const { segments } = await api("/api/lex", { language, source });
  for (const pre of document.querySelectorAll(".code")) {
    pre.textContent = "";
    for (const segment of segments) {
      if (segment.kind === null) pre.append(document.createTextNode(segment.text));
      else pre.append(el("span", { className: `k-${segment.kind}`, textContent: segment.text }));
    }
  }
}

function renderMath(node, theme) {
  // The formula is the one the video's own scenes are about: a macro call and
  // what it expands to. Its parts take the palette's working colours.
  const tex = String.raw`\textcolor{${theme.keyword}}{\texttt{swap}}
    (\textcolor{${theme.identifier}}{a}, \textcolor{${theme.identifier}}{b})
    \;\longmapsto\;
    \textcolor{${theme.builtin}}{\texttt{let}}\;
    \textcolor{${theme.literal}}{t} = \textcolor{${theme.identifier}}{a}`;
  try {
    katex.render(tex, node, { throwOnError: false, displayMode: true });
  } catch {
    node.textContent = "";
  }
}

async function renderPanes() {
  const a = await displayTheme(state.theme);
  paint($("#pane-a .surface"), a);
  renderMath($("#pane-a .math"), a);
  $("#pane-a .pane-name").textContent = state.theme.name;

  const paneB = $("#pane-b");
  const comparing = Boolean(state.compare);
  const side = comparing && state.mode === "side";
  $("#stage").classList.toggle("side", side);
  paneB.hidden = !side;
  $("#toggle-hint").hidden = !(comparing && state.mode === "toggle");

  if (comparing) {
    const b = await displayTheme(state.compare);
    if (side) {
      paint($("#pane-b .surface"), b);
      renderMath($("#pane-b .math"), b);
      $("#pane-b .pane-name").textContent = state.compare.name;
    } else if (state.showing === "b") {
      paint($("#pane-a .surface"), b);
      renderMath($("#pane-a .math"), b);
      $("#pane-a .pane-name").textContent = `${state.compare.name} — comparing`;
    }
  }
}

/* What to actually paint: the theme, or the theme as someone with that form
   of colour blindness sees it. */
async function displayTheme(theme) {
  const full = await resolveChrome(theme);
  if (!state.cvd) return full;
  const simulated = await api("/api/simulate", { theme: full, kind: state.cvd });
  return { ...full, ...simulated };
}

// --- hue map ----------------------------------------------------------------

const HUE_MAP_ROLES = ["identifier", "keyword", "builtin", "literal", "string", "comment"];

function renderHueMap() {
  const svg = $("#hue-map");
  svg.textContent = "";
  const ns = "http://www.w3.org/2000/svg";
  const add = (tag, attrs) => {
    const node = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    svg.append(node);
    return node;
  };

  for (const r of [40, 80, 120]) add("circle", { class: "ring", cx: 0, cy: 0, r });
  for (let angle = 0; angle < 360; angle += 30) {
    const rad = (angle * Math.PI) / 180;
    add("line", {
      class: "spoke", x1: 0, y1: 0,
      x2: 120 * Math.cos(rad), y2: 120 * Math.sin(rad),
      "stroke-opacity": 0.5,
    });
  }

  const place = ([, chroma, hue]) => {
    const rad = (hue * Math.PI) / 180;
    const radius = Math.min(120, (chroma / 0.25) * 120);
    return [radius * Math.cos(rad), -radius * Math.sin(rad)];
  };

  const background = state.analysis.oklch.background;
  if (background) {
    const [x, y] = place(background);
    add("circle", { class: "bg-marker", cx: x, cy: y, r: 9 });
  }

  for (const role of HUE_MAP_ROLES) {
    const point = state.analysis.oklch[role];
    if (!point) continue;
    const [x, y] = place(point);
    add("circle", { class: "dot", cx: x, cy: y, r: 6, fill: state.theme[role] });
    add("text", { class: "dot-label", x: x + 9, y: y + 3 }).textContent = role;
  }
}

// --- the whole view ---------------------------------------------------------

let analyzeTimer = null;

function render() {
  $("#theme-name").value = state.theme.name;
  $("#dirty").hidden = !dirty();

  const background = colorRow("background");
  $("#row-background").replaceChildren(background);
  $("#rows-tokens").replaceChildren(...TOKEN_ROLES.map((r) => colorRow(r)));
  $("#rows-chrome").replaceChildren(
    ...CHROME_ROLES.map((r) => colorRow(r, { chrome: true }))
  );

  renderPanes();
  renderHueMap();

  // Colours are already on screen by now; the numbers can lag a frame or two
  // behind a drag without anyone noticing.
  clearTimeout(analyzeTimer);
  analyzeTimer = setTimeout(async () => {
    try {
      state.analysis = await api("/api/analyze", state.theme);
      $("#rows-tokens").replaceChildren(...TOKEN_ROLES.map((r) => colorRow(r)));
      $("#rows-chrome").replaceChildren(
        ...CHROME_ROLES.map((r) => colorRow(r, { chrome: true }))
      );
      renderHueMap();
    } catch (error) {
      toast(error.message);
    }
  }, 60);
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 2400);
}

// --- files ------------------------------------------------------------------

async function openTheme(path) {
  const { theme, path: resolved } = await api(`/api/theme?path=${encodeURIComponent(path)}`);
  state.theme = theme;
  state.path = resolved;
  state.saved = JSON.stringify(theme);
  history.past.length = history.future.length = 0;
  render();
  toast(`Opened ${theme.name}`);
}

async function save(path) {
  const target = path || state.path;
  if (!target) return saveAs();
  await api("/api/theme", { path: target, theme: state.theme });
  state.path = target;
  state.saved = JSON.stringify(state.theme);
  $("#dirty").hidden = true;
  toast(`Saved to ${target}`);
}

function saveAs() {
  const slug = state.theme.name.trim().replace(/\s+/g, "-") || "untitled";
  $("#save-path").value = state.path
    ? state.path.replace(/[^/]+$/, `${slug}.theme.json`)
    : `${catalogue.directory}/${slug}.theme.json`;
  $("#save-dialog").showModal();
}

let catalogue = { names: [], directory: "", languages: [] };

async function refreshCatalogue() {
  catalogue = await api("/api/themes");
  $("#language").replaceChildren(
    ...catalogue.languages.map((name) => el("option", { value: name, textContent: name }))
  );
  $("#language").value = catalogue.languages.includes("lisp") ? "lisp" : catalogue.languages[0];

  $("#compare-with").replaceChildren(
    el("option", { value: "", textContent: "off" }),
    ...catalogue.names.map((name) => el("option", { value: name, textContent: name }))
  );
}

async function fillThemeList() {
  const list = $("#theme-list");
  list.replaceChildren();
  for (const name of catalogue.names) {
    const { theme } = await api(`/api/theme?path=${encodeURIComponent(name)}`);
    const button = el("button", { type: "button" });
    button.append(el("span", { textContent: name }));
    const swatches = el("span", { className: "swatches" });
    for (const role of ["background", "keyword", "builtin", "literal", "string"]) {
      const chip = el("i");
      chip.style.background = theme[role];
      swatches.append(chip);
    }
    button.append(swatches);
    button.addEventListener("click", () => {
      $("#open-dialog").close();
      openTheme(name).catch((e) => toast(e.message));
    });
    const item = el("li");
    item.append(button);
    list.append(item);
  }
}

// --- events -----------------------------------------------------------------

document.addEventListener("click", async (event) => {
  const action = event.target.closest("[data-act]")?.dataset.act;
  const generate = event.target.closest("[data-gen]")?.dataset.gen;
  const mode = event.target.closest("[data-mode]")?.dataset.mode;

  try {
    if (action === "open") { await fillThemeList(); $("#open-dialog").showModal(); }
    if (action === "save") await save();
    if (action === "save-as") saveAs();
    if (action === "undo") undo();
    if (action === "redo") redo();

    if (generate) {
      const produced = await api(`/api/generate/${generate}`, state.theme);
      change((theme) => Object.assign(theme, produced));
      toast(generate === "palette" ? "Generated a palette" : `Generated ${generate}`);
    }

    if (mode) {
      state.mode = mode;
      for (const button of document.querySelectorAll("#compare-mode button")) {
        button.classList.toggle("on", button.dataset.mode === mode);
      }
      renderPanes();
    }
  } catch (error) {
    toast(error.message);
  }
});

$("#theme-name").addEventListener("input", (e) => {
  state.theme.name = e.target.value;
  $("#dirty").hidden = !dirty();
});

$("#language").addEventListener("change", (e) => {
  $("#source").value = SAMPLES[e.target.value] ?? $("#source").value;
  renderCode();
});
$("#source").addEventListener("input", () => renderCode());

$("#font-size").addEventListener("input", (e) => {
  document.documentElement.style.setProperty("--code-size", `${e.target.value}px`);
  $("#font-size-out").value = e.target.value;
});

$("#cvd").addEventListener("change", (e) => { state.cvd = e.target.value; renderPanes(); });

$("#compare-with").addEventListener("change", async (e) => {
  if (!e.target.value) {
    state.compare = null;
  } else {
    const { theme } = await api(`/api/theme?path=${encodeURIComponent(e.target.value)}`);
    state.compare = theme;
  }
  $("#compare-mode").hidden = !state.compare;
  renderPanes();
});

$("#open-confirm").addEventListener("click", () => {
  const path = $("#open-path").value.trim();
  if (path) openTheme(path).catch((error) => toast(error.message));
});

// On the button rather than the dialog's `close` event: a dialog closed by
// script does not reliably carry its returnValue through to the listener, and
// a save that silently does not happen is the worst possible failure here.
$("#save-confirm").addEventListener("click", () => {
  save($("#save-path").value.trim()).catch((error) => toast(error.message));
});

document.addEventListener("keydown", (event) => {
  const typing = /^(INPUT|TEXTAREA)$/.test(event.target.tagName);
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
    event.preventDefault();
    event.shiftKey ? redo() : undo();
  }
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    save().catch((error) => toast(error.message));
  }
  if (event.key === " " && !typing && state.compare && state.mode === "toggle") {
    event.preventDefault();
    state.showing = state.showing === "a" ? "b" : "a";
    renderPanes();
  }
});

addEventListener("beforeunload", (event) => {
  if (dirty()) event.preventDefault();
});

// --- start ------------------------------------------------------------------

(async () => {
  await refreshCatalogue();
  $("#source").value = SAMPLES.lisp;
  await openTheme(catalogue.names.includes("one-dark") ? "one-dark" : catalogue.names[0]);
  await renderCode();
})();

})();
