/* ViewsAI Social Video Engine — studio logic */
const $ = (s) => document.querySelector(s);
const state = { master: null, platforms: new Set(), job: null, poll: null };

/* platform cards */
const ASPECT_LABEL = { "9:16": "9:16", "4:5": "4:5", "1:1": "1:1", "16:9": "16:9" };

async function loadPlatforms() {
  const r = await fetch("/api/platforms");
  const data = await r.json();
  const wrap = $("#plats");
  for (const key of Object.keys(data)) {
    const p = data[key];
    const el = document.createElement("div");
    el.className = "plat";
    el.innerHTML = `<div class="ico">${ASPECT_LABEL[p.aspect]}</div>
      <div><div class="nm">${pretty(key)}</div><div class="sz">${p.size}</div></div>`;
    el.onclick = () => {
      el.classList.toggle("on");
      state.platforms.has(key) ? state.platforms.delete(key) : state.platforms.add(key);
      refreshGo();
    };
    wrap.appendChild(el);
  }
  $("#all").onclick = () => { document.querySelectorAll(".plat").forEach((e, i) => { e.classList.add("on"); state.platforms.add(Object.keys(data)[i]); }); refreshGo(); };
  $("#clear").onclick = () => { document.querySelectorAll(".plat").forEach((e) => e.classList.remove("on")); state.platforms.clear(); refreshGo(); };
}
function pretty(k) { return k.split("-").map(w => w[0].toUpperCase() + w.slice(1)).join(" "); }

/* upload */
async function upload(file) {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch("/api/upload", { method: "POST", body: fd });
  const info = await r.json();
  if (info.error) { showErr(info.error); return; }
  state.master = info;
  $("#drop").classList.add("hidden");
  $("#master-meta").classList.remove("hidden");
  $("#m-name").textContent = info.name;
  $("#m-size").textContent = `${info.width}×${info.height} (${info.aspect})`;
  $("#m-dur").textContent = `${info.duration}s`;
  $("#m-audio").textContent = info.has_audio ? "audio ✓" : "no audio";
  refreshGo();
}
const drop = $("#drop");
drop.onclick = () => $("#file").click();
drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); upload(e.dataTransfer.files[0]); };
$("#file").onchange = (e) => upload(e.target.files[0]);
$("#replace").onclick = () => { state.master = null; $("#master-meta").classList.add("hidden"); $("#drop").classList.remove("hidden"); refreshGo(); };

/* create */
function refreshGo() {
  $("#go").disabled = !(state.master && state.platforms.size > 0);
}
function showErr(m) { $("#err").textContent = m; $("#err").classList.remove("hidden"); }
function clearErr() { $("#err").classList.add("hidden"); }

$("#go").onclick = async () => {
  clearErr();
  const body = {
    master_id: state.master.id,
    platforms: [...state.platforms],
    title: $("#no-text").checked ? "" : $("#title").value.trim(),
    caption: $("#no-text").checked ? "" : $("#caption").value.trim(),
    cta: $("#no-text").checked ? "" : $("#cta").value.trim(),
    mode: $("#mode").value,
    accent: $("#no-text").checked ? null : $("#accent").value.slice(1),
    fg: $("#no-text").checked ? null : $("#fg").value.slice(1),
    cover: $("#cover").checked,
  };
  if (!body.title && !body.caption && !body.cta && !$("#no-text").checked) {
    if (!confirm("No text entered — render without overlays?")) return;
  }
  const r = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json();
  if (j.error) { showErr(j.error); return; }
  state.job = j.id;
  $("#card-progress").classList.remove("hidden");
  $("#card-results").classList.add("hidden");
  $("#proglist").innerHTML = "";
  for (const p of body.platforms) {
    const li = document.createElement("li");
    li.id = "li-" + p;
    li.textContent = "⏳ " + pretty(p);
    $("#proglist").appendChild(li);
  }
  pollJob();
};

async function pollJob() {
  const r = await fetch(`/api/jobs/${state.job}`);
  const s = await r.json();
  $("#prog-pill").textContent = `${s.done.length}/${s.total}`;
  $("#barfill").style.width = `${(s.done.length / s.total) * 100}%`;
  for (const p of s.done) { const li = $("#li-" + p); if (li) { li.className = "ok"; li.textContent = "✓ " + pretty(p); } }
  if (s.current) { const li = $("#li-" + s.current); if (li) { li.className = "now"; li.textContent = "▶ " + pretty(s.current) + " (rendering…)"; } }
  for (const e of s.errors) { const li = $("#li-" + e.platform); if (li) { li.className = "fail"; li.textContent = "✗ " + pretty(e.platform) + " — " + e.detail.slice(0, 80); } }
  if (!s.finished) { state.poll = setTimeout(pollJob, 900); return; }
  loadResults();
}

async function loadResults() {
  const r = await fetch(`/api/jobs/${state.job}/results`);
  const { results } = await r.json();
  const wrap = $("#results");
  wrap.innerHTML = "";
  for (const res of results) {
    const el = document.createElement("div");
    el.className = "res";
    const tag = res.cover ? "cover" : res.platform;
    el.innerHTML = `<div class="plat-nm">${pretty(tag)}</div>
      <div class="file">${res.name}</div>
      <a class="dl" href="${res.url}" download>↓ Download (${res.size_mb} MB)</a>`;
    wrap.appendChild(el);
  }
  $("#card-results").classList.remove("hidden");
  $("#card-progress").classList.add("hidden");
}

loadPlatforms();
