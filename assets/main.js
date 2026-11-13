(() => {
  "use strict";

  // ------------------------------------------------------------------ config
  const GITHUB_USER = "giulianolorenzo-PhD";
  const DEFAULT_ART = "color-chars";    // id from assets/ascii.js
  const SHOW_PICKER = false;            // the bottom bar for trying art styles
  // used until (or if) the GitHub API answers
  const FALLBACK = { created: "2023-12-01T09:49:18Z", pushed: "2026-11-12T18:53:23Z" };

  const $ = (id) => document.getElementById(id);
  const VARIANTS = window.ASCII_VARIANTS || [];
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  };

  // ------------------------------------------------------------------ ascii art
  const art = $("art");

  function renderArt(v) {
    art.textContent = "";
    art.style.setProperty("--art-cols", v.cols);
    art.style.setProperty("--art-rows", v.rows);

    if (v.type === "pixels") {
      const canvas = document.createElement("canvas");
      canvas.width = v.w;
      canvas.height = v.h;
      const ctx = canvas.getContext("2d");
      const img = ctx.createImageData(v.w, v.h);
      for (let i = 0; i < v.w * v.h; i++) {
        const hex = v.px.substr(i * 6, 6);
        if (hex === "------") continue;
        img.data[i * 4] = parseInt(hex.slice(0, 2), 16);
        img.data[i * 4 + 1] = parseInt(hex.slice(2, 4), 16);
        img.data[i * 4 + 2] = parseInt(hex.slice(4, 6), 16);
        img.data[i * 4 + 3] = 255;
      }
      ctx.putImageData(img, 0, 0);
      art.append(canvas);
      return;
    }

    const pre = document.createElement("pre");
    if (!v.colors) {
      pre.textContent = v.lines.join("\n");
    } else {
      const frag = document.createDocumentFragment();
      v.lines.forEach((line, y) => {
        let gap = "";
        [...line].forEach((ch, x) => {
          if (ch === " ") { gap += " "; return; }
          if (gap) { frag.append(gap); gap = ""; }
          const s = document.createElement("span");
          s.textContent = ch;
          s.style.color = "#" + v.colors.substr((y * v.cols + x) * 6, 6);
          frag.append(s);
        });
        frag.append(gap + "\n");
      });
      pre.append(frag);
    }
    art.append(pre);
  }

  // ------------------------------------------------------------------ style picker
  const tabs = $("tabs");
  let current = 0;

  function select(i, { save = true } = {}) {
    if (!VARIANTS.length) return;
    current = (i + VARIANTS.length) % VARIANTS.length;
    const v = VARIANTS[current];
    renderArt(v);
    [...tabs.children].forEach((b, j) => b.setAttribute("aria-selected", String(j === current)));
    if (save) {
      store.set("ascii-style", v.id);
      const url = new URL(location.href);
      url.searchParams.set("ascii", v.id);
      history.replaceState(null, "", url);
    }
  }

  function initPicker() {
    const fromUrl = new URLSearchParams(location.search).get("ascii");
    const wanted = SHOW_PICKER ? (fromUrl || store.get("ascii-style") || DEFAULT_ART) : (fromUrl || DEFAULT_ART);
    let start = VARIANTS.findIndex((v) => v.id === wanted);
    if (start < 0) start = Math.max(0, VARIANTS.findIndex((v) => v.id === DEFAULT_ART));

    if (!SHOW_PICKER) {
      $("picker").remove();
      document.body.style.paddingBottom = "0";
      select(start, { save: false });
      return;
    }

    VARIANTS.forEach((v, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.setAttribute("role", "tab");
      b.title = v.desc;
      b.innerHTML = `<span class="n">${i + 1}</span>`;
      b.append(v.label);
      b.addEventListener("click", () => select(i));
      tabs.append(b);
    });

    document.addEventListener("keydown", (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const n = parseInt(e.key, 10);
      if (n >= 1 && n <= VARIANTS.length) select(n - 1);
      else if (e.key === "ArrowRight") select(current + 1);
      else if (e.key === "ArrowLeft") select(current - 1);
    });

    select(start, { save: Boolean(fromUrl) });
  }

  // ------------------------------------------------------------------ live info
  const DAY = 864e5;

  function fmtDate(d) {
    const p = Object.fromEntries(
      new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })
        .formatToParts(d).map((x) => [x.type, x.value])
    );
    const t = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false }).format(d);
    return `${p.weekday} ${p.day} ${p.month} ${p.year} at ${t}`;
  }

  const setAge = (iso) => { $("age").textContent = `${Math.floor((Date.now() - new Date(iso)) / DAY)} days`; };
  const setUpdate = (iso) => { $("update").textContent = fmtDate(new Date(iso)); };

  function initLive() {
    setAge(FALLBACK.created);
    setUpdate(FALLBACK.pushed);

    const api = (path) => fetch(`https://api.github.com/${path}`, { headers: { Accept: "application/vnd.github+json" } })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);
    api(`users/${GITHUB_USER}`).then((u) => u && u.created_at && setAge(u.created_at));
    api(`users/${GITHUB_USER}/repos?sort=pushed&per_page=1`).then((r) => r && r[0] && setUpdate(r[0].pushed_at));

    const t0 = Date.now();
    const up = $("uptime");
    const tick = () => {
      const s = Math.floor((Date.now() - t0) / 1000);
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      up.textContent = h ? `${h}h ${m}m` : `${m}m ${s % 60}s`;
    };
    tick();
    setInterval(tick, 1000);
  }

  // ------------------------------------------------------------------ boot sequence
  function boot() {
    const term = $("term");
    const fetchEl = $("fetch");
    const cmd = $("cmd");
    const prompt = $("prompt-cmd");
    if (reduced) return;

    const text = cmd.textContent;
    const lines = [...fetchEl.querySelectorAll(".info .ln, .info .rule")];
    const timers = [];
    const later = (ms, fn) => timers.push(setTimeout(fn, ms));
    let done = false;

    const finish = () => {
      if (done) return;
      done = true;
      timers.forEach(clearTimeout);
      cmd.textContent = text;
      prompt.classList.remove("typing");
      term.classList.remove("booting");
      fetchEl.classList.remove("printing");
      lines.forEach((l) => l.classList.remove("on"));
      removeEventListener("keydown", finish, true);
      removeEventListener("pointerdown", finish, true);
    };

    term.classList.add("booting");
    prompt.classList.add("typing");
    cmd.textContent = "";
    addEventListener("keydown", finish, true);
    addEventListener("pointerdown", finish, true);

    let t = 350;
    [...text].forEach((ch) => { t += 55 + Math.random() * 45; later(t, () => { cmd.textContent += ch; }); });
    t += 320;
    later(t, () => {
      prompt.classList.remove("typing");
      fetchEl.classList.add("printing");
      term.classList.remove("booting");
      $("prompt-end").style.visibility = "hidden";
    });
    lines.forEach((l, i) => later(t + 40 + i * 24, () => l.classList.add("on")));
    t += 40 + lines.length * 24 + 120;
    later(t, () => { $("prompt-end").style.visibility = ""; finish(); });
  }

  initPicker();
  initLive();
  boot();
})();
