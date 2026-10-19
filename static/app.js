/* AgenticX Decision console */
const $ = (id) => document.getElementById(id);
const state = { mock: false, workspaces: [], ws: null, rules: [], spec: null };

async function api(path, opts = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = typeof data.detail === "string"
      ? data.detail
      : (data.detail && data.detail.problems ? data.detail.problems.join("；") : resp.statusText);
    throw new Error(detail || String(resp.status));
  }
  return data;
}

/* ── steps nav ── */
document.querySelectorAll(".step").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".step").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`step-${btn.dataset.step}`).classList.add("active");
    if (btn.dataset.step === "2") loadWorkspaces();
    if (btn.dataset.step === "3") renderRunRules();
  });
});

/* ── step 1: rules ── */
const EXAMPLE_RULE = "示例成员人数应当在3到15人之间，且人数为奇数（虚构示例规则）";
$("btn-example").addEventListener("click", () => { $("rule-text").value = EXAMPLE_RULE; });

$("btn-decompose").addEventListener("click", async () => {
  const text = $("rule-text").value.trim();
  if (!text) return alert("先写一条规则");
  $("btn-decompose").disabled = true;
  $("btn-decompose").textContent = "拆解中…";
  try {
    const out = await api("/api/rules/decompose", { method: "POST", body: { text } });
    if (out.ok) { fillSpec(out.spec); markSpec(true, ""); }
    else { markSpec(false, out.problems || ["拆解失败"]); $("decompose-result").classList.remove("hidden"); $("spec-status").textContent = "请手工修正"; }
  } catch (e) { alert("拆解失败：" + e.message); }
  finally { $("btn-decompose").disabled = false; $("btn-decompose").textContent = "拆解规则"; }
});

function fillSpec(spec) {
  state.spec = spec;
  $("decompose-result").classList.remove("hidden");
  $("spec-name").value = spec.name || "";
  $("spec-type").value = spec.type || "rule";
  $("spec-template").value = spec.template || "numeric_range";
  $("spec-template").disabled = spec.type !== "rule";
  $("spec-params").value = JSON.stringify(spec.params || {}, null, 2);
  $("spec-regulation").value = spec.regulation || "";
  $("spec-expect").value = spec.expect_verdict || "";
}

function collectSpec() {
  return {
    name: $("spec-name").value.trim(),
    type: $("spec-type").value,
    template: $("spec-type").value === "rule" ? $("spec-template").value : null,
    params: JSON.parse($("spec-params").value || "{}"),
    regulation: $("spec-regulation").value.trim() || "待补充",
    expect_verdict: $("spec-expect").value.trim(),
  };
}

function markSpec(ok, problems) {
  const box = $("spec-problems");
  $("spec-status").textContent = ok ? "✓ 校验通过" : "✗ 有问题";
  $("spec-status").className = "badge " + (ok ? "ok" : "bad");
  if (problems && problems.length) {
    box.classList.remove("hidden");
    box.innerHTML = problems.map((p) => `<div>• ${esc(p)}</div>`).join("");
  } else box.classList.add("hidden");
}

$("spec-type").addEventListener("change", () => { $("spec-template").disabled = $("spec-type").value !== "rule"; });

$("btn-save-rule").addEventListener("click", async () => {
  let spec;
  try { spec = collectSpec(); } catch { return alert("参数不是合法 JSON"); }
  try {
    await api("/api/rules", { method: "POST", body: { spec, expect_verdict: spec.expect_verdict } });
    $("decompose-result").classList.add("hidden");
    $("rule-text").value = "";
    loadRules();
  } catch (e) { markSpec(false, e.message.split("；")); }
});

async function loadRules() {
  const out = await api("/api/rules");
  state.rules = out.rules || [];
  $("rule-count").textContent = `${state.rules.length} 条`;
  const box = $("rules-list");
  if (!state.rules.length) { box.innerHTML = `<div class="muted">还没有规则。写一条 → 拆解 → 保存。</div>`; return; }
  box.innerHTML = state.rules.map((r) => `
    <div class="rule-card">
      <div>
        <div class="rule-name">${esc(r.name)} <span class="badge ${badgeClass(r.type)}">${typeLabel(r)}</span></div>
        <div class="rule-meta">${r.type === "rule" ? esc(r.template) : typeLabel(r)} · ${esc(r.regulation || "")}</div>
      </div>
      <button class="btn ghost small" data-del="${esc(r.id)}">删除</button>
    </div>`).join("");
  box.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api(`/api/rules/${b.dataset.del}`, { method: "DELETE" });
      loadRules();
    }));
}

function typeLabel(r) {
  return { rule: "模板", semantic: "语义", cross_file: "跨文件" }[r.type] || r.type;
}
function badgeClass(t) {
  return { rule: "ok", semantic: "warn", cross_file: "info" }[t] || "";
}

/* ── step 2: workspaces ── */
async function loadWorkspaces() {
  const out = await api("/api/workspaces");
  state.workspaces = out.workspaces || [];
  const box = $("ws-list");
  box.innerHTML = state.workspaces.map((w) => `
    <div class="ws-card ${state.ws && state.ws.id === w.id ? "sel" : ""}" data-ws="${esc(w.id)}">
      <div class="ws-kind">${{ pdf: "单文件 PDF", package: `材料包 · ${w.files || "?"} 个文件`, demo: "离线演示" }[w.kind] || w.kind}</div>
      <div class="ws-name">${esc(w.name)}</div>
    </div>`).join("");
  box.querySelectorAll("[data-ws]").forEach((c) =>
    c.addEventListener("click", () => {
      state.ws = state.workspaces.find((w) => w.id === c.dataset.ws);
      box.querySelectorAll(".ws-card").forEach((x) => x.classList.remove("sel"));
      c.classList.add("sel");
    }));
}

/* ── step 3: run ── */
function renderRunRules() {
  const box = $("run-rules");
  $("run-context").textContent =
    `工作区：${state.ws ? state.ws.name : "未选（默认演示）"} · 规则 ${state.rules.length} 条`;
  if (!state.rules.length) { box.innerHTML = `<div class="muted">规则集为空，回第①步添加。</div>`; return; }
  box.innerHTML = state.rules.map((r) => `
    <label class="chk"><input type="checkbox" value="${esc(r.id)}" checked> ${esc(r.name)}
      <span class="badge ${badgeClass(r.type)}">${typeLabel(r)}</span></label>`).join("");
}

$("btn-run").addEventListener("click", async () => {
  const ids = [...document.querySelectorAll("#run-rules input:checked")].map((i) => i.value);
  $("btn-run").disabled = true;
  $("results").innerHTML = "";
  $("run-summary").classList.add("hidden");
  try {
    const resp = await fetch("/api/audit/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace: state.ws ? state.ws.id : "demo", rule_ids: ids, mock: state.mock }),
    });
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || resp.statusText);
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
        const line = chunk.split("\n").find((l) => l.startsWith("data: "));
        if (line) handleEvent(JSON.parse(line.slice(6)));
      }
    }
  } catch (e) { $("results").innerHTML += `<div class="problems">执行失败：${esc(e.message)}</div>`; }
  finally { $("btn-run").disabled = false; }
});

function handleEvent(ev) {
  if (ev.event === "start") {
    $("results").innerHTML = ev.mock
      ? `<div class="muted">离线演示：回放内置剧本（${ev.total} 项），不调用 API。</div>` : "";
  } else if (ev.event === "item_result") {
    $("results").insertAdjacentHTML("beforeend", resultCard(ev));
  } else if (ev.event === "done") {
    const s = ev.summary;
    $("run-summary").classList.remove("hidden");
    $("run-summary").innerHTML =
      `共 ${s.items} 项 · 合格 ${s.verdicts["合格"]} · 不合格 ${s.verdicts["不合格"]} · 存疑 ${s.verdicts["存疑"]} · 拦截 ${s.blocked}` +
      `<span class="muted"> · 调用 ${s.calls} 次 · 输入 ${s.prompt_tokens} tok · 输出 ${s.completion_tokens} tok</span>`;
  }
}

function resultCard(r) {
  const v = r.agent_verdict;
  const cls = r.blocked ? "blocked" : { "合格": "ok", "不合格": "bad", "存疑": "warn" }[v] || "";
  const head = `<div class="res-head"><strong>${esc(r.name)}</strong>
    <span class="badge ${cls}">${r.blocked ? "已拦截" : esc(v || "无结论")}</span>
    ${r.demo ? `<span class="badge demo">演示</span>` : ""}</div>`;
  const meta = `<div class="res-meta">${esc(r.type)}${r.match_expectation === null || r.match_expectation === undefined ? "" : (r.match_expectation ? " · 与期望一致 ✓" : " · 与期望不一致 ✗")}</div>`;
  const evidence = r.evidence ? `<div class="res-evidence">证据：${esc(r.evidence)}</div>` : "";
  const problems = (r.problems && r.problems.length)
    ? `<div class="problems">${r.problems.map((p) => `• ${esc(p)}`).join("<br>")}</div>` : "";
  const u = r.usage || {};
  const usage = u.calls ? `<div class="res-usage muted">调用 ${u.calls} 次 · 输入 ${u.prompt_tokens} tok（缓存命中 ${u.cached_tokens}）· 输出 ${u.completion_tokens} tok</div>` : "";
  return `<div class="result-card">${head}${meta}${evidence}${problems}${usage}</div>`;
}

/* ── settings ── */
$("btn-settings").addEventListener("click", openSettings);
$("btn-close-settings").addEventListener("click", () => $("settings-modal").classList.add("hidden"));
$("settings-modal").addEventListener("click", (e) => {
  if (e.target === $("settings-modal")) $("settings-modal").classList.add("hidden");
});

async function openSettings() {
  $("settings-modal").classList.remove("hidden");
  const out = await api("/api/settings");
  state.mock = out.mock;
  $("mock-banner").classList.toggle("hidden", !out.mock);
  const p = out.profile || {};
  $("set-base-url").value = p.base_url || "";
  $("set-model").value = p.model || "";
  $("set-key").value = "";
  const st = p.stages || {};
  for (const s of ["decompose", "main", "vision"]) {
    $(`stage-${s}-model`).value = (st[s] || {}).model || "";
    $(`stage-${s}-url`).value = (st[s] || {}).base_url || "";
  }
  $("key-status").textContent = out.key_configured ? "✓ key 已配置" : "未配置 key（填一次即可）";
  $("key-status").className = "key-status " + (out.key_configured ? "ok" : "warn");
}

$("btn-save-settings").addEventListener("click", async () => {
  $("settings-msg").textContent = "保存中…";
  try {
    await api("/api/settings", {
      method: "POST",
      body: {
        key: $("set-key").value.trim(),
        base_url: $("set-base-url").value.trim(),
        model: $("set-model").value.trim(),
        stages: Object.fromEntries(["decompose", "main", "vision"].map((s) => [s, {
          model: $(`stage-${s}-model`).value.trim(),
          base_url: $(`stage-${s}-url`).value.trim(),
        }])),
      },
    });
    $("settings-msg").textContent = "✓ 已保存";
    openSettings();
  } catch (e) { $("settings-msg").textContent = "保存失败：" + e.message; }
});

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ── boot ── */
(async function boot() {
  const h = await api("/api/health");
  state.mock = h.mock;
  $("mock-banner").classList.toggle("hidden", !h.mock);
  loadRules();
})();
