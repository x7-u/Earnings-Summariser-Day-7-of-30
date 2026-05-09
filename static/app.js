// Day 7 BRIEF front-end. CSRF double-submit, single AbortController,
// SVG tone curve drawn client-side from the JSON.

(() => {
  "use strict";

  const $  = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  const form = $("#analyse-form");
  const btn = $("#run-btn");
  const statusLine = $("#status-line");
  const errorCard = $("#error-card");
  const empty = $("#empty-state");
  const resultPane = $("#result-pane");
  const sampleCard = $("#sample-card");
  const pasteCard = $("#paste-card");
  const uploadCard = $("#upload-card");

  let inflight = null;
  let lastBody = null;
  let savedRuns = loadSaved();
  let toneRoleVisible = {CEO: true, CFO: true, EXEC: true, ANALYST: true, OPERATOR: true, OTHER: true, COO: true};
  let qaFilter = "";

  function readCookie(name) {
    return document.cookie.split(/;\s*/)
      .map(p => p.split("="))
      .reduce((a, [k, v]) => (k === name ? decodeURIComponent(v || "") : a), "");
  }
  function csrfHeaders() { return { "X-CSRF-Token": readCookie("csrf_token") }; }
  function setStatus(msg, kind) {
    statusLine.textContent = msg || "";
    statusLine.style.color = kind === "error" ? "#FECACA"
                            : kind === "ok"   ? "#86EFAC" : "";
  }
  function show(el) {
    if (!el) return;
    el.classList.remove("hidden");
    // The paste-card and upload-card start with the HTML `hidden` attribute,
    // which the class can't override. Strip it so the toggle actually works.
    el.removeAttribute("hidden");
  }
  function hide(el) { if (el) el.classList.add("hidden"); }
  function fmtNum(x, d = 0) {
    if (x === null || x === undefined || !isFinite(x)) return "n/a";
    return Number(x).toLocaleString(undefined, {
      minimumFractionDigits: d, maximumFractionDigits: d,
    });
  }
  function fmtCcy(x, d = 0) {
    if (x === null || !isFinite(x)) return "n/a";
    return "$" + fmtNum(x, d);
  }
  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, ch =>
      ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[ch]);
  }

  // ---- Drag-and-drop file upload ----
  const dropZone = $("#drop-zone");
  if (dropZone) {
    ["dragover", "dragenter"].forEach(ev => dropZone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropZone.classList.add("is-drag");
    }));
    ["dragleave", "drop"].forEach(ev => dropZone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropZone.classList.remove("is-drag");
    }));
    dropZone.addEventListener("drop", (e) => {
      const files = e.dataTransfer && e.dataTransfer.files;
      if (files && files.length) {
        $("#file-input").files = files;
        $("#drop-name").textContent = files[0].name;
        // Auto-select upload source
        $$('input[name="source"]').forEach(r => { r.checked = (r.value === "upload"); });
        $$('input[name="source"]').forEach(r => r.dispatchEvent(new Event("change")));
      }
    });
    $("#file-input").addEventListener("change", (e) => {
      const f = e.target.files[0];
      $("#drop-name").textContent = f ? f.name : "";
    });
  }

  // ---- Ctrl/Cmd + Enter submit ----
  document.addEventListener("keydown", (ev) => {
    const isSubmitChord = (ev.ctrlKey || ev.metaKey) && ev.key === "Enter";
    if (!isSubmitChord) return;
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    // Ignore if user is in the follow-up box (it has its own Enter handler)
    if (document.activeElement && document.activeElement.id === "fu-input") return;
    ev.preventDefault();
    form.dispatchEvent(new Event("submit", { cancelable: true }));
  });

  // ---- Source toggle ----
  $$('input[name="source"]').forEach(r => r.addEventListener("change", () => {
    const v = r.checked ? r.value : null;
    if (!v) return;
    hide(sampleCard); hide(pasteCard); hide(uploadCard);
    if (v === "samples") show(sampleCard);
    if (v === "paste") show(pasteCard);
    if (v === "upload") show(uploadCard);
  }));

  // ---- Analyse submit ----
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (inflight) inflight.abort();
    inflight = new AbortController();
    btn.disabled = true;
    setStatus("Reading transcript and asking the AI...");
    hide(errorCard);

    const fd = new FormData();
    const source = $('input[name="source"]:checked').value;
    if (source === "samples") {
      fd.append("use_samples", "true");
      fd.append("sample_id", $("#sample-select").value);
    } else if (source === "paste") {
      const t = $("#paste-text").value.trim();
      if (!t) { setStatus("Paste a transcript first.", "error"); btn.disabled = false; return; }
      fd.append("text", t);
    } else {
      const f = $("#file-input").files[0];
      if (!f) { setStatus("Pick a .txt or .pdf file first.", "error"); btn.disabled = false; return; }
      fd.append("file", f);
    }
    if ($("#skip-ai").checked) fd.append("skip_ai", "true");
    fd.append("self_consistency", $("#self-consistency").value);
    const m = $("#model").value.trim();
    if (m) fd.append("model", m);

    try {
      const res = await fetch("/api/analyse", {
        method: "POST", body: fd, headers: csrfHeaders(),
        signal: inflight.signal,
      });
      const body = await res.json();
      if (!res.ok) { showError(body.error || `HTTP ${res.status}`); return; }
      lastBody = body;
      render(body);
      try { localStorage.setItem("day07.lastResult.v1", JSON.stringify(body)); } catch (_) {}
      setStatus(`DONE IN ${body.elapsed_ms}MS / AI COST $${(body.total_cost_usd || 0).toFixed(5)}`, "ok");
    } catch (e) {
      if (e.name === "AbortError") return;
      showError(e.message || String(e));
    } finally {
      btn.disabled = false;
    }
  });

  function showError(msg) {
    errorCard.textContent = msg;
    show(errorCard);
    setStatus("FAILED", "error");
  }

  // ---- Render ----
  function render(body) {
    const md = body.metadata || {};
    const h = body.headline || {};

    $("#rm-company").textContent = md.company || "--";
    $("#rm-ticker").textContent  = md.ticker || "--";
    $("#rm-period").textContent  = md.fiscal_period || "--";
    $("#rm-id").textContent      = body.run_id || "--";
    // Mode badge: orange RUN for transcript runs, magenta FILING for SEC EDGAR runs
    const modeTag = $("#rm-mode-tag");
    if (modeTag) {
      if (body.mode === "filing") {
        modeTag.textContent = "FILING";
        modeTag.style.background = "#06B6D4";
      } else {
        modeTag.textContent = "RUN";
        modeTag.style.background = "";
      }
    }

    // Hero
    const tone = (h.overall_tone || "--").toUpperCase();
    const heroTone = $("#hero-tone");
    heroTone.textContent = tone;
    heroTone.className = "hero-tone is-" + (h.overall_tone || "default");
    $("#hero-conf").textContent = (h.confidence_score === undefined) ? "--"
                                : `${(h.confidence_score * 100).toFixed(1)}%`;
    $("#hero-hedge").textContent    = fmtNum(h.hedge_count);
    $("#hero-cert").textContent     = fmtNum(h.certainty_count);
    $("#hero-defl").textContent     = fmtNum(h.deflection_count);
    $("#hero-claims").textContent   = fmtNum(h.quantitative_claims);
    $("#hero-analysts").textContent = fmtNum(h.analyst_count);
    $("#hero-cost").textContent     = "$" + (body.total_cost_usd || 0).toFixed(5);

    // AI verdict
    const es = body.exec_summary || {};
    if (es && (es.headline || es.bull_case)) {
      $("#ai-headline").textContent = es.headline || "";
      $("#ai-bull").textContent = es.bull_case || "";
      $("#ai-bear").textContent = es.bear_case || "";
      const ul = $("#ai-actions"); ul.innerHTML = "";
      (es.actions || []).forEach(a => {
        const li = document.createElement("li"); li.textContent = a; ul.appendChild(li);
      });
      show($("#ai-card"));
      $("#fu-answer").hidden = true;
      $("#fu-status").textContent = "";
    } else {
      hide($("#ai-card"));
    }

    // Tone curve
    if (body.tone_curve && body.tone_curve.length) {
      _lastTonePoints = body.tone_curve;
      $("#tone-host").innerHTML = renderToneCurve(body.tone_curve);
      attachToneTooltips(body.tone_curve);
      show($("#tone-card"));
    } else {
      _lastTonePoints = [];
      hide($("#tone-card"));
    }

    // Guidance
    if (body.guidance && body.guidance.length) {
      $("#guidance-table").innerHTML = renderGuidance(body.guidance);
      show($("#guidance-card"));
    } else {
      hide($("#guidance-card"));
    }

    // Themes
    if (body.themes && body.themes.length) {
      $("#theme-grid").innerHTML = body.themes.map(t => `
        <div class="theme-cell">
          <div class="theme-name">${escapeHtml(t.name)}</div>
          <div class="theme-meta">${escapeHtml(t.sentiment)} &middot; weight ${(t.weight*100).toFixed(0)}%</div>
          <div class="theme-bar"><div class="theme-bar-fill" style="width:${(t.weight*100).toFixed(0)}%"></div></div>
          <div class="theme-quotes">${(t.key_quotes || []).slice(0,2).map(q => `&ldquo;${escapeHtml(q)}&rdquo;`).join("<br><br>")}</div>
        </div>
      `).join("");
      show($("#themes-card"));
    } else {
      hide($("#themes-card"));
    }

    // Q&A
    if (body.qa && body.qa.length) {
      _lastQA = body.qa;
      $("#qa-table").innerHTML = renderQA(body.qa);
      $("#qa-filter-meta").textContent = "";
      show($("#qa-card"));
    } else {
      _lastQA = [];
      hide($("#qa-card"));
    }

    // Risks
    if (body.risks && body.risks.length) {
      $("#risks-list").innerHTML = body.risks.map(r => `
        <li>
          <span class="risk-pill sev-${escapeHtml(r.severity)}">${escapeHtml(r.severity.toUpperCase())}</span>
          <span class="risk-cat">${escapeHtml(r.category)}</span>
          <span class="risk-quote">&ldquo;${escapeHtml(r.quote)}&rdquo;</span>
        </li>
      `).join("");
      show($("#risks-card"));
    } else {
      hide($("#risks-card"));
    }

    // Quotes (phrase + claims)
    $("#phrase-table").innerHTML = renderPhrases(body.phrase_hits || []);
    $("#claims-table").innerHTML = renderClaims(body.number_claims || []);
    $("#qsub-tone-count").textContent = (body.phrase_hits || []).length;
    $("#qsub-claims-count").textContent = (body.number_claims || []).length;
    if ((body.phrase_hits || []).length || (body.number_claims || []).length) {
      show($("#quotes-card"));
    } else {
      hide($("#quotes-card"));
    }

    // Downloads
    setDl("dl-xlsx", body.xlsx_filename);
    setDl("dl-qa-csv", body.qa_csv_filename);
    setDl("dl-g-csv", body.guidance_csv_filename);
    setDl("dl-pdf", body.pdf_filename);
    setDl("dl-pptx", body.pptx_filename);
    show($("#downloads"));

    syncURL(md);
    hide(empty);
    show(resultPane);

    // Warnings banner
    const warns = body.warnings || [];
    if (warns.length) {
      const ul = $("#warnings-list");
      ul.innerHTML = "";
      warns.forEach(w => {
        const li = document.createElement("li"); li.textContent = w; ul.appendChild(li);
      });
      show($("#warnings-card"));
    } else {
      hide($("#warnings-card"));
    }

    // Auto-scroll to AI verdict (if present) so the user sees it without scrolling
    if (body.exec_summary && (body.exec_summary.headline || body.exec_summary.bull_case)) {
      requestAnimationFrame(() => {
        const card = $("#ai-card");
        if (card && !card.classList.contains("hidden")) {
          card.scrollIntoView({behavior: "smooth", block: "start"});
        }
      });
    }

    refreshSaved();
  }

  function setDl(id, fname) {
    const a = $("#" + id);
    if (fname) {
      a.href = "/api/download/" + encodeURIComponent(fname);
      a.classList.remove("hidden");
    } else {
      a.classList.add("hidden");
    }
  }

  // ---- Tone curve SVG ----
  let _lastTonePoints = [];
  let _lastQA = [];

  function renderToneCurve(points) {
    const w = 920, h = 240, pad = 36;
    const innerW = w - 2 * pad, innerH = h - 2 * pad;
    if (!points.length) return "";
    const xAt = i => pad + (i / Math.max(1, points.length - 1)) * innerW;
    const yAt = t => pad + (1 - (t + 1) / 2) * innerH;
    const navy = "#0A1628", cream = "#F4F1EA", grey = "#6B7280", orange = "#FF6B00", cyan = "#06B6D4";
    const role_colour = {
      CEO: "#FFD166", CFO: cyan, EXEC: "#A78BFA",
      ANALYST: orange, OPERATOR: grey, OTHER: grey,
      COO: "#34D399",
    };
    const parts = [];
    parts.push(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="100%" height="${h}" id="tone-svg">`);
    parts.push(`<rect width="${w}" height="${h}" fill="${navy}"/>`);
    parts.push(`<rect x="${pad}" y="${pad}" width="${innerW}" height="${innerH}" fill="none" stroke="${grey}" stroke-width="0.6"/>`);
    const y0 = yAt(0);
    parts.push(`<line x1="${pad}" y1="${y0}" x2="${pad+innerW}" y2="${y0}" stroke="${grey}" stroke-width="0.6" stroke-dasharray="2 4"/>`);
    // Polyline
    const pts = points.map((p,i) => `${xAt(i).toFixed(1)},${yAt(p.tone).toFixed(1)}`).join(" ");
    parts.push(`<polyline points="${pts}" fill="none" stroke="${cream}" stroke-width="2"/>`);
    points.forEach((p, i) => {
      const x = xAt(i), y = yAt(p.tone);
      const c = role_colour[p.speaker_role] || grey;
      const visible = toneRoleVisible[p.speaker_role] !== false;
      const opacity = visible ? 1 : 0.18;
      parts.push(`<circle data-i="${i}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5" fill="${c}" stroke="${cream}" stroke-width="0.8" opacity="${opacity}" style="cursor:crosshair"/>`);
    });
    parts.push(`<text x="${pad}" y="${pad - 8}" fill="${cream}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="10">+1 confident</text>`);
    parts.push(`<text x="${pad}" y="${pad + innerH + 18}" fill="${cream}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="10">-1 defensive</text>`);
    parts.push(`</svg>`);
    return parts.join("");
  }

  function attachToneTooltips(points) {
    const host = $("#tone-host");
    const tip = $("#tone-tooltip");
    if (!host) return;
    host.querySelectorAll("circle[data-i]").forEach(circ => {
      circ.addEventListener("mouseenter", (ev) => {
        const i = parseInt(circ.getAttribute("data-i"), 10);
        const p = points[i];
        if (!p) return;
        tip.innerHTML = `<span class="tt-role">${escapeHtml(p.speaker_role)}</span> &middot; turn ${i+1} &middot; tone ${p.tone.toFixed(2)} &middot; ${p.word_count} words`;
        const rect = host.getBoundingClientRect();
        const cx = ev.clientX - rect.left;
        tip.style.left = Math.min(rect.width - 320, Math.max(0, cx + 12)) + "px";
        tip.style.top = (ev.clientY - rect.top + 12) + "px";
        tip.hidden = false;
      });
      circ.addEventListener("mouseleave", () => { tip.hidden = true; });
    });
  }

  // Role chip click toggles visibility + re-renders tone curve
  document.addEventListener("click", (ev) => {
    const pill = ev.target.closest("#tone-legend .lg-pill");
    if (!pill) return;
    const role = pill.getAttribute("data-role");
    toneRoleVisible[role] = !toneRoleVisible[role];
    pill.classList.toggle("is-on", toneRoleVisible[role]);
    if (_lastTonePoints.length) {
      $("#tone-host").innerHTML = renderToneCurve(_lastTonePoints);
      attachToneTooltips(_lastTonePoints);
    }
  });

  // Q&A filter input
  document.addEventListener("input", (ev) => {
    if (ev.target && ev.target.id === "qa-filter") {
      qaFilter = ev.target.value.trim().toLowerCase();
      if (!_lastQA.length) return;
      const filtered = qaFilter
        ? _lastQA.filter(q =>
            (q.analyst_name || "").toLowerCase().includes(qaFilter)
            || (q.analyst_firm || "").toLowerCase().includes(qaFilter)
            || (q.question_summary || "").toLowerCase().includes(qaFilter)
            || (q.answer_summary || "").toLowerCase().includes(qaFilter)
            || (q.tension || "").toLowerCase().includes(qaFilter)
            || (q.management_clarity || "").toLowerCase().includes(qaFilter))
        : _lastQA;
      $("#qa-table").innerHTML = renderQA(filtered);
      $("#qa-filter-meta").textContent = qaFilter
        ? `Showing ${filtered.length} of ${_lastQA.length} exchanges.`
        : "";
    }
  });

  // ---- Tables ----
  function renderGuidance(rows) {
    let html = `<thead><tr>
      <th>Metric</th><th>Period</th><th>Direction</th>
      <th>Range</th><th>Unit</th><th>Quote</th>
    </tr></thead><tbody>`;
    rows.forEach(g => {
      const dirCls = g.direction === "up" || g.direction === "raised" ? "dir-up"
                    : g.direction === "down" || g.direction === "lowered" || g.direction === "withdrawn" ? "dir-down"
                    : "";
      let rng = "";
      if (g.range_low !== null && g.range_high !== null) rng = `${g.range_low} to ${g.range_high}`;
      else if (g.range_low !== null) rng = `${g.range_low}`;
      html += `<tr>
        <td>${escapeHtml(g.metric)}</td>
        <td>${escapeHtml(g.period)}</td>
        <td class="${dirCls}">${escapeHtml(g.direction)}</td>
        <td>${rng}</td>
        <td>${escapeHtml(g.unit)}</td>
        <td style="text-align:left">&ldquo;${escapeHtml(g.quote)}&rdquo;</td>
      </tr>`;
    });
    return html + "</tbody>";
  }

  function renderQA(rows) {
    let html = `<thead><tr>
      <th>Analyst</th><th>Firm</th><th>Question</th><th>Answer</th>
      <th>Tension</th><th>Clarity</th>
    </tr></thead><tbody>`;
    rows.forEach(q => {
      html += `<tr>
        <td>${escapeHtml(q.analyst_name)}</td>
        <td style="text-align:left">${escapeHtml(q.analyst_firm)}</td>
        <td style="text-align:left">${escapeHtml(q.question_summary)}</td>
        <td style="text-align:left">${escapeHtml(q.answer_summary)}</td>
        <td class="tens-${escapeHtml(q.tension)}">${escapeHtml(q.tension)}</td>
        <td class="clar-${escapeHtml(q.management_clarity)}">${escapeHtml(q.management_clarity)}</td>
      </tr>`;
    });
    return html + "</tbody>";
  }

  function renderPhrases(rows) {
    if (!rows.length) return `<thead><tr><th>(none)</th></tr></thead>`;
    let html = `<thead><tr>
      <th>Bucket</th><th>Phrase</th><th>Speaker</th><th>Role</th><th>Context</th>
    </tr></thead><tbody>`;
    rows.slice(0, 80).forEach(p => {
      html += `<tr>
        <td>${escapeHtml(p.bucket)}</td>
        <td style="text-align:left">${escapeHtml(p.phrase)}</td>
        <td>${escapeHtml(p.speaker)}</td>
        <td>${escapeHtml(p.role)}</td>
        <td style="text-align:left">${escapeHtml(p.context)}</td>
      </tr>`;
    });
    return html + "</tbody>";
  }
  function renderClaims(rows) {
    if (!rows.length) return `<thead><tr><th>(none)</th></tr></thead>`;
    let html = `<thead><tr>
      <th>Raw</th><th>Unit</th><th>Speaker</th><th>Role</th><th>Context</th>
    </tr></thead><tbody>`;
    rows.slice(0, 80).forEach(c => {
      html += `<tr>
        <td>${escapeHtml(c.raw)}</td>
        <td>${escapeHtml(c.unit)}</td>
        <td>${escapeHtml(c.speaker)}</td>
        <td>${escapeHtml(c.role)}</td>
        <td style="text-align:left">${escapeHtml(c.context)}</td>
      </tr>`;
    });
    return html + "</tbody>";
  }

  // ---- AI follow-up ----
  $("#fu-btn").addEventListener("click", async () => {
    const q = $("#fu-input").value.trim();
    if (!q || !lastBody || !lastBody.run_id) return;
    $("#fu-status").textContent = "Asking the analyst...";
    $("#fu-answer").hidden = true;
    const fd = new FormData();
    fd.append("run_id", lastBody.run_id);
    fd.append("question", q);
    try {
      const r = await fetch("/api/followup", {
        method: "POST", body: fd, headers: csrfHeaders(),
      });
      const j = await r.json();
      if (j.error) { $("#fu-status").textContent = "Error: " + j.error; return; }
      $("#fu-answer").textContent = j.answer || "(empty)";
      $("#fu-answer").hidden = false;
      $("#fu-status").textContent = `cost $${(j.cost_usd||0).toFixed(5)} / model ${j.model||""}`;
    } catch (e) {
      $("#fu-status").textContent = "Failed: " + (e.message || e);
    }
  });
  $("#fu-input").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); $("#fu-btn").click(); }
  });

  // ---- EDGAR ----
  $("#edgar-btn").addEventListener("click", async () => {
    const t = $("#edgar-ticker").value.trim();
    if (!t) return;
    $("#edgar-result").innerHTML = "Looking up...";
    try {
      const r = await fetch("/api/edgar/" + encodeURIComponent(t));
      const j = await r.json();
      if (j.error) {
        $("#edgar-result").innerHTML =
          `<span style="color:#FECACA">${escapeHtml(j.error)}</span>`;
        return;
      }
      const filings = (j.filings || []).slice(0, 5);
      let html =
        `<div class="edgar-head"><strong>${escapeHtml(j.company_name)}</strong>` +
        ` <span class="edgar-cik">CIK ${escapeHtml(j.cik)}</span></div>`;
      filings.forEach(f => {
        html += `
          <div class="edgar-row" data-url="${escapeHtml(f.url)}"
               data-form="${escapeHtml(f.form)}"
               data-date="${escapeHtml(f.date)}"
               data-ticker="${escapeHtml(j.ticker || t)}">
            <a href="${escapeHtml(f.url)}" target="_blank" class="edgar-link">
              ${escapeHtml(f.form)} ${escapeHtml(f.date)}
            </a>
            <button type="button" class="edgar-analyse-btn">ANALYSE</button>
          </div>`;
      });
      $("#edgar-result").innerHTML = html;
    } catch (e) {
      $("#edgar-result").textContent = "Failed: " + e.message;
    }
  });

  // Delegated handler for the ANALYSE button on each EDGAR filing row.
  document.addEventListener("click", async (ev) => {
    const btn = ev.target.closest(".edgar-analyse-btn");
    if (!btn) return;
    const row = btn.closest(".edgar-row");
    if (!row) return;
    const url = row.getAttribute("data-url");
    const form = row.getAttribute("data-form");
    const date = row.getAttribute("data-date");
    const ticker = row.getAttribute("data-ticker");
    if (!url) return;
    btn.disabled = true;
    const originalLabel = btn.textContent;
    btn.textContent = "FETCHING...";
    setStatus(`Fetching ${form} ${date} from SEC...`);
    hide(errorCard);

    const fd = new FormData();
    fd.append("url", url);
    fd.append("ticker", ticker || "");
    fd.append("form", form || "");
    fd.append("date", date || "");
    if ($("#skip-ai").checked) fd.append("skip_ai", "true");
    const m = $("#model").value.trim();
    if (m) fd.append("model", m);

    try {
      const res = await fetch("/api/analyse_edgar", {
        method: "POST", body: fd, headers: csrfHeaders(),
      });
      const body = await res.json();
      if (!res.ok) {
        showError(body.error || `HTTP ${res.status}`);
        return;
      }
      lastBody = body;
      render(body);
      try { localStorage.setItem("day07.lastResult.v1", JSON.stringify(body)); } catch (_) {}
      const cost = (body.total_cost_usd || 0).toFixed(5);
      setStatus(`EDGAR ${form} ${date} ANALYSED IN ${body.elapsed_ms}MS / AI COST $${cost}`, "ok");
    } catch (e) {
      showError(e.message || String(e));
    } finally {
      btn.disabled = false;
      btn.textContent = originalLabel;
    }
  });

  // ---- Multi-quarter ----
  $("#mq-run").addEventListener("click", async () => {
    const ids = $$(".mq-pick:checked").map(c => c.value);
    if (ids.length < 2) { setStatus("Pick at least 2 samples for multi-quarter.", "error"); return; }
    setStatus("Running multi-quarter compare...");
    const fd = new FormData();
    fd.append("sample_ids", ids.join(","));
    fd.append("skip_ai", "true");
    try {
      const r = await fetch("/api/multiquarter", {
        method: "POST", body: fd, headers: csrfHeaders(),
      });
      const j = await r.json();
      if (j.error) { setStatus("Multi-q failed: " + j.error, "error"); return; }
      renderMQ(j);
      show($("#mq-card"));
      $("#mq-card").scrollIntoView({behavior: "smooth", block: "start"});
      setStatus("Multi-quarter compare done.", "ok");
    } catch (e) {
      setStatus("Multi-q failed: " + e.message, "error");
    }
  });
  function renderMQ(j) {
    let html = `<thead><tr>
      <th>Period</th><th>Tone</th><th>Confidence</th>
      <th>Hedge</th><th>Certainty</th><th>Deflection</th>
      <th>Rev. guide low</th><th>Rev. guide high</th><th>Unit</th>
    </tr></thead><tbody>`;
    (j.cells || []).forEach(c => {
      html += `<tr>
        <td>${escapeHtml(c.period)}</td>
        <td>${escapeHtml(c.overall_tone)}</td>
        <td>${(c.confidence_score*100).toFixed(1)}%</td>
        <td>${c.hedge_count}</td>
        <td>${c.certainty_count}</td>
        <td>${c.deflection_count}</td>
        <td>${c.revenue_guidance_low === null ? "n/a" : fmtNum(c.revenue_guidance_low, 1)}</td>
        <td>${c.revenue_guidance_high === null ? "n/a" : fmtNum(c.revenue_guidance_high, 1)}</td>
        <td>${escapeHtml(c.revenue_unit)}</td>
      </tr>`;
    });
    $("#mq-table").innerHTML = html + "</tbody>";
  }

  // ---- Save / load + compare runs ----
  function loadSaved() {
    try { return JSON.parse(localStorage.getItem("day07.savedRuns.v1") || "[]"); }
    catch (_) { return []; }
  }
  function persist() {
    try { localStorage.setItem("day07.savedRuns.v1", JSON.stringify(savedRuns.slice(-30))); }
    catch (_) {}
  }
  $("#save-btn").addEventListener("click", async () => {
    if (!lastBody || !lastBody.run_id) return;
    const label = (prompt("Label this run:", lastBody.metadata.ticker || "run") || "").trim();
    if (!label) return;
    const fd = new FormData();
    fd.append("label", label);
    try {
      await fetch(`/api/runs/${lastBody.run_id}/save`, {
        method: "POST", body: fd, headers: csrfHeaders(),
      });
    } catch (_) {}
    savedRuns = savedRuns.filter(r => r.run_id !== lastBody.run_id);
    savedRuns.push({
      run_id: lastBody.run_id, label,
      ticker: lastBody.metadata.ticker,
      period: lastBody.metadata.fiscal_period,
      ts: Date.now(),
    });
    persist();
    refreshSaved();
    setStatus(`SAVED AS "${label.toUpperCase()}"`, "ok");
  });
  function refreshSaved() {
    if (!savedRuns.length) { hide($("#saved-runs-block")); return; }
    show($("#saved-runs-block"));
    const list = $("#saved-list");
    list.innerHTML = "";
    savedRuns.slice().reverse().forEach(s => {
      const li = document.createElement("li");
      li.innerHTML = `
        <input type="checkbox" data-rid="${s.run_id}">
        <span data-rid="${s.run_id}">${escapeHtml(s.label)} - ${escapeHtml(s.ticker || "")} ${escapeHtml(s.period || "")}</span>
      `;
      li.querySelector("span").onclick = () => loadCachedRun(s.run_id);
      list.appendChild(li);
    });
    $("#compare-btn").hidden = savedRuns.length < 2;
  }
  async function loadCachedRun(runId) {
    setStatus("Loading saved run...");
    try {
      const r = await fetch(`/api/runs/${runId}`);
      const j = await r.json();
      if (!r.ok) { setStatus("Load failed: " + (j.error || r.status), "error"); return; }
      lastBody = j;
      render(j);
      setStatus("LOADED", "ok");
    } catch (e) {
      setStatus("Load failed: " + e.message, "error");
    }
  }
  $("#compare-btn").addEventListener("click", async () => {
    const checked = $$(".saved-list input[type='checkbox']:checked").map(c => c.getAttribute("data-rid"));
    if (checked.length !== 2) { setStatus("Pick exactly two saved runs.", "error"); return; }
    const fd = new FormData();
    fd.append("a", checked[0]); fd.append("b", checked[1]);
    const r = await fetch("/api/compare", { method: "POST", body: fd, headers: csrfHeaders() });
    const j = await r.json();
    if (!r.ok) { setStatus("Compare failed.", "error"); return; }
    renderCompare(j);
    show($("#compare-card"));
    $("#compare-card").scrollIntoView({behavior: "smooth", block: "start"});
  });
  function renderCompare(j) {
    let html = `<thead><tr>
      <th>Metric</th>
      <th>${escapeHtml(j.a_company || j.a_id)} ${escapeHtml(j.a_period || "")} (A)</th>
      <th>${escapeHtml(j.b_company || j.b_id)} ${escapeHtml(j.b_period || "")} (B)</th>
      <th>Delta (B - A)</th>
    </tr></thead><tbody>`;
    const order = [
      ["confidence_score", "Confidence", "pct"],
      ["hedge_count", "Hedge", ""],
      ["certainty_count", "Certainty", ""],
      ["deflection_count", "Deflection", ""],
      ["quantitative_claims", "Quant claims", ""],
      ["minutes", "Minutes", ""],
      ["analyst_count", "Analysts", ""],
      ["word_count", "Word count", ""],
    ];
    const f = (v, kind) => v === null || v === undefined ? "n/a"
                        : kind === "pct" ? `${(v*100).toFixed(1)}%` : fmtNum(v);
    order.forEach(([k, label, kind]) => {
      const d = j.deltas[k] || {};
      const cls = d.delta === null ? "" : d.delta > 0 ? "dir-up" : "dir-down";
      html += `<tr>
        <td>${label}</td>
        <td>${f(d.a, kind)}</td>
        <td>${f(d.b, kind)}</td>
        <td class="${cls}">${d.delta === null ? "n/a" : (d.delta > 0 ? "+" : "") + f(d.delta, kind)}</td>
      </tr>`;
    });
    $("#compare-table").innerHTML = html + "</tbody>";
  }

  // ---- Markdown brief export + Copy verdict ----
  function buildMarkdown(body) {
    const md = body.metadata || {};
    const h = body.headline || {};
    const es = body.exec_summary || {};
    const lines = [];
    lines.push(`# ${md.company || ""} (${md.ticker || ""}) - ${md.fiscal_period || ""}`);
    lines.push("");
    lines.push(`**Tone:** ${(h.overall_tone || "").toUpperCase()}  `);
    lines.push(`**Confidence:** ${(((h.confidence_score || 0) * 100).toFixed(1))}%  `);
    lines.push(`**Hedge / Certainty / Deflection:** ${h.hedge_count || 0} / ${h.certainty_count || 0} / ${h.deflection_count || 0}  `);
    lines.push(`**Distinct analysts:** ${h.analyst_count || 0}`);
    lines.push("");
    if (es && es.headline) {
      lines.push(`## Verdict`);
      lines.push("");
      lines.push(`> ${es.headline}`);
      lines.push("");
    }
    if (es && es.bull_case) {
      lines.push(`### Bull case`);
      lines.push("");
      lines.push(es.bull_case);
      lines.push("");
    }
    if (es && es.bear_case) {
      lines.push(`### Bear case`);
      lines.push("");
      lines.push(es.bear_case);
      lines.push("");
    }
    if (es && (es.actions || []).length) {
      lines.push(`### Actions`);
      lines.push("");
      es.actions.forEach(a => lines.push(`- ${a}`));
      lines.push("");
    }
    if ((body.guidance || []).length) {
      lines.push(`## Forward guidance`);
      lines.push("");
      lines.push(`| Metric | Period | Direction | Range | Quote |`);
      lines.push(`|---|---|---|---|---|`);
      body.guidance.forEach(g => {
        let rng = "";
        if (g.range_low !== null && g.range_high !== null) rng = `${g.range_low} to ${g.range_high}`;
        else if (g.range_low !== null) rng = `${g.range_low}`;
        lines.push(`| ${g.metric} | ${g.period} | ${g.direction} | ${rng} ${g.unit} | ${g.quote.replace(/\|/g, " ")} |`);
      });
      lines.push("");
    }
    if ((body.qa || []).length) {
      lines.push(`## Analyst Q & A`);
      lines.push("");
      body.qa.forEach(q => {
        lines.push(`**${q.analyst_name}** (${q.analyst_firm}) - tension: ${q.tension}, clarity: ${q.management_clarity}`);
        lines.push(`- Q: ${q.question_summary}`);
        lines.push(`- A: ${q.answer_summary}`);
        lines.push("");
      });
    }
    if ((body.risks || []).length) {
      lines.push(`## Risk flags`);
      lines.push("");
      body.risks.forEach(r => lines.push(`- [${r.severity.toUpperCase()}] ${r.category}: ${r.quote}`));
      lines.push("");
    }
    return lines.join("\n");
  }

  $("#dl-md").addEventListener("click", () => {
    if (!lastBody) return;
    const md = buildMarkdown(lastBody);
    const blob = new Blob([md], { type: "text/markdown; charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const slug = (lastBody.metadata.ticker || "brief").toLowerCase();
    a.download = `brief_${slug}.md`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setStatus("MARKDOWN BRIEF DOWNLOADED", "ok");
  });

  $("#copy-verdict").addEventListener("click", async () => {
    if (!lastBody) return;
    const es = lastBody.exec_summary || {};
    const h = lastBody.headline || {};
    const md = lastBody.metadata || {};
    const text = [
      `${md.company || ""} (${md.ticker || ""}) - ${md.fiscal_period || ""}`,
      `Tone: ${(h.overall_tone || "").toUpperCase()}  Confidence: ${((h.confidence_score || 0) * 100).toFixed(1)}%`,
      "",
      `Verdict: ${es.headline || ""}`,
      "",
      `Bull: ${es.bull_case || ""}`,
      `Bear: ${es.bear_case || ""}`,
    ].join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setStatus("VERDICT COPIED TO CLIPBOARD", "ok");
    } catch (_) {
      setStatus("Could not copy. Browser blocked clipboard write.", "error");
    }
  });

  // ---- URL + print ----
  function syncURL(md) {
    if (!md.ticker) return;
    const params = new URLSearchParams();
    params.set("t", md.ticker);
    if (md.fiscal_period) params.set("p", md.fiscal_period);
    history.replaceState(null, "", "?" + params.toString());
  }
  $("#share-btn").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(location.href); setStatus("URL COPIED", "ok"); }
    catch (_) { setStatus(location.href, "ok"); }
  });
  $("#print-btn").addEventListener("click", () => window.print());

  // ---- Restore on load ----
  try {
    const cached = localStorage.getItem("day07.lastResult.v1");
    if (cached) {
      const body = JSON.parse(cached);
      lastBody = body;
      render(body);
      setStatus("RESTORED FROM LOCAL CACHE", "ok");
    }
  } catch (_) {}
  refreshSaved();
})();
