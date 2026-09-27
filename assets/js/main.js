/* Laundromat site interactions. No dependencies. */
(function () {
  "use strict";
  var SITE = window.SITE || {};
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ---------------- Desktop sub-menus (click/keyboard support) ---------------- */
  $$(".nav-item.has-sub").forEach(function (item) {
    var btn = $(".sub-toggle", item);
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = !item.classList.contains("is-open");
      closeMenus();
      item.classList.toggle("is-open", open);
      btn.setAttribute("aria-expanded", String(open));
    });
  });

  function closeMenus() {
    $$(".nav-item.is-open").forEach(function (el) {
      el.classList.remove("is-open");
      var b = $(".sub-toggle", el);
      if (b) b.setAttribute("aria-expanded", "false");
    });
  }
  document.addEventListener("click", closeMenus);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { closeMenus(); closeMobile(); }
  });

  /* ---------------- Mobile menu with drill-down panels ---------------- */
  var toggle = $(".menu-toggle");
  var mobile = $("#mobile-nav");

  function showPanel(id) {
    $$(".m-panel", mobile).forEach(function (p) { p.hidden = p.id !== id; });
    var target = document.getElementById(id);
    var first = target && $("button, a", target);
    if (first) first.focus();
  }
  function closeMobile() {
    if (!mobile || mobile.hidden) return;
    mobile.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Open menu");
  }
  if (toggle && mobile) {
    toggle.addEventListener("click", function () {
      var open = mobile.hidden;
      mobile.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      if (open) showPanel("m-panel-root");
    });
    $$(".m-forward", mobile).forEach(function (b) {
      b.addEventListener("click", function () { showPanel(b.getAttribute("data-panel")); });
    });
    $$(".m-back", mobile).forEach(function (b) {
      b.addEventListener("click", function () { showPanel("m-panel-root"); });
    });
    window.addEventListener("resize", function () { if (window.innerWidth > 980) closeMobile(); });
  }

  /* ---------------- Sliders (scroll-snap + arrow buttons) ---------------- */
  $$("[data-slider]").forEach(function (slider) {
    var track = $("[data-track]", slider);
    var prev = $("[data-prev]", slider);
    var next = $("[data-next]", slider);
    function step() {
      var slide = track.children[0];
      if (!slide) return track.clientWidth;
      var gap = parseFloat(getComputedStyle(track).columnGap || getComputedStyle(track).gap) || 0;
      return slide.getBoundingClientRect().width + gap;
    }
    function update() {
      var max = track.scrollWidth - track.clientWidth - 2;
      prev.disabled = track.scrollLeft <= 2;
      next.disabled = track.scrollLeft >= max;
      var hide = track.scrollWidth <= track.clientWidth + 2;
      prev.hidden = next.hidden = hide;
    }
    prev.addEventListener("click", function () { track.scrollBy({ left: -step(), behavior: "smooth" }); });
    next.addEventListener("click", function () { track.scrollBy({ left: step(), behavior: "smooth" }); });
    track.addEventListener("scroll", function () { window.requestAnimationFrame(update); }, { passive: true });
    track.addEventListener("keydown", function (e) {
      if (e.key === "ArrowRight") { e.preventDefault(); next.click(); }
      if (e.key === "ArrowLeft") { e.preventDefault(); prev.click(); }
    });
    window.addEventListener("resize", update);
    window.addEventListener("load", update);
    update();
  });

  /* ---------------- ZIP code check ---------------- */
  $$("[data-zip-form]").forEach(function (form) {
    var input = $("input", form);
    var msg = $(".zip-msg", form);
    input.addEventListener("input", function () {
      input.value = input.value.replace(/\D/g, "").slice(0, 5);
      msg.textContent = "";
      msg.className = "zip-msg";
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var zip = input.value.trim();
      msg.className = "zip-msg";
      if (!/^\d{5}$/.test(zip)) {
        msg.textContent = "Please enter a valid 5-digit ZIP code.";
        msg.classList.add("is-error");
        input.focus();
        return;
      }
      // SITE.zips maps each delivery ZIP to its area name ("" when no area is named).
      var zips = SITE.zips || {};
      var hasList = Object.keys(zips).length > 0;
      var served = Object.prototype.hasOwnProperty.call(zips, zip);
      if (hasList && !served) {
        msg.innerHTML = "We don't deliver to " + zip + " yet. <a href=\"/about-us/contact-us/\">Contact us</a> and we'll tell you when we expand.";
        msg.classList.add("is-error");
        return;
      }
      var where = served ? (zips[zip] ? zips[zip] + " (" + zip + ")" : zip) : "";
      if (!SITE.pickupUrl) {
        msg.textContent = served ? "We deliver to " + where + "! Call us to schedule a pickup."
                                 : "Call us to schedule a pickup.";
        msg.classList.add("is-ok");
        return;
      }
      msg.textContent = (served ? "We deliver to " + where + "!" : "") + " Taking you to schedule a pickup...";
      msg.classList.add("is-ok");
      var url = SITE.pickupUrl + (SITE.pickupUrl.indexOf("?") === -1 ? "?" : "&") + "zip=" + encodeURIComponent(zip);
      window.location.href = url;
    });
  });

  /* ---------------- Forms (contact / bid) ---------------- */
  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  $$("[data-form]").forEach(function (form) {
    var status = $(".form-status", form);
    var button = $("button[type=submit]", form);

    function setError(field, text) {
      var wrap = field.closest(".field");
      if (!wrap) return;
      wrap.classList.toggle("has-error", !!text);
      $(".field-error", wrap).textContent = text || "";
      field.setAttribute("aria-invalid", text ? "true" : "false");
    }
    function validate() {
      var firstBad = null;
      $$("input:not([type=hidden]):not([name=_gotcha]), textarea", form).forEach(function (f) {
        var v = f.value.trim();
        var err = "";
        if (f.required && !v) err = "This field is required.";
        else if (v && f.type === "email" && !EMAIL_RE.test(v)) err = "Please enter a valid email address.";
        else if (v && f.type === "tel" && v.replace(/\D/g, "").length < 10) err = "Please enter a valid phone number.";
        setError(f, err);
        if (err && !firstBad) firstBad = f;
      });
      if (firstBad) firstBad.focus();
      return !firstBad;
    }
    $$("input, textarea", form).forEach(function (f) {
      f.addEventListener("input", function () { if (f.closest(".has-error")) setError(f, ""); });
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      status.className = "form-status";
      status.textContent = "";
      if (!validate()) return;
      if (form.elements._gotcha && form.elements._gotcha.value) return; // bot

      var data = new FormData(form);
      if (window.grecaptcha && $(".g-recaptcha", form) && !data.get("g-recaptcha-response")) {
        status.textContent = "Please confirm you are not a robot.";
        status.classList.add("is-error");
        return;
      }

      if (!SITE.formEndpoint) {
        // No form service set up yet: fall back to the visitor's email app.
        if (!SITE.email) {
          status.textContent = "Online messages aren't available yet. Please call us instead.";
          status.classList.add("is-error");
          return;
        }
        var lines = [];
        data.forEach(function (v, k) { if (k.charAt(0) !== "_" && k !== "g-recaptcha-response" && v) lines.push(k.replace(/_/g, " ") + ": " + v); });
        window.location.href = "mailto:" + SITE.email + "?subject=" + encodeURIComponent(data.get("_subject") || "Website message") +
          "&body=" + encodeURIComponent(lines.join("\n"));
        status.textContent = "Opening your email app to send this message...";
        status.classList.add("is-ok");
        return;
      }

      button.disabled = true;
      var label = button.textContent;
      button.textContent = "Sending...";
      fetch(SITE.formEndpoint, { method: "POST", body: data, headers: { Accept: "application/json" } })
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          form.reset();
          if (window.grecaptcha) try { window.grecaptcha.reset(); } catch (x) {}
          status.textContent = "Thanks! Your message has been sent. We'll be in touch soon.";
          status.classList.add("is-ok");
        })
        .catch(function () {
          status.textContent = "Sorry, something went wrong sending your message. Please try again or give us a call.";
          status.classList.add("is-error");
        })
        .then(function () { button.disabled = false; button.textContent = label; });
    });
  });

  /* ---------------- Blog: category filter + load more ---------------- */
  $$("[data-blog]").forEach(function (blog) {
    var PAGE = 6;
    var shown = PAGE;
    var cards = $$(".blog-card", $("[data-results]", blog));
    var boxes = $$("[data-filter]", blog);
    var more = $("[data-more]", blog);
    var empty = $("[data-empty]", blog);
    var clear = $("[data-clear]", blog);

    function render() {
      var active = boxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
      var matches = cards.filter(function (c) { return !active.length || active.indexOf(c.getAttribute("data-cat")) !== -1; });
      cards.forEach(function (c) { c.hidden = true; });
      matches.slice(0, shown).forEach(function (c) { c.hidden = false; });
      more.hidden = matches.length <= shown;
      empty.hidden = matches.length > 0;
      clear.hidden = !active.length;
    }
    boxes.forEach(function (b) { b.addEventListener("change", function () { shown = PAGE; render(); }); });
    more.addEventListener("click", function () { shown += PAGE; render(); });
    clear.addEventListener("click", function () { boxes.forEach(function (b) { b.checked = false; }); shown = PAGE; render(); });
    render();
  });

  /* ---------------- Footer year ---------------- */
  $$("[data-year]").forEach(function (el) { el.textContent = new Date().getFullYear(); });

  /* ---------------- Live chat (tawk.to), only if configured ---------------- */
  if (SITE.tawkProperty && SITE.tawkWidget) {
    window.Tawk_API = window.Tawk_API || {};
    window.Tawk_LoadStart = new Date();
    var s = document.createElement("script");
    s.async = true;
    s.src = "https://embed.tawk.to/" + encodeURIComponent(SITE.tawkProperty) + "/" + encodeURIComponent(SITE.tawkWidget);
    s.charset = "UTF-8";
    s.setAttribute("crossorigin", "*");
    document.body.appendChild(s);
  }
})();
