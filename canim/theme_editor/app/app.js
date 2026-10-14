/* The page holds no color math and no lexer. Both live in canim and are
   asked for over the API, so what you see is what a render produces rather
   than a second implementation that drifts. Colors still apply instantly,
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
  haskell: `module Machine where

-- every branch of the parser lands somewhere
data State = Idle | Vending Int deriving (Show, Eq)

step :: State -> String -> Either String State
step Idle "coin" = Right (Vending 25)
step (Vending n) _
  | n >= 100  = Left "sold out"
  | otherwise = Right (Vending (n + 25))
step s _ = pure s`,
};

const state = {
  theme: null,
  path: null,
  saved: null,      // the JSON of the last saved state, to detect edits
  resolved: null,   // the theme with every unpinned chrome color filled in
  analysis: { contrast: {}, warnings: {}, oklch: {} },
  compare: null,    // the theme being compared against
  mode: "side",
  showing: "a",     // which theme the single pane shows in toggle mode
  cvd: "",
  gen: { harmony: null, chroma: null, spread: null },  // filled from the server
  builtin: false,   // opened from canim's own themes directory
  openedAs: null,   // the name it had when opened, to spot a rename
};

const history = { past: [], future: [] };

const $ = (sel) => document.querySelector(sel);

// --- instant tooltip --------------------------------------------------------

/* `title` waits about a second before it shows, which is useless for something
   you scan while dragging a color. This appears on the first hover frame. */
const tip = Object.assign(document.createElement("div"), { id: "tip", hidden: true });
document.body.append(tip);

function showTip(target, lines) {
  tip.replaceChildren(...lines.map((text) =>
    Object.assign(document.createElement("div"), { className: "line", textContent: text })));
  tip.hidden = false;
  const box = target.getBoundingClientRect();
  const own = tip.getBoundingClientRect();
  const left = Math.min(box.left, innerWidth - own.width - 10);
  const above = box.top - own.height - 8;
  tip.style.left = `${Math.max(8, left)}px`;
  tip.style.top = `${above > 8 ? above : box.bottom + 8}px`;
}

const hideTip = () => { tip.hidden = true; };

function withTip(node, lines) {
  node.addEventListener("pointerenter", () => showTip(node, lines));
  node.addEventListener("pointerleave", hideTip);
  return node;
}
const el = (tag, props = {}) => Object.assign(document.createElement(tag), props);



// --- color picker -----------------------------------------------------------

/* HSV↔hex lives here rather than on the server because it is the mechanics of
   the input widget, not a judgement about color. Everything that decides
   whether a palette is any good — contrast, separation, generation, OKLCH —
   still happens in canim. Going over the wire per pointermove would also make
   dragging feel dead. */

function hexToHsv(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
  let h = 0;
  if (d) {
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
    else if (max === g) h = ((b - r) / d + 2) / 6;
    else h = ((r - g) / d + 4) / 6;
  }
  return { h, s: max ? d / max : 0, v: max };
}

function hsvToHex({ h, s, v }) {
  const i = Math.floor(h * 6), f = h * 6 - i;
  const p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s);
  const [r, g, b] = [[v, t, p], [q, v, p], [p, v, t],
                     [p, q, v], [t, p, v], [v, p, q]][i % 6];
  return "#" + [r, g, b].map((c) =>
    Math.round(c * 255).toString(16).padStart(2, "0")).join("");
}

const picker = Object.assign(document.createElement("div"), { id: "picker", hidden: true });
picker.innerHTML = `
  <div class="area"><span class="knob"></span></div>
  <div class="hue"><span class="knob"></span></div>
  <div class="foot">
    <span class="preview"></span>
    <input class="hex" spellcheck="false" maxlength="7" aria-label="Hex color">
  </div>`;
document.body.append(picker);

const pickerState = { hsv: { h: 0, s: 0, v: 0 }, onChange: null, gesture: null };

function paintPicker() {
  const hex = hsvToHex(pickerState.hsv);
  const { h, s, v } = pickerState.hsv;
  picker.style.setProperty("--picker-hue", hsvToHex({ h, s: 1, v: 1 }));
  picker.querySelector(".area .knob").style.left = `${s * 100}%`;
  picker.querySelector(".area .knob").style.top = `${(1 - v) * 100}%`;
  picker.querySelector(".hue .knob").style.left = `${h * 100}%`;
  picker.querySelector(".preview").style.background = hex;
  const field = picker.querySelector(".hex");
  if (document.activeElement !== field) field.value = hex;
  return hex;
}

function openPicker(anchor, value, onChange) {
  pickerState.hsv = hexToHsv(value);
  pickerState.onChange = onChange;
  pickerState.gesture = newGesture("hex");   // typing a hex is one undo step
  picker.hidden = false;
  paintPicker();
  const box = anchor.getBoundingClientRect();
  const own = picker.getBoundingClientRect();
  picker.style.left = `${Math.min(box.left, innerWidth - own.width - 10)}px`;
  picker.style.top = `${Math.min(box.bottom + 6, innerHeight - own.height - 10)}px`;
  picker.querySelector(".hex").focus({ preventScroll: true });
}

const closePicker = () => {
  picker.hidden = true;
  pickerState.onChange = null;
  endGesture();
};

function drag(node, move) {
  node.addEventListener("pointerdown", (event) => {
    node.setPointerCapture(event.pointerId);
    pickerState.gesture = newGesture("drag");   // the whole drag is one undo step
    const run = (e) => {
      const box = node.getBoundingClientRect();
      move((e.clientX - box.left) / box.width, (e.clientY - box.top) / box.height);
      pickerState.onChange?.(paintPicker());
    };
    run(event);
    const up = () => {
      node.removeEventListener("pointermove", run);
      node.removeEventListener("pointerup", up);
      pickerState.gesture = newGesture("hex");
      endGesture();
    };
    node.addEventListener("pointermove", run);
    node.addEventListener("pointerup", up);
  });
}

const clamp = (n) => Math.max(0, Math.min(1, n));
drag(picker.querySelector(".area"), (x, y) => {
  pickerState.hsv.s = clamp(x);
  pickerState.hsv.v = clamp(1 - y);
});
drag(picker.querySelector(".hue"), (x) => { pickerState.hsv.h = clamp(x); });

picker.querySelector(".hex").addEventListener("input", (event) => {
  const value = event.target.value.trim();
  if (/^#[0-9a-fA-F]{6}$/.test(value)) {
    pickerState.hsv = hexToHsv(value.toLowerCase());
    paintPicker();
    pickerState.onChange?.(value.toLowerCase());
  }
});

document.addEventListener("pointerdown", (event) => {
  if (!picker.hidden && !picker.contains(event.target)
      && !event.target.closest(".swatch")) closePicker();
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePicker(); });

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

/* Every change goes through here, so undo covers generating a palette as well
   as nudging one swatch.

   A gesture is one continuous action that fires many changes — a drag in the
   picker, typing a name. All of its changes share one undo step; without this,
   undo after a drag walks back one pointermove at a time and looks broken. */
let gesture = null;
let gestures = 0;
const newGesture = (kind) => `${kind}:${++gestures}`;
const endGesture = () => { gesture = null; };

function change(mutate, during = null) {
  if (during === null || during !== gesture) {
    history.past.push(JSON.stringify(state.theme));
    history.future.length = 0;
  }
  gesture = during;
  mutate(state.theme);
  render();
}

function travel(from, to) {
  if (!from.length) return;
  // The picker is bound to the value it opened with; leaving it open after
  // undo would let the next drag write over what undo just restored.
  closePicker();
  endGesture();
  to.push(JSON.stringify(state.theme));
  state.theme = JSON.parse(from.pop());
  render();
}

const undo = () => travel(history.past, history.future);
const redo = () => travel(history.future, history.past);

const dirty = () => JSON.stringify(state.theme) !== state.saved;

// --- rows -------------------------------------------------------------------

function colorRow(role, { chrome = false } = {}) {
  const key = chrome ? `chrome_${role}` : role;
  const pinned = !chrome || key in state.theme;
  const value = state.theme[key] ?? derivedValue(role);

  const row = el("div", { className: "row" });
  row.classList.toggle("pinned", chrome && pinned);
  row.classList.toggle("derived", chrome && !pinned);
  row.dataset.key = key;

  const swatch = el("button", { className: "swatch", type: "button" });
  swatch.style.setProperty("--swatch", value);
  swatch.setAttribute("aria-label", `${role} — ${value}`);
  swatch.addEventListener("click", () => {
    openPicker(swatch, value, (next) => setColor(key, next));
  });

  const label = el("span", { className: "label" });
  label.append(el("span", { textContent: role }));
  const warnings = state.analysis.warnings[key];
  if (warnings) {
    label.append(withTip(el("span", { className: "warn", textContent: "⚠️" }), warnings));
  }

  // One button per row, generating that role the way the whole-palette pass
  // would. On the background it generates everything, because "from the
  // background" is the only thing the background could mean.
  const isBackground = role === "background";
  const gen = el("button", {
    className: "gen", type: "button", textContent: isBackground ? "✦ all" : "✦",
  });
  withTip(gen, [isBackground
    ? "Generate every token color from this background."
    : `Generate ${role} from the background.`]);
  gen.addEventListener("click", async () => {
    try {
      let produced;
      if (isBackground) {
        produced = await api("/api/generate/palette", { ...state.theme, ...state.gen });
      } else if (chrome) {
        // Chrome is generated as a set — take the one field this row owns,
        // which also pins it, since a generated value is a chosen one.
        const all = await api("/api/generate/chrome", state.theme);
        produced = { [key]: all[key] };
      } else {
        produced = await api("/api/generate/role",
          { background: state.theme.background, role });
      }
      change((theme) => Object.assign(theme, produced));
    } catch (error) { toast(error.message); }
  });

  row.append(swatch, label, gen);

  if (chrome) {
    const unpin = el("button", { className: "unpin", type: "button", textContent: "×" });
    withTip(unpin, ["Let this follow the background again."]);
    unpin.addEventListener("click", () => change((t) => { delete t[key]; }));
    row.append(unpin);
  } else {
    row.append(el("span"));
  }

  const ratio = state.analysis.contrast[key];
  if (ratio === undefined || isBackground) return row;

  const readout = el("div", { className: "readout" });
  const track = el("div", { className: "track" });
  const fill = el("div", { className: "fill" + (ratio < 4.5 ? " low" : "") });
  fill.style.width = `${Math.min(100, (ratio / 21) * 100)}%`;
  track.append(fill);
  const explanation = `Contrast against the background: ${ratio.toFixed(1)} to 1. `
    + "The tick is 4.5, about where text stops being comfortable to read. "
    + "The bar is full at 21, the most any two colors can differ.";
  track.title = explanation;
  const number = el("span", { className: "value", textContent: `${ratio.toFixed(1)}:1` });
  number.title = explanation;
  readout.append(track, number);

  const wrap = el("div");
  wrap.append(row, readout);
  return wrap;
}

/* What an unpinned chrome field currently resolves to, from the last time the
   server worked the theme out. Reading it back off the painted preview instead
   showed the previous state's value whenever the paint had not landed yet —
   after an undo, an unpinned row could show the pinned color it used to be. */
function derivedValue(role) {
  return state.resolved?.[`chrome_${role}`] ?? "#000000";
}

function setColor(key, value) {
  change((theme) => { theme[key] = value; }, pickerState.gesture);
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
  // what it expands to. Its parts take the palette's working colors.
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

/* Each render awaits the server, so two in flight can finish in either order.
   Only the newest one paints; an older one landing late would put a state
   back on screen that undo had already left. */
let paneRun = 0;

async function renderPanes() {
  const run = ++paneRun;
  const stale = () => run !== paneRun;

  const full = await resolveChrome(state.theme);
  if (stale()) return;
  state.resolved = full;
  $("#rows-chrome").replaceChildren(
    ...CHROME_ROLES.map((r) => colorRow(r, { chrome: true }))
  );

  const a = await simulated(full);
  const b = state.compare ? await displayTheme(state.compare) : null;
  if (stale()) return;

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
   of color blindness sees it. */
async function displayTheme(theme) {
  return simulated(await resolveChrome(theme));
}

async function simulated(full) {
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

  // A full-chroma rainbow at the rim, so the plot reads as the hue wheel it
  // is: every dot's angle can be checked against the color sitting out there.
  // Drawn as arcs rather than a gradient because the wheel wraps, and a
  // linear gradient cannot close a circle.
  const RIM = 122;
  for (let angle = 0; angle < 360; angle += 4) {
    const a0 = (angle * Math.PI) / 180;
    const a1 = ((angle + 4.6) * Math.PI) / 180;
    add("path", {
      class: "rainbow",
      stroke: `hsl(${angle} 95% 60%)`,
      d: `M ${RIM * Math.cos(a0)} ${-RIM * Math.sin(a0)}`
       + ` A ${RIM} ${RIM} 0 0 0 ${RIM * Math.cos(a1)} ${-RIM * Math.sin(a1)}`,
    });
  }

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
let analyzeRun = 0;

function render() {
  // Only when it differs, so typing in it does not have its caret reset.
  if ($("#theme-name").value !== state.theme.name) $("#theme-name").value = state.theme.name;
  $("#dirty").hidden = !dirty();
  $("#builtin").hidden = !state.builtin;

  const background = colorRow("background");
  $("#row-background").replaceChildren(background);
  $("#rows-tokens").replaceChildren(...TOKEN_ROLES.map((r) => colorRow(r)));
  $("#rows-chrome").replaceChildren(
    ...CHROME_ROLES.map((r) => colorRow(r, { chrome: true }))
  );

  renderPanes();
  renderHueMap();

  // Colors are already on screen by now; the numbers can lag a frame or two
  // behind a drag without anyone noticing.
  clearTimeout(analyzeTimer);
  const run = ++analyzeRun;
  analyzeTimer = setTimeout(async () => {
    try {
      const analysis = await api("/api/analyze", state.theme);
      if (run !== analyzeRun) return;   // a newer state is already being analyzed
      state.analysis = analysis;
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
  const { theme, path: resolved, builtin } = await api(
    `/api/theme?path=${encodeURIComponent(path)}`);
  state.theme = theme;
  state.path = resolved;
  state.builtin = Boolean(builtin);
  state.openedAs = theme.name;
  state.saved = JSON.stringify(theme);
  history.past.length = history.future.length = 0;
  render();
  toast(`Opened ${theme.name}`);
}

async function save(path) {
  // Save never writes back over a theme canim ships. Editing one and hitting
  // Save is how you explore, not how you replace what the videos render with,
  // so it turns into Save as with a name of its own.
  if (!path && state.builtin) return saveAs();
  const target = path || state.path;
  if (!target) return saveAs();
  await api("/api/theme", { path: target, theme: state.theme });
  state.path = target;
  state.builtin = false;   // wherever it landed, it is yours now
  state.openedAs = state.theme.name;
  state.saved = JSON.stringify(state.theme);
  render();   // the built-in and unsaved badges both just changed
  toast(`Saved to ${target}`);
}

/** What a copy of the current theme should be called. */
function suggestedName() {
  const name = state.theme.name.trim();
  // Only rename when it is still carrying the built-in's own name. Once you
  // have called it something, that is the name.
  return state.builtin && name === state.openedAs ? `${name} custom` : name;
}

function saveAs() {
  $("#save-current").textContent = state.builtin
    ? `${state.openedAs} is one of canim's own themes, so it is not written `
      + `back over. Choose where your version goes.`
    : state.path
      ? `Currently saved at ${state.path}`
      : "Not saved anywhere yet.";
  $("#save-dialog").showModal();
}

let catalogue = { names: [], directory: "", languages: [] };

async function refreshCatalogue() {
  catalogue = await api("/api/themes");
  $("#language").replaceChildren(
    ...catalogue.languages.map((name) => el("option", { value: name, textContent: name }))
  );
  $("#language").value = catalogue.languages.includes("python") ? "python" : catalogue.languages[0];

  $("#compare-with").replaceChildren(
    el("option", { value: "", textContent: "off" }),
    ...catalogue.names.map((name) => el("option", { value: name, textContent: name }))
  );

  // The knobs start where canim's own defaults are, rather than at a number
  // typed into the page that could drift from them.
  const { harmony, spread, chroma } = catalogue.defaults;
  state.gen = { harmony, spread, chroma };
  $("#harmony").replaceChildren(
    ...catalogue.harmonies.map((name) =>
      el("option", { value: name, textContent: name, selected: name === harmony }))
  );
  for (const [id, value] of [["chroma", chroma], ["spread", spread]]) {
    $(`#${id}`).value = value;
    knobLabel(id, value);
  }
}

async function fillThemeList() {
  // Read the folders again every time: a theme saved since the page loaded
  // has to show up without a refresh.
  catalogue = await api("/api/themes");
  const list = $("#theme-list");
  list.replaceChildren();
  const groups = [
    ["canim", catalogue.names.map((name) => ({ name, at: name }))],
    ["yours", (catalogue.workspace || []).map((t) => ({ name: t.name, at: t.path }))],
  ];
  for (const [label, entries] of groups) {
    if (!entries.length) continue;
    list.append(el("li", { className: "group-label", textContent: label }));
    await addEntries(entries);
  }
}

async function addEntries(entries) {
  const list = $("#theme-list");
  for (const { name, at } of entries) {
    const { theme } = await api(`/api/theme?path=${encodeURIComponent(at)}`);
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
      openTheme(at).catch((e) => toast(e.message));
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
      const produced = await api(`/api/generate/${generate}`, { ...state.theme, ...state.gen });
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

// The name goes through history like a color does. Setting it behind undo's
// back meant the next undo quietly reverted it along with something else.
let nameGesture = null;
$("#theme-name").addEventListener("focus", () => { nameGesture = newGesture("name"); });
$("#theme-name").addEventListener("blur", endGesture);
$("#theme-name").addEventListener("input", (e) => {
  const name = e.target.value;
  change((theme) => { theme.name = name; }, nameGesture);
});

$("#language").addEventListener("change", (e) => {
  $("#source").value = SAMPLES[e.target.value] ?? $("#source").value;
  renderCode();
});
$("#source").addEventListener("input", () => renderCode());

$("#font-size").addEventListener("input", (e) => {
  // The surface sizes everything inside it off this, so the chrome strip and
  // the formula scale with the code rather than staying put.
  document.documentElement.style.setProperty("--preview-size", `${e.target.value}px`);
  $("#font-size-out").value = e.target.value;
});

function knobLabel(id, value) {
  $(`#${id}-out`).value = id === "chroma" ? Number(value).toFixed(2) : Math.round(value);
}

for (const id of ["chroma", "spread"]) {
  $(`#${id}`).addEventListener("input", (event) => {
    state.gen[id] = Number(event.target.value);
    knobLabel(id, event.target.value);
  });
}
$("#harmony").addEventListener("change", (e) => { state.gen.harmony = e.target.value; });

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

$("#open-browse").addEventListener("click", async () => {
  try {
    const { path } = await api("/api/pick", { save: false });
    if (!path) return;  // cancelled
    $("#open-dialog").close();
    await openTheme(path);
  } catch (error) { toast(error.message); }
});

$("#save-browse").addEventListener("click", async () => {
  try {
    const name = suggestedName();
    const slug = name.replace(/\s+/g, "-") || "untitled";
    const { path } = await api("/api/pick", { save: true, suggested: `${slug}.theme.json` });
    if (!path) return;  // cancelled
    // The copy carries the suggested name, so the file and the theme inside
    // it agree about what it is called.
    if (name !== state.theme.name) change((theme) => { theme.name = name; });
    $("#save-dialog").close();
    await save(path.endsWith(".theme.json") ? path : `${path}.theme.json`);
  } catch (error) { toast(error.message); }
});

document.addEventListener("keydown", (event) => {
  const typing = /^(INPUT|TEXTAREA)$/.test(event.target.tagName);
  // The sample code is text you edit, and undo there means undo the typing.
  const ownUndo = event.target.id === "source";
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z" && !ownUndo) {
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
  $("#source").value = SAMPLES[$("#language").value] ?? "";
  await openTheme(catalogue.names.includes("one-dark") ? "one-dark" : catalogue.names[0]);
  await renderCode();
})();

})();
