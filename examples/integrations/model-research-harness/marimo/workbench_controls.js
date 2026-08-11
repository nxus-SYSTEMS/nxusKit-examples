const MODE_GUIDANCE_ITEMS = [
  "Fixture — deterministic synthetic evidence; it does not call a provider.",
  "Auto — may attempt a compatible enabled live provider, then falls back only where supported.",
  "Live — runs the selected enabled provider and model.",
];

const PROVIDER_LABELS = {
  claude: "Claude",
  openai: "OpenAI",
  groq: "Groq",
  xai: "xAI",
  ollama: "Ollama",
  lmstudio: "LM Studio",
};

const CATEGORY_LABELS = {
  "safe-built-in": "Built-in",
  "engine-backed": "Reasoning engine",
  "external-adapter": "External adapter",
  promptfoo: "Promptfoo import",
  "lifecycle-sensitive": "Lifecycle-sensitive",
};

function splitFilters(value) {
  return String(value || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

export function buildSubmittedRequest(state) {
  const providerBacked = state.mode === "auto" || state.mode === "live";
  return {
    config_id: state.configId,
    mode: state.mode,
    provider: providerBacked ? state.provider || null : null,
    model: providerBacked ? state.model || null : null,
    include_tests: splitFilters(state.includeTests),
    exclude_tests: splitFilters(state.excludeTests),
    allow_external: state.allowExternal === true,
    write_reports: state.writeReports === true,
  };
}

export function runActionAvailability({
  configEnabled,
  configNeedsTrust = false,
  allowExternal = false,
  mode,
  provider,
  model,
  runActive,
}) {
  if (runActive) return { enabled: false, reason: "active_run" };
  if (!configEnabled) return { enabled: false, reason: "config_unavailable" };
  if (configNeedsTrust && !allowExternal) {
    return { enabled: false, reason: "external_trust_required" };
  }
  if (mode === "live" && (!provider || !model)) {
    return { enabled: false, reason: "live_selection_incomplete" };
  }
  if (mode === "auto" && provider && !model) {
    return { enabled: false, reason: "provider_model_incomplete" };
  }
  return { enabled: true, reason: null };
}

export function contextualControlState(category) {
  return {
    allowExternal: {
      disabled: category !== "external-adapter",
      help: "Allows this configuration's declared external-command adapter only after Run Evaluation.",
    },
    writeReports: {
      disabled: false,
      help: "Writes bounded local JSON and Markdown files after Run Evaluation.",
    },
  };
}

export function engineUsageState(engine, configuredEngines) {
  if (engine.enabled !== true) {
    return { code: "unavailable", label: "Unavailable" };
  }
  if (configuredEngines.includes(engine.id)) {
    return { code: "used", label: "Used by This Configuration" };
  }
  return { code: "available_not_used", label: "Available, Not Used" };
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function section(title) {
  const card = element("section", "workbench-section");
  card.appendChild(element("h3", "section-title", title));
  return card;
}

function labelledSelect(label, value, options, onChange) {
  const field = element("label", "control-field");
  field.appendChild(element("span", "control-label", label));
  const select = element("select", "control-select");
  for (const optionRow of options) {
    const option = element("option", "", optionRow.label);
    option.value = optionRow.id;
    option.selected = optionRow.id === value;
    option.disabled = optionRow.enabled === false;
    option.title = optionRow.reason || optionRow.message || "";
    select.appendChild(option);
  }
  select.addEventListener("change", () => onChange(select.value));
  field.appendChild(select);
  return field;
}

function jsonRow(key, control) {
  const row = element("div", "json-row");
  row.appendChild(element("code", "json-key", `"${key}":`));
  row.appendChild(control);
  return row;
}

function detailItem(label, value) {
  const item = element("div", "model-detail-item");
  item.appendChild(element("span", "detail-label", label));
  item.appendChild(element("span", "detail-value", value || "not reported"));
  return item;
}

function helpLabel(label, help, id) {
  const row = element("span", "checkbox-label-with-help");
  row.appendChild(element("span", "", label));
  const info = element("span", "inline-info", "ⓘ");
  info.setAttribute("aria-hidden", "true");
  info.title = help;
  row.appendChild(info);
  const description = element("span", "visually-hidden", help);
  description.id = id;
  row.appendChild(description);
  return row;
}

function render({ model, el }) {
  const uiState = { search: "" };
  let pollTimer = null;
  let activeRun = null;
  const watched = [
    "configs",
    "selected_config",
    "modes",
    "selected_mode",
    "providers",
    "selected_provider",
    "models",
    "selected_model",
    "model_state",
    "model_message",
    "discovery_loading",
    "engines",
    "include_tests",
    "exclude_tests",
    "allow_external",
    "write_reports",
    "poll_generation",
    "completed_generation",
    "completion_state",
  ];

  function save(name, value) {
    model.set(name, value);
    model.save_changes();
  }

  function schedulePoll() {
    if (pollTimer !== null) window.clearTimeout(pollTimer);
    const loading =
      model.get("discovery_loading") === true ||
      model.get("model_state") === "loading";
    if (loading) {
      pollTimer = window.setTimeout(() => {
        save("poll_generation", model.get("poll_generation") + 1);
      }, 250);
    }
  }

  function reconcileRun() {
    if (!activeRun) return;
    if (model.get("completed_generation") >= activeRun.generation) {
      activeRun = null;
    }
  }

  function renderAll() {
    reconcileRun();
    el.replaceChildren();
    const root = element("div", "workbench-controls");
    root.appendChild(
      element("h2", "workbench-heading", "Configure the Workbench ..."),
    );

    const configMode = section("Configuration and Mode");
    const configGrid = element("div", "control-grid config-mode-grid");
    configGrid.appendChild(
      labelledSelect(
        "Built-in Configuration",
        model.get("selected_config"),
        (model.get("configs") || []).map((config) => ({
          ...config,
          label: config.label || config.id,
        })),
        (value) => {
          const next = (model.get("configs") || []).find(
            (config) => config.id === value,
          );
          model.set("selected_config", value);
          if (next?.category !== "external-adapter") {
            model.set("allow_external", false);
          }
          model.save_changes();
        },
      ),
    );
    const modeField = element("div", "control-field");
    const modeLabel = element("div", "label-with-info");
    modeLabel.appendChild(element("span", "control-label", "Mode"));
    const info = element("button", "info-button", "ⓘ");
    info.type = "button";
    info.setAttribute("aria-label", "Mode guidance");
    const tooltip = element("div", "mode-tooltip");
    tooltip.id = "workbench-mode-guidance";
    tooltip.hidden = true;
    tooltip.setAttribute("role", "tooltip");
    tooltip.appendChild(element("strong", "", "Mode guidance"));
    const list = element("ul", "mode-tooltip-list");
    for (const guidance of MODE_GUIDANCE_ITEMS) {
      list.appendChild(element("li", "", guidance));
    }
    tooltip.appendChild(list);
    info.setAttribute("aria-describedby", tooltip.id);
    const show = () => {
      tooltip.hidden = false;
      info.setAttribute("aria-expanded", "true");
    };
    const hide = () => {
      tooltip.hidden = true;
      info.setAttribute("aria-expanded", "false");
    };
    info.addEventListener("mouseenter", show);
    info.addEventListener("mouseleave", () => {
      if (document.activeElement !== info) hide();
    });
    info.addEventListener("focus", show);
    info.addEventListener("blur", hide);
    info.addEventListener("click", show);
    info.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        hide();
        info.blur();
      }
    });
    modeLabel.appendChild(info);
    modeLabel.appendChild(tooltip);
    modeField.appendChild(modeLabel);
    const modeSelect = labelledSelect(
      "",
      model.get("selected_mode"),
      model.get("modes") || [],
      (value) => save("selected_mode", value),
    );
    const modeControl = modeSelect.querySelector("select");
    modeControl.setAttribute("aria-label", "Mode");
    modeField.appendChild(modeControl);
    configGrid.appendChild(modeField);
    configMode.appendChild(configGrid);
    const selectedConfig = (model.get("configs") || []).find(
      (config) => config.id === model.get("selected_config"),
    );
    if (selectedConfig) {
      configMode.appendChild(
        element("p", "config-description", selectedConfig.description),
      );
      const testCount = Number(selectedConfig.test_count || 0);
      configMode.appendChild(
        element(
          "p",
          "config-meta",
          `${CATEGORY_LABELS[selectedConfig.category] || selectedConfig.category} · ${testCount} ${testCount === 1 ? "test" : "tests"}`,
        ),
      );
      configMode.appendChild(
        element(
          "p",
          `config-note ${selectedConfig.enabled ? "available" : "unavailable"}`,
          selectedConfig.reason,
        ),
      );
    }
    root.appendChild(configMode);

    const providerModel = section("Provider and Model");
    const providerGrid = element("div", "provider-grid");
    for (const provider of model.get("providers") || []) {
      const button = element(
        "button",
        "provider-button",
        PROVIDER_LABELS[provider.id] || provider.id,
      );
      button.type = "button";
      button.disabled = provider.enabled !== true;
      button.title = provider.reason || "Provider unavailable.";
      button.classList.toggle("unavailable", provider.enabled !== true);
      button.classList.toggle(
        "selected",
        provider.id === model.get("selected_provider"),
      );
      button.addEventListener("click", () => save("selected_provider", provider.id));
      providerGrid.appendChild(button);
    }
    providerModel.appendChild(providerGrid);
    const modelToolbar = element("div", "model-toolbar");
    const selectedProvider = (model.get("providers") || []).find(
      (provider) => provider.id === model.get("selected_provider"),
    );
    const providerEnabled = selectedProvider?.enabled === true;
    const search = element("input", "model-search");
    search.type = "search";
    search.placeholder = "Filter models";
    search.value = uiState.search;
    search.disabled = !providerEnabled;
    search.setAttribute("aria-label", "Filter models");
    search.addEventListener("input", () => {
      uiState.search = search.value;
      renderAll();
    });
    modelToolbar.appendChild(search);
    const modelSelect = element("select", "model-select");
    modelSelect.setAttribute("aria-label", "Model");
    const prompt = element("option", "", "Select a model");
    prompt.value = "";
    prompt.selected = !model.get("selected_model");
    modelSelect.appendChild(prompt);
    const query = uiState.search.trim().toLowerCase();
    for (const available of model.get("models") || []) {
      if (
        query &&
        !`${available.name} ${available.id}`.toLowerCase().includes(query)
      ) {
        continue;
      }
      const option = element("option", "", available.name || available.id);
      option.value = available.id;
      option.selected = available.id === model.get("selected_model");
      modelSelect.appendChild(option);
    }
    modelSelect.disabled = !providerEnabled || model.get("model_state") === "loading";
    modelSelect.addEventListener("change", () =>
      save("selected_model", modelSelect.value || null),
    );
    modelToolbar.appendChild(modelSelect);
    const refresh = element("button", "refresh-button", "Refresh models");
    refresh.type = "button";
    refresh.disabled = !providerEnabled;
    refresh.addEventListener("click", () =>
      save("refresh_generation", model.get("refresh_generation") + 1),
    );
    modelToolbar.appendChild(refresh);
    providerModel.appendChild(modelToolbar);
    providerModel.appendChild(
      element(
        "p",
        `model-status ${model.get("model_state")}`,
        model.get("model_message"),
      ),
    );
    const selectedModel = (model.get("models") || []).find(
      (item) => item.id === model.get("selected_model"),
    );
    if (selectedModel) {
      const details = element("div", "model-details");
      details.appendChild(detailItem("Description", selectedModel.description));
      details.appendChild(
        detailItem(
          "Capabilities",
          selectedModel.supports?.length ? selectedModel.supports.join(", ") : null,
        ),
      );
      details.appendChild(
        detailItem(
          "Context window",
          selectedModel.context_window
            ? `${selectedModel.context_window} tokens`
            : null,
        ),
      );
      details.appendChild(detailItem("Local", selectedModel.local ? "yes" : "no"));
      providerModel.appendChild(details);
    }
    root.appendChild(providerModel);

    const evaluation = section("Evaluation Configuration");
    const jsonPanel = element("div", "json-panel");
    jsonPanel.appendChild(element("code", "json-brace", "{"));
    const include = element("input", "json-input");
    include.value = model.get("include_tests");
    include.placeholder = "test-id, another-test";
    include.addEventListener("input", () => save("include_tests", include.value));
    jsonPanel.appendChild(jsonRow("include_tests", include));
    const exclude = element("input", "json-input");
    exclude.value = model.get("exclude_tests");
    exclude.placeholder = "slow-test";
    exclude.addEventListener("input", () => save("exclude_tests", exclude.value));
    jsonPanel.appendChild(jsonRow("exclude_tests", exclude));
    jsonPanel.appendChild(
      element(
        "p",
        "filter-guidance",
        "Blank runs all configured tests. Use comma-separated test IDs to include or exclude a subset.",
      ),
    );
    const controlState = contextualControlState(selectedConfig?.category);
    for (const [key, label, state, helpId] of [
      [
        "allow_external",
        "Allow External Adapter",
        controlState.allowExternal,
        "allow-external-help",
      ],
      [
        "write_reports",
        "Write Local Report Files",
        controlState.writeReports,
        "write-reports-help",
      ],
    ]) {
      const wrapper = element("label", "json-checkbox");
      const checkbox = element("input");
      checkbox.type = "checkbox";
      checkbox.checked = state.disabled ? false : model.get(key) === true;
      checkbox.disabled = state.disabled;
      checkbox.setAttribute("aria-describedby", helpId);
      wrapper.classList.toggle("disabled", state.disabled);
      checkbox.addEventListener("change", () => save(key, checkbox.checked));
      wrapper.appendChild(checkbox);
      wrapper.appendChild(helpLabel(label, state.help, helpId));
      jsonPanel.appendChild(jsonRow(key, wrapper));
    }
    jsonPanel.appendChild(element("code", "json-brace", "}"));
    evaluation.appendChild(jsonPanel);
    root.appendChild(evaluation);

    const capabilities = section("Evaluation Engine Usage");
    capabilities.appendChild(
      element(
        "p",
        "capability-legend",
        "Muted capabilities are unavailable. Execution still occurs only after Run Evaluation.",
      ),
    );
    const engineGrid = element("div", "engine-grid");
    for (const engine of model.get("engines") || []) {
      const item = element("div", "engine-option");
      const usage = engineUsageState(
        engine,
        selectedConfig?.configured_engines || [],
      );
      item.classList.add(usage.code.replaceAll("_", "-"));
      item.title = engine.reason || "";
      item.setAttribute("role", "group");
      item.setAttribute(
        "aria-label",
        `${engine.id}: ${usage.label}. ${engine.reason || "No availability detail."}`,
      );
      item.appendChild(
        element(
          "span",
          "engine-label",
          `${engine.id.toUpperCase()}${engine.tier === "pro" ? " · Pro" : ""}`,
        ),
      );
      item.appendChild(
        element("span", "engine-status", usage.label),
      );
      engineGrid.appendChild(item);
    }
    capabilities.appendChild(engineGrid);
    const actionRow = element("div", "action-row");
    const status = element("div", "run-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.textContent = activeRun
      ? "Evaluation is running through nxusKit…"
      : "Evaluation starts only after you press Run Evaluation.";
    actionRow.appendChild(status);
    const run = element("button", "run-button", "Run Evaluation");
    run.type = "button";
    const availability = runActionAvailability({
      configEnabled: selectedConfig?.enabled === true,
      configNeedsTrust: selectedConfig?.category === "external-adapter",
      allowExternal: model.get("allow_external"),
      mode: model.get("selected_mode"),
      provider: model.get("selected_provider"),
      model: model.get("selected_model"),
      runActive: activeRun !== null,
    });
    run.disabled = !availability.enabled;
    const reasons = {
      config_unavailable: selectedConfig?.reason,
      external_trust_required: "Acknowledge the external-adapter trust gate first.",
      live_selection_incomplete: "Live requires an available provider and model.",
      provider_model_incomplete: "Select a model for the selected provider.",
    };
    run.title = reasons[availability.reason] || "";
    run.addEventListener("click", () => {
      const generation = model.get("submit_generation") + 1;
      activeRun = { generation };
      model.set(
        "submitted_request",
        buildSubmittedRequest({
          configId: model.get("selected_config"),
          mode: model.get("selected_mode"),
          provider: model.get("selected_provider"),
          model: model.get("selected_model"),
          includeTests: model.get("include_tests"),
          excludeTests: model.get("exclude_tests"),
          allowExternal: model.get("allow_external"),
          writeReports: model.get("write_reports"),
        }),
      );
      model.set("submit_generation", generation);
      model.save_changes();
      renderAll();
    });
    actionRow.appendChild(run);
    capabilities.appendChild(actionRow);
    root.appendChild(capabilities);

    el.appendChild(root);
    schedulePoll();
  }

  for (const name of watched) model.on(`change:${name}`, renderAll);
  renderAll();
  return () => {
    if (pollTimer !== null) window.clearTimeout(pollTimer);
    for (const name of watched) model.off(`change:${name}`, renderAll);
  };
}

export default { render };
