const SCENARIOS = [
  ["car-wash", "Car wash planning"],
  ["coupon-stack", "Coupon stacking policy"],
  ["pallet-door", "Pallet and loading door"],
  ["cold-chain", "Medical cold-chain review"],
  ["synthetic-claims-audit", "Synthetic claims audit"],
];

const MODE_GUIDANCE_ITEMS = [
  "Fixture — deterministic synthetic evidence; it does not call a provider.",
  "Auto — may attempt a compatible enabled live provider, then falls back only where supported.",
  "Live — runs the selected enabled provider.",
];
const MODE_GUIDANCE = MODE_GUIDANCE_ITEMS.join("\n");

const PROVIDER_LABELS = {
  claude: "Claude",
  openai: "OpenAI",
  groq: "Groq",
  xai: "xAI",
  ollama: "Ollama",
  lmstudio: "LM Studio",
};

export function hasSelectedApplicableEngine(engines, selectedIds) {
  const selected = new Set(selectedIds || []);
  return (engines || []).some(
    (engine) =>
      engine.enabled === true &&
      engine.applicable === true &&
      selected.has(engine.id),
  );
}

export function modeOptionPresentation(mode) {
  let label = mode.label || mode.id;
  if (mode.id === "auto" && mode.resolved_mode === "fixture") {
    label = `${label} — Fixture`;
  } else if (
    mode.id === "live" &&
    mode.enabled !== true &&
    mode.compatibility_code ===
      "coupon_live_strict_schema_transport_unavailable_v1_0_5"
  ) {
    label = `${label} — unavailable (v1.0.5 strict schema)`;
  }
  return {
    label,
    disabled: mode.enabled !== true,
    title: mode.message || "",
  };
}

export function modeDisabledForState(mode, scenario, fixtureLlmOverride) {
  if (mode.enabled !== true) return true;
  if (fixtureLlmOverride !== true || mode.id === "fixture") return false;
  return !(scenario === "coupon-stack" && mode.id === "auto");
}

export function analyzeActionAvailability({
  scenario,
  mode,
  modes,
  fixtureLlmOverride,
  hasApplicableEngine,
  runActive,
  provider,
  model,
}) {
  if (runActive) return { enabled: false, reason: "active_run" };
  if (!hasApplicableEngine) {
    return { enabled: false, reason: "applicable_engine_required" };
  }
  const selectedMode = (modes || []).find((option) => option.id === mode);
  if (
    !selectedMode ||
    modeDisabledForState(selectedMode, scenario, fixtureLlmOverride)
  ) {
    return { enabled: false, reason: "mode_unavailable" };
  }
  if (mode === "live" && (!provider || !model)) {
    return { enabled: false, reason: "live_selection_incomplete" };
  }
  return { enabled: true, reason: null };
}

export function scenarioModePresentation(scenario, modes) {
  if (scenario !== "coupon-stack") return { badge: null, summary: null };
  const auto = (modes || []).find((mode) => mode.id === "auto");
  return {
    badge: "v1.0.5 · Fixture-backed",
    summary: auto?.message || null,
  };
}

export function providerControlPresentation(provider) {
  const reasons = [provider.reason, provider.applicability_reason].filter(Boolean);
  return {
    disabled: provider.selectable !== true,
    scenarioInapplicable: provider.applicable === false,
    globallyUnavailable: provider.enabled !== true,
    title: reasons.join(" "),
  };
}

export function buildSubmittedRequest(state) {
  const containedCoupon =
    state.scenario === "coupon-stack" &&
    (state.mode === "fixture" || state.mode === "auto");
  return {
    scenario: state.scenario,
    mode: state.mode,
    provider: containedCoupon ? null : state.provider || null,
    model: containedCoupon ? null : state.model || null,
    mechanisms: [...state.mechanisms],
    max_repair_attempts: state.maxRepairAttempts,
  };
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function section(title) {
  const card = element("section", "reasoning-section");
  card.appendChild(element("h3", "section-title", title));
  return card;
}

function selectControl(labelText, value, options, onChange) {
  const field = element("label", "control-field");
  field.appendChild(element("span", "control-label", labelText));
  const select = element("select", "control-select");
  for (const [id, label] of options) {
    const option = element("option", "", label);
    option.value = id;
    option.selected = id === value;
    select.appendChild(option);
  }
  select.addEventListener("change", () => onChange(select.value));
  field.appendChild(select);
  return field;
}

function detailItem(label, value) {
  const item = element("div", "model-detail-item");
  item.appendChild(element("span", "detail-label", label));
  item.appendChild(element("span", "detail-value", value || "not reported"));
  return item;
}

function formatElapsed(milliseconds, includeMilliseconds) {
  const totalMilliseconds = Math.max(0, Math.floor(milliseconds));
  const hours = Math.floor(totalMilliseconds / 3600000);
  const minutes = Math.floor((totalMilliseconds % 3600000) / 60000);
  const seconds = Math.floor((totalMilliseconds % 60000) / 1000);
  const base = [hours, minutes, seconds]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
  if (!includeMilliseconds) return base;
  return `${base}.${String(totalMilliseconds % 1000).padStart(3, "0")}`;
}

function render({ model, el }) {
  const uiState = { search: "" };
  let pollTimer = null;
  let runTimer = null;
  let runStatusText = null;
  let activeRun = null;
  const watched = [
    "scenario",
    "mode",
    "modes",
    "providers",
    "selected_provider",
    "models",
    "selected_model",
    "model_state",
    "model_message",
    "discovery_loading",
    "engines",
    "selected_engines",
    "max_repair_attempts",
    "poll_generation",
    "completed_generation",
    "completed_elapsed_ms",
    "completion_state",
    "fixture_llm_override",
  ];

  function save(name, value) {
    model.set(name, value);
    model.save_changes();
  }

  function schedulePoll() {
    if (pollTimer !== null) window.clearTimeout(pollTimer);
    const loading =
      model.get("discovery_loading") === true || model.get("model_state") === "loading";
    if (loading) {
      pollTimer = window.setTimeout(() => {
        save("poll_generation", model.get("poll_generation") + 1);
      }, 250);
    }
  }

  function runElapsedSeconds() {
    if (!activeRun) return 0;
    const endpoint = activeRun.completedAt || Date.now();
    return Math.max(0, (endpoint - activeRun.startedAt) / 1000);
  }

  function updateRunStatusText() {
    if (!runStatusText || !activeRun) return;
    const activeElapsedMs = Math.floor(runElapsedSeconds()) * 1000;
    const elapsed =
      activeRun.phase === "running"
        ? formatElapsed(activeElapsedMs, false)
        : formatElapsed(model.get("completed_elapsed_ms"), true);
    if (activeRun.phase === "running") {
      const previousResultNotice =
        model.get("completed_generation") > 0
          ? " Previous completed results remain visible below until this run finishes."
          : "";
      runStatusText.textContent = `Analyzing through nxusKit… ${elapsed} elapsed.${previousResultNotice}`;
    } else if (activeRun.phase === "completed") {
      runStatusText.textContent = `Analysis completed in ${elapsed}.`;
    } else {
      runStatusText.textContent = `Analysis stopped after ${elapsed}. Review the message below.`;
    }
  }

  function stopRunTimer() {
    if (runTimer !== null) window.clearInterval(runTimer);
    runTimer = null;
  }

  function reconcileCompletedRun() {
    if (!activeRun || activeRun.phase !== "running") return;
    if (model.get("completed_generation") < activeRun.generation) return;
    activeRun.phase = model.get("completion_state") === "completed" ? "completed" : "failed";
    activeRun.completedAt = Date.now();
    stopRunTimer();
  }

  function beginRun(generation) {
    stopRunTimer();
    activeRun = {
      generation,
      phase: "running",
      startedAt: Date.now(),
      completedAt: null,
    };
    renderAll();
    runTimer = window.setInterval(updateRunStatusText, 1000);
  }

  function renderAll() {
    reconcileCompletedRun();
    el.replaceChildren();
    const root = element("div", "reasoning-controls");
    root.appendChild(
      element("h2", "reasoning-heading", "Choose Scenario and Configure Reasoning ..."),
    );

    const scenarioMode = section("Scenario and Mode");
    const scenarioModeGrid = element("div", "control-grid scenario-mode-grid");
    scenarioModeGrid.appendChild(
      selectControl("Scenario", model.get("scenario"), SCENARIOS, (value) =>
        save("scenario", value),
      ),
    );
    const modeField = element("div", "control-field");
    const modeLabel = element("div", "label-with-info");
    modeLabel.appendChild(element("span", "control-label", "Mode"));
    const scenarioPresentation = scenarioModePresentation(
      model.get("scenario"),
      model.get("modes"),
    );
    const badgeText =
      model.get("scenario") === "synthetic-claims-audit"
        ? "Fixture-only · no LLM"
        : scenarioPresentation.badge;
    if (badgeText) {
      const badge = element("span", "mode-badge", badgeText);
      badge.setAttribute("role", "note");
      badge.title = scenarioPresentation.summary ||
        "This deterministic synthetic data-quality audit is Fixture-only and does not invoke an LLM provider.";
      modeLabel.appendChild(badge);
    }
    const info = element("button", "info-button", "ⓘ");
    info.type = "button";
    info.setAttribute("aria-label", `Mode guidance: ${MODE_GUIDANCE}`);
    const tooltip = element("div", "mode-tooltip");
    const tooltipId = "reasoning-mode-guidance";
    tooltip.id = tooltipId;
    tooltip.hidden = true;
    tooltip.setAttribute("role", "tooltip");
    tooltip.appendChild(element("strong", "", "Mode guidance"));
    const tooltipList = element("ul", "mode-tooltip-list");
    for (const guidance of MODE_GUIDANCE_ITEMS) {
      tooltipList.appendChild(element("li", "", guidance));
    }
    tooltip.appendChild(tooltipList);
    info.setAttribute("aria-describedby", tooltipId);
    info.setAttribute("aria-expanded", "false");
    const showTooltip = () => {
      tooltip.hidden = false;
      info.setAttribute("aria-expanded", "true");
    };
    const hideTooltip = () => {
      tooltip.hidden = true;
      info.setAttribute("aria-expanded", "false");
    };
    info.addEventListener("mouseenter", showTooltip);
    info.addEventListener("mouseleave", () => {
      if (document.activeElement !== info) hideTooltip();
    });
    info.addEventListener("focus", showTooltip);
    info.addEventListener("blur", hideTooltip);
    info.addEventListener("click", (event) => {
      event.stopPropagation();
      showTooltip();
    });
    info.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        hideTooltip();
        info.blur();
      }
    });
    modeLabel.appendChild(info);
    modeLabel.appendChild(tooltip);
    modeField.appendChild(modeLabel);
    const modeSelect = element("select", "control-select");
    modeSelect.setAttribute("aria-label", "Mode");
    for (const mode of model.get("modes") || []) {
      const presentation = modeOptionPresentation(mode);
      const option = element("option", "", presentation.label);
      option.value = mode.id;
      option.selected = mode.id === model.get("mode");
      const providerBackedModesDisabled =
        model.get("fixture_llm_override") === true &&
        mode.id !== "fixture" &&
        !(model.get("scenario") === "coupon-stack" && mode.id === "auto");
      option.disabled = modeDisabledForState(
        mode,
        model.get("scenario"),
        model.get("fixture_llm_override"),
      );
      option.title = presentation.title;
      if (providerBackedModesDisabled && !presentation.disabled) {
        option.textContent = `${mode.label} — disabled (fixture smoke override)`;
      }
      modeSelect.appendChild(option);
    }
    modeSelect.addEventListener("change", () => save("mode", modeSelect.value));
    modeField.appendChild(modeSelect);
    if (model.get("fixture_llm_override") === true) {
      modeField.appendChild(
        element(
          "p",
          "mode-warning",
          "Provider-backed modes are disabled because this process was launched with the deterministic fixture LLM smoke override.",
        ),
      );
    }
    if (scenarioPresentation.summary) {
      modeField.appendChild(
        element("p", "mode-summary", scenarioPresentation.summary),
      );
    }
    scenarioModeGrid.appendChild(modeField);
    scenarioMode.appendChild(scenarioModeGrid);
    root.appendChild(scenarioMode);

    const providerModel = section("Provider and Model");
    const providerGrid = element("div", "provider-grid");
    for (const provider of model.get("providers") || []) {
      const presentation = providerControlPresentation(provider);
      const providerButton = element(
        "button",
        "provider-button",
        PROVIDER_LABELS[provider.id] || provider.id,
      );
      providerButton.type = "button";
      providerButton.disabled = presentation.disabled;
      providerButton.title = presentation.title || "Provider unavailable.";
      providerButton.classList.toggle(
        "scenario-inapplicable",
        presentation.scenarioInapplicable,
      );
      providerButton.classList.toggle(
        "globally-unavailable",
        presentation.globallyUnavailable,
      );
      providerButton.classList.toggle(
        "selected",
        provider.id === model.get("selected_provider"),
      );
      providerButton.addEventListener("click", () => save("selected_provider", provider.id));
      providerGrid.appendChild(providerButton);
    }
    providerModel.appendChild(providerGrid);

    const modelToolbar = element("div", "model-toolbar");
    const selectedProviderOption = (model.get("providers") || []).find(
      (provider) => provider.id === model.get("selected_provider"),
    );
    const selectedProviderSelectable = selectedProviderOption?.selectable === true;
    const search = element("input", "model-search");
    search.type = "search";
    search.placeholder = "Filter models";
    search.value = uiState.search;
    search.setAttribute("aria-label", "Filter models");
    search.disabled = !selectedProviderSelectable;
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
    for (const availableModel of model.get("models") || []) {
      const searchable = `${availableModel.name} ${availableModel.id}`.toLowerCase();
      if (query && !searchable.includes(query)) continue;
      const option = element("option", "", availableModel.name || availableModel.id);
      option.value = availableModel.id;
      option.selected = availableModel.id === model.get("selected_model");
      modelSelect.appendChild(option);
    }
    modelSelect.disabled =
      !selectedProviderSelectable || model.get("model_state") === "loading";
    modelSelect.addEventListener("change", () => save("selected_model", modelSelect.value || null));
    modelToolbar.appendChild(modelSelect);
    const refresh = element("button", "refresh-button", "Refresh models");
    refresh.type = "button";
    refresh.disabled = !selectedProviderSelectable;
    refresh.addEventListener("click", () =>
      save("refresh_generation", model.get("refresh_generation") + 1),
    );
    modelToolbar.appendChild(refresh);
    providerModel.appendChild(modelToolbar);
    providerModel.appendChild(
      element("p", `model-status ${model.get("model_state")}`, model.get("model_message")),
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
          selectedModel.context_window ? `${selectedModel.context_window} tokens` : null,
        ),
      );
      details.appendChild(detailItem("Size", selectedModel.size));
      details.appendChild(detailItem("Local", selectedModel.local ? "yes" : "no"));
      providerModel.appendChild(details);
    }
    root.appendChild(providerModel);

    const reasoningEngines = section("Reasoning Engines");
    const engineLegend = element(
      "p",
      "engine-legend",
      "Muted engines are unavailable. Italic engines are available but are not applied to this scenario.",
    );
    reasoningEngines.appendChild(engineLegend);
    const engineGrid = element("div", "engine-grid");
    const selectedEngines = model.get("selected_engines") || [];
    const hasApplicableEngine = hasSelectedApplicableEngine(
      model.get("engines"),
      selectedEngines,
    );
    for (const engine of model.get("engines") || []) {
      const row = element("label", "engine-option");
      if (engine.emphasis === "unsupported_for_scenario") {
        row.classList.add("unsupported-for-scenario");
      }
      if (!engine.enabled) row.classList.add("unavailable");
      row.title = engine.tooltip || "";
      const checkbox = element("input", "engine-checkbox");
      checkbox.type = "checkbox";
      checkbox.value = engine.id;
      checkbox.checked = selectedEngines.includes(engine.id);
      checkbox.disabled = !engine.enabled;
      checkbox.addEventListener("change", () => {
        const current = new Set(model.get("selected_engines") || []);
        if (checkbox.checked) current.add(engine.id);
        else current.delete(engine.id);
        save("selected_engines", [...current]);
      });
      row.appendChild(checkbox);
      row.appendChild(
        element(
          "span",
          "engine-label",
          `${engine.label}${engine.tier === "pro" ? " · Pro" : ""}`,
        ),
      );
      engineGrid.appendChild(row);
    }
    reasoningEngines.appendChild(engineGrid);
    const actionRow = element("div", "action-row");
    const status = element("div", "analysis-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    if (activeRun) {
      if (activeRun.phase === "running") {
        status.appendChild(element("span", "analysis-spinner"));
      }
      runStatusText = element("span", "analysis-status-text");
      status.appendChild(runStatusText);
      updateRunStatusText();
    } else if (!hasApplicableEngine) {
      runStatusText = null;
      status.appendChild(
        element(
          "span",
          "analysis-status-text",
          "Select at least one available Reasoning Engine that applies to this scenario.",
        ),
      );
    } else {
      runStatusText = null;
      status.appendChild(
        element("span", "analysis-status-text", "Analysis starts only after you press Analyze."),
      );
    }
    actionRow.appendChild(status);
    const attempts = element("label", "attempts-field");
    attempts.title = "One initial response plus up to this many repaired responses.";
    attempts.appendChild(element("span", "control-label", "Maximum repair attempts"));
    const attemptsInput = element("input", "attempts-input");
    attemptsInput.type = "number";
    attemptsInput.min = "1";
    attemptsInput.max = "10";
    attemptsInput.value = String(model.get("max_repair_attempts"));
    attemptsInput.addEventListener("input", () => {
      const value = Number(attemptsInput.value);
      if (Number.isInteger(value) && value >= 1 && value <= 10) {
        save("max_repair_attempts", value);
      }
    });
    attempts.appendChild(attemptsInput);
    actionRow.appendChild(attempts);
    const analyze = element("button", "analyze-button", "Analyze");
    analyze.type = "button";
    const analyzeAvailability = analyzeActionAvailability({
      scenario: model.get("scenario"),
      mode: model.get("mode"),
      modes: model.get("modes"),
      fixtureLlmOverride: model.get("fixture_llm_override"),
      hasApplicableEngine,
      runActive: activeRun?.phase === "running",
      provider: model.get("selected_provider"),
      model: model.get("selected_model"),
    });
    analyze.disabled = !analyzeAvailability.enabled;
    if (analyzeAvailability.reason === "applicable_engine_required") {
      analyze.title =
        "Select at least one available Reasoning Engine that applies to this scenario.";
    } else if (analyzeAvailability.reason === "live_selection_incomplete") {
      analyze.title = "Live requires an available provider and selected model.";
    }
    analyze.addEventListener("click", () => {
      const nextGeneration = model.get("submit_generation") + 1;
      beginRun(nextGeneration);
      model.set("submitted_request", buildSubmittedRequest({
        scenario: model.get("scenario"),
        mode: model.get("mode"),
        provider: model.get("selected_provider") || null,
        model: model.get("selected_model") || null,
        mechanisms: [...model.get("selected_engines")],
        maxRepairAttempts: model.get("max_repair_attempts"),
      }));
      model.set("submit_generation", nextGeneration);
      model.save_changes();
    });
    actionRow.appendChild(analyze);
    reasoningEngines.appendChild(actionRow);
    root.appendChild(reasoningEngines);

    el.appendChild(root);
    schedulePoll();
  }

  for (const name of watched) model.on(`change:${name}`, renderAll);
  renderAll();
  return () => {
    if (pollTimer !== null) window.clearTimeout(pollTimer);
    stopRunTimer();
    for (const name of watched) model.off(`change:${name}`, renderAll);
  };
}

export default { render };
