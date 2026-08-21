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
    .fc-root { --fc-primary: #176b45; --fc-primary-text: #fff; --fc-background: #fff;
      --fc-body-text: #17211b; --fc-muted-background: #f5f8f6;
      font: 14px/1.45 system-ui, -apple-system, sans-serif; color: var(--fc-body-text); }
    .fc-floating { position: fixed; bottom: 20px; z-index: 2147483000; }
    .fc-bottom-right { right: 20px; } .fc-bottom-left { left: 20px; }
    .fc-toggle { border: 0; border-radius: 999px; background: var(--fc-primary);
      color: var(--fc-primary-text);
      padding: 13px 18px; cursor: pointer; box-shadow: 0 8px 28px #0003; font-weight: 700; }
    .fc-panel { width: min(380px, calc(100vw - 32px)); height: min(620px, calc(100vh - 100px));
      background: var(--fc-background); border: 1px solid #d8e1dc; border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 16px 48px #0003; display: flex; flex-direction: column; }
    .fc-floating .fc-panel { margin-bottom: 10px; } .fc-hidden { display: none; }
    .fc-header { background: var(--fc-primary); color: var(--fc-primary-text);
      padding: 10px 12px 10px 16px;
      font-weight: 700; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .fc-header-brand { min-width: 0; display: flex; align-items: center; gap: 9px; }
    .fc-header-logo { width: 28px; height: 28px; border-radius: 6px; object-fit: contain;
      background: var(--fc-background); }
    .fc-header-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .fc-header-actions { display: flex; align-items: center; gap: 3px; }
    .fc-header-button, .fc-close { border: 0; background: transparent; color: var(--fc-primary-text);
      min-height: 32px; border-radius: 8px; cursor: pointer; font: inherit; }
    .fc-header-button { padding: 5px 8px; font-size: 12px; font-weight: 700; }
    .fc-close { width: 32px; height: 32px;
      border-radius: 8px; cursor: pointer; font: 24px/1 system-ui, sans-serif; }
    .fc-header-button:hover, .fc-header-button:focus-visible,
    .fc-close:hover, .fc-close:focus-visible { background: #ffffff24; outline: 2px solid #ffffffaa; }
    .fc-messages { flex: 1; overflow-y: auto; padding: 14px;
      background: var(--fc-muted-background); }
    .fc-message { max-width: 86%; margin: 0 0 10px; padding: 9px 11px; border-radius: 12px;
      white-space: pre-wrap; overflow-wrap: anywhere; }
    .fc-assistant { background: white; border: 1px solid #d8e1dc; }
    .fc-user { background: var(--fc-primary); color: var(--fc-primary-text); margin-left: auto; }
    .fc-status { color: #617067; font-size: 12px; margin: 8px 0; }
    .fc-error { color: #a12622; }
    .fc-form { display: flex; gap: 8px; padding: 12px; border-top: 1px solid #d8e1dc; }
    .fc-input { min-width: 0; flex: 1; border: 1px solid #aebcb4; border-radius: 9px;
      padding: 10px; font: inherit; }
    .fc-send { border: 0; border-radius: 9px; background: var(--fc-primary);
      color: var(--fc-primary-text);
      padding: 9px 13px; cursor: pointer; font-weight: 700; }
    .fc-send:disabled, .fc-input:disabled { opacity: .55; cursor: wait; }
    .fc-card { background: white; border: 1px solid #d8e1dc; border-radius: 12px;
      margin: 10px 0; overflow: hidden; }
    .fc-image { width: 100%; height: 130px; object-fit: cover; background: #e7ece9; }
    .fc-card-body { padding: 11px; } .fc-card-title { font-weight: 750; margin-bottom: 4px; }
    .fc-meta { color: #526158; font-size: 12px; margin-bottom: 6px; }
    .fc-reason { margin: 5px 0; }
    .fc-link { display: inline-block; margin-top: 7px; color: var(--fc-primary); font-weight: 700; }
    .fc-card-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .fc-estimate { border: 1px solid var(--fc-primary); border-radius: 8px;
      background: var(--fc-background); color: var(--fc-primary); padding: 6px 8px;
      cursor: pointer; font: inherit; font-weight: 700; margin-top: 7px; }
    .fc-feedback { display: flex; align-items: center; gap: 7px; margin: 8px 0 12px; color: #526158;
      font-size: 12px; }
    .fc-feedback-button { border: 1px solid #aebcb4; border-radius: 999px; background: white;
      color: #17211b; padding: 5px 9px; cursor: pointer; font: inherit; }
    .fc-feedback-button:disabled { opacity: .55; cursor: default; }
    .fc-calculator { flex: 1; overflow-y: auto; padding: 16px; background: var(--fc-muted-background); }
    .fc-calculator h2 { font-size: 18px; margin: 0 0 4px; }
    .fc-calculator-intro { color: #526158; margin: 0 0 14px; }
    .fc-calculator-product { background: var(--fc-background); border: 1px solid #d8e1dc;
      border-radius: 9px; padding: 9px 10px; margin-bottom: 12px; }
    .fc-calculator-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .fc-field { display: grid; gap: 4px; font-size: 12px; font-weight: 650; }
    .fc-field input, .fc-field select { min-width: 0; border: 1px solid #aebcb4;
      border-radius: 8px; padding: 9px; background: var(--fc-background); color: var(--fc-body-text);
      font: inherit; }
    .fc-field-wide { grid-column: 1 / -1; }
    .fc-calculate { grid-column: 1 / -1; border: 0; border-radius: 9px;
      background: var(--fc-primary); color: var(--fc-primary-text); padding: 10px;
      cursor: pointer; font: inherit; font-weight: 700; }
    .fc-calculator-result { margin-top: 14px; background: var(--fc-background);
      border: 1px solid #d8e1dc; border-radius: 10px; padding: 12px; }
    .fc-result-line { display: flex; justify-content: space-between; gap: 12px; margin: 4px 0; }
    .fc-result-line strong { text-align: right; }
    .fc-disclaimer { color: #617067; font-size: 11px; margin: 10px 0 0; }
  `;

  const root = element("div", "fc-root");
  const panel = element("section", "fc-panel");
  const header = element("div", "fc-header");
  const headerBrand = element("div", "fc-header-brand");
  const headerLogo = element("img", "fc-header-logo fc-hidden");
  headerLogo.alt = "";
  const headerTitle = element("span", "fc-header-title", "Flooring Assistant");
  headerBrand.append(headerLogo, headerTitle);
  const headerActions = element("div", "fc-header-actions");
  const calculatorToggle = element("button", "fc-header-button fc-hidden", "Calculator");
  calculatorToggle.type = "button";
  calculatorToggle.setAttribute("aria-expanded", "false");
  const close = element("button", "fc-close", "\u00d7");
  close.type = "button";
  close.setAttribute("aria-label", "Close chat");
  headerActions.append(calculatorToggle, close);
  header.append(headerBrand, headerActions);
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

  const calculator = element("section", "fc-calculator fc-hidden");
  calculator.setAttribute("aria-label", "Flooring calculator");
  calculator.appendChild(element("h2", "", "Flooring calculator"));
  calculator.appendChild(
    element("p", "fc-calculator-intro", "Estimate material, cartons, and product cost.")
  );
  const calculatorProduct = element("div", "fc-calculator-product", "No product selected");
  const calculatorForm = element("form", "fc-calculator-form");

  function numberField(labelText, name, value) {
    const label = element("label", "fc-field");
    label.appendChild(element("span", "", labelText));
    const field = element("input");
    field.type = "number";
    field.name = name;
    field.min = "0.1";
    field.step = "0.1";
    field.required = true;
    if (value !== undefined) field.value = String(value);
    label.appendChild(field);
    return { label: label, input: field };
  }

  const lengthField = numberField("Room length (ft)", "length");
  const widthField = numberField("Room width (ft)", "width");
  const wasteField = numberField("Waste allowance (%)", "waste", 10);
  wasteField.input.min = "0";
  wasteField.input.max = "30";
  const calculate = element("button", "fc-calculate", "Calculate material");
  calculate.type = "submit";
  const calculatorResult = element("div", "fc-calculator-result fc-hidden");
  calculatorResult.setAttribute("aria-live", "polite");
  calculatorForm.append(lengthField.label, widthField.label, wasteField.label, calculate);
  calculator.append(calculatorProduct, calculatorForm, calculatorResult);

  panel.append(header, calculator, messages, form);
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

  let calculatorSettings = {
    enabled: true,
    default_waste_percent: 10,
    max_room_dimension_feet: 500,
    show_price_estimate: true
  };
  let selectedCalculatorProduct = null;

  function setCalculatorOpen(opening) {
    if (!calculatorSettings.enabled) return;
    calculator.classList.toggle("fc-hidden", !opening);
    messages.classList.toggle("fc-hidden", opening);
    form.classList.toggle("fc-hidden", opening);
    calculatorToggle.setAttribute("aria-expanded", String(opening));
    calculatorToggle.textContent = opening ? "Back to chat" : "Calculator";
    if (opening) lengthField.input.focus();
    else input.focus();
  }

  function selectCalculatorProduct(card) {
    selectedCalculatorProduct = card || null;
    calculatorResult.classList.add("fc-hidden");
    calculatorResult.replaceChildren();
    if (!card) {
      calculatorProduct.textContent = "No product selected — showing material area only.";
      return;
    }
    const details = [card.name, `SKU ${card.sku}`];
    if (card.price != null) details.push(`$${card.price}${card.price_unit ? `/${card.price_unit}` : ""}`);
    if (card.carton_sq_ft != null) details.push(`${card.carton_sq_ft} sq ft/carton`);
    calculatorProduct.textContent = details.join(" · ");
  }

  calculatorToggle.addEventListener("click", function () {
    const opening = calculator.classList.contains("fc-hidden");
    if (opening && selectedCalculatorProduct === null) selectCalculatorProduct(null);
    setCalculatorOpen(opening);
  });

  function resultLine(label, value) {
    const line = element("div", "fc-result-line");
    line.append(element("span", "", label), element("strong", "", value));
    return line;
  }

  calculatorForm.addEventListener("submit", function (event) {
    event.preventDefault();
    const length = Number(lengthField.input.value);
    const width = Number(widthField.input.value);
    const waste = Number(wasteField.input.value);
    const maximum = Number(calculatorSettings.max_room_dimension_feet);
    if (
      !Number.isFinite(length) || !Number.isFinite(width) || !Number.isFinite(waste) ||
      length <= 0 || width <= 0 || length > maximum || width > maximum || waste < 0 || waste > 30
    ) {
      calculatorResult.replaceChildren(
        element("div", "fc-error", `Enter dimensions up to ${maximum} ft and waste from 0–30%.`)
      );
      calculatorResult.classList.remove("fc-hidden");
      return;
    }

    const roomArea = length * width;
    const materialArea = roomArea * (1 + waste / 100);
    const cartonCoverage = Number(selectedCalculatorProduct && selectedCalculatorProduct.carton_sq_ft);
    const cartons = Number.isFinite(cartonCoverage) && cartonCoverage > 0
      ? Math.ceil(materialArea / cartonCoverage)
      : null;
    const purchaseArea = cartons === null ? materialArea : cartons * cartonCoverage;
    const unitPrice = Number(selectedCalculatorProduct && selectedCalculatorProduct.price);
    const canEstimatePrice = calculatorSettings.show_price_estimate &&
      Number.isFinite(unitPrice) && unitPrice > 0;

    calculatorResult.replaceChildren(
      resultLine("Room area", `${roomArea.toFixed(2)} sq ft`),
      resultLine(`Material with ${waste}% waste`, `${materialArea.toFixed(2)} sq ft`)
    );
    if (cartons !== null) {
      calculatorResult.appendChild(resultLine("Cartons required", String(cartons)));
      calculatorResult.appendChild(
        resultLine("Purchase coverage", `${purchaseArea.toFixed(2)} sq ft`)
      );
    }
    if (canEstimatePrice) {
      calculatorResult.appendChild(
        resultLine("Estimated material cost", `$${(purchaseArea * unitPrice).toFixed(2)}`)
      );
    }
    calculatorResult.appendChild(
      element(
        "p",
        "fc-disclaimer",
        "Estimate only. Confirm measurements, waste, carton coverage, taxes, and installation with the retailer."
      )
    );
    calculatorResult.classList.remove("fc-hidden");
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
    const price = card.price == null
      ? "Price unavailable"
      : `$${card.price}${card.price_unit ? `/${card.price_unit}` : ""}`;
    body.appendChild(element("div", "fc-meta", `SKU: ${card.sku} · ${price}`));
    (card.reasons || []).slice(0, 3).forEach(function (reason) {
      body.appendChild(element("div", "fc-reason", reason));
    });
    const actions = element("div", "fc-card-actions");
    const productUrl = safeHttpUrl(card.product_url);
    if (productUrl) {
      const link = element("a", "fc-link", "View product");
      link.href = productUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.addEventListener("click", function () {
        trackEvent("product_clicked", { interaction_id: interactionId, sku: card.sku });
      });
      actions.appendChild(link);
    }
    if (calculatorSettings.enabled) {
      const estimate = element("button", "fc-estimate", "Estimate project");
      estimate.type = "button";
      estimate.addEventListener("click", function () {
        selectCalculatorProduct(card);
        setCalculatorOpen(true);
      });
      actions.appendChild(estimate);
    }
    body.appendChild(actions);
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
      const theme = config.theme || {};
      root.style.setProperty("--fc-primary", theme.primary_color || "#176b45");
      root.style.setProperty("--fc-primary-text", theme.primary_text_color || "#ffffff");
      root.style.setProperty("--fc-background", theme.background_color || "#ffffff");
      root.style.setProperty("--fc-body-text", theme.body_text_color || "#17211b");
      root.style.setProperty("--fc-muted-background", theme.muted_background_color || "#f5f8f6");
      if (!targetSelector) toggle.textContent = theme.launcher_text || "Chat with us";
      const logoUrl = safeHttpUrl(theme.logo_url);
      if (logoUrl) {
        headerLogo.src = logoUrl;
        headerLogo.addEventListener("error", function () {
          headerLogo.classList.add("fc-hidden");
        }, { once: true });
        headerLogo.classList.remove("fc-hidden");
      }
      calculatorSettings = Object.assign(calculatorSettings, config.calculator || {});
      wasteField.input.value = String(calculatorSettings.default_waste_percent);
      lengthField.input.max = String(calculatorSettings.max_room_dimension_feet);
      widthField.input.max = String(calculatorSettings.max_room_dimension_feet);
      calculatorToggle.classList.toggle("fc-hidden", !calculatorSettings.enabled);
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
      addMessage(
        "assistant",
        theme.welcome_message || "Tell me about the room and the flooring look you prefer."
      );
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
