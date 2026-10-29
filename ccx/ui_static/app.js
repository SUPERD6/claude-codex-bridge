/* ccx ui: draws what /api/data returns. A button whose ccx command the server allows (`run`) asks the server to
   prepare it, shows the exact command it answered and runs it only on a second click (K6); every other button,
   and every button in a snapshot, shows the command to copy. The page never sends a command, only which button.
   Every visible word comes from strings.json (one table, zh + en). Data (titles, summaries, file names) is
   always escaped: it may contain text written by others. No inline handlers: one delegated click listener. */
"use strict";
(function () {
  let STR = {zh: {}, en: {}};
  let LANG = "en", D = null, ALL = null, TOKEN = "", SNAP = false, OFFLINE = false, lastOk = 0, TESTS = false, HIDDEN = 0;
  let filt = "all", sel = null, expanded = {}, query = "", histOpen = {}, drawerSig = "", drawerStable = "", pending = null, chosen = null;
  let ACT = null, FLASH = null;     /* the one button being prepared / confirmed, and the last outcome line */
  const KNOWN = {claude: "Claude", codex: "Codex", deepseek: "DeepSeek", gemini: "Gemini"};
  const FIXED = {claude: "claude", codex: "codex", deepseek: "deepseek"};
  const SPARE = 4;
  const $ = (id) => document.getElementById(id);

  /* ---------- words ---------- */
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"}[c])); }
  function raw(h) { return {__html: h}; }
  /* t(key, params): params are data, so they are escaped unless wrapped with raw(); a missing key shows as [key] */
  function t(k, p) {
    if (p && p.n === 1 && (STR[LANG] || {})[k + "_1"] !== undefined) k += "_1";     // "1 piece", not "1 pieces"
    let s = (STR[LANG] || {})[k];
    if (s === undefined) s = (STR.en || {})[k];
    if (s === undefined) return "[" + esc(k) + "]";
    if (Array.isArray(s)) return s;
    if (p) for (const x in p) { const v = p[x]; s = s.split("{" + x + "}").join(v && v.__html !== undefined ? v.__html : esc(v)); }
    return s;
  }
  function chooseLang() {
    let saved = null;
    try { saved = localStorage.getItem("ccx-lang"); } catch (e) { /* private window */ }
    if (saved === "zh" || saved === "en") return saved;
    if (D && (D.lang === "zh" || D.lang === "en")) return D.lang;
    return (navigator.language || "en").toLowerCase().startsWith("zh") ? "zh" : "en";
  }

  /* ---------- numbers and times ---------- */
  function usd(x) { return x >= 0.995 ? "$" + x.toFixed(2) : x >= 0.0995 ? "$" + x.toFixed(3) : "$" + (x || 0).toFixed(4); }
  function tok(n) { return n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? (n / 1e3).toFixed(1) + "k" : String(n || 0); }
  function dur(s) {
    s = Math.max(0, Math.round(s || 0));
    if (s < 3600) return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
    return t("dur_h", {h: Math.floor(s / 3600), m: Math.floor((s % 3600) / 60)});
  }
  function clock(ts) {
    if (!ts) return "";
    const d = new Date(ts * 1000), now = new Date();
    const hm = String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
    if (d.toDateString() === now.toDateString()) return hm;
    const y = new Date(now); y.setDate(now.getDate() - 1);
    if (d.toDateString() === y.toDateString()) return t("yesterday", {h: hm});
    return t("date_hm", {m: d.getMonth() + 1, d: d.getDate(), h: hm});
  }
  function ago(ts) {
    const s = Math.max(0, Date.now() / 1000 - ts);
    return s < 60 ? t("ago_s", {n: Math.round(s)}) : s < 3600 ? t("ago_m", {n: Math.round(s / 60)}) : t("ago_h", {n: Math.round(s / 3600)});
  }

  /* ---------- agents: known colours fixed, any new one gets the next spare colour ---------- */
  function tone(agent) {
    if (FIXED[agent]) return FIXED[agent];
    const others = ((D && D.agents) || []).filter(a => !FIXED[a]);
    const i = others.indexOf(agent);
    return "x" + ((i < 0 ? others.length : i) % SPARE);
  }
  function agentName(a) { return KNOWN[a] || (a ? a.charAt(0).toUpperCase() + a.slice(1) : t("notyet")); }
  function who(agent, model) {
    if (!agent) return `<span class="who">${t("notyet")}</span>`;
    const c = tone(agent);
    return `<span class="who" style="background:var(--c-${c}-bg);color:var(--c-${c}-ink)">${esc(agentName(agent))}${model ? " · " + esc(model) : ""}</span>`;
  }

  /* ---------- walking the data ---------- */
  function walk(list, f, chain) { for (const p of list || []) { f(p, chain || []); if (p.children) walk(p.children, f, (chain || []).concat([p])); } }
  function acts(list) { const out = []; walk(list, (p, ch) => { if (p.act) out.push({p, chain: ch}); }); return out; }
  function below(p) { return acts(p.children || []).length; }
  /* evaluations, tests and dismissed leftovers (marked `test` by ccx ui) are left out unless asked for */
  function view(d) {
    HIDDEN = 0;
    if (!d || TESTS) return d;
    const prune = (list) => list.filter(p => { if (p.test) HIDDEN++; return !p.test; })
      .map(p => p.children ? Object.assign({}, p, {children: prune(p.children)}) : p);
    const projects = [];
    for (const pr of d.projects || []) {
      if (pr.test) { for (const tk of pr.tasks) walk(tk.pieces, () => HIDDEN++); continue; }
      const tasks = [];
      for (const tk of pr.tasks) {
        if (tk.test) { walk(tk.pieces, () => HIDDEN++); continue; }
        tasks.push(Object.assign({}, tk, {pieces: prune(tk.pieces)}));
      }
      if (tasks.length) projects.push(Object.assign({}, pr, {tasks}));
    }
    return Object.assign({}, d, {projects, leads: (d.leads || []).filter(l => !l.test),
                                 discussions: (d.discussions || []).filter(x => !x.test),
                                 conversations: (d.conversations || []).filter(x => !x.test)});
  }
  function findProject(id) { return ((D && D.projects) || []).find(x => x.id === id); }
  function findTask(pr, id) { return pr && pr.tasks.find(x => x.id === id); }
  function findPiece(list, id) { let hit = null; walk(list, (p, ch) => { if (p.id === id) hit = {p, chain: ch}; }); return hit; }
  function taskTitle(tk) { return tk.title || (tk.kind === "queue" ? t("queue_task") : t("untitled")); }
  function href(parts, s) { return "#/" + parts.map(encodeURIComponent).join("/") + (s ? "?sel=" + encodeURIComponent(s) : ""); }

  /* ---------- side bar ---------- */
  function quotaHTML() {
    const q = (D && D.quota) || [];
    if (!q.length) return `<div class="qnote">${t("q_none")}</div>`;
    return q.map(w => {
      const used = w.used == null ? null : Math.round(w.used * 100), pj = w.projected == null ? null : Math.round(w.projected * 100);
      const win = w.minutes === 300 || w.window === "five_hour" ? t("w_5h") : w.minutes === 10080 || w.window === "seven_day" ? t("w_7d") : w.minutes ? t("w_min", {n: Math.round(w.minutes / 60)}) : esc(w.window);
      let note = "";
      if (used == null) note = t("q_reset");
      else if (w.note) note = t("q_early");
      else note = `<span class="${pj > 100 ? "fail" : ""}">${t("q_proj", {p: pj})}</span>`;
      const reset = w.resets_at ? t("q_resets", {at: clock(w.resets_at)}) : "";
      return `<div class="qrow"><span>${esc(agentName(w.agent))} · ${win}</span><span>${used == null ? "—" : used + "%"}</span></div>
        <div class="qbar"><i style="width:${Math.min(100, used || 0)}%"></i>${pj != null && !w.note ? `<span class="pj" style="left:calc(${Math.min(100, pj)}% - 2px)"></span>` : ""}</div>
        <div class="qnote">${note}${reset ? " · " + reset : ""}</div>`;
    }).join("");
  }
  function renderSide(route) {
    const all = [];
    for (const pr of (D && D.projects) || []) for (const tk of pr.tasks) all.push(...acts(tk.pieces));
    all.push(...convTodos());
    let state = SNAP ? `<span class="dot snap"></span>${t("snapshot")}` : OFFLINE ? `<span class="dot off"></span>${t("offline")}` :
      `<span class="dot"></span>${D ? t("updated", {a: raw(ago(D.generated))}) : "…"}`;
    let h = `<div class="brand"><b>ccx</b><span style="color:var(--muted)">${t("now")}</span><span class="live">${state}</span></div>
      <input class="search" id="search" placeholder="${esc(t("search"))}" value="${esc(query)}" aria-label="${esc(t("search"))}">
      <nav class="nav" id="nav"><a href="#/" class="${route.length ? "" : "cur"}">${t("overview")}${all.length ? `<span class="badge">${all.length}</span>` : ""}</a>`;
    const talks = (D && D.discussions) || [];
    if (talks.length) h += `<a href="#/discuss" class="${route[0] === "discuss" ? "cur" : ""}">${t("disc_nav")}<span class="mini-n">${talks.length}</span></a>`;
    for (const c of convs()) h += `<a href="${convHref(c.id)}" class="${route[0] === "conv" && route[1] === c.id ? "cur" : ""}">${t("conv_nav")} · ${esc(c.name)}${(c.todos || []).length ? `<span class="badge">${c.todos.length}</span>` : `<span class="mini-n">${c.threads}</span>`}</a>`;
    const q = query.toLowerCase();
    for (const pr of (D && D.projects) || []) {
      const need = pr.tasks.reduce((a, x) => a + acts(x.pieces).length, 0);
      const pmatch = !q || pr.name.toLowerCase().includes(q);
      let inner = "";
      for (const tk of pr.tasks) {
        const s = stats(tk.pieces), k = acts(tk.pieces).length, title = taskTitle(tk);
        const tmatch = !q || title.toLowerCase().includes(q) || pmatch;
        const hits = [];
        if (q) walk(tk.pieces, (p, ch) => { if ((p.title || "").toLowerCase().includes(q)) hits.push({p, ch}); });
        if (!tmatch && !hits.length) continue;
        inner += `<a class="task ${route[1] === tk.id && !route[2] ? "cur" : ""}" href="${href([pr.id, tk.id])}">${esc(title)}${k ? `<span class="badge">${k}</span>` : `<span class="mini"><i style="width:${s.n ? Math.round(100 * s.d / s.n) : 0}%"></i></span>`}</a>`;
        for (const {p, ch} of hits.slice(0, 8)) inner += `<a class="hit" href="${href([pr.id, tk.id].concat(ch.map(x => x.id)), p.id)}">↳ ${esc(p.title)}</a>`;
        if (route[0] === pr.id && route[1] === tk.id && !q) (function sub(list, depth) {
          for (const p of list) if (p.children) {
            const kk = below(p);
            inner += `<a class="sub ${route[route.length - 1] === p.id && route.length > 2 ? "cur" : ""}" style="padding-left:${22 + 16 * depth}px" href="${href(subPath(pr, tk, p))}">↳ ${esc(p.title)}${kk ? `<span class="badge">${kk}</span>` : ""}</a>`;
            sub(p.children, depth + 1);
          }
        })(tk.pieces, 1);
      }
      if (!pmatch && !inner) continue;
      h += `<a class="proj ${route[0] === pr.id && !route[1] ? "cur" : ""}" href="${href([pr.id])}" title="${esc(pr.path)}">▾ ${esc(pr.name)}${need ? `<span class="badge">${need}</span>` : ""}</a>` + inner;
    }
    h += `</nav><div class="foot"><div>${t("quota")}</div>${quotaHTML()}
      <div class="tools"><button data-do="lang">${t("lang_other")}</button><button data-do="theme">${t("theme")}</button>
      <button data-do="tests" aria-pressed="${TESTS}">${TESTS ? t("tests_hide") : t("tests_show", {n: HIDDEN})}</button></div></div>`;
    const side = $("side");
    const focused = document.activeElement && document.activeElement.id === "search";
    const pos = focused ? document.activeElement.selectionStart : null;
    side.innerHTML = h;
    if (focused) { const s = $("search"); s.focus(); try { s.setSelectionRange(pos, pos); } catch (e) { /* ok */ } }
  }
  function subPath(pr, tk, p) { const f = findPiece(tk.pieces, p.id); return [pr.id, tk.id].concat((f ? f.chain : []).map(x => x.id)).concat([p.id]); }
  function stats(list) { return {n: list.length, d: list.filter(p => p.status === "done").length}; }

  /* ---------- overview ---------- */
  function quotaWarn() {
    const bad = ((D && D.quota) || []).filter(w => w.used != null && !w.note && w.projected > 1).sort((a, b) => b.projected - a.projected)[0];
    return bad ? `<span class="warn">${t("ov_quota_bad", {a: agentName(bad.agent), p: Math.round(bad.projected * 100)})}</span>` : "";
  }
  function renderOverview() {
    const todos = [];
    let running = 0, tasks = 0;
    for (const pr of D.projects) for (const tk of pr.tasks) {
      tasks++;
      walk(tk.pieces, (p, ch) => { if (p.status === "run") running++; if (p.act) todos.push({pr, tk, p, ch}); });
    }
    const ct = convTodos();
    let h = banner() + `<h1>${t("ov_title")}</h1>`;
    if (!tasks) {
      h += `<p class="lead">${t("empty")}</p>` + (ct.length ? `<h2>${t("todo_all")}</h2><div class="todo">${convTodoHTML(ct)}</div>` : "")
        + sugHTML() + leadsHTML() + discRecentHTML() + othersHTML() + weekHTML();
      return h;
    }
    const parts = [t("ov_running", {n: running})], nsug = (D && D.suggestions_total) || ((D && D.suggestions) || []).length;
    const nwait = todos.length + ct.length;
    parts.push(nwait ? `<span class="warn">${t("ov_waiting", {n: nwait})}</span>` : `<span class="good">${t("ov_nothing")}</span>`);
    if (nsug) parts.push(`<span class="warn">${t("ov_sug", {n: nsug})}</span>`);
    const qw = quotaWarn(); if (qw) parts.push(qw);
    if (D.inbox) parts.push(`<span class="warn">${t("ov_inbox", {n: D.inbox})}</span>`);
    h += `<p class="lead">${parts.join(" · ")}</p>`;
    if (nwait) {
      h += `<h2>${t("todo_all")}</h2><div class="todo">` + convTodoHTML(ct);
      todos.sort((a, b) => (a.p.act.kind === "review") - (b.p.act.kind === "review"));
      for (const x of todos) h += `<a class="${x.p.act.kind === "review" ? "rv" : ""}" href="${href([x.pr.id, x.tk.id].concat(x.ch.map(c => c.id)), x.p.id)}"><b>${esc(x.p.title)}</b><span>${t(x.p.act.what)}</span><span class="where">${esc(x.pr.name)} › ${esc(taskTitle(x.tk))}</span></a>`;
      h += `</div>`;
    }
    h += runningHTML() + sugHTML() + leadsHTML() + discRecentHTML();
    h += `<h2>${t("projects")}</h2><div class="grid">`;
    for (const pr of D.projects) {
      let n = 0, d = 0, need = 0; const ws = new Set();
      for (const tk of pr.tasks) { const s = stats(tk.pieces); n += s.n; d += s.d; need += acts(tk.pieces).length; walk(tk.pieces, p => { if (p.worker) ws.add(p.worker); }); }
      h += `<a class="card pcard" href="${href([pr.id])}"><div class="top"><b>${esc(pr.name)}</b>${levelHTML(pr)}${need ? `<span class="badge">${t("needs_n", {n: need})}</span>` : ""}${(pr.rules || []).length ? `<span class="rulesb" title="${esc(t("rules_title"))}">${t("rules_n", {n: pr.rules.length})}</span>` : ""}</div>
        <div class="pbar"><i style="width:${n ? Math.round(100 * d / n) : 0}%"></i></div><div class="m">${t("tasks_pieces", {t: pr.tasks.length, d, n})}</div>
        <div class="whos">${[...ws].map(w => who(w)).join("")}</div></a>`;
    }
    return h + `</div>` + othersHTML() + weekHTML();
  }
  /* U4: every run going on now, with its agent, time so far, tokens when known, and the piece's own stop button
     (the same prepare -> exact command -> second click as everywhere; a snapshot shows the command) */
  function runningHTML() {
    const rs = ((D && D.running) || []).filter(r => TESTS || !r.test);
    if (!rs.length) return "";
    let h = `<h2>${t("run_now")}</h2><div class="runs">`;
    for (const r of rs) {
      const key = r.project + "|" + r.task + "|" + r.piece;
      h += `<div class="runrow${r.stale ? " stale" : ""}"><div class="rt"><a href="${href([r.project, r.task], r.piece)}">${esc(r.title)}</a> ${who(r.worker, r.model)}</div>`
        + `<span class="rm"><span data-rsecs="${esc(r.piece)}">${t("run_for", {t: dur(r.secs)})}</span>${r.tokens ? " · " + t("run_tokens", {n: tok(r.tokens)}) : ""}${r.stale ? ` · <span class="warn">${t("run_stale")}</span>` : ""}</span>`;
      if (r.btn && !SNAP) h += `<button class="btn bad" data-rbtn="${esc(r.btn)}" data-key="${esc(key)}">${t("b_stop")}</button>`;
      else if (r.cmd) h += `<code class="mono">${esc(r.cmd)}</code>`;
      h += `<div class="cmd" data-actbox="${esc(key)}" hidden></div></div>`;
    }
    return h + `</div>`;
  }
  /* H5: notes ccx suggests keeping, each waiting for a yes or no (the page's one write; a snapshot shows the command) */
  const SUG_KINDS = {preference: "sug_preference", decision: "sug_decision", pitfall: "sug_pitfall"};
  function sugHTML() {
    const ss = (D && D.suggestions) || [];
    if (!ss.length) return "";
    let h = `<h2>${t("sug_title")}</h2><p class="stat">${t("sug_lead")}</p><div class="todo sug">`;
    for (const s of ss) {
      const id = esc(s.id), busy = sugBusy[s.id];
      h += `<div class="sugrow"><div><b>${esc(s.text)}</b><span class="where">${t(SUG_KINDS[s.kind] || "sug_other")} · ${esc(s.source || "")}</span></div>`;
      h += SNAP ? `<code>ccx mem accept ${id}</code>`
        : `<span class="acts"><button class="btn primary" data-sug="${id}" data-ok="1"${busy ? " disabled" : ""}>${t("sug_yes")}</button>`
          + `<button class="btn" data-sug="${id}" data-ok="0"${busy ? " disabled" : ""}>${t("sug_no")}</button></span>`;
      h += (busy === "err" ? `<span class="warn">${t("sug_failed")}</span>` : "") + `</div>`;
    }
    const more = ((D && D.suggestions_total) || 0) - ss.length;
    return h + `</div>` + (more > 0 ? `<p class="stat">${t("sug_more", {n: more})}</p>` : "");
  }
  const sugBusy = {};
  async function decideSug(id, ok) {
    sugBusy[id] = 1; render();
    try {
      await api("/api/suggestion", {method: "POST", headers: {"X-CCX-Token": TOKEN, "Content-Type": "application/json"},
                                    body: JSON.stringify({id: +id, accept: ok})});
      D.suggestions = (D.suggestions || []).filter(s => String(s.id) !== String(id));
      if (D.suggestions_total) D.suggestions_total--;
      delete sugBusy[id];
    } catch (e) { sugBusy[id] = "err"; }
    render();
  }
  function discRecentHTML() {
    const talks = (D && D.discussions) || [];
    return talks.length ? `<h2>${t("disc_recent")}</h2>` + discListHTML() : "";
  }
  function leadsHTML() {
    const ls = (D && D.leads) || [];
    if (!ls.length) return "";
    return `<h2>${t("leads_now")}</h2><div class="leads">` + ls.map(l => `<div class="card">${who(l.agent, l.model)} <span style="color:var(--muted);font-size:13px">${esc(shortPath(l.cwd))} · ${ago(l.last)}${l.helpers && l.helpers.length ? " · " + t("helpers_n", {n: l.helpers.length}) : ""}</span></div>`).join("") + `</div>`;
  }
  function shortPath(p) { if (!p) return ""; const s = String(p).replace(/\\/g, "/").split("/").filter(Boolean); return s[s.length - 1] || p; }
  function weekHTML() {
    const w = (D && D.week) || {runs: 0};
    let h = `<h2>${t("worth")}</h2>` + monthHTML() + `<p class="stat">${t("week_spent", {u: usd(w.usd || 0), n: w.runs || 0})}${w.cash_usd ? " " + t("week_cash", {u: usd(w.cash_usd)}) : ""}</p>`;
    return h + trackHTML();
  }
  /* H9: who is right the first time, per kind of work (judged pieces only) */
  function trackHTML() {
    const tr = (D && D.track) || {}, rows = [];
    for (const kind of Object.keys(tr).sort()) for (const a of Object.keys(tr[kind]).sort()) {
      const s = tr[kind][a];
      if (s.judged) rows.push(`<tr><td>${esc(t("kind_" + kind))}</td><td>${who(a)}</td><td>${s.judged}${s.enough ? "" : ` <span class="cost">${t("track_few")}</span>`}</td><td>${Math.round(100 * s.first_right)}%</td><td>${Math.round(100 * s.rework)}%</td></tr>`);
    }
    if (!rows.length) return `<h2>${t("track_title")}</h2><p class="stat">${t("track_none", {n: (D && D.track_min) || 5})}</p>`;
    return `<h2>${t("track_title")}</h2><table class="track"><thead><tr><th>${t("track_kind")}</th><th>${t("track_who")}</th><th>${t("track_judged")}</th><th>${t("track_first")}</th><th>${t("track_rework")}</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
  }
  function banner() {
    if (SNAP) return `<div class="banner snap">${t("snap_banner", {at: clock(D.generated)})}</div>`;
    if (OFFLINE) return `<div class="banner">${t("offline_banner")}</div>`;
    if (FLASH && Date.now() - FLASH.at < 20000) return `<div class="banner ${FLASH.ok ? "ok" : ""}" role="status">${FLASH.html}</div>`;
    return "";
  }

  /* ---------- K6: this month, the other projects, optional slots (autonomy level, inbox) ---------- */
  function monthHTML() {
    const m = D && D.month;
    if (!m) return `<p class="stat">${t("month_wait")}</p>`;
    const since = new Date(m.since * 1000), day = t("date_md", {m: since.getMonth() + 1, d: since.getDate()});
    let h = `<p class="stat">${t("month_spent", {d: day, u: usd(m.sub_usd || 0), n: m.runs || 0})}</p>`;
    if (m.saving == null) return h + `<p class="stat">${t("month_saving_none")}</p>`;
    const ci = m.ci95 && m.ci95.length === 2 ? t("month_ci", {a: usd(Math.abs(m.ci95[0])) , b: usd(Math.abs(m.ci95[1])), neg: m.ci95[0] < 0 ? "−" : ""}) : "";
    h += `<p class="stat"><b>${t(m.saving >= 0 ? "month_saving" : "month_extra", {u: usd(Math.abs(m.saving)), ci, n: m.n || 0})}</b></p>`;
    return h + `<p class="stat cost">${t(m.kind === "measured" ? "month_measured" : "month_model")}</p>`;
  }
  function othersHTML() {
    const os = ((D && D.others) || []).filter(o => TESTS || !o.test);
    if (!os.length) return "";
    const more = ((D && D.others_total) || 0) - os.length;
    return `<h2>${t("others_title")}</h2><p class="stat">${t("others_lead")}</p><div class="others">`
      + os.map(o => `<span class="chip" title="${esc(o.summary || o.path)}">${esc(o.name)}${o.last ? ` <i>${ago(o.last)}</i>` : ""}</span>`).join("")
      + (more > 0 ? `<span class="chip more">${t("others_more", {n: more})}</span>` : "") + `</div>`;
  }
  function levelHTML(pr) { return pr.level ? `<span class="lvlb" title="${esc(t("level_title"))}">${esc(pr.level)}</span>` : ""; }
  function rulesHTML(pr) {
    if (!(pr.rules || []).length) return "";
    return `<h2>${t("rules_title")}</h2><p class="stat">${t("rules_lead")}</p><ul class="files">`
      + pr.rules.map(r => `<li><span class="mono">${esc(r.file)}:${esc(r.line)}</span> ${esc(r.text)}</li>`).join("") + `</ul>`;
  }

  /* ---------- K6: a button that runs its ccx command: prepare -> the exact command -> confirm -> run once ---------- */
  function where(key) { const [project, task, piece] = key.split("|"); return {project, task, piece: piece === "_" ? null : piece}; }
  function actBox(key, b) {
    if (!ACT || ACT.key !== key) return "";
    const cancel = `<button class="btn" data-do="act-cancel">${t("act_cancel")}</button>`;
    if (ACT.stage === "usd") return `<div class="k">${t(b ? b.label : "b_budget")} — ${t("act_usd")}</div><div class="acts"><input type="number" id="usdin" min="0.01" max="10000" step="0.5" value="${esc(ACT.usd)}" aria-label="${esc(t("act_usd"))}"><button class="btn primary" data-do="act-usd">${t("act_next")}</button>${cancel}</div>`;
    if (ACT.stage === "busy") return `<div class="k">${t("act_busy")}</div>`;
    if (ACT.stage === "err") return `<div class="k"><span class="warn">${t("act_failed", {e: ACT.msg || ""})}</span></div><div class="acts">${cancel}</div>`;
    if (ACT.stage === "confirm") return `<div class="k">${t(ACT.label)} — ${t("act_will")}</div><code class="mono" id="cmdtext">${esc(ACT.cmd)}</code>`
      + `<p class="${ACT.spends ? "warn" : "cost"}" style="margin:6px 0">${t(ACT.spends ? "act_spends" : "act_records")}</p>`
      + `<div class="acts"><button class="btn ${ACT.spends ? "bad" : "primary"}" data-do="act-run">${t(ACT.spends ? "act_confirm_spend" : "act_confirm")}</button>${cancel}<button data-do="copy">${t("copy")}</button></div>`;
    return "";
  }
  function paintAct() {
    const c = $("cmd");
    if (c && ACT) { c.hidden = true; chosen = null; }      /* one box at a time: the copy-only one goes */
    for (const el of document.querySelectorAll("[data-actbox]")) {
      const key = el.dataset.actbox, h = actBox(key, ACT && ACT.key === key ? ACT.b : null);
      el.innerHTML = h; el.hidden = !h;
    }
  }
  async function prepare(key, btn, b, fill) {
    ACT = {key, btn, b, label: b.label, stage: "busy"}; paintAct();
    try {
      const r = await post("/api/act/prepare", Object.assign(where(key), {btn, fill: fill || {}}));
      Object.assign(ACT, {stage: "confirm", cmd: r.cmd, nonce: r.nonce, spends: r.spends});
    } catch (e) { Object.assign(ACT, {stage: "err", msg: e.message}); }
    paintAct();
  }
  async function runAct() {
    if (!ACT || ACT.stage !== "confirm") return;
    const a = ACT; a.stage = "busy"; paintAct();
    try {
      const r = await post("/api/act/run", {nonce: a.nonce});
      const html = r.started ? t("act_started", {c: raw(`<code class="mono">${esc(r.cmd)}</code>`)})
        : r.ok ? t("act_done", {c: raw(`<code class="mono">${esc(r.cmd)}</code>`)})
        : t("act_exit", {c: raw(`<code class="mono">${esc(r.cmd)}</code>`), e: String(r.exit), m: (r.err || r.out || "").slice(-300)});
      FLASH = {at: Date.now(), ok: !!r.ok, html}; ACT = null;
      await refresh(); render();
    } catch (e) { Object.assign(a, {stage: "err", msg: e.message}); paintAct(); }
  }
  async function post(path, body) {
    const r = await fetch(path, {method: "POST", cache: "no-store", credentials: "omit",
      headers: {"X-CCX-Token": TOKEN, "Content-Type": "application/json"}, body: JSON.stringify(body)});
    let j = {}; try { j = await r.json(); } catch (e) { /* empty */ }
    if (!r.ok) throw new Error(j.error || String(r.status));
    return j;
  }
  /* a button was pressed: runnable ones go through prepare; the rest (and every one in a snapshot) show the command */
  function pressBtn(key, holder, id) {
    const b = (id[0] === "a" ? (holder.act || {}).buttons : holder.ctl || [])[+id.slice(1)];
    if (!b) return;
    if (SNAP || !b.run) { if (id[0] === "a") showCmd(holder, +id.slice(1), false); else fillCmd(b.label, b.cmd); return; }
    if (b.cmd.includes("{reason}") || b.cmd.includes("{note}")) { showCmd(holder, +id.slice(1), false); return; }
    if (b.cmd.includes("{usd}")) {
      const tk = findTask(findProject(where(key).project), where(key).task) || {};
      const base0 = holder === tk ? Math.max(tk.budget || 0, tk.spent || 0) : 0;
      ACT = {key, btn: id, b, label: b.label, stage: "usd", usd: (Math.ceil(base0) + 5).toFixed(2)}; paintAct(); return;
    }
    prepare(key, id, b, {});
  }

  /* ---------- discussions (ccx discuss): turns drawn as a conversation ---------- */
  function discListHTML(cur) {
    const talks = (D && D.discussions) || [];
    if (!talks.length) return `<p class="lead">${t("disc_none")}</p>`;
    return `<div class="todo talks">` + talks.map(x => `<a class="${x.id === cur ? "cur" : ""}" href="#/discuss/${encodeURIComponent(x.id)}"><b>${esc(x.question)}</b><span>${t("disc_state_" + (x.state || "running"))} · ${(x.turns || []).length} ${t("disc_turns")} · ${usd(x.usd || 0)}</span><span class="where">${clock(x.ts)}</span></a>`).join("") + `</div>`;
  }
  function discHTML(id) {
    const talks = (D && D.discussions) || [];
    const x = talks.find(d => d.id === id) || (!id ? talks[0] : null);
    let h = banner() + `<div class="crumbs"><a href="#/">${t("overview")}</a> › ${t("disc_nav")}</div><h1>${t("disc_title")}</h1>`;
    if (!x) return h + discListHTML();
    const rl = x.roles || {};
    h += `<p class="lead"><b>${esc(x.question)}</b><br>${["proposer", "critic", "judge"].map(r => `${t("role_" + r)} ${who(rl[r])}`).join(" ")}${x.judge_independent === false ? " · " + t("disc_two") : ""}</p><div class="chat">`;
    let rnd = 0;
    for (const tn of x.turns || []) {
      if (tn.round !== rnd && tn.role !== "judge") { rnd = tn.round; h += `<div class="rnd">${t("disc_round", {n: rnd})}</div>`; }
      h += `<div class="msg ${esc(tn.role)}"><div class="hd">${who(tn.agent, tn.model)} <span>${t("role_" + tn.role)}</span><span class="cost">${usd(tn.usd || 0)}</span>${tn.unparsed ? ` <span class="warn">${t("disc_unparsed")}</span>` : ""}</div>
        <p>${esc(tn.summary)}</p>${(tn.points || []).length ? `<ul>${tn.points.map(pt => `<li>${esc(pt)}</li>`).join("")}</ul>` : ""}</div>`;
    }
    if (x.state === "running" || x.state === "starting") h += `<div class="rnd">${t("disc_state_" + x.state)}…</div>`;
    h += `</div>`;
    const r = x.result;
    if (r) {
      h += `<h2>${t("disc_outcome")}${x.agreed ? ` <span class="good">${t("disc_agreed")}</span>` : ""}</h2><div class="card outcome"><p><b>${t("disc_recommend")}</b> ${esc(r.recommendation)}</p>`;
      for (const [k, lab] of [["consensus", "disc_consensus"], ["disagreements", "disc_disagree"], ["reasons", "disc_reasons"]])
        if ((r[k] || []).length) h += `<div class="k">${t(lab)}</div><ul>${r[k].map(s => `<li>${esc(s)}</li>`).join("")}</ul>`;
      if (r.note) h += `<p class="cost">${esc(r.note)}</p>`;
      if (r.unparsed) h += `<p class="cost"><span class="warn">${esc(r.unparsed)}</span></p>`;
      h += `</div>`;
    }
    if (x.error) h += `<p class="lead"><span class="warn">${esc(x.error)}</span></p>`;
    h += `<p class="cost">${t("disc_total", {u: usd(x.usd || 0)})} · <code class="mono">ccx discuss --show ${esc(x.id)}</code></p>`;
    if (talks.length > 1) h += `<h2>${t("disc_others")}</h2>` + discListHTML(x.id);
    return h;
  }

  /* ---------- U2: the agents' conversation (each project's board: ccx say / ccx reply), I1: the person's reply ----------
     Every message is text written by agents (or remote copies of the board): esc() always, shown as plain text. The
     reply goes through the same two steps as a button: prepare (the server answers what it will write and a nonce),
     then a second click writes it once, as the person, via ui. It is a message on the board, never a command. */
  let CONV = null, CONVKEY = "", CONVSIG = "", CONVBUSY = false, CONVERR = "", SAY = null;
  const DRAFT = {};
  function convs() { return (D && D.conversations) || []; }
  function convTodos() { const out = []; for (const c of convs()) for (const x of c.todos || []) out.push({c, x}); return out; }
  function convHref(pid, th) { return "#/conv/" + encodeURIComponent(pid) + (th ? "/" + encodeURIComponent(th) : ""); }
  function vendorOf(w) { const v = String(w || "").split(":")[0].trim().toLowerCase(); return v === "dsh" || v === "deepseek-codex" ? "deepseek" : v === "human" || v === "person" ? "user" : v; }
  function toName(w) { const v = vendorOf(w); return v === "all" ? t("conv_all") : v === "user" ? t("conv_you") : agentName(v); }
  function msgWho(m) { return m.who === "user" ? `<span class="who you">${t("conv_you")}</span>` : who(m.who); }
  function convTodoHTML(list) {
    return list.map(({c, x}) => `<a class="conv" href="${convHref(c.id, x.key)}"><b>${esc(x.text)}</b><span>${x.kind === "stuck" ? t("conv_todo_stuck", {n: x.run}) : t("conv_todo_asks", {w: agentName(vendorOf(x.from))})}</span><span class="where">${esc(c.name)} › ${t("conv_nav")} › ${esc(x.thread)}</span></a>`).join("");
  }
  function convLinkHTML(pid) {
    const c = convs().find(x => x.id === pid);
    return c ? `<p class="stat"><a href="${convHref(pid)}">${t("conv_page_link", {n: c.threads})}</a>${(c.todos || []).length ? ` <span class="badge">${c.todos.length}</span>` : ""}</p>` : "";
  }
  /* one read of /api/conv/<project>; true when a thread changed */
  async function loadConv(pid) {
    const j = await api("/api/conv/" + encodeURIComponent(pid));
    const sig = JSON.stringify([j.threads, j.threads_total]), changed = CONVKEY !== pid || sig !== CONVSIG;
    CONV = j; CONVKEY = pid; CONVSIG = sig; CONVERR = "";
    return changed;
  }
  function wantConv(pid) {
    if (SNAP || CONVBUSY || (CONVKEY === pid && (CONV || CONVERR))) return;
    CONVBUSY = true;
    loadConv(pid).catch(e => { CONV = null; CONVKEY = pid; CONVERR = (e && e.message) || "?"; })
      .then(() => { CONVBUSY = false; if (route().r[0] === "conv") render(); });
  }
  function msgHTML(m) {
    const via = m.via && m.via !== m.from ? " · " + t("conv_via", {v: m.via}) : "";
    return `<div class="msg bmsg${m.who === "user" ? " you" : ""}${m.asks ? " asks" : ""}"><div class="hd">${msgWho(m)}<span>→ ${esc(toName(m.to))}</span><span class="mono">#${esc(m.id)}${m.reply_to ? " re #" + esc(m.reply_to) : ""}</span><span class="cost">${clock(m.ts)}${via}</span></div>`
      + `<p class="btext">${esc(m.text)}</p>${m.cut ? `<p class="cost">${t("conv_cut", {n: m.chars})}</p>` : ""}${m.asks ? `<p class="warn">${t("conv_asks_you")}</p>` : ""}</div>`;
  }
  function threadHead(pid, x, open) {
    const flags = (x.stuck ? ` <span class="warn">${t("conv_stuck", {n: x.run})}</span>` : "") + ((x.asks || []).length ? ` <span class="warn">${t("conv_asks_badge")}</span>` : "");
    return `<h2>${open ? esc(x.thread) : `<a href="${convHref(pid, x.key)}">${esc(x.thread)}</a>`} <span class="cost">${t("conv_msgs", {n: x.n})} · ${clock(x.last)}</span>${flags}</h2>`;
  }
  function sayBox(key) {
    if (!SAY || SAY.key !== key) return "";
    const cancel = `<button class="btn" data-do="say-cancel">${t("act_cancel")}</button>`;
    if (SAY.stage === "busy") return `<div class="k">${t("act_busy")}</div>`;
    if (SAY.stage === "err") return `<div class="k"><span class="warn">${t("act_failed", {e: SAY.msg || ""})}</span></div><div class="acts">${cancel}</div>`;
    return `<div class="k">${t("conv_will", {to: toName(SAY.to), thread: SAY.thread, id: SAY.id})}</div><pre class="says btext mono">${esc(SAY.text)}</pre>`
      + `<p class="cost">${t("conv_not_run")} <code class="mono">${esc(SAY.cmd || "")}</code></p>`
      + `<div class="acts"><button class="btn primary" data-do="say-run">${t("conv_send")}</button>${cancel}</div>`;
  }
  function replyHTML(pid, x) {
    const key = pid + "|" + x.key, d = DRAFT[key] || "", max = (CONV && CONV.say_max) || 4000, box = sayBox(key);
    return `<div class="card reply"><label class="k" for="saytext">${t("conv_reply_to", {to: toName(x.reply.to), id: x.reply.id})}</label>`
      + `<textarea id="saytext" data-saykey="${esc(key)}" maxlength="${max}" rows="4">${esc(d)}</textarea>`
      + `<div class="acts"><span class="cost" id="saycount">${t("conv_chars", {n: d.length, m: max})}</span><button class="btn primary" data-do="say-prep">${t("conv_reply")}</button></div>`
      + `<p class="cost">${t("conv_reply_rule", {m: max})}</p><div class="cmd" id="saybox"${box ? "" : " hidden"}>${box}</div></div>`;
  }
  function renderConv(pid, th) {
    const c = convs().find(x => x.id === pid), name = c ? c.name : CONV && CONVKEY === pid ? CONV.project.name : "";
    let h = banner() + `<div class="crumbs"><a href="#/">${t("overview")}</a> › ${name ? esc(name) + " › " : ""}${th ? `<a href="${convHref(pid)}">${t("conv_title")}</a> › ${esc(th)}` : t("conv_title")}</div>`;
    h += `<h1>${t("conv_title")}${name ? " · " + esc(name) : ""}</h1><p class="lead">${t("conv_lead", {n: (CONV && CONV.max_machine) || 6})}</p>`;
    if (SNAP) {
      if (c && (c.todos || []).length) h += `<div class="todo">${convTodoHTML(convTodos().filter(z => z.c.id === pid))}</div>`;
      return h + `<p class="lead">${t("conv_snap")}</p>`;
    }
    if (CONVKEY !== pid || (!CONV && !CONVERR)) { wantConv(pid); return h + `<p class="lead">${t("conv_loading")}</p>`; }
    if (CONVERR || !CONV) return h + `<p class="lead">${t("conv_gone")}</p>`;
    if (!CONV.threads.length) return h + `<p class="lead">${t("conv_none")}</p>`;
    if (th) {
      const x = CONV.threads.find(z => z.key === th);
      if (!x) return h + `<p class="lead">${t("conv_gone")}</p>`;
      h += threadHead(pid, x, true);
      if (x.more) h += `<p class="cost">${t("conv_more", {n: x.more, t: x.thread})}</p>`;
      h += `<div class="chat">${x.messages.map(msgHTML).join("")}</div>`;
      if (x.clipped) h += `<p class="cost">${t("conv_clipped", {t: x.thread})}</p>`;
      return h + replyHTML(pid, x);
    }
    for (const x of CONV.threads) {
      h += threadHead(pid, x, false) + `<div class="chat">${x.messages.slice(-3).map(msgHTML).join("")}</div>`;
      h += `<p class="stat"><a href="${convHref(pid, x.key)}">${t("conv_open")}</a></p>`;
    }
    if (CONV.threads_total > CONV.threads.length) h += `<p class="cost">${t("conv_more_threads", {n: CONV.threads_total - CONV.threads.length})}</p>`;
    return h;
  }
  /* a redraw keeps what the person is typing: the draft, the focus and the caret */
  function drawConv(pid, th) {
    const ta = $("saytext"), focused = ta && document.activeElement === ta, a = focused ? ta.selectionStart : 0, b = focused ? ta.selectionEnd : 0;
    const keep = window.scrollY;
    $("main").innerHTML = renderConv(pid, th);
    const nt = $("saytext");
    if (focused && nt) { nt.focus(); try { nt.setSelectionRange(a, b); } catch (e) { /* ok */ } }
    window.scrollTo(0, keep);
  }
  function paintSay() {
    const box = $("saybox"), ta = $("saytext"); if (!box || !ta) return;
    const h = sayBox(ta.dataset.saykey); box.innerHTML = h; box.hidden = !h;
  }
  async function prepSay() {
    const ta = $("saytext"); if (!ta || !CONV || SNAP) return;
    const key = ta.dataset.saykey, cut = key.indexOf("|"), pid = key.slice(0, cut), thread = key.slice(cut + 1);
    const x = CONV.threads.find(z => z.key === thread), text = ta.value;
    SAY = {key, stage: "busy", text}; paintSay();
    try {
      const r = await post("/api/say/prepare", {project: pid, thread, reply_to: x ? x.reply.id : null, text});
      if (SAY && SAY.key === key && SAY.text === text) Object.assign(SAY, {stage: "confirm", nonce: r.nonce, to: r.to, id: r.reply_to, thread: r.thread, cmd: r.cmd});
    } catch (e) { if (SAY && SAY.key === key) Object.assign(SAY, {stage: "err", msg: e.message}); }
    paintSay();
  }
  async function runSay() {
    if (!SAY || SAY.stage !== "confirm") return;
    const s = SAY; s.stage = "busy"; paintSay();
    try {
      const r = await post("/api/say/run", {nonce: s.nonce});
      FLASH = {at: Date.now(), ok: true, html: t("conv_sent", {id: r.posted.id, thread: r.posted.thread})};
      delete DRAFT[s.key]; SAY = null;
      const ta = $("saytext"); if (ta) ta.value = "";
      try { await refresh(); } catch (e) { /* the next poll */ }
      const rt = route().r; if (rt[0] === "conv") { try { await loadConv(rt[1]); } catch (e) { /* the next poll */ } }
      render();
    } catch (e) { Object.assign(s, {stage: "err", msg: e.message}); paintSay(); }
  }

  /* ---------- a project page ---------- */
  function renderProject(pr) {
    let h = banner() + `<div class="crumbs"><a href="#/">${t("overview")}</a> › ${esc(pr.name)}</div><h1>${esc(pr.name)}${levelHTML(pr)}</h1><p class="lead mono" style="font-size:13px">${esc(pr.path)}</p>${convLinkHTML(pr.id)}${rulesHTML(pr)}<h2>${t("tasks")}</h2><div class="grid">`;
    for (const tk of pr.tasks) {
      const s = stats(tk.pieces), k = acts(tk.pieces).length, ws = new Set();
      walk(tk.pieces, p => { if (p.worker) ws.add(p.worker); });
      h += `<a class="card pcard" href="${href([pr.id, tk.id])}"><div class="top"><b>${esc(taskTitle(tk))}</b>${k ? `<span class="badge">${t("needs_n", {n: k})}</span>` : ""}</div>
        <div class="pbar"><i style="width:${s.n ? Math.round(100 * s.d / s.n) : 0}%"></i></div><div class="m">${t("pieces", {d: s.d, n: s.n})} · ${clock(tk.asked)}</div><div class="whos">${[...ws].map(w => who(w)).join("")}</div></a>`;
    }
    return h + "</div>";
  }

  /* ---------- a task page (or a split piece's own page): the org chart, the to-dos on it, the side panel ---------- */
  const SHOW = 4, NEEDS_SHOWN = 6;
  function statusHTML(p) {
    const steps = t("step");
    if (p.status === "done") return `<span class="st pass">${t(p.verdict && p.verdict.soft ? "st_done_soft" : "st_done")}</span>`;
    if (p.status === "run") return `<span class="st" style="color:var(--teal)">${t("st_run", {s: steps[p.step] || "", t: dur(p.secs)})}${p.tokens ? " · " + tok(p.tokens) : ""}</span>`;
    if (p.status === "review") return `<span class="st" style="color:var(--amber)">${t("st_review")}</span>`;
    if (p.status === "decide") return `<span class="st fail">${t("st_decide")}</span>`;
    if (p.status === "fail") return `<span class="st fail">${t("st_fail")}</span>`;
    if (p.status === "split") return `<span class="st" style="color:var(--teal)">${t("st_split")}</span>`;
    return `<span class="st" style="color:var(--muted)">${t("st_queued")}</span>`;
  }
  function pieceHTML(p, base) {
    const cls = p.act ? p.act.kind : p.status === "run" ? "run" : "";
    const flag = p.act ? `<span class="flag">${p.act.kind === "review" ? t("flag_review") : "!"}</span>` : "";
    const dots = p.status === "run" || p.act ? `<span class="dots">${t("step").map((_, i) => `<i class="${(p.skip || []).includes(i) ? "x" : i < p.step ? "d" : i === p.step ? "n" : ""}"></i>`).join("")}</span>` : "";
    let drill = "";
    if (p.children) {
      const c = p.children, n = c.length, d = c.filter(x => x.status === "done").length, r = c.filter(x => x.status === "run").length, k = below(p);
      const pc = x => (100 * x / n).toFixed(1) + "%";
      const link = href(base.concat([p.id]));
      drill = `<div class="pr">${t("in_split", {n, d, r, k})}</div><span class="inbar"><i class="ok" style="width:${pc(d)}"></i><i class="rn" style="width:${pc(r)}"></i><i class="nd" style="width:${pc(c.filter(x => x.act).length)}"></i></span>`
        + (k ? `<a class="inner" href="${link}">${t("inner_needs", {n: k})}</a> ` : "") + `<a class="drill" href="${link}">${t("open_level")}</a>`;
    }
    if (p.native && p.native.length) drill += ` <span class="native">${t("native", {n: p.native.length})}</span>`;
    const from = p._from ? `<div class="pr">${t("from", {w: agentName(p._from.worker), t: p._from.title})}</div>` : "";
    const dim = (filt === "mine" && !p.act) || (filt === "run" && p.status !== "run") ? " dim" : "";
    const rev = p.reviewer ? `<div class="pr">${t("rev", {w: p.reviewer})}</div>` : "";
    return `<div class="piece ${cls}${dim}${sel === p.id ? " on" : ""}" role="button" tabindex="0" data-sel="${esc(p.id)}">${flag}${from}<div class="pt">${esc(p.title)}</div>${rev}${statusHTML(p)}${dots}${drill}</div>`;
  }
  function columns(list) {
    const groups = new Map();
    for (const p of list) { const k = p.worker || "_wait"; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(p); }
    const known = Object.keys(FIXED);
    const rank = k => k === "_wait" ? 99 : known.includes(k) ? known.indexOf(k) : 10;
    return [...groups.keys()].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b)).map(k => [k, groups.get(k)]);
  }
  function renderTask(pr, tk, chainIds) {
    let node = null, chain = [];
    if (chainIds.length) {
      const f = findPiece(tk.pieces, chainIds[chainIds.length - 1]);
      if (f && f.p.children) { node = f.p; chain = f.chain.concat([f.p]); }
    }
    const list = node ? node.children : tk.pieces;
    const base = [pr.id, tk.id].concat(chain.map(x => x.id));
    for (const p of list) if (p.children) p.children.forEach(ch => { if (ch.worker && ch.worker !== p.worker) ch._from = p; });
    const cols = columns(list);
    const s = stats(list);
    const sep = LANG === "zh" ? "、" : ", ";
    const parts = cols.map(([w, ps]) => t("sum_part", {who: w === "_wait" ? t("notyet") : agentName(w), n: ps.length})).join(sep);
    let h = banner() + `<div class="crumbs"><a href="#/">${t("overview")}</a> › <a href="${href([pr.id])}">${esc(pr.name)}</a> › `
      + (node ? `<a href="${href([pr.id, tk.id])}">${esc(taskTitle(tk))}</a> › ` + chain.map((x, i) => i === chain.length - 1 ? esc(x.title) : `<a href="${href([pr.id, tk.id].concat(chain.slice(0, i + 1).map(c => c.id)))}">${esc(x.title)}</a>`).join(" › ") : esc(taskTitle(tk))) + `</div>`;
    h += `<h1>${esc(node ? node.title : taskTitle(tk))}${node ? `<span class="lvl">${t("level", {l: chain.length + 1})}</span>` : ""}</h1>`;
    h += `<p class="lead">${node ? t("sub_sum", {parent: agentName(node.worker), n: list.length, parts}) : t("sum", {n: list.length, parts})} ${t("pieces", {d: s.d, n: s.n})}.</p>`;
    const needs = list.filter(p => p.act).sort((a, b) => (a.act.kind === "review") - (b.act.kind === "review"));
    if (needs.length) {
      const first = needs.slice(0, NEEDS_SHOWN);
      h += `<div class="needs"><span style="color:var(--muted);font-size:13.5px;align-self:center">${t("needs_here")}</span>${first.map(p => `<button type="button" data-sel="${esc(p.id)}" class="chip-todo ${p.act.kind === "review" ? "rv" : ""}${sel === p.id ? " sel" : ""}" aria-pressed="${sel === p.id}" title="${esc(p.title)}">${esc(p.title)} · ${t(p.act.what)}</button>`).join("")}`
        + (needs.length > first.length ? `<button type="button" data-filt="mine" class="chip-todo rv">${t("needs_more", {n: needs.length - first.length})}</button>` : "") + `</div>`;
    }
    h += `<div class="filters">${[["all", "f_all"], ["mine", "f_mine"], ["run", "f_run"]].map(([k, l]) => `<button class="${filt === k ? "on" : ""}" data-filt="${k}">${t(l)}</button>`).join("")}</div>`;
    h += `<div class="layout"><div class="card"><div class="orgwrap"><div class="org">`;
    if (!node) {
      h += `<div class="box you"><div class="t">${t("you_asked", {t: taskTitle(tk)})}</div><div class="m">${t("asked_at", {h: clock(tk.asked)})}</div></div><div class="vline"></div>`;
      const sent = list.filter(p => p.worker).length;
      const lead = tk.lead && tk.lead.agent ? who(tk.lead.agent, null).replace(/>[^<]*<\/span>$/, ">" + t("boss", {m: agentName(tk.lead.agent) + (tk.lead.model ? " · " + tk.lead.model : "")}) + "</span>") : `<span class="who">${t("boss_unknown")}</span>`;
      h += `<div class="box boss"><div>${lead}</div><div class="t">${t("boss_sum", {n: list.length, s: sent})}</div>`;
      if (tk.spent || tk.budget) h += `<div class="cost">${tk.budget ? t("spent_budget", {u: usd(tk.spent || 0), b: usd(tk.budget)}) : t("spent", {u: usd(tk.spent)})}</div>`;
      const tkey = pr.id + "|" + tk.id + "|_";
      if ((tk.ctl || []).length) h += `<div class="acts tctl">${tk.ctl.map((b, i) => `<button class="btn" data-tbtn="c${i}" data-key="${esc(tkey)}">${t(b.label)}</button>`).join("")}</div><div class="cmd" data-actbox="${esc(tkey)}" hidden></div>`;
      if (tk.helpers && tk.helpers.length) h += `<div class="helper">${t("helper", {n: tk.helpers.length})}</div>`;
      h += `</div>`;
    } else {
      h += `<div class="box boss"><div>${who(node.worker, node.model)}</div><div class="t">${esc(node.title)}</div><div class="m">${t("split_n", {n: list.length})}</div></div>`;
    }
    h += `<div class="cols" style="--half:${(50 / Math.max(1, cols.length)).toFixed(2)}">`;
    for (const [w, ps] of cols) {
      const c = w === "_wait" ? null : tone(w);
      const head = w === "_wait" ? `<span class="who">${t("notyet")}</span>` : who(w, ps.find(p => p.model) ? ps.find(p => p.model).model : "");
      const urgent = ps.filter(p => p.act || p.status === "run" || p.id === sel), rest = ps.filter(p => !(p.act || p.status === "run" || p.id === sel));
      const key = (node ? node.id : tk.id) + ":" + w;
      const shown = expanded[key] ? rest : rest.slice(0, Math.max(0, SHOW - urgent.length)), folded = rest.length - shown.length;
      const spent = ps.reduce((a, p) => a + (p.usd || 0), 0);
      h += `<div class="col ${w === "_wait" ? "wait" : ""}" style="border-top-color:${c ? `var(--c-${c})` : "var(--muted)"}"><div class="head">${head}<span class="cnt">${t("count", {n: ps.length})}</span></div>${spent ? `<div class="spent">${t("col_spent", {u: usd(spent)})}</div>` : ""}
        ${urgent.concat(shown).map(p => pieceHTML(p, base)).join("")}${folded ? `<button class="more" data-more="${esc(key)}">${t("more_done", {n: folded})}</button>` : ""}</div>`;
    }
    h += `</div></div></div><div class="legend">${t("legend")}</div>`;
    const hist = node ? [] : (tk.hist || []);
    if (hist.length) {
      const hk = pr.id + "/" + tk.id;
      h += `<details class="hist" data-hist="${esc(hk)}"${histOpen[hk] ? " open" : ""}><summary>${t("hist")}</summary><ul class="tl">${hist.map(x => `<li class="${esc(x.tone || "")}"><time>${clock(x.ts)}</time>${histText(x)}</li>`).join("")}</ul></details>`;
    }
    h += `</div><aside class="drawer card" id="drawer"></aside></div>`;
    if (!sel || !findPiece(list, sel)) sel = needs.length ? needs[0].id : null;
    const old = $("drawer");
    const busy = old && (old.contains(document.activeElement) || !!(old.querySelector("#reasons") || {}).innerHTML);
    $("main").innerHTML = h;
    renderDrawer(list, base, old, busy);
    paintAct();
  }
  /* the fields that change every poll while a run goes on: a panel someone is using keeps its old copy of them */
  function stableOf(p) { const c = Object.assign({}, p); for (const k of ["secs", "tokens", "beat", "ts", "_from"]) delete c[k]; return c; }
  function histText(x) {
    const p = Object.assign({}, x.p || {});
    if (p.w) p.w = agentName(p.w);
    p.soft = p.soft ? "(" + t("soft") + ")" : "";
    return t(x.k, p);
  }

  /* ---------- the side panel: details, and for a red/amber block the reason, evidence and buttons ---------- */
  function renderDrawer(list, base, old, busy) {
    const d = $("drawer"); if (!d) return;
    const f = sel ? findPiece(list, sel) : null;
    const jd = f && JUDGE[judgeKey(f.p)] ? 1 : 0;
    const sig = JSON.stringify([LANG, sel, f && f.p, jd]), stable = JSON.stringify([LANG, sel, f && stableOf(f.p), jd]);
    if (old && (sig === drawerSig || (busy && stable === drawerStable))) { d.replaceWith(old); return; }
    drawerSig = sig; drawerStable = stable;
    if (!f) { d.innerHTML = `<p class="empty">${t("pick")}</p>`; return; }
    const p = f.p, a = p.act;
    let h = "";
    if (a) h += `<span class="tag ${a.kind}">${t(a.kind === "review" ? "t_review" : "t_decide")}</span>`;
    h += `<div class="what">${esc(p.title)}${a ? (LANG === "zh" ? "：" : ": ") + t(a.what) : ""}</div>`;
    if (a && a.why) h += `<p class="why">${whyText(a.why)}</p>`;
    h += `<dl class="dl"><dt>${t("d_who")}</dt><dd>${p.worker ? who(p.worker, p.model) : esc(t("notyet"))}${p.effort ? ` <span style="color:var(--muted)">${esc(p.effort)}</span>` : ""}</dd>`;
    h += `<dt>${t("d_state")}</dt><dd>${statusHTML(p)}</dd>`;
    if (p.secs) h += `<dt>${t("d_time")}</dt><dd>${dur(p.secs)}${p.rounds > 1 ? " · " + t("rounds", {n: p.rounds}) : ""}</dd>`;
    if (p.usd || p.tokens) h += `<dt>${t("d_cost")}</dt><dd>${usd(p.usd || 0)}${p.tokens ? " · " + tok(p.tokens) + " tokens" : ""}${p.live ? " · " + t("live") : ""}</dd>`;
    if (p.check) h += `<dt>${t("ev_check")}</dt><dd><span class="${p.check.passed ? "pass" : "fail"}">${t(p.check.passed ? "passed" : "failed")}</span> <span class="mono" style="font-size:12px">${esc(p.check.cmd || "")}</span></dd>`;
    if (p.review && p.review.verdict && p.review.verdict !== "not-run") h += `<dt>${t("ev_review")}</dt><dd><span class="${p.review.verdict === "pass" ? "pass" : "fail"}">${t("rv_" + p.review.verdict)}</span>${p.reviewer ? " · " + esc(p.reviewer) : ""}</dd>`;
    if (p.verdict) h += `<dt>${t("d_verdict")}</dt><dd>${t(p.verdict.ok ? "vd_ok" : "vd_bad")}${p.verdict.soft ? " (" + t("soft") + ")" : ""}</dd>`;
    if (p.children) h += `<dt>${t("d_inside")}</dt><dd>${t("in_split", {n: p.children.length, d: p.children.filter(x => x.status === "done").length, r: p.children.filter(x => x.status === "run").length, k: below(p)})}<br><a href="${href(base.concat([p.id]))}">${t("open_level")}</a></dd>`;
    if (p.run_id) h += `<dt>${t("d_run")}</dt><dd class="mono" style="font-size:12px">${esc(p.run_id)}</dd>`;
    h += `</dl>`;
    h += judgeHTML(p);
    if (p.review && p.review.issues && p.review.issues.length) h += `<h3>${t("issues")}</h3><ul class="files">${p.review.issues.map(x => `<li>${esc(x)}</li>`).join("")}</ul>`;
    if (p.native && p.native.length) h += `<h3>${t("d_native", {w: agentName(p.worker)})}</h3><ul class="nlist">${p.native.map(x => `<li><span class="mono">${esc(x.id)}</span><div class="m">${tok(x.tokens)} tokens</div></li>`).join("")}</ul>`;
    const ctl = p.ctl || [], key = base[0] + "|" + base[1] + "|" + p.id;
    if (a || ctl.length) {
      const one = (b, id) => `<button class="btn ${esc(b.style || "")}" data-btn="${id}" data-key="${esc(key)}">${t(b.label)}${b.run && !SNAP ? (b.spends ? " ▸" : "") : ""}</button>`;
      h += `<div class="acts">${(a ? a.buttons : []).map((b, i) => one(b, "a" + i)).join("")}${ctl.map((b, i) => one(b, "c" + i)).join("")}</div>`;
      if (!a) h += `<p class="cost">${t("ctl_running")}</p>`;
      h += `<div id="reasons"></div><div class="cmd" data-actbox="${esc(key)}" hidden></div><div class="cmd" id="cmd" hidden></div>`;
    }
    d.innerHTML = h;
    wantJudge(p);
    paintAct();
    if (ACT && ACT.key === key) return;
    if (a && chosen && chosen.sel === p.id) fillCmd(chosen.label, chosen.cmd);
    else if (a && (SNAP || !a.buttons[0].run)) showCmd(p, 0, true);
  }
  /* ---------- U1: is it right? what the agent says beside what ccx ran, and the change from ccx's own snapshots ----------
     Every name, output and diff line is data written by others (a file may be called <img onerror=...>): esc() always. */
  const JUDGE = {}, JBUSY = {}, JFILES = 40;
  function judgeKey(p) { return p && p.run_id ? p.run_id + ":" + p.status + ":" + (p.attempts || 0) + ":" + (p.rounds || 0) : ""; }
  function wantJudge(p) {
    const k = judgeKey(p);
    if (SNAP || !k || p.live || JUDGE[k] || JBUSY[k]) return;
    JBUSY[k] = 1;
    api("/api/judge/" + encodeURIComponent(p.run_id))
      .then(j => { JUDGE[k] = j; }, e => { JUDGE[k] = {error: (e && e.message) || "?"}; })
      .then(() => {
        delete JBUSY[k];
        const cur = currentList(), d = $("drawer");
        if (cur && sel === p.id && d && !d.contains(document.activeElement)) { drawerSig = ""; renderDrawer(cur.list, cur.base, null, false); }
      });
  }
  function diffLines(s) {
    return String(s).split("\n").map(l => {
      const c = l.startsWith("+++") || l.startsWith("---") ? "" : l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : l.startsWith("@@") ? "hunk" : "";
      return c ? `<span class="${c}">${esc(l)}</span>` : esc(l);
    }).join("\n");
  }
  function fileList(list) {
    const more = list.length - JFILES;
    return `<ul class="files mono">${list.slice(0, JFILES).map(x => `<li>${esc(x)}</li>`).join("")}</ul>` + (more > 0 ? `<p class="cost">${t("j_more", {n: more})}</p>` : "");
  }
  function judgeHTML(p) {
    const j = JUDGE[judgeKey(p)] || null, c = p.check;
    let h = "";
    /* the two columns only for a piece that has run: a queued to-do or a live run has said nothing and ccx has run
       nothing yet, and "no check was given" would be wrong there */
    if (!p.live && (p.run_id || p.summary || p.verification || c)) {
    h += `<div class="judge"><div class="jcol"><h3>${t("j_says")}</h3>`;
    if (p.summary) h += `<p class="says">${esc(p.summary)}</p>`;
    h += p.verification ? `<div class="k">${t("j_verified")}</div><p class="says">${esc(p.verification)}</p>` : `<p class="cost">${t("j_no_verif")}</p>`;
    h += `</div><div class="jcol"><h3>${t("j_ran")}</h3>`;
    if (c) {
      const cls = c.passed ? "pass" : c.passed === false ? "fail" : "cost", word = c.passed ? "passed" : c.passed === false ? "failed" : "j_not_judged";
      h += `<p class="says"><span class="${cls}">${t(word)}</span>${c.exit != null ? " · " + t("j_exit", {e: c.exit}) : ""}</p><code class="mono jcmd">${esc(c.cmd || "")}</code>`;
      if (c.broken) h += `<p class="warn">${esc(c.broken)}</p>`;
      if (c.unchanged_tree) h += `<p class="warn">${t("j_unchanged")}</p>`;
      if (c.weak) h += `<p class="warn">${esc(c.weak)}</p>`;
      h += c.tail ? `<div class="k">${t("j_tail")}</div><pre class="tail mono">${esc(c.tail)}</pre>` : `<p class="cost">${t("j_no_tail")}</p>`;
    } else h += `<p class="cost">${t("j_no_check")}</p>`;
    h += `</div></div>`;
    }
    if (j && j.changed) {
      const mm = j.mismatch;
      if (mm) {
        h += `<div class="mismatch"><b>${t("j_mismatch")}</b>`;
        if ((mm.said_not_changed || []).length) h += `<div class="k">${t("j_said_not")}</div>` + fileList(mm.said_not_changed);
        if ((mm.changed_not_said || []).length) h += `<div class="k">${t("j_changed_not")}</div>` + fileList(mm.changed_not_said);
        if ((mm.changed_not_said || []).length && c && c.cmd) h += `<p class="cost">${t("j_check_files")}</p>`;
        h += `</div>`;
      } else if (j.changed.length) h += `<p class="good-note">${t("j_match")}</p>`;
      h += `<h3>${t("j_changed", {n: j.changed.length})}</h3>` + fileList(j.changed.map(x => x.status + "  " + x.path));
      if (j.chain_from) h += `<p class="cost">${t("j_chain", {r: j.chain_from})}</p>`;
      if ((j.untracked_before || []).length) h += `<p class="cost">${t("j_untracked_before", {n: j.untracked_before.length})}</p>`;
      if (j.diff != null) h += `<details class="diffbox"><summary>${t("j_diff")}</summary><pre class="diff mono">${diffLines(j.diff)}</pre>${j.truncated ? `<p class="warn">${t("j_truncated")}</p>` : ""}</details>`;
      if (j.truncated) h += `<p class="warn">${t("j_truncated")}</p>`;
    } else if (p.files && p.files.length) h += `<h3>${t("ev_changed")}</h3>` + fileList(p.files);
    if (j && j.note) h += `<p class="cost">${t(j.note)}</p>`;
    if (j && j.error) h += `<p class="cost">${t("j_failed", {e: j.error})}</p>`;
    if (!j && p.run_id && !p.live) h += `<p class="cost">${t(SNAP ? "j_snap" : "j_loading")}</p>`;
    return h;
  }
  function whyText(why) {
    const [k, p] = why; const q = Object.assign({}, p || {});
    if (q.at) q.at = clock(q.at); else if ("at" in q) q.at = t("unknown");
    if (q.agent) q.agent = agentName(q.agent);
    return t(k, q);
  }
  function quoteArg(s) { s = String(s).replace(/"/g, "'"); return `"${s}"`; }
  function showCmd(p, i, quiet) {
    const a = p.act, c = $("cmd"), r = $("reasons"); if (!a || !c) return;
    const b = a.buttons[i];
    if (r) r.innerHTML = "";
    if (!quiet && ACT) { ACT = null; paintAct(); }
    if (a.reasons && b.style === "bad" && !quiet) {
      r.innerHTML = `<div class="reasons"><div style="font-size:13px;color:var(--muted);margin-bottom:4px">${t("why_bad")}</div>`
        + [["unfinished", "r1"], ["wrong", "r2"], ["overreach", "r3"]].map(([v, l]) => `<label><input type="radio" name="r" value="${v}"> ${t(l)}</label>`).join("")
        + `<label><input type="radio" name="r" value="other" checked> ${t("r4")}<input type="text" id="rnote" maxlength="200"></label><button class="btn bad" style="margin-top:6px;min-height:32px" data-reason="${i}">${t(b.run && !SNAP ? "act_next" : "r_ok")}</button></div>`;
      c.hidden = true; return;
    }
    if (b.cmd.includes("{reason}") || b.cmd.includes("{note}")) { if (quiet) { c.hidden = true; return; } }
    fillCmd(b.label, b.cmd);
  }
  function fillCmd(label, cmd) {
    const c = $("cmd"); if (!c) return;
    chosen = {sel, label, cmd};
    c.hidden = !cmd;
    c.innerHTML = cmd ? `<div class="k">${t(label)} — ${t("will_run")}</div><code class="mono" id="cmdtext">${esc(cmd)}</code><button data-do="copy">${t("copy")}</button>` : "";
  }
  function copy(text, btn) {
    const done = () => { btn.textContent = t("copied"); };
    if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(text).then(done, () => fallbackCopy(text) && done()); return; }
    if (fallbackCopy(text)) done();
  }
  function fallbackCopy(text) {
    const ta = document.createElement("textarea"); ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select(); let ok = false; try { ok = document.execCommand("copy"); } catch (e) { ok = false; } ta.remove(); return ok;
  }

  /* ---------- routing: #/  #/project  #/project/task  #/project/task/piece/... ---------- */
  function route() {
    const [path, qs] = (location.hash.replace(/^#\/?/, "") || "").split("?");
    const r = path ? path.split("/").map(decodeURIComponent).filter(Boolean) : [];
    const s = new URLSearchParams(qs || "").get("sel");
    return {r, s};
  }
  let lastRoute = "";
  function render() {
    if (!D) return;
    LANG = chooseLang();
    document.documentElement.lang = LANG === "zh" ? "zh-CN" : "en";
    const {r, s} = route();
    const key = r.join("/");
    if (key !== lastRoute) { lastRoute = key; filt = "all"; sel = s || null; }
    else if (s && pending !== s) { sel = s; }
    pending = s;
    renderSide(r);
    const main = $("main");
    if (r[0] === "discuss") { main.innerHTML = discHTML(r[1]); return; }
    if (r[0] === "conv") { drawConv(r[1], r[2]); return; }
    const pr = r.length ? findProject(r[0]) : null;
    const tk = pr && r[1] ? findTask(pr, r[1]) : null;
    if (!pr) { main.innerHTML = renderOverview(); paintAct(); return; }
    if (!tk) { main.innerHTML = renderProject(pr); return; }
    const keep = window.scrollY;
    renderTask(pr, tk, r.slice(2));
    window.scrollTo(0, keep);
  }
  function currentList() {
    const {r} = route(); const pr = findProject(r[0]); const tk = pr && findTask(pr, r[1]); if (!tk) return null;
    if (r.length > 2) { const f = findPiece(tk.pieces, r[r.length - 1]); if (f && f.p.children) return {list: f.p.children, base: [pr.id, tk.id].concat(f.chain.map(x => x.id)).concat([f.p.id])}; }
    return {list: tk.pieces, base: [pr.id, tk.id]};
  }

  /* ---------- events (one listener; no inline handlers, the page's CSP forbids them) ---------- */
  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-sel],[data-filt],[data-more],[data-btn],[data-tbtn],[data-rbtn],[data-reason],[data-do],[data-sug]");
    if (!el) return;
    if (el.dataset.do === "say-prep") { prepSay(); return; }
    if (el.dataset.do === "say-run") { runSay(); return; }
    if (el.dataset.do === "say-cancel") { SAY = null; paintSay(); return; }
    if (el.dataset.sug !== undefined) { if (!SNAP && !el.disabled) decideSug(el.dataset.sug, el.dataset.ok === "1"); return; }
    if (el.dataset.do === "act-cancel") { ACT = null; paintAct(); return; }
    if (el.dataset.do === "act-run") { runAct(); return; }
    if (el.dataset.do === "act-usd") {
      const v = ($("usdin") || {}).value;
      if (ACT) { ACT.usd = v; prepare(ACT.key, ACT.btn, ACT.b, {usd: v}); }
      return;
    }
    if (el.dataset.tbtn !== undefined) {           /* a task's own control (the queue's budget) */
      const w = where(el.dataset.key), tk = findTask(findProject(w.project), w.task);
      if (tk) pressBtn(el.dataset.key, tk, el.dataset.tbtn);
      return;
    }
    if (el.dataset.rbtn !== undefined) {           /* the "running now" strip's stop: that piece's own button */
      const w = where(el.dataset.key), tk = findTask(findProject(w.project), w.task), f = tk && findPiece(tk.pieces, w.piece);
      if (f) pressBtn(el.dataset.key, f.p, el.dataset.rbtn);
      return;
    }
    if (el.dataset.do === "lang") { LANG = LANG === "zh" ? "en" : "zh"; try { localStorage.setItem("ccx-lang", LANG); } catch (x) { /* ok */ } render(); return; }
    if (el.dataset.do === "theme") {
      const root = document.documentElement, dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      root.dataset.theme = dark ? "light" : "dark"; try { localStorage.setItem("ccx-theme", root.dataset.theme); } catch (x) { /* ok */ } return;
    }
    if (el.dataset.do === "tests") { TESTS = !TESTS; try { localStorage.setItem("ccx-tests", TESTS ? "1" : ""); } catch (x) { /* ok */ } D = view(ALL); render(); return; }
    if (el.dataset.do === "copy") { const c = $("cmdtext"); if (c) copy(c.textContent, el); return; }
    if (el.dataset.filt) { filt = el.dataset.filt; render(); return; }
    if (el.dataset.more) { expanded[el.dataset.more] = 1; render(); return; }
    const cur = currentList();
    if (el.dataset.sel !== undefined && !e.target.closest("a[href]")) {
      sel = el.dataset.sel; render();
      if (innerWidth < 1100) { const d = $("drawer"); if (d) d.scrollIntoView({behavior: "smooth", block: "start"}); }
      return;
    }
    if (!cur) return;
    const f = sel ? findPiece(cur.list, sel) : null; if (!f || !(f.p.act || (f.p.ctl || []).length)) return;
    if (el.dataset.btn !== undefined) { pressBtn(el.dataset.key, f.p, el.dataset.btn); return; }
    if (el.dataset.reason !== undefined && f.p.act) {
      const i = +el.dataset.reason, b = f.p.act.buttons[i];
      const pick = document.querySelector("#reasons input[name=r]:checked"), note = ($("rnote") || {}).value || "";
      const reason = pick ? pick.value : "other";
      const text = note || t("r_" + reason + "_note");
      $("reasons").innerHTML = "";
      if (b.run && !SNAP) { prepare(cur.base[0] + "|" + cur.base[1] + "|" + f.p.id, "a" + i, b, {reason, note: text}); return; }
      const cmd = b.cmd.split("{reason}").join(reason).split("{note}").join(quoteArg(b.cmd.includes("{reason}") ? text : reason + ": " + text));
      fillCmd(b.label, cmd);
    }
  });
  document.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target.matches && e.target.matches(".piece[data-sel]")) { e.preventDefault(); e.target.click(); }
  });
  document.addEventListener("input", (e) => {
    if (e.target.id === "search") { query = e.target.value; const {r} = route(); renderSide(r); }
    if (e.target.id === "usdin" && ACT) ACT.usd = e.target.value;
    if (e.target.id === "saytext") {
      const key = e.target.dataset.saykey, max = (CONV && CONV.say_max) || 4000;
      DRAFT[key] = e.target.value;
      const n = $("saycount"); if (n) n.textContent = t("conv_chars", {n: e.target.value.length, m: max});
      if (SAY && SAY.key === key && SAY.stage !== "busy" && SAY.text !== e.target.value) { SAY = null; paintSay(); }
    }
  });
  document.addEventListener("toggle", (e) => { if (e.target.dataset && e.target.dataset.hist) histOpen[e.target.dataset.hist] = e.target.open; }, true);
  addEventListener("hashchange", render);

  /* ---------- talking to ccx ui ---------- */
  async function api(path, opts) {
    const r = await fetch(path, Object.assign({headers: {"X-CCX-Token": TOKEN}, cache: "no-store", credentials: "omit"}, opts || {}));
    if (!r.ok) throw new Error(String(r.status));
    return r.json();
  }
  /* Only a real change redraws the page; while a run goes on, its time and tokens are patched in place, so clicks,
     focus and scroll are left alone. */
  const VOLATILE = new Set(["secs", "tokens", "beat", "generated", "last", "reading_age_min", "hours_left"]);
  function stableSig(d) { return d ? JSON.stringify(d, (k, v) => VOLATILE.has(k) ? undefined : v) : ""; }
  function patchLive() {
    const live = $("side") && $("side").querySelector(".brand .live");
    if (live && D) live.innerHTML = `<span class="dot"></span>${t("updated", {a: raw(ago(D.generated))})}`;
    for (const r of (D && D.running) || []) for (const el of document.querySelectorAll("[data-rsecs]")) if (el.dataset.rsecs === r.piece) el.innerHTML = t("run_for", {t: dur(r.secs)});
    const cur = currentList(); if (!cur) return;
    walk(cur.list, p => {
      if (p.status !== "run") return;
      for (const el of document.querySelectorAll(".piece[data-sel]")) if (el.dataset.sel === p.id) {
        const st = el.querySelector(".st"); if (st) st.outerHTML = statusHTML(p);
      }
    });
    const f = sel ? findPiece(cur.list, sel) : null, d = $("drawer");
    if (f && f.p.status === "run" && d && !d.contains(document.activeElement)) { drawerSig = ""; renderDrawer(cur.list, cur.base, null, false); }
  }
  /* one read of /api/data; true when something besides the ticking numbers changed */
  async function refresh() {
    const got = await api("/api/data");
    const changed = stableSig(got) !== stableSig(ALL) || OFFLINE;
    ALL = got; D = view(got); OFFLINE = false; lastOk = Date.now();
    return changed;
  }
  /* U5: new to-dos are read out by screen readers through the one live region outside the redrawn page */
  let SEEN = null;
  function announce() {
    const now = new Set(), fresh = [];
    for (const pr of (D && D.projects) || []) for (const tk of pr.tasks) walk(tk.pieces, p => {
      if (!p.act) return;
      const k = pr.id + "|" + tk.id + "|" + p.id + "|" + p.act.what;
      now.add(k);
      if (SEEN && !SEEN.has(k)) fresh.push(p.title + " — " + t(p.act.what));
    });
    for (const {c, x} of convTodos()) {
      const k = c.id + "|" + x.key + "|" + x.kind + "|" + x.id;
      now.add(k);
      if (SEEN && !SEEN.has(k)) fresh.push(x.text + " — " + t(x.kind === "stuck" ? "conv_todo_stuck" : "conv_todo_asks", {n: x.run, w: agentName(vendorOf(x.from))}));
    }
    SEEN = now;
    const el = $("announce");
    if (el && fresh.length) el.textContent = t("todo_new", {n: fresh.length}) + " " + fresh.slice(0, 3).join("; ");
  }
  async function poll() {
    try {
      let changed = await refresh();
      const rt = route().r;
      if (rt[0] === "conv" && rt[1] && !SNAP) { try { changed = (await loadConv(rt[1])) || changed; } catch (e) { /* shown on the page */ } }
      if (changed) { render(); announce(); } else patchLive();
    } catch (e) {
      if (!OFFLINE && Date.now() - lastOk > 8000) { OFFLINE = true; render(); }
    }
    setTimeout(poll, ((D && D.poll_s) || 3) * 1000);
  }
  /* "still open"; hidden=1 from a background tab, whose timers the browser wakes about once a minute: the server then
     waits several minutes instead of one before it decides the page is gone */
  function alive() { if (!SNAP && TOKEN) api("/api/alive" + (document.hidden ? "?hidden=1" : ""), {method: "POST"}).catch(() => {}); }
  function beat() {
    if (!OFFLINE || Date.now() - lastOk < 60000) alive();
    setTimeout(beat, ((D && D.beat_s) || 10) * 1000);
  }
  /* shown again: say so at once, not in 10 s. Going hidden sends nothing: closing a tab also turns it hidden, and that
     last word must not keep the server up for minutes; a tab that stays open says "hidden" on its next timer beat */
  document.addEventListener("visibilitychange", () => { if (!document.hidden) alive(); });
  addEventListener("focus", alive);

  async function start() {
    try { const th = localStorage.getItem("ccx-theme"); if (th === "dark" || th === "light") document.documentElement.dataset.theme = th; } catch (e) { /* ok */ }
    try { TESTS = localStorage.getItem("ccx-tests") === "1"; } catch (e) { /* ok */ }
    const inlineStr = document.getElementById("ccx-strings"), snap = document.getElementById("ccx-snapshot");
    if (snap) {
      SNAP = true; STR = JSON.parse(inlineStr.textContent); ALL = JSON.parse(snap.textContent); D = view(ALL);
      if (!location.hash) location.hash = "#/";
      render(); return;
    }
    const m = location.hash.match(/^#k=([A-Za-z0-9_-]+)(?:&(\/.*))?$/);      // #k=TOKEN or #k=TOKEN&/project/task
    if (m) {
      TOKEN = m[1];
      try { sessionStorage.setItem("ccx-token", TOKEN); } catch (e) { /* ok */ }
      history.replaceState(null, "", location.pathname + "#" + (m[2] || "/"));
    } else {
      try { TOKEN = sessionStorage.getItem("ccx-token") || ""; } catch (e) { TOKEN = ""; }
    }
    try { STR = await (await fetch("/strings.json", {cache: "no-store"})).json(); } catch (e) { /* keys show */ }
    LANG = chooseLang();
    if (!TOKEN) { $("main").innerHTML = `<h1>ccx ui</h1><p class="lead">${t("no_token")}</p>`; return; }
    alive();
    await poll();
    setTimeout(beat, ((D && D.beat_s) || 10) * 1000);
  }
  start();
})();
