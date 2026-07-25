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
  let hasInk = false;
  let drawing = false;
  let snagPhotos = {}; // snagName -> dataURL
  let canvas, ctx;

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

  function escapeHtml(s) {
    return String(s || "")
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

  function renderForm() {
    if (!payload) return;
    role = payload.role;
    const summary = payload.summary || {};
    let html = '<section class="pg-signoff__card pg-anim-in" id="pg-signoff-app">';
    html += '<div class="pg-signoff__summary">';
    html += "<h1>" + escapeHtml(summary.customer_name || summary.name) + "</h1><dl>";
    html +=
      "<div><dt>Job</dt><dd>" + escapeHtml(summary.name) + "</dd></div>";
    if (summary.installation_address) {
      html +=
        "<div><dt>Address</dt><dd>" +
        escapeHtml(summary.installation_address) +
        "</dd></div>";
    }
    if (summary.external_quote_ref) {
      html +=
        "<div><dt>Quote</dt><dd>" +
        escapeHtml(summary.external_quote_ref) +
        "</dd></div>";
    }
    if (summary.date_installed) {
      html +=
        "<div><dt>Installed</dt><dd>" +
        escapeHtml(summary.date_installed) +
        "</dd></div>";
    }
    html += "</dl></div>";

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
          html += "<small>Status: " + escapeHtml(snag.status || "Open") + "</small></span></label>";
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
      '<div class="pg-signoff__section"><label>Signature</label><div class="pg-signoff__pad-wrap"><canvas id="sig-pad"></canvas></div>' +
      '<button type="button" class="pg-btn pg-btn--ghost" id="btn-clear-sig">Clear signature</button></div>';
    html +=
      '<button type="button" class="pg-btn pg-btn--primary" id="btn-submit">Submit sign-off</button>' +
      '<p class="pg-signoff__muted" id="status-msg"></p></section>';

    mount.innerHTML = html;
    bindForm();
  }

  function resizeCanvas() {
    canvas = $("#sig-pad");
    if (!canvas) return;
    ctx = canvas.getContext("2d");
    const ratio = Math.max(window.devicePixelRatio || 1, 1);
    const width = canvas.clientWidth || 600;
    const height = Math.round(width * 0.4);
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.lineWidth = 2.4;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#1a3a5c";
    hasInk = false;
  }

  function pointerPos(e) {
    const rect = canvas.getBoundingClientRect();
    const point = e.touches ? e.touches[0] : e;
    return { x: point.clientX - rect.left, y: point.clientY - rect.top };
  }

  function bindSignature() {
    resizeCanvas();
    function start(e) {
      drawing = true;
      const p = pointerPos(e);
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
      e.preventDefault();
    }
    function move(e) {
      if (!drawing) return;
      const p = pointerPos(e);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
      hasInk = true;
      e.preventDefault();
    }
    function end(e) {
      drawing = false;
      e.preventDefault();
    }
    canvas.addEventListener("mousedown", start);
    canvas.addEventListener("mousemove", move);
    canvas.addEventListener("mouseup", end);
    canvas.addEventListener("mouseleave", end);
    canvas.addEventListener("touchstart", start, { passive: false });
    canvas.addEventListener("touchmove", move, { passive: false });
    canvas.addEventListener("touchend", end);
    $("#btn-clear-sig").addEventListener("click", resizeCanvas);
    window.addEventListener("resize", resizeCanvas);
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

  function gatherPayload() {
    const data = {};
    if (role === "client") {
      data.client_name = ($("#client_name").value || "").trim();
      data.sign_off_comments = $("#sign_off_comments").value || "";
      data.client_signature = canvas.toDataURL("image/png");
    } else {
      data.technician_name = $("#technician_name").value || "";
      data.technician_signature = canvas.toDataURL("image/png");
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
    if (!hasInk) return "Please provide a signature.";
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
      statusMsg.style.color = "#6b7280";

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
