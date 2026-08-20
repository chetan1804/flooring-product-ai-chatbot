(function () {
  "use strict";

  const script = document.currentScript;
  if (!script || script.dataset.flooringLoaded === "true") return;
  script.dataset.flooringLoaded = "true";

  const siteCode = script.dataset.site || "default";
  const requestedPosition = script.dataset.position;
  const targetSelector = script.dataset.target;
  const apiOrigin = new URL(script.src, window.location.href).origin;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function safeHttpUrl(value) {
    if (!value) return null;
    try {
      const candidate = /^[a-z][a-z0-9+.-]*:/i.test(value) ? value : `https://${value}`;
      const parsed = new URL(candidate);
      return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
    } catch (_error) {
      return null;
    }
  }

  function resolveTarget() {
    if (!targetSelector) return null;
    try {
      return document.querySelector(targetSelector);
    } catch (_error) {
      return null;
    }
  }

  const mount = resolveTarget() || element("div");
  if (!mount.parentNode) document.body.appendChild(mount);
  const shadow = mount.shadowRoot || (mount.attachShadow ? mount.attachShadow({ mode: "open" }) : mount);
  const style = element("style");
  style.textContent = `
    :host { all: initial; }
    .fc-root { font: 14px/1.45 system-ui, -apple-system, sans-serif; color: #17211b; }
    .fc-floating { position: fixed; bottom: 20px; z-index: 2147483000; }
    .fc-bottom-right { right: 20px; } .fc-bottom-left { left: 20px; }
    .fc-toggle { border: 0; border-radius: 999px; background: #176b45; color: white;
      padding: 13px 18px; cursor: pointer; box-shadow: 0 8px 28px #0003; font-weight: 700; }
    .fc-panel { width: min(380px, calc(100vw - 32px)); height: min(620px, calc(100vh - 100px));
      background: #fff; border: 1px solid #d8e1dc; border-radius: 16px; overflow: hidden;
      box-shadow: 0 16px 48px #0003; display: flex; flex-direction: column; }
    .fc-floating .fc-panel { margin-bottom: 10px; } .fc-hidden { display: none; }
    .fc-header { background: #176b45; color: white; padding: 10px 12px 10px 16px;
      font-weight: 700; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .fc-close { border: 0; background: transparent; color: white; width: 32px; height: 32px;
      border-radius: 8px; cursor: pointer; font: 24px/1 system-ui, sans-serif; }
    .fc-close:hover, .fc-close:focus-visible { background: #ffffff24; outline: 2px solid #ffffffaa; }
    .fc-messages { flex: 1; overflow-y: auto; padding: 14px; background: #f5f8f6; }
    .fc-message { max-width: 86%; margin: 0 0 10px; padding: 9px 11px; border-radius: 12px;
      white-space: pre-wrap; overflow-wrap: anywhere; }
    .fc-assistant { background: white; border: 1px solid #d8e1dc; }
    .fc-user { background: #176b45; color: white; margin-left: auto; }
    .fc-status { color: #617067; font-size: 12px; margin: 8px 0; }
    .fc-error { color: #a12622; }
    .fc-form { display: flex; gap: 8px; padding: 12px; border-top: 1px solid #d8e1dc; }
    .fc-input { min-width: 0; flex: 1; border: 1px solid #aebcb4; border-radius: 9px;
      padding: 10px; font: inherit; }
    .fc-send { border: 0; border-radius: 9px; background: #176b45; color: white;
      padding: 9px 13px; cursor: pointer; font-weight: 700; }
    .fc-send:disabled, .fc-input:disabled { opacity: .55; cursor: wait; }
    .fc-card { background: white; border: 1px solid #d8e1dc; border-radius: 12px;
      margin: 10px 0; overflow: hidden; }
    .fc-image { width: 100%; height: 130px; object-fit: cover; background: #e7ece9; }
    .fc-card-body { padding: 11px; } .fc-card-title { font-weight: 750; margin-bottom: 4px; }
    .fc-meta { color: #526158; font-size: 12px; margin-bottom: 6px; }
    .fc-reason { margin: 5px 0; }
    .fc-link { display: inline-block; margin-top: 7px; color: #176b45; font-weight: 700; }
    .fc-feedback { display: flex; align-items: center; gap: 7px; margin: 8px 0 12px; color: #526158;
      font-size: 12px; }
    .fc-feedback-button { border: 1px solid #aebcb4; border-radius: 999px; background: white;
      color: #17211b; padding: 5px 9px; cursor: pointer; font: inherit; }
    .fc-feedback-button:disabled { opacity: .55; cursor: default; }
  `;

  const root = element("div", "fc-root");
  const panel = element("section", "fc-panel");
  const header = element("div", "fc-header");
  const headerTitle = element("span", "fc-header-title", "Flooring Assistant");
  const close = element("button", "fc-close", "\u00d7");
  close.type = "button";
  close.setAttribute("aria-label", "Close chat");
  header.append(headerTitle, close);
  const messages = element("div", "fc-messages");
  const form = element("form", "fc-form");
  const input = element("input", "fc-input");
  input.type = "text";
  input.maxLength = 4000;
  input.placeholder = "Describe the flooring you need";
  input.setAttribute("aria-label", "Message");
  const send = element("button", "fc-send", "Send");
  send.type = "submit";
  form.append(input, send);
  panel.append(header, messages, form);
  root.append(panel);
  shadow.append(style, root);

  let toggle = null;
  if (!targetSelector) {
    const position = requestedPosition === "bottom-left" ? "bottom-left" : "bottom-right";
    root.classList.add("fc-floating", `fc-${position}`);
    panel.classList.add("fc-hidden");
    toggle = element("button", "fc-toggle", "Chat with us");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    toggle.addEventListener("click", function () {
      const opening = panel.classList.contains("fc-hidden");
      panel.classList.toggle("fc-hidden");
      toggle.setAttribute("aria-expanded", String(opening));
      if (opening) input.focus();
    });
    root.append(toggle);
  } else {
    toggle = element("button", "fc-toggle fc-hidden", "Open chat");
    toggle.type = "button";
    toggle.addEventListener("click", function () {
      panel.classList.remove("fc-hidden");
      toggle.classList.add("fc-hidden");
      input.focus();
    });
    root.append(toggle);
  }

  close.addEventListener("click", function () {
    panel.classList.add("fc-hidden");
    if (targetSelector) toggle.classList.remove("fc-hidden");
    else toggle.setAttribute("aria-expanded", "false");
    toggle.focus();
  });

  function addMessage(role, text) {
    const node = element("div", `fc-message fc-${role}`, text);
    messages.appendChild(node);
    messages.scrollTop = messages.scrollHeight;
  }

  function addStatus(text, isError) {
    const node = element("div", `fc-status${isError ? " fc-error" : ""}`, text);
    messages.appendChild(node);
    messages.scrollTop = messages.scrollHeight;
    return node;
  }

  function renderCard(card, interactionId) {
    const wrapper = element("article", "fc-card");
    const imageUrl = safeHttpUrl(card.image || card.swatch);
    if (imageUrl) {
      const image = element("img", "fc-image");
      image.src = imageUrl;
      image.alt = card.name;
      image.loading = "lazy";
      wrapper.appendChild(image);
    }
    const body = element("div", "fc-card-body");
    body.appendChild(element("div", "fc-card-title", card.name));
    const price = card.price == null ? "Price unavailable" : `$${card.price}`;
    body.appendChild(element("div", "fc-meta", `SKU: ${card.sku} · ${price}`));
    (card.reasons || []).slice(0, 3).forEach(function (reason) {
      body.appendChild(element("div", "fc-reason", reason));
    });
    const productUrl = safeHttpUrl(card.product_url);
    if (productUrl) {
      const link = element("a", "fc-link", "View product");
      link.href = productUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.addEventListener("click", function () {
        trackEvent("product_clicked", { interaction_id: interactionId, sku: card.sku });
      });
      body.appendChild(link);
    }
    wrapper.appendChild(body);
    messages.appendChild(wrapper);
  }

  async function request(path, options) {
    const response = await fetch(`${apiOrigin}${path}`, options);
    const payload = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(payload.detail || "Request failed. Please try again.");
    return payload;
  }

  let sessionId = null;
  function trackEvent(eventType, details) {
    if (!sessionId) return;
    request("/api/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ session_id: sessionId, event_type: eventType }, details))
    }).catch(function () { /* Analytics must never interrupt the customer experience. */ });
  }

  function renderFeedback(interactionId) {
    const wrapper = element("div", "fc-feedback");
    wrapper.appendChild(element("span", "", "Was this helpful?"));
    const options = [
      ["helpful", "Yes"],
      ["not_helpful", "No"]
    ];
    options.forEach(function (option) {
      const button = element("button", "fc-feedback-button", option[1]);
      button.type = "button";
      button.addEventListener("click", async function () {
        wrapper.querySelectorAll("button").forEach(function (item) { item.disabled = true; });
        try {
          await request("/api/feedback", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              session_id: sessionId,
              interaction_id: interactionId,
              rating: option[0]
            })
          });
          wrapper.textContent = "Thanks for your feedback.";
        } catch (_error) {
          wrapper.textContent = "Feedback could not be saved.";
          wrapper.classList.add("fc-error");
        }
      });
      wrapper.appendChild(button);
    });
    messages.appendChild(wrapper);
  }

  async function initialize() {
    input.disabled = true;
    send.disabled = true;
    const loading = addStatus("Connecting…", false);
    try {
      const config = await request(`/api/config/${encodeURIComponent(siteCode)}`);
      headerTitle.textContent = config.chatbot_title;
      if (!requestedPosition && config.position && root.classList.contains("fc-floating")) {
        root.classList.remove("fc-bottom-left", "fc-bottom-right");
        root.classList.add(`fc-${config.position}`);
      }
      const session = await request("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ site_code: siteCode })
      });
      sessionId = session.session_id;
      trackEvent("widget_opened", {});
      loading.remove();
      addMessage("assistant", "Tell me about the room and the flooring look you prefer.");
      input.disabled = false;
      send.disabled = false;
    } catch (error) {
      loading.textContent = error.message || "Unable to connect to the flooring assistant.";
      loading.classList.add("fc-error");
    }
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    const message = input.value.trim();
    if (!message || !sessionId) return;
    addMessage("user", message);
    input.value = "";
    input.disabled = true;
    send.disabled = true;
    const loading = addStatus("Finding the best match…", false);
    try {
      const response = await request("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: message })
      });
      loading.remove();
      addMessage("assistant", response.message);
      (response.recommendations || []).forEach(function (card) {
        renderCard(card, response.interaction_id);
      });
      renderFeedback(response.interaction_id);
    } catch (error) {
      loading.textContent = error.message || "Something went wrong. Please try again.";
      loading.classList.add("fc-error");
    } finally {
      input.disabled = false;
      send.disabled = false;
      input.focus();
    }
  });

  initialize();
})();
