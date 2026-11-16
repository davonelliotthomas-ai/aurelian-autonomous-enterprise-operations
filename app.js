/* The interface is JavaScript; Python business logic is executed by Pyodide.
 * A clearly labelled JavaScript fallback keeps the showcase usable if the
 * external Python runtime CDN is inaccessible. It is never mislabelled Python.
 */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const dataInput = $("input-data");
  const runButton = $("run-engine");
  const fmt = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
  const state = { mode: "json", pyodide: null, fallback: false, report: null, source: "" };
  const SAMPLE_PATHS = { json: "./sample.json", csv: "./sample.csv" };
  const CODE_PATHS = { "engine.py": "./engine.py", "cli.py": "./cli.py", "test_engine.py": "./test_engine.py" };

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
  }
  function moneyFromCents(cents) { return fmt.format(cents / 100); }
  function runtime(label, type) {
    const el = $("runtime-status");
    el.className = "runtime-status " + (type || "");
    el.querySelector("span:last-child").textContent = label;
  }
  function setMode(mode, reset) {
    state.mode = mode;
    ["json", "csv"].forEach((name) => {
      const selected = name === mode;
      const tab = $(name + "-mode");
      tab.classList.toggle("selected", selected);
      tab.setAttribute("aria-selected", String(selected));
    });
    $("editor-filename").textContent = "events." + mode;
    if (reset) loadSample();
  }
  async function loadSample() {
    try {
      const response = await fetch(SAMPLE_PATHS[state.mode]);
      if (!response.ok) throw new Error("Sample data unavailable");
      const source = await response.text();
      dataInput.value = state.mode === "json" ? JSON.stringify(JSON.parse(source), null, 2) : source.trim();
    } catch (error) {
      dataInput.value = state.mode === "json" ? "[]" : "source,external_id,category,amount,occurred_at,tags\n";
      showError(error.message);
    }
  }
  function showError(message) {
    $("error-banner").hidden = false;
    $("error-banner").textContent = message;
    $("output-chip").textContent = "INPUT ERROR";
    $("output-chip").classList.remove("success");
  }
  function clearError() { $("error-banner").hidden = true; $("error-banner").textContent = ""; }

  function renderReport(report, elapsed) {
    state.report = report;
    clearError();
    const summary = report.summary;
    $("total-value").textContent = moneyFromCents(summary.total_amount_cents);
    $("accepted-value").textContent = String(summary.accepted_records);
    $("duplicates-value").textContent = String(summary.duplicate_keys);
    $("rejected-value").textContent = String(summary.rejected_rows);
    $("output-chip").textContent = state.fallback ? "PREVIEW MODE" : "PYTHON EXECUTED";
    $("output-chip").classList.add("success");
    $("category-subtitle").textContent = summary.categories + " categories";

    const biggest = Math.max(1, ...report.categories.map((item) => item.amount_cents));
    $("category-chart").innerHTML = report.categories.length ? report.categories.map((item) =>
      '<div class="chart-row"><div class="chart-labels"><span>' + escapeHtml(item.category) +
      ' <small>· ' + item.count + ' records</small></span><strong>' + moneyFromCents(item.amount_cents) +
      '</strong></div><div class="chart-track"><div class="chart-bar" style="width:' +
      Math.max(2, (item.amount_cents / biggest) * 100).toFixed(2) +
      '%"></div></div></div>'
    ).join("") : '<div class="empty-chart">No accepted records to visualize.</div>';

    $("records-body").innerHTML = report.records.length ? report.records.map((record) =>
      "<tr><td>" + escapeHtml(record.external_id) + "</td><td>" + escapeHtml(record.source) +
      "</td><td>" + escapeHtml(record.category) + "</td><td>" + moneyFromCents(record.amount_cents) +
      "</td><td>" + escapeHtml(record.occurred_at) +
      '</td><td><span class="table-status">Verified</span></td></tr>'
    ).join("") : '<tr><td colspan="6" class="empty-row">No accepted records.</td></tr>';

    if (report.rejected.length) {
      $("quality-footer").innerHTML = '<span class="quality-log"><strong>Quality log · ' +
        report.rejected.length + " quarantined:</strong> " +
        report.rejected.map((row) => "Row " + row.row + ": " + escapeHtml(row.reason)).join(" · ") +
        "</span>";
    } else {
      $("quality-footer").textContent = "Quality log · All rows passed validation.";
    }
    $("execution-detail").textContent = summary.input_rows + " rows · " + elapsed.toFixed(1) + " ms";
    $("download-report").disabled = false;
  }

  function dateMs(value) {
    if (typeof value !== "string" || !(/[zZ]|[+-]\d\d:\d\d$/.test(value))) throw Error("occurred_at must include a timezone");
    const time = Date.parse(value);
    if (!Number.isFinite(time)) throw Error("occurred_at must be ISO-8601");
    return time;
  }
  function cents(value) {
    if (typeof value === "number" && !Number.isInteger(value)) throw Error("amount must be a decimal string or integer");
    if (typeof value !== "string" && typeof value !== "number") throw Error("amount must be a decimal string or integer");
    const input = String(value);
    if (!/^\d+(?:\.\d{1,2})?$/.test(input)) throw Error("amount must be a finite non-negative number with at most two decimal places");
    const parts = input.split(".");
    const numeric = Number(parts[0]) * 100 + Number((parts[1] || "").padEnd(2, "0"));
    if (!Number.isSafeInteger(numeric) || numeric > 9000000000000000) throw Error("amount exceeds supported range");
    return numeric;
  }
  function normalized(row) {
    const fields = ["source", "external_id", "category"];
    for (const name of fields) if (typeof row[name] !== "string" || !row[name].trim()) throw Error(name + " must be non-empty text");
    if (row.tags !== undefined && !Array.isArray(row.tags)) throw Error("tags must be a list");
    const tags = [...new Set(row.tags || [])];
    if (tags.some((tag) => typeof tag !== "string" || !tag.trim())) throw Error("tag must be non-empty text");
    return {
      source: row.source.trim(), external_id: row.external_id.trim(),
      category: row.category.trim(), amount_cents: cents(row.amount),
      occurred_at: new Date(dateMs(row.occurred_at)).toISOString().replace(".000Z", "Z"),
      tags
    };
  }
  function fallbackAnalyze(input, mode) {
    let rows;
    if (mode === "json") {
      rows = JSON.parse(input);
      if (!Array.isArray(rows)) throw Error("Input must be a JSON array of event objects");
    } else {
      const lines = input.trim().split(/\r?\n/);
      const headers = (lines.shift() || "").split(",");
      for (const column of ["source", "external_id", "category", "amount", "occurred_at"])
        if (!headers.includes(column)) throw Error("CSV must contain source, external_id, category, amount, occurred_at");
      rows = lines.filter(Boolean).map((line) => {
        const values = line.split(",");
        const row = Object.fromEntries(headers.map((name, i) => [name, values[i] || ""]));
        row.tags = row.tags ? row.tags.split("|").filter(Boolean) : [];
        return row;
      });
    }
    const latest = new Map(), rejected = [];
    let duplicates = 0;
    rows.forEach((row, index) => {
      try {
        if (!row || Array.isArray(row) || typeof row !== "object") throw Error("record must be a JSON object");
        const item = normalized(row);
        const key = JSON.stringify([item.source, item.external_id]);
        if (latest.has(key)) {
          duplicates++;
          if (Date.parse(item.occurred_at) > Date.parse(latest.get(key).occurred_at)) latest.set(key, item);
        } else latest.set(key, item);
      } catch (error) { rejected.push({ row: index + 1, reason: error.message }); }
    });
    const records = [...latest.values()].sort((a, b) =>
      b.amount_cents - a.amount_cents || a.external_id.localeCompare(b.external_id) || a.source.localeCompare(b.source));
    const groups = new Map();
    records.forEach((record) => {
      const group = groups.get(record.category) || { category: record.category, count: 0, amount_cents: 0 };
      group.count++;
      group.amount_cents += record.amount_cents;
      groups.set(record.category, group);
    });
    const categories = [...groups.values()].sort((a, b) => b.amount_cents - a.amount_cents || a.category.localeCompare(b.category));
    const total = records.reduce((sum, row) => sum + row.amount_cents, 0);
    return {
      summary: {
        input_rows: rows.length, accepted_records: records.length, rejected_rows: rejected.length,
        duplicate_keys: duplicates, total_amount_cents: total,
        total_amount: (total / 100).toFixed(2), categories: categories.length
      }, categories, records, rejected
    };
  }

  async function runEngine() {
    const start = performance.now();
    runButton.disabled = true;
    runButton.textContent = "Processing…";
    try {
      let report;
      if (state.pyodide) {
        const fn = state.pyodide.globals.get(state.mode === "json" ? "analyze_json" : "analyze_csv");
        try { report = JSON.parse(fn(dataInput.value)); }
        finally { if (typeof fn.destroy === "function") fn.destroy(); }
      } else if (state.fallback) report = fallbackAnalyze(dataInput.value, state.mode);
      else throw Error("Python runtime is still loading");
      renderReport(report, performance.now() - start);
    } catch (error) { showError(error.message || String(error)); }
    finally { runButton.disabled = false; runButton.innerHTML = 'Run ' + (state.fallback ? 'preview' : 'Python engine') + ' <span aria-hidden="true">→</span>'; }
  }

  async function bootstrapPython() {
    try {
      const script = document.createElement("script");
      script.src = "https://cdn.jsdelivr.net/pyodide/v314.0.8/full/pyodide.js";
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(Error("Runtime download timed out")), 25000);
        script.onload = () => { clearTimeout(timer); resolve(); };
        script.onerror = () => { clearTimeout(timer); reject(Error("Runtime download blocked")); };
        document.head.appendChild(script);
      });
      const pyodide = await window.loadPyodide();
      const response = await fetch("./engine.py");
      if (!response.ok) throw Error("Python engine source unavailable");
      const python = await response.text();
      await pyodide.runPythonAsync(python);
      state.pyodide = pyodide;
      state.fallback = false;
      runtime("CPython / WebAssembly ready", "ready");
    } catch (error) {
      console.warn("Aurelian Python runtime unavailable; using labelled preview fallback:", error);
      state.fallback = true;
      runtime("JavaScript preview · Python CDN unavailable", "error");
    }
    runButton.disabled = false;
    runEngine();
  }

  async function showCode(file) {
    document.querySelectorAll(".code-tab").forEach((tab) => tab.classList.toggle("selected", tab.dataset.file === file));
    $("code-title").textContent = file;
    $("code-preview").textContent = "Loading " + file + "…";
    try {
      const response = await fetch(CODE_PATHS[file]);
      if (!response.ok) throw Error("Source not available");
      const source = await response.text();
      $("code-preview").textContent = source;
      state.source = source;
    } catch (error) { $("code-preview").textContent = error.message; }
  }

  function bindEvents() {
    $("json-mode").addEventListener("click", () => setMode("json", true));
    $("csv-mode").addEventListener("click", () => setMode("csv", true));
    $("load-sample").addEventListener("click", loadSample);
    runButton.addEventListener("click", runEngine);
    $("file-input").addEventListener("change", async (event) => {
      const file = event.target.files[0];
      if (!file) return;
      setMode(file.name.toLowerCase().endsWith(".csv") ? "csv" : "json", false);
      dataInput.value = await file.text();
      event.target.value = "";
    });
    $("download-report").addEventListener("click", () => {
      if (!state.report) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(state.report, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url; link.download = "aurelian-signal-report.json";
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    document.querySelectorAll(".code-tab").forEach((tab) => tab.addEventListener("click", () => showCode(tab.dataset.file)));
    $("copy-code").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(state.source);
        $("copy-code").textContent = "Copied ✓";
        setTimeout(() => { $("copy-code").textContent = "Copy code ⧉"; }, 1800);
      } catch (error) { $("copy-code").textContent = "Select text to copy"; }
    });
  }

  bindEvents();
  loadSample();
  showCode("engine.py");
  bootstrapPython();
})();
