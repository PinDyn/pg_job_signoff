/**
 * PG Job Signoff — Phase 2 PWA client
 * Same APIs as Phase 1; adds installability, offline queue, snag photos, motion.
 */
(function () {
  const boot = window.__PG_SIGNOFF_BOOT__ || {};
  const root = document.getElementById("pg-root");
  const mount = document.getElementById("pg-mount");
  if (!root || !mount) return;

  const token = boot.token || root.dataset.token || "";
  const DB_NAME = "pg_signoff_v2";
  const STORE = "queue";

  let payload = boot.payload || null;
  let role = boot.role || (payload && payload.role) || "";
  let deferredInstall = null;
  let snagPhotos = {}; // snagName -> dataURL
  let pads = {};

  function $(sel, el) {
    return (el || document).querySelector(sel);
  }

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return match ? decodeURIComponent(match[2]) : "";
  }

  function setNetPill() {
    const pill = $("#net-pill");
    if (!pill) return;
    if (navigator.onLine) {
      pill.textContent = "Online";
      pill.classList.remove("pg-pill--warn");
    } else {
      pill.textContent = "Offline — will sync";
      pill.classList.add("pg-pill--warn");
    }
  }

  function openDb() {
    return new Promise(function (resolve, reject) {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = function () {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
        }
      };
      req.onsuccess = function () {
        resolve(req.result);
      };
      req.onerror = function () {
        reject(req.error);
      };
    });
  }

  function queueSubmit(entry) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        const tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).add(entry);
        tx.oncomplete = function () {
          resolve();
        };
        tx.onerror = function () {
          reject(tx.error);
        };
      });
    });
  }

  function readQueue() {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        const tx = db.transaction(STORE, "readonly");
        const req = tx.objectStore(STORE).getAll();
        req.onsuccess = function () {
          resolve(req.result || []);
        };
        req.onerror = function () {
          reject(req.error);
        };
      });
    });
  }

  function removeQueued(id) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        const tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).delete(id);
        tx.oncomplete = function () {
          resolve();
        };
        tx.onerror = function () {
          reject(tx.error);
        };
      });
    });
  }

  function apiCall(method, body) {
    return fetch("/api/method/" + method, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-Frappe-CSRF-Token": getCookie("csrf_token") || "",
      },
      body: JSON.stringify(body || {}),
      credentials: "same-origin",
    }).then(function (res) {
      return res.json().then(function (json) {
        if (!res.ok || json.exc || json.exception) {
          let msg = "Request failed";
          try {
            if (json._server_messages) {
              const parsed = JSON.parse(json._server_messages);
              msg = JSON.parse(parsed[0]).message || msg;
            } else if (typeof json.message === "string") {
              msg = json.message;
            }
          } catch (e) {}
          throw new Error(msg.replace(/<[^>]+>/g, ""));
        }
        return json.message;
      });
    });
  }

  function flushQueue() {
    if (!navigator.onLine) return Promise.resolve();
    return readQueue().then(function (items) {
      let chain = Promise.resolve();
      items.forEach(function (item) {
        chain = chain.then(function () {
          return apiCall("pg_job_signoff.api.signoff.submit_signoff", {
            token: item.token,
            data: item.data,
          }).then(function () {
            return removeQueued(item.id);
          });
        });
      });
      return chain;
    });
  }

  function registerSW() {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker
      .register("/pg-signoff-sw.js", { scope: "/" })
      .catch(function () {});
  }

  function textVal(value) {
    if (value === 0) return "0";
    if (value === null || value === undefined) return "";
    return String(value);
  }

  function escapeHtml(s) {
    return textVal(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderError(msg) {
    mount.innerHTML =
      '<section class="pg-signoff__card pg-signoff__error pg-anim-in">' +
      "<h1>Unable to open sign-off</h1>" +
      "<p>" +
      escapeHtml(msg) +
      "</p></section>";
  }

  function renderSuccess(queued) {
    mount.innerHTML =
      '<section class="pg-signoff__card pg-signoff__success pg-anim-pop">' +
      "<h1>Signed — thank you</h1>" +
      "<p>" +
      (queued
        ? "Saved on this device. It will sync when you are back online."
        : "Your sign-off has been recorded for this job.") +
      "</p></section>";
  }

  function infoRow(label, value) {
    if (value === null || value === undefined || value === "") return "";
    return (
      '<div class="pg-info-row"><dt>' +
      escapeHtml(label) +
      "</dt><dd>" +
      escapeHtml(value) +
      "</dd></div>"
    );
  }

  function formatDate(value) {
    if (!value) return "";
    const raw = String(value);
    // Keep YYYY-MM-DD readable; leave datetimes as returned
    if (/^\d{4}-\d{2}-\d{2}/.test(raw)) {
      try {
        const d = new Date(raw);
        if (!isNaN(d.getTime())) {
          return d.toLocaleDateString("en-ZA", {
            year: "numeric",
            month: "short",
            day: "numeric",
          });
        }
      } catch (e) {}
    }
    return raw;
  }

  function renderSummary(summary, signed) {
    let html = '<div class="pg-signoff__doc-title">';
    html +=
      "<h1>" +
      escapeHtml(summary.customer_name || summary.name || "Job sign-off") +
      "</h1>";
    html +=
      "<p>" +
      escapeHtml((payload && payload.title) || "Job sign-off") +
      (summary.name ? " · " + escapeHtml(summary.name) : "") +
      "</p></div>";

    html += '<div class="pg-signoff__summary"><dl>';
    html += infoRow("Job number", summary.name);
    html += infoRow("Status", summary.status);
    html += infoRow("Client name", summary.customer_name);
    html += infoRow("Contact number", summary.contact_number);
    html += infoRow("Email address", summary.email_address);
    html += infoRow("Installation address", summary.installation_address);
    html += infoRow("Quote number", summary.external_quote_ref);
    html += infoRow("Installation date", formatDate(summary.date_installed));
    html += infoRow("Technician", summary.technician_name);
    html += infoRow("Sales consultant", summary.sales_consultant);
    html += infoRow("Installation team", summary.installation_team);
    html += infoRow("Return visit date", formatDate(summary.return_visit_date));
    html += "</dl>";

    if (!signed) {
      html += "</div>";
      return html;
    }

    const techDone = !!(signed && signed.technician);
    const clientDone = !!(signed && signed.client);
    html += '<div class="pg-signoff__progress" aria-label="Sign-off progress">';
    html +=
      '<span class="pg-sign-badge' +
      (techDone ? " pg-sign-badge--done" : "") +
      '">' +
      (techDone ? "✓ " : "") +
      "Technician</span>";
    html +=
      '<span class="pg-sign-badge' +
      (clientDone ? " pg-sign-badge--done" : "") +
      '">' +
      (clientDone ? "✓ " : "") +
      "Client</span>";
    html += "</div></div>";
    return html;
  }

  function setSubtitle() {
    const subtitle = $("#form-subtitle");
    if (subtitle && payload && payload.title) subtitle.textContent = payload.title;
  }

  function renderControl(field) {
    const id = "f-" + field.fieldname;
    const value = escapeHtml(textVal(field.value));
    if (field.type === "textarea") {
      return (
        '<textarea id="' +
        id +
        '" data-field="' +
        escapeHtml(field.fieldname) +
        '" rows="3">' +
        value +
        "</textarea>"
      );
    }
    if (field.type === "select") {
      let html =
        '<select id="' +
        id +
        '" data-field="' +
        escapeHtml(field.fieldname) +
        '"' +
        (field.required ? " required" : "") +
        "><option value=\"\">Select…</option>";
      (field.options || []).forEach(function (opt) {
        html +=
          '<option value="' +
          escapeHtml(opt) +
          '"' +
          (textVal(field.value) === String(opt) ? " selected" : "") +
          ">" +
          escapeHtml(opt) +
          "</option>";
      });
      return html + "</select>";
    }
    const inputType = field.type === "date" ? "date" : field.type === "number" ? "number" : "text";
    return (
      '<input id="' +
      id +
      '" type="' +
      inputType +
      '" data-field="' +
      escapeHtml(field.fieldname) +
      '" value="' +
      value +
      '"' +
      (inputType === "number" ? ' step="any" inputmode="decimal"' : "") +
      (field.required ? " required" : "") +
      ">"
    );
  }

  function renderField(field) {
    if (field.type === "check") {
      return (
        '<label class="pg-choice"><input type="checkbox" data-field="' +
        escapeHtml(field.fieldname) +
        '"' +
        (field.value ? " checked" : "") +
        "><span>" +
        escapeHtml(field.label) +
        "</span></label>"
      );
    }
    if (field.type === "select" && field.layout === "row") {
      return '<label class="pg-yn-row"><span>' + escapeHtml(field.label) + "</span>" + renderControl(field) + "</label>";
    }
    return (
      '<div class="pg-field"><label for="f-' +
      escapeHtml(field.fieldname) +
      '">' +
      escapeHtml(field.label) +
      (field.required ? " *" : "") +
      "</label>" +
      renderControl(field) +
      "</div>"
    );
  }

  function renderLine(section, row) {
    let html = '<div class="pg-line" data-line>';
    (section.columns || []).forEach(function (col) {
      const value = row ? textVal(row[col.fieldname]) : "";
      html += '<label class="pg-field"><span>' + escapeHtml(col.label) + "</span>";
      if (col.type === "select") {
        html += '<select data-col="' + escapeHtml(col.fieldname) + '"><option value=""></option>';
        (col.options || []).forEach(function (opt) {
          html +=
            '<option value="' +
            escapeHtml(opt) +
            '"' +
            (value === String(opt) ? " selected" : "") +
            ">" +
            escapeHtml(opt) +
            "</option>";
        });
        html += "</select>";
      } else {
        const inputType = col.type === "date" ? "date" : col.type === "number" ? "number" : "text";
        html +=
          '<input type="' +
          inputType +
          '" data-col="' +
          escapeHtml(col.fieldname) +
          '" value="' +
          escapeHtml(value) +
          '"' +
          (inputType === "number" ? ' step="any"' : "") +
          ">";
      }
      html += "</label>";
    });
    return html + "</div>";
  }

  function renderStructuredForm() {
    setSubtitle();
    role = payload.role;
    const summary = payload.summary || {};
    const rolePill = $("#role-pill");
    if (rolePill) {
      rolePill.hidden = false;
      rolePill.textContent = payload.title || "Form";
    }
    const statusPill = $("#status-pill");
    if (statusPill && summary.status) {
      statusPill.hidden = false;
      statusPill.textContent = summary.status;
    }

    let html = '<section class="pg-signoff__card pg-anim-in" id="pg-signoff-app">';
    html += renderSummary(summary, null);
    (payload.sections || []).forEach(function (section) {
      if (section.type === "note") {
        html +=
          '<div class="pg-signoff__section"><h2>' +
          escapeHtml(section.title || "") +
          '</h2><p class="pg-note">' +
          escapeHtml(section.text) +
          "</p></div>";
        return;
      }
      if (section.type === "lines") {
        html +=
          '<div class="pg-signoff__section"><h2>' +
          escapeHtml(section.title || "") +
          '</h2><div class="pg-lines" data-lines="' +
          escapeHtml(section.fieldname) +
          '">';
        (section.rows || []).forEach(function (row) {
          html += renderLine(section, row);
        });
        html +=
          '</div><button type="button" class="pg-btn pg-btn--ghost" data-add-line="' +
          escapeHtml(section.fieldname) +
          '">Add line</button></div>';
        return;
      }
      if (section.type === "signatures") {
        html += '<div class="pg-signoff__section"><h2>' + escapeHtml(section.title || "Signatures") + "</h2>";
        (section.pads || []).forEach(function (pad) {
          html += '<div class="pg-sig-block">';
          html +=
            "<label>" + escapeHtml(pad.label) + (pad.required ? " *" : "") + "</label>";
          html +=
            '<input type="text" data-field="' +
            escapeHtml(pad.name_field) +
            '" value="' +
            escapeHtml(pad.name_value || "") +
            '" placeholder="Name" autocomplete="name">';
          html +=
            '<div class="pg-signoff__pad-wrap"><canvas class="pg-sig-canvas" id="sig-' +
            escapeHtml(pad.fieldname) +
            '" data-sig="' +
            escapeHtml(pad.fieldname) +
            '"></canvas></div>';
          html +=
            '<button type="button" class="pg-btn pg-btn--ghost" data-clear-sig="sig-' +
            escapeHtml(pad.fieldname) +
            '">Clear signature</button></div>';
        });
        html += "</div>";
        return;
      }
      html += '<div class="pg-signoff__section"><h2>' + escapeHtml(section.title || "") + "</h2>";
      if (section.layout === "grid") {
        html += '<div class="pg-choice-grid">';
        (section.fields || []).forEach(function (field) {
          if (field.type === "check") html += renderField(field);
        });
        html += "</div>";
        (section.fields || []).forEach(function (field) {
          if (field.type !== "check") html += renderField(field);
        });
      } else {
        (section.fields || []).forEach(function (field) {
          html += renderField(field);
        });
      }
      html += "</div>";
    });
    html +=
      '<button type="button" class="pg-btn pg-btn--primary" id="btn-submit">Submit</button>' +
      '<p class="pg-signoff__muted" id="status-msg"></p></section>';
    mount.innerHTML = html;
    bindAddLines();
    bindForm();
  }

  function bindAddLines() {
    document.querySelectorAll("[data-add-line]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const name = btn.getAttribute("data-add-line");
        const section = (payload.sections || []).filter(function (item) {
          return item.fieldname === name;
        })[0];
        const host = document.querySelector('[data-lines="' + name + '"]');
        if (!section || !host) return;
        host.insertAdjacentHTML("beforeend", renderLine(section, {}));
      });
    });
  }

  function renderForm() {
    if (!payload) return;
    if (payload.form_type) {
      renderStructuredForm();
      return;
    }
    renderLegacyForm();
  }

  function renderLegacyForm() {
    if (!payload) return;
    setSubtitle();
    role = payload.role;
    const summary = payload.summary || {};
    const signed = payload.already_signed || {};

    const rolePill = $("#role-pill");
    if (rolePill) {
      rolePill.hidden = false;
      rolePill.textContent = role === "technician" ? "Technician" : "Client";
    }
    const statusPill = $("#status-pill");
    if (statusPill && summary.status) {
      statusPill.hidden = false;
      statusPill.textContent = summary.status;
    }

    let html = '<section class="pg-signoff__card pg-anim-in" id="pg-signoff-app">';
    html += renderSummary(summary, signed);

    if (role === "client") {
      const checks = payload.checklist_summary || [];
      if (checks.length) {
        html += '<div class="pg-signoff__section"><h2>Checklist summary</h2><ul class="pg-signoff__checks">';
        checks.forEach(function (item) {
          html +=
            "<li><span>" +
            escapeHtml(item.label) +
            "</span><strong>" +
            escapeHtml(item.value) +
            "</strong></li>";
        });
        html += "</ul></div>";
      }
      html +=
        '<div class="pg-signoff__section"><label for="client_name">Your name</label>' +
        '<input id="client_name" type="text" value="' +
        escapeHtml(payload.client_name || "") +
        '" autocomplete="name" required></div>';
      html +=
        '<div class="pg-signoff__section"><label for="sign_off_comments">Comment (optional)</label>' +
        '<textarea id="sign_off_comments" rows="3" placeholder="Any notes for PG Aluminium">' +
        escapeHtml(payload.sign_off_comments || "") +
        "</textarea></div>";
    }

    if (role === "technician") {
      html +=
        '<div class="pg-signoff__section"><label for="technician_name">Technician name</label><select id="technician_name" required><option value="">Select…</option>';
      (payload.technician_name_options || []).forEach(function (opt) {
        const sel = payload.technician_name === opt ? " selected" : "";
        html +=
          '<option value="' +
          escapeHtml(opt) +
          '"' +
          sel +
          ">" +
          escapeHtml(opt) +
          "</option>";
      });
      html += "</select></div>";

      const snags = payload.snags || [];
      if (snags.length) {
        html +=
          '<div class="pg-signoff__section"><h2>Snags — mark completed</h2><ul class="pg-signoff__snags" id="snag-list">';
        snags.forEach(function (snag) {
          const done = snag.status === "Resolved";
          html += '<li class="pg-snag-card">';
          html += '<label class="pg-signoff__snag">';
          html +=
            '<input type="checkbox" data-snag-name="' +
            escapeHtml(snag.name) +
            '"' +
            (done ? " checked disabled" : "") +
            ">";
          html += "<span><strong>" + escapeHtml(snag.description || "Snag") + "</strong>";
          if (snag.location) html += "<em>" + escapeHtml(snag.location) + "</em>";
          html += "<small>Status: " + escapeHtml(snag.status || "Open");
          if (snag.priority) html += " · Priority: " + escapeHtml(snag.priority);
          if (snag.target_completion) {
            html += " · Target: " + escapeHtml(formatDate(snag.target_completion));
          }
          html += "</small></span></label>";
          html +=
            '<div class="pg-photo-row"><label class="pg-photo-btn">Add photo<input type="file" accept="image/*" capture="environment" data-snag-photo="' +
            escapeHtml(snag.name) +
            '" hidden></label>';
          html +=
            '<div class="pg-photo-preview" data-preview="' +
            escapeHtml(snag.name) +
            '"></div></div>';
          if (snag.photo) {
            html +=
              '<img class="pg-existing-photo" src="' +
              escapeHtml(snag.photo) +
              '" alt="Existing snag photo">';
          }
          html += "</li>";
        });
        html += "</ul></div>";
      } else {
        html += '<p class="pg-signoff__muted">No snags listed on this job.</p>';
      }
    }

    html +=
      '<div class="pg-signoff__section"><label>Signature</label><div class="pg-signoff__pad-wrap"><canvas class="pg-sig-canvas" id="sig-pad"></canvas></div>' +
      '<button type="button" class="pg-btn pg-btn--ghost" id="btn-clear-sig">Clear signature</button></div>';
    html +=
      '<button type="button" class="pg-btn pg-btn--primary" id="btn-submit">Submit sign-off</button>' +
      '<p class="pg-signoff__muted" id="status-msg"></p></section>';

    mount.innerHTML = html;
    bindForm();
  }

  function tunePad(pad) {
    if (/Android|Mobile|iPhone|iPad|iPod/i.test(navigator.userAgent)) {
      pad.off();
      pad._drawingStroke = false;
      pad._handleMouseEvents();
      if ("ontouchstart" in window) pad._handleTouchEvents();
    }
  }

  function resizePad(canvas, pad) {
    if (!canvas || !pad) return;
    const data = pad.toData();
    const ratio = Math.max(window.devicePixelRatio || 1, 1);
    const width = Math.max(1, Math.floor(canvas.offsetWidth || (canvas.parentElement && canvas.parentElement.clientWidth) || 300));
    const height = Math.max(1, Math.floor(canvas.offsetHeight || 180));
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    canvas.getContext("2d").setTransform(ratio, 0, 0, ratio, 0, 0);
    pad.clear();
    if (data && data.length) pad.fromData(data);
  }

  function resizeAllPads() {
    Object.keys(pads).forEach(function (id) {
      resizePad(document.getElementById(id), pads[id]);
    });
  }

  function bindSignature() {
    pads = {};
    if (typeof window.SignaturePad === "undefined") {
      console.error("SignaturePad library missing");
      return;
    }

    document.querySelectorAll(".pg-sig-canvas").forEach(function (canvas) {
      const pad = new window.SignaturePad(canvas, {
        minWidth: 0.8,
        maxWidth: 2.6,
        penColor: "#111111",
        backgroundColor: "rgb(255, 255, 255)",
        throttle: 8,
      });
      tunePad(pad);
      pads[canvas.id] = pad;
      resizePad(canvas, pad);
    });

    document.querySelectorAll("[data-clear-sig]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const pad = pads[btn.getAttribute("data-clear-sig")];
        if (pad) pad.clear();
      });
    });
    const legacyClear = $("#btn-clear-sig");
    if (legacyClear) {
      legacyClear.addEventListener("click", function () {
        if (pads["sig-pad"]) pads["sig-pad"].clear();
      });
    }

    let resizeTimer = null;
    function scheduleResize() {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(resizeAllPads, 150);
    }
    window.addEventListener("resize", scheduleResize);
    window.addEventListener("orientationchange", function () {
      setTimeout(scheduleResize, 300);
    });
    if (typeof ResizeObserver !== "undefined") {
      document.querySelectorAll(".pg-signoff__pad-wrap").forEach(function (wrap) {
        new ResizeObserver(scheduleResize).observe(wrap);
      });
    }
    requestAnimationFrame(function () {
      requestAnimationFrame(resizeAllPads);
    });
  }

  function bindPhotos() {
    document.querySelectorAll("input[data-snag-photo]").forEach(function (input) {
      input.addEventListener("change", function () {
        const file = input.files && input.files[0];
        const snagName = input.getAttribute("data-snag-photo");
        if (!file || !snagName) return;
        const reader = new FileReader();
        reader.onload = function () {
          const dataUrl = reader.result;
          // compress via canvas
          const img = new Image();
          img.onload = function () {
            const max = 1280;
            let w = img.width;
            let h = img.height;
            if (w > max || h > max) {
              const scale = Math.min(max / w, max / h);
              w = Math.round(w * scale);
              h = Math.round(h * scale);
            }
            const c = document.createElement("canvas");
            c.width = w;
            c.height = h;
            c.getContext("2d").drawImage(img, 0, 0, w, h);
            const out = c.toDataURL("image/jpeg", 0.72);
            snagPhotos[snagName] = out;
            const preview = document.querySelector('[data-preview="' + snagName + '"]');
            if (preview) {
              preview.innerHTML = '<img src="' + out + '" alt="Snag photo preview">';
            }
          };
          img.src = dataUrl;
        };
        reader.readAsDataURL(file);
      });
    });
  }

  function gatherStructured() {
    const data = { fields: {}, lines: {}, signatures: {} };
    document.querySelectorAll("[data-field]").forEach(function (el) {
      const name = el.getAttribute("data-field");
      data.fields[name] = el.type === "checkbox" ? (el.checked ? 1 : 0) : el.value || "";
    });
    document.querySelectorAll("[data-lines]").forEach(function (host) {
      const rows = [];
      host.querySelectorAll("[data-line]").forEach(function (line) {
        const row = {};
        let any = false;
        line.querySelectorAll("[data-col]").forEach(function (input) {
          row[input.getAttribute("data-col")] = input.value || "";
          if (input.value) any = true;
        });
        if (any) rows.push(row);
      });
      data.lines[host.getAttribute("data-lines")] = rows;
    });
    Object.keys(pads).forEach(function (id) {
      const canvas = document.getElementById(id);
      const field = canvas && canvas.getAttribute("data-sig");
      const pad = pads[id];
      if (!field || !pad || pad.isEmpty()) return;
      data.signatures[field] = pad.toDataURL("image/png");
    });
    return data;
  }

  function gatherPayload() {
    if (payload && payload.form_type) return gatherStructured();
    const data = {};
    const pad = pads["sig-pad"];
    const signature = pad && !pad.isEmpty() ? pad.toDataURL("image/png") : "";
    if (role === "client") {
      data.client_name = ($("#client_name").value || "").trim();
      data.sign_off_comments = $("#sign_off_comments").value || "";
      data.client_signature = signature;
    } else {
      data.technician_name = $("#technician_name").value || "";
      data.technician_signature = signature;
      const resolved = [];
      document.querySelectorAll('#snag-list input[type="checkbox"]:checked').forEach(function (box) {
        resolved.push(box.getAttribute("data-snag-name"));
      });
      data.resolved_snags = resolved;
      data.snag_photos = snagPhotos;
    }
    return data;
  }

  function validate(data) {
    if (payload && payload.form_type) {
      if (!data.fields.technician_name) return "Select the technician.";
      let missing = "";
      (payload.sections || []).forEach(function (section) {
        (section.fields || []).forEach(function (field) {
          if (!missing && field.required && !data.fields[field.fieldname]) missing = field.label + " is required.";
        });
        (section.pads || []).forEach(function (pad) {
          const signed = !!data.signatures[pad.fieldname];
          if (!missing && pad.required && !signed) missing = pad.label + " signature is required.";
          if (!missing && signed && !(data.fields[pad.name_field] || "").trim()) {
            missing = pad.label + " name is required.";
          }
        });
      });
      return missing || null;
    }
    const pad = pads["sig-pad"];
    if (!pad || pad.isEmpty()) return "Please provide a signature.";
    if (role === "client" && !data.client_name) return "Please enter your name.";
    if (role === "technician" && !data.technician_name) return "Please select technician name.";
    return null;
  }

  function bindForm() {
    bindSignature();
    bindPhotos();
    const submitBtn = $("#btn-submit");
    const statusMsg = $("#status-msg");

    submitBtn.addEventListener("click", function () {
      const data = gatherPayload();
      const err = validate(data);
      if (err) {
        statusMsg.textContent = err;
        statusMsg.style.color = "#b42318";
        return;
      }
      submitBtn.disabled = true;
      statusMsg.textContent = navigator.onLine ? "Submitting…" : "Saving offline…";
      statusMsg.style.color = "#555555";

      const doSubmit = function () {
        return apiCall("pg_job_signoff.api.signoff.submit_signoff", {
          token: token,
          data: data,
        });
      };

      const onOk = function (queued) {
        renderSuccess(!!queued);
      };

      if (!navigator.onLine) {
        queueSubmit({
          token: token,
          data: data,
          created: Date.now(),
        })
          .then(function () {
            onOk(true);
          })
          .catch(function (e) {
            submitBtn.disabled = false;
            statusMsg.textContent = e.message || "Could not save offline.";
            statusMsg.style.color = "#b42318";
          });
        return;
      }

      doSubmit()
        .then(function () {
          onOk(false);
        })
        .catch(function (e) {
          // Network failure mid-flight → queue
          return queueSubmit({ token: token, data: data, created: Date.now() }).then(
            function () {
              onOk(true);
            },
            function () {
              submitBtn.disabled = false;
              statusMsg.textContent = e.message || "Submit failed.";
              statusMsg.style.color = "#b42318";
            }
          );
        });
    });
  }

  function bootApp() {
    registerSW();
    setNetPill();
    window.addEventListener("online", function () {
      setNetPill();
      flushQueue();
    });
    window.addEventListener("offline", setNetPill);

    window.addEventListener("beforeinstallprompt", function (e) {
      e.preventDefault();
      deferredInstall = e;
      const btn = $("#btn-install");
      if (btn) {
        btn.hidden = false;
        btn.onclick = function () {
          deferredInstall.prompt();
        };
      }
    });

    if (boot.error && !payload) {
      renderError(boot.error);
      return;
    }

    if (!token) {
      renderError("Missing sign-off token.");
      return;
    }

    const show = function () {
      renderForm();
      flushQueue();
    };

    if (payload) {
      show();
      // Refresh in background when online
      if (navigator.onLine) {
        apiCall("pg_job_signoff.api.signoff.get_signoff_payload", { token: token })
          .then(function (fresh) {
            payload = fresh;
            role = fresh.role;
          })
          .catch(function () {});
      }
      return;
    }

    apiCall("pg_job_signoff.api.signoff.get_signoff_payload", { token: token })
      .then(function (fresh) {
        payload = fresh;
        role = fresh.role;
        show();
      })
      .catch(function (e) {
        renderError(e.message || "This sign-off link is invalid or expired.");
      });
  }

  bootApp();
})();
