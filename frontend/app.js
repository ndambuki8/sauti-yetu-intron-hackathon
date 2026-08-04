// Voice Triage Hint — frontend logic (no frameworks, plain JS).

const $ = (id) => document.getElementById(id);

// ---------- Tabs ----------
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    $("tab-triage").hidden = btn.dataset.tab !== "triage";
    $("tab-benchmark").hidden = btn.dataset.tab !== "benchmark";
  });
});

// ---------- Languages ----------
async function loadLanguages() {
  const res = await fetch("/api/languages");
  const { languages } = await res.json();
  for (const selectId of ["triage-language", "bench-language"]) {
    const select = $(selectId);
    for (const [code, name] of Object.entries(languages)) {
      const option = document.createElement("option");
      option.value = code;
      option.textContent = `${name} (${code})`;
      select.appendChild(option);
    }
    select.value = "sw";
  }
}
loadLanguages();

// ---------- Audio capture (record or upload) ----------
let triageBlob = null;
let triageFilename = "recording.webm";
let mediaRecorder = null;
let chunks = [];

const recordBtn = $("record-btn");

recordBtn.addEventListener("click", async () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    chunks = [];
    mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      triageBlob = new Blob(chunks, { type: mediaRecorder.mimeType || "audio/webm" });
      triageFilename = "recording.webm";
      const preview = $("triage-preview");
      preview.src = URL.createObjectURL(triageBlob);
      preview.hidden = false;
      recordBtn.textContent = "Start recording";
      recordBtn.classList.remove("recording");
      $("triage-submit").disabled = false;
    };
    mediaRecorder.start();
    recordBtn.textContent = "Stop recording";
    recordBtn.classList.add("recording");
  } catch (err) {
    showStatus("triage-status", `Microphone error: ${err.message}`, true);
  }
});

$("triage-file").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  triageBlob = file;
  triageFilename = file.name;
  const preview = $("triage-preview");
  preview.src = URL.createObjectURL(file);
  preview.hidden = false;
  $("triage-submit").disabled = false;
});

// ---------- Status helper ----------
function showStatus(id, message, isError = false) {
  const el = $(id);
  el.textContent = message;
  el.hidden = !message;
  el.classList.toggle("error", isError);
}

// ---------- Triage ----------
$("triage-submit").addEventListener("click", async () => {
  if (!triageBlob) return;
  $("triage-result").hidden = true;
  showStatus("triage-status", "Transcribing with Intron Sahara and running triage...");
  $("triage-submit").disabled = true;

  const form = new FormData();
  form.append("audio", triageBlob, triageFilename);
  form.append("language_code", $("triage-language").value);

  try {
    const res = await fetch("/api/triage", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    renderTriage(data);
    showStatus("triage-status", "");
  } catch (err) {
    showStatus("triage-status", `Triage failed: ${err.message}`, true);
  } finally {
    $("triage-submit").disabled = false;
  }
});

function renderTriage(data) {
  const t = data.triage;

  const badge = $("urgency-badge");
  badge.textContent = t.urgency;
  badge.className = `badge ${t.urgency}`;

  $("topic").textContent = t.topic;
  $("department").textContent = `Route to: ${t.suggested_department}`;
  $("other-topics").textContent = t.other_possible_topics.length
    ? `Also possible: ${t.other_possible_topics.join("; ")}`
    : "";

  const intake = $("intake-card");
  intake.innerHTML = "";
  const labels = {
    patient_language: "Patient language",
    presenting_complaint: "Presenting complaint",
    key_findings: "Key findings / entities",
    possible_conditions: "Possible conditions",
    red_flags: "Red flags",
  };
  for (const [key, label] of Object.entries(labels)) {
    const value = t.intake_card[key];
    if (!value) continue;
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    intake.append(dt, dd);
  }

  const questions = $("questions");
  questions.innerHTML = "";
  t.clarifying_questions.forEach((q) => {
    const li = document.createElement("li");
    li.textContent = q;
    questions.appendChild(li);
  });

  $("transcript").textContent = data.transcript || "(no transcript returned)";
  $("summary").textContent = data.summary || "(no summary returned)";

  $("suggestions-block").hidden = !t.intron_suggestions;
  $("suggestions").textContent = t.intron_suggestions || "";

  $("triage-result").hidden = false;
}

// ---------- Benchmark ----------
function updateBenchReady() {
  $("bench-submit").disabled = !(
    $("bench-file").files[0] && $("bench-reference").value.trim()
  );
}
$("bench-file").addEventListener("change", updateBenchReady);
$("bench-reference").addEventListener("input", updateBenchReady);

$("bench-submit").addEventListener("click", async () => {
  const file = $("bench-file").files[0];
  if (!file) return;
  $("bench-result").hidden = true;
  showStatus(
    "bench-status",
    "Running Intron Sahara, Whisper, and MMS... first run may take several minutes."
  );
  $("bench-submit").disabled = true;

  const form = new FormData();
  form.append("audio", file, file.name);
  form.append("reference_transcript", $("bench-reference").value.trim());
  form.append("language_code", $("bench-language").value);

  try {
    const res = await fetch("/api/benchmark", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    renderBenchmark(data);
    showStatus("bench-status", "");
  } catch (err) {
    showStatus("bench-status", `Benchmark failed: ${err.message}`, true);
  } finally {
    updateBenchReady();
  }
});

function renderBenchmark(data) {
  $("bench-best").textContent = data.best_model
    ? `Lowest WER on this clip: ${data.best_model}`
    : "No model produced a scoreable transcript.";

  const tbody = $("bench-table").querySelector("tbody");
  tbody.innerHTML = "";
  data.results.forEach((r) => {
    const tr = document.createElement("tr");
    const fmt = (v) => (v === null || v === undefined ? "—" : v);
    if (r.error) {
      tr.innerHTML = `<td>${r.model}<br><small>${r.kind}</small></td>
        <td colspan="4" class="err"></td>`;
      tr.querySelector(".err").textContent = `Error: ${r.error}`;
    } else {
      tr.innerHTML = `<td>${r.model}<br><small>${r.kind}</small></td>
        <td>${fmt(r.wer)}</td><td>${fmt(r.cer)}</td>
        <td>${fmt(r.latency_seconds)}</td><td class="hyp"></td>`;
      tr.querySelector(".hyp").textContent = r.transcript || "(empty)";
    }
    tbody.appendChild(tr);
  });
  $("bench-result").hidden = false;
}
