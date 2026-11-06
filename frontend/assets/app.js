const $ = s => document.querySelector(s);

function usd(value) {
  return "$" + Number(value).toFixed(3);
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, character => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }[character]));
}

function inlineMarkdown(value) {
  return value
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/_([^_]+)_/g, "<em>$1</em>");
}

function renderMarkdown(markdown) {
  const lines = escapeHtml(markdown).split("\n");
  const html = [];
  let code = false;
  let codeLines = [];
  let listType = null;

  const closeList = () => {
    if (listType) {
      html.push(`</${listType}>`);
      listType = null;
    }
  };

  lines.forEach(line => {
    if (line.trim().startsWith("```")) {
      if (code) {
        html.push(`<pre><code>${codeLines.join("\n")}</code></pre>`);
        codeLines = [];
      }
      code = !code;
      closeList();
      return;
    }
    if (code) {
      codeLines.push(line);
      return;
    }

    const heading = line.match(/^#{1,3}\s+(.+)$/);
    const unordered = line.match(/^[-*]\s+(.+)$/);
    const ordered = line.match(/^\d+\.\s+(.+)$/);
    if (!line.trim()) {
      closeList();
      return;
    }
    if (heading) {
      closeList();
      const level = Math.min(heading[0].indexOf(" "), 3);
      html.push(`<h${level}>${inlineMarkdown(heading[1])}</h${level}>`);
      return;
    }
    if (unordered || ordered) {
      const nextType = unordered ? "ul" : "ol";
      if (listType !== nextType) {
        closeList();
        listType = nextType;
        html.push(`<${listType}>`);
      }
      html.push(`<li>${inlineMarkdown((unordered || ordered)[1])}</li>`);
      return;
    }
    closeList();
    html.push(`<p>${inlineMarkdown(line)}</p>`);
  });

  if (code) html.push(`<pre><code>${codeLines.join("\n")}</code></pre>`);
  closeList();
  return html.join("");
}

async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const storedKey = sessionStorage.getItem("routewise_api_key");
  if (storedKey) headers.set("Authorization", `Bearer ${storedKey}`);
  const response = await fetch(url, { ...options, headers });
  if (response.status !== 401) return response;

  const key = window.prompt("Enter your RouteWise API key for this browser session:");
  if (!key) return response;
  sessionStorage.setItem("routewise_api_key", key.trim());
  headers.set("Authorization", `Bearer ${key.trim()}`);
  return fetch(url, { ...options, headers });
}

function pareto(svg, threshold, color) {
  const X = x => 50 + x * 500;
  const Y = y => 270 - (y - 55) / 35 * 240;
  const quality = x => 62 + 22 * (1 - Math.pow(1 - x, 2.6));
  let html = "";
  [60, 70, 80, 90].forEach(y => {
    html += `<line x1="50" x2="550" y1="${Y(y)}" y2="${Y(y)}" stroke="#d5dbe6"/><text class="svgsub" x="8" y="${Y(y) + 4}">${y}%</text>`;
  });
  [0, 25, 50, 75, 100].forEach(x => {
    html += `<text class="svgsub" x="${X(x / 100) - 10}" y="295">${x}%</text>`;
  });
  html += `<text class="svgsub" x="50" y="315">Cost compared with always using the strong model</text>`;
  html += `<line x1="${X(0)}" y1="${Y(62)}" x2="${X(1)}" y2="${Y(84)}" stroke="#5b6478" stroke-dasharray="6 5" stroke-width="2"/>`;
  let points = "";
  for (let i = 0; i <= 20; i++) {
    const x = i / 20;
    points += `${X(x)},${Y(quality(x))} `;
  }
  html += `<polyline points="${points}" fill="none" stroke="#14213d" stroke-width="3.5"/>`;
  html += `<text class="svgtxt" x="${X(.3)}" y="${Y(quality(.3)) - 12}">Trained router</text>`;
  html += `<text class="svgsub" x="${X(.55)}" y="${Y(62 + 22 * .55) + 22}">Random routing</text>`;
  const x = 0.1 + (threshold - 0.3) / 0.6 * 0.8;
  html += `<circle cx="${X(x)}" cy="${Y(quality(x))}" r="11" fill="${color}" opacity=".25"/><circle cx="${X(x)}" cy="${Y(quality(x))}" r="6" fill="${color}"/>`;
  svg.innerHTML = html;
}

async function routePrompt(prompt, threshold) {
  const response = await apiFetch("/api/route", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, threshold })
  });
  if (!response.ok) throw new Error("The router API returned an error.");
  return response.json();
}

async function completePrompt(prompt, threshold) {
  const response = await apiFetch("/api/playground", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "routewise",
      messages: [{ role: "user", content: prompt }],
      threshold
    })
  });
  if (!response.ok) throw new Error("The model provider returned an error.");
  const data = await response.json();
  return {
    content: data.choices?.[0]?.message?.content || "The provider returned an empty answer.",
    model: data.model || "configured provider"
  };
}

function playground() {
  const textarea = $("#prompt");
  const threshold = $("#t");
  const submit = $("#submit-prompt");
  let lastPrompt = "";

  async function run() {
    const prompt = textarea.value.trim();
    const t = Number(threshold.value);
    $("#tv").textContent = t.toFixed(2);
    pareto($("#pareto"), t, prompt ? "var(--cheap)" : "#14213d");
    if (!prompt) {
      $("#route").textContent = "Waiting for a prompt";
      $("#why").textContent = "Type a prompt or pick an example to see where it goes.";
      $("#tag").style.background = "var(--mute)";
      return;
    }

    submit.disabled = true;
    submit.classList.add("loading");
    submit.innerHTML = "Routing and generating <span>...</span>";
    $("#submit-hint").textContent = "Using one provider request for this prompt.";
    $("#route").textContent = "Routing...";
    $("#answer").textContent = "Generating answer...";
    try {
      const result = await routePrompt(prompt, t);
      const answer = await completePrompt(prompt, t);
      const color = result.cheap ? "var(--cheap)" : "var(--strong)";
      $("#tag").style.background = color;
      $("#route").textContent = result.cheap ? "Cheap model" : "Strong model";
      $("#why").textContent = `${result.explanation} Your threshold is ${t.toFixed(2)}.`;
      $("#c1").textContent = usd(result.estimated_cost_per_1000);
      $("#c0").textContent = usd(result.strong_cost_per_1000);
      $("#sv").textContent = Math.round((1 - result.estimated_cost_per_1000 / result.strong_cost_per_1000) * 100) + "%";
      $("#lat").textContent = Math.round(result.latency_ms) + " ms";
      $("#rl").textContent = result.router_latency_ms.toFixed(1) + " ms";
      $("#source").textContent = `Answered by ${answer.model} (${result.cheap ? "cheap" : "strong"} tier).`;
      $("#answer").innerHTML = renderMarkdown(answer.content);
      $("#submit-hint").textContent = "Response complete.";
      if (prompt !== lastPrompt) {
        $("#rc").className = "rail cheap" + (result.cheap ? "" : " off");
        $("#rs").className = "rail strong" + (result.cheap ? " off" : "");
        lastPrompt = prompt;
      }
    } catch (error) {
      $("#route").textContent = "Router unavailable";
      $("#why").textContent = error.message;
      $("#source").textContent = "Provider response unavailable.";
      $("#answer").textContent = "Unable to generate an answer.";
      $("#submit-hint").textContent = "Try submitting again.";
    } finally {
      submit.disabled = false;
      submit.classList.remove("loading");
      submit.innerHTML = "Submit prompt <span>↗</span>";
    }
  }

  const updatePreview = () => {
    const prompt = textarea.value.trim();
    const t = Number(threshold.value);
    $("#tv").textContent = t.toFixed(2);
    pareto($("#pareto"), t, prompt ? "var(--cheap)" : "#14213d");
  };
  submit.addEventListener("click", run);
  textarea.addEventListener("input", updatePreview);
  threshold.addEventListener("input", updatePreview);
  document.querySelectorAll("[data-p]").forEach(button => {
    button.onclick = () => {
      textarea.value = button.dataset.p;
      updatePreview();
      textarea.focus();
    };
  });
  updatePreview();
}

async function dashboard() {
  try {
    const response = await apiFetch("/api/dashboard");
    if (!response.ok) throw new Error("The dashboard API returned an error.");
    const data = await response.json();
    $("#reqs").textContent = data.requests_routed;
    $("#share").textContent = Math.round(data.cheap_share * 100) + "%";
    $("#save").textContent = Math.round(data.estimated_savings * 100) + "%";
    $("#p95").textContent = data.router_p95_ms.toFixed(1) + " ms";
    $("#split").innerHTML = `<div style="width:${data.cheap_share * 100}%;background:var(--cheap)"></div><div style="flex:1;background:var(--strong)"></div>`;
    const bins = Array(10).fill(0);
    data.confidence_scores.forEach(score => bins[Math.min(9, Math.floor(score * 10))]++);
    const max = Math.max(...bins, 1);
    $("#hist").innerHTML = bins.map((bin, index) => `<div class="${index >= 6 ? "c" : ""}" style="height:${bin / max * 100}%" title="${index * 10}-${index * 10 + 10}%: ${bin}"></div>`).join("");
    $("#rows").innerHTML = data.recent_requests.map(row => `<tr><td>Request</td><td>${Math.round(row.score * 100)}%</td><td><span class="pill" style="background:${row.cheap ? "var(--cheap)" : "var(--strong)"}">${row.cheap ? "Cheap" : "Strong"}</span></td><td>${Math.round(row.latency_ms)} ms</td><td>${usd(row.estimated_cost_per_1000)}</td></tr>`).join("");
  } catch (error) {
    $("#rows").innerHTML = `<tr><td colspan="5">${error.message}</td></tr>`;
  }
}

document.addEventListener("DOMContentLoaded", () => $("#prompt") ? playground() : dashboard());
