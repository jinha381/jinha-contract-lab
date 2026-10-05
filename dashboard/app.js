const $ = (id) => document.getElementById(id);
const state = { cases: [], selected: null, address: "", evidence: null };
const names = { R0: "판정 전제조건", R1: "관리대상 검증", R2: "승인 적합성", R3: "거래·실행기록 대응", R4: "자산흐름 정합성" };
const nf = new Intl.NumberFormat("ko-KR");

function node(tag, className, value) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (value !== undefined) item.textContent = String(value);
  return item;
}
function empty(container, message) { container.replaceChildren(node("div", "empty", message)); }
function showMessage(message) { $("message").textContent = message; $("message").hidden = !message; }
function short(value, left = 7, right = 6) { return value ? `${value.slice(0, left)}…${value.slice(-right)}` : "—"; }
function sol(lamports) { return typeof lamports === "number" ? `${(lamports / 1e9).toLocaleString("ko-KR", {maximumFractionDigits: 9})} SOL` : "—"; }
function statusBadge(value) { return node("span", `status ${String(value).toLowerCase()}`, value || "—"); }

async function get(path) {
  const response = await fetch(path, { cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

async function loadStatus() {
  try {
    const data = await get("/api/status");
    $("rpcValue").textContent = data.rpc.replace("http://", "");
    $("slotValue").textContent = nf.format(data.slot);
    $("heightValue").textContent = nf.format(data.block_height);
    $("connectionPill").classList.remove("offline");
    $("connectionPill").lastElementChild.textContent = "Localnet connected";
    $("updatedAt").textContent = `Updated ${new Date().toLocaleTimeString("ko-KR")}`;
    showMessage("");
  } catch (error) {
    $("connectionPill").classList.add("offline");
    $("connectionPill").lastElementChild.textContent = "RPC offline";
    showMessage(`Localnet 연결 실패: ${error.message}`);
  }
}

async function loadCases() {
  try {
    state.cases = (await get("/api/cases")).cases;
    const list = $("caseList"); list.replaceChildren();
    if (!state.cases.length) { empty(list, "증거 JSON이 없습니다."); return; }
    state.cases.forEach((item) => {
      const button = node("button", "case-item"); button.type = "button";
      button.classList.toggle("selected", state.selected === item.id);
      const main = node("div"); main.append(node("strong", "", item.case_id || item.id), node("small", "", `${item.id} · ${item.transaction_count || 0} TX`));
      button.append(main, node("span", `case-state ${item.coverage_complete ? "" : "incomplete"}`, item.coverage_complete ? "COMPLETE" : "REVIEW"));
      button.addEventListener("click", () => loadCase(item.id)); list.append(button);
    });
    if (state.selected && state.cases.some((x) => x.id === state.selected)) await loadCase(state.selected);
    else await loadCase(state.cases[0].id);
  } catch (error) { empty($("caseList"), `증거 조회 실패: ${error.message}`); }
}

async function loadCase(id) {
  try {
    const item = await get(`/api/case?id=${encodeURIComponent(id)}`);
    state.selected = id;
    document.querySelectorAll(".case-item").forEach((button, i) => button.classList.toggle("selected", state.cases[i].id === id));
    const evidence = item.evidence, context = evidence.C || {};
    state.evidence = evidence;
    $("caseTitle").textContent = context.case_id || id;
    $("caseSubtitle").textContent = `${short(context.wallet, 9, 8)} · ${evidence.T?.length || 0} transactions · ${context.asset || "—"}`;
    $("coverageBadge").textContent = evidence.coverage_complete ? "COVERAGE CLAIMED" : "COVERAGE UNVERIFIED";
    $("caseNote").textContent = evidence.evidence_note || "판정은 제공된 증거를 기준으로 계산하며 기록의 진위는 별도 검증이 필요합니다.";
    $("coverageBadge").className = `coverage-badge ${evidence.coverage_complete ? "complete" : "incomplete"}`;
    for (const key of ["M1", "M2"]) {
      const target = $(key.toLowerCase() + "Verdict");
      target.textContent = item[key].verdict;
      target.className = `verdict-${item[key].verdict.toLowerCase()}`;
    }
    const rules = $("ruleRows"); rules.replaceChildren();
    Object.entries(item.M2.checks).forEach(([id, value]) => {
      const row = node("div", "rule-row"); row.append(node("span", "rule-id", id), node("span", "rule-name", names[id]), statusBadge(value)); rules.append(row);
    });
    const reasons = $("reasonList"); reasons.replaceChildren();
    if (!item.M2.reasons.length) reasons.append(node("p", "", "기록된 불일치 또는 판단보류 사유가 없습니다."));
    item.M2.reasons.forEach((reason) => reasons.append(node("p", "", `${reason.rule} · ${reason.status} · ${reason.detail}`)));
    $("rawEvidence").textContent = JSON.stringify(evidence, null, 2);
    if (context.wallet && /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(context.wallet)) {
      $("walletInput").value = context.wallet;
      await loadWallet(context.wallet);
    }
  } catch (error) { showMessage(`사례 로드 실패: ${error.message}`); }
}

async function loadWallet(address) {
  state.address = address;
  const tbody = $("txRows");
  tbody.replaceChildren(node("tr")); tbody.firstChild.append(node("td", "empty", "RPC 조회 중…")); tbody.firstChild.firstChild.colSpan = 5;
  try {
    const data = await get(`/api/wallet?address=${encodeURIComponent(address)}`);
    $("balanceValue").textContent = sol(data.balance);
    const saved = state.evidence?.C?.wallet === address ? (state.evidence.T || []) : [];
    const fromEvidence = data.transactions.length === 0 && saved.length > 0;
    const transactions = fromEvidence ? saved.map((t) => ({signature:t.txid, block_time:Date.parse(t.time)/1000, state:t.status, fee:t.fee, transfers:[{from:t.from,to:t.to,lamports:t.amount}]})) : data.transactions;
    $("txCount").textContent = `${transactions.length} transactions`;
    $("chainNote").textContent = fromEvidence ? "저장된 증거 JSON의 거래입니다 · 현재 RPC의 이력 조회에서는 반환되지 않았습니다" : `RPC 조회 결과 · ${data.commitment} · 주소 기준 최대 ${data.limit}개 · 관측범위 완전성은 별도 검토 필요`;
    tbody.replaceChildren();
    if (!transactions.length) { const row = node("tr"); const cell = node("td", "empty", "현재 RPC에서 조회되는 거래가 없습니다."); cell.colSpan = 5; row.append(cell); tbody.append(row); }
    transactions.forEach((tx) => {
      const row = node("tr");
      const time = tx.block_time ? new Date(tx.block_time * 1000).toISOString().replace("T", " ").slice(0, 19) : "—";
      const transfer = tx.transfers?.[0]; const outgoing = transfer?.from === address; const incoming = transfer?.to === address;
      const type = transfer ? outgoing ? "OUTGOING" : incoming ? "INCOMING" : "OTHER" : "OTHER";
      const amount = transfer ? `${outgoing ? "−" : incoming ? "+" : ""}${sol(transfer.lamports)}` : "—";
      const signature = node("span", "mono txid", short(tx.signature, 9, 8)); signature.title = tx.signature + (fromEvidence ? " · saved evidence" : " · live RPC");
      row.append(node("td", "mono", time), node("td"), node("td", `direction ${outgoing ? "out" : "in"}`, type), node("td", "mono", amount), node("td"));
      row.children[1].append(signature); row.children[4].append(statusBadge(tx.state)); tbody.append(row);
    });
  } catch (error) {
    $("balanceValue").textContent = "—";
    tbody.replaceChildren(); const row = node("tr"); const cell = node("td", "empty", `거래 조회 실패: ${error.message}`); cell.colSpan = 5; row.append(cell); tbody.append(row);
  }
}

$("walletForm").addEventListener("submit", (event) => { event.preventDefault(); loadWallet($("walletInput").value.trim()); });
$("refreshButton").addEventListener("click", async () => { await Promise.all([loadStatus(), loadCases()]); if (!state.selected && state.address) await loadWallet(state.address); });
Promise.all([loadStatus(), loadCases()]);
setInterval(loadStatus, 15000);
