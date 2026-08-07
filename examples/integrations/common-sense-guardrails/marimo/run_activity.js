const LIVE_EDGE_THRESHOLD = 32;

export function isAtLiveEdge(viewport) {
  return (
    viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight <=
    LIVE_EDGE_THRESHOLD
  );
}

export function normalizePaneState(pane, narrow) {
  if (narrow) return pane === "collapsed" ? "collapsed" : "expanded";
  return ["collapsed", "normal", "expanded"].includes(pane) ? pane : "normal";
}

export function nextPaneState(pane, narrow) {
  const normalized = normalizePaneState(pane, narrow);
  if (narrow) return normalized === "collapsed" ? "expanded" : "collapsed";
  if (normalized === "collapsed") return "normal";
  if (normalized === "normal") return "expanded";
  return "collapsed";
}

export function latestLinkedEventId(interaction) {
  const links = interaction?.linked_event_ids || [];
  return links.length ? links[links.length - 1] : null;
}

export function liveEdgeSelectionSource(source) {
  return ["activity-scroll", "interaction-scroll"].includes(source)
    ? source
    : "live-follow";
}

export function shouldRecenterOnResize(
  followLive,
  activeInteractionId,
  resizedInteractionId,
) {
  return !followLive && activeInteractionId === resizedInteractionId;
}

export function createFollowState() {
  let following = true;
  let unseen = 0;
  const snapshot = () => ({ following, unseen });
  return {
    onAnalyze() {
      following = true;
      unseen = 0;
      return snapshot();
    },
    onManualScroll(atLiveEdge) {
      if (atLiveEdge) {
        following = true;
        unseen = 0;
      } else if (following) {
        following = false;
        unseen = 0;
      }
      return snapshot();
    },
    onInteractionUpdate() {
      if (!following) unseen += 1;
      return snapshot();
    },
    snapshot,
  };
}

export function createProgrammaticScrollGuard({
  schedule = (callback) => setTimeout(callback, 320),
  cancel = (timerId) => clearTimeout(timerId),
} = {}) {
  const sources = new Map();
  const timers = new Map();

  function cancelTimer(target) {
    if (!timers.has(target)) return;
    cancel(timers.get(target));
    timers.delete(target);
  }

  function armIdleFallback(target) {
    cancelTimer(target);
    const timerId = schedule(() => {
      sources.delete(target);
      timers.delete(target);
    });
    timers.set(target, timerId);
  }

  return {
    begin(target, source) {
      sources.set(target, source);
      armIdleFallback(target);
    },
    noteScroll(target) {
      if (!sources.has(target)) return false;
      armIdleFallback(target);
      return true;
    },
    end(target) {
      if (sources.has(target)) armIdleFallback(target);
    },
    isActive(target) {
      return sources.has(target);
    },
    clear() {
      for (const target of sources.keys()) cancelTimer(target);
      sources.clear();
    },
  };
}

export function nearestLinkedId(items, viewportCenter) {
  let nearest = null;
  let distance = Number.POSITIVE_INFINITY;
  for (const item of items) {
    const itemDistance = Math.abs(item.center - viewportCenter);
    if (item.id && itemDistance < distance) {
      nearest = item.id;
      distance = itemDistance;
    }
  }
  return nearest;
}

export function paneStateOnAnalyze(narrow) {
  return narrow ? "expanded" : "normal";
}

export function nextLinkedInteractionId(ids, currentId, direction) {
  if (!ids.length) return null;
  const currentIndex = ids.indexOf(currentId);
  const fallbackIndex = direction > 0 ? 0 : ids.length - 1;
  const nextIndex = currentIndex < 0 ? fallbackIndex : currentIndex + direction;
  return ids[Math.max(0, Math.min(ids.length - 1, nextIndex))];
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function phaseLabel(phase) {
  return {
    initial_recommendation: "Initial Recommendation",
    fact_extraction: "Fact Extraction",
    fact_extraction_repair: "Fact Extraction Repair",
    repaired_recommendation: "Repaired Recommendation",
  }[phase] || "LLM Interaction";
}

function callNumber(interactionId) {
  const number = Number.parseInt(String(interactionId || "").slice(4), 10);
  return Number.isFinite(number) ? number : "?";
}

function appendLabeledText(parent, labelText, content, className = "") {
  const section = element("section", `interaction-section ${className}`.trim());
  section.appendChild(element("h5", "interaction-section-title", labelText));
  const text = element("pre", "interaction-plain-text");
  text.textContent = String(content ?? "");
  section.appendChild(text);
  parent.appendChild(section);
}

function renderRepairContext(parent, interaction) {
  const repair = interaction.repair_context;
  if (!repair) return;
  const section = element("section", "interaction-section repair-context");
  section.appendChild(
    element(
      "h5",
      "interaction-section-title",
      `Repair Attempt ${repair.repair_attempt} → Response Attempt ${interaction.response_attempt}`,
    ),
  );
  section.appendChild(
    element(
      "p",
      "interaction-fact",
      `Triggered by: ${(repair.triggering_engines || []).join(", ") || "not reported"}. Blocking findings: ${repair.blocking_finding_count}.`,
    ),
  );
  const instructions = element("ul", "repair-instructions");
  for (const instruction of repair.repair_instructions || []) {
    instructions.appendChild(element("li", "", instruction));
  }
  section.appendChild(instructions);
  const delta = repair.prompt_delta || { added: [], removed: [] };
  const changes = element("div", "prompt-delta");
  changes.appendChild(element("h6", "", "Changes from Previous Prompt"));
  for (const removed of delta.removed || []) {
    changes.appendChild(element("div", "prompt-delta-removed", `− ${removed}`));
  }
  for (const added of delta.added || []) {
    changes.appendChild(element("div", "prompt-delta-added", `+ ${added}`));
  }
  if (!(delta.added || []).length && !(delta.removed || []).length) {
    changes.appendChild(element("p", "interaction-muted", "No line changes."));
  }
  section.appendChild(changes);
  parent.appendChild(section);
}

function renderOutcome(parent, interaction) {
  const outcome = interaction.outcome;
  if (!outcome) return;
  const section = element("section", "interaction-section interaction-outcome");
  section.appendChild(element("h5", "interaction-section-title", "Reasoning Engine Outcome"));
  const previous =
    outcome.previous_blocking_finding_count === null
      ? "not comparable"
      : outcome.previous_blocking_finding_count;
  section.appendChild(
    element(
      "p",
      "interaction-fact",
      `Decision: ${outcome.status}. Blocking findings: ${outcome.blocking_finding_count}; previous: ${previous}; measured change: ${outcome.delta}.`,
    ),
  );
  const engines = element("ul", "interaction-engines");
  for (const engine of outcome.engines || []) {
    engines.appendChild(
      element(
        "li",
        `interaction-engine interaction-status-${engine.status}`,
        `${engine.id}: ${engine.status} (${engine.blocking_finding_count} blocking)`,
      ),
    );
  }
  section.appendChild(engines);
  parent.appendChild(section);
}

function updateInteractionCard(card, interaction, openNew) {
  const wasOpen = card.open;
  card.className = `interaction-card interaction-phase-${interaction.phase} interaction-status-${interaction.status}`;
  card.dataset.interactionId = interaction.id;
  const summary = document.createElement("summary");
  summary.className = "interaction-card-summary";
  const title = element(
    "span",
    "interaction-card-title",
    `LLM Call ${callNumber(interaction.id)} · ${phaseLabel(interaction.phase)} · Response Attempt ${interaction.response_attempt}`,
  );
  summary.appendChild(title);
  summary.appendChild(
    element(
      "span",
      `activity-status interaction-status-${interaction.status}`,
      interaction.status,
    ),
  );
  const body = element("div", "interaction-card-body");
  const source =
    interaction.source === "fixture"
      ? "Fixture · no provider contacted"
      : "Live · provider contacted through nxusKit";
  body.appendChild(
    element(
      "p",
      "interaction-identity",
      `${source} · ${interaction.provider} / ${interaction.model}`,
    ),
  );
  const messages = interaction.messages || [];
  appendLabeledText(body, "System Prompt", messages[0]?.content || "");
  appendLabeledText(body, "User Prompt", messages[1]?.content || "");
  if (interaction.status === "requested") {
    appendLabeledText(body, "Response", "Waiting for response…", "waiting-response");
  } else if (interaction.status === "stopped") {
    appendLabeledText(body, "Stopped", interaction.safe_error || "Request stopped.", "stopped-response");
  } else {
    appendLabeledText(body, "Response", interaction.response_content || "");
  }
  renderRepairContext(body, interaction);
  renderOutcome(body, interaction);
  card.replaceChildren(summary, body);
  card.open = openNew || wasOpen || interaction.status === "requested";
}

function updateEventRow(row, event) {
  row.className = `activity-event activity-status-${event.status}`;
  row.dataset.eventId = event.id;
  if (event.llm_interaction_id) {
    row.dataset.interactionId = event.llm_interaction_id;
    row.tabIndex = 0;
    row.setAttribute(
      "aria-label",
      `${event.message}; linked to LLM call ${callNumber(event.llm_interaction_id)}`,
    );
  } else {
    delete row.dataset.interactionId;
    row.tabIndex = -1;
    row.setAttribute("aria-label", `${event.message}; no LLM call`);
  }
  const timestamp = String(event.timestamp_utc || "").split("T")[1] || "";
  const component = event.component || {};
  const identity = [component.id, component.model].filter(Boolean).join(" / ");
  const children = [
    element("time", "activity-time", timestamp),
    element("span", "activity-status", event.status),
  ];
  if (event.llm_interaction_id) {
    children.push(
      element(
        "span",
        "activity-llm-link",
        `LLM ${callNumber(event.llm_interaction_id)}`,
      ),
    );
  } else {
    children.push(element("span", "activity-no-llm", "No LLM call"));
  }
  if (identity) children.push(element("span", "activity-component", identity));
  children.push(element("span", "activity-message", event.message));
  row.replaceChildren(...children);
}

function render({ model, el }) {
  let currentExportUrl = null;
  let previousModelState = null;
  const eventNodes = new Map();
  const interactionNodes = new Map();
  const followState = createFollowState();
  const scrollGuard = createProgrammaticScrollGuard();
  const state = {
    pane: "normal",
    followLive: true,
    unseen: 0,
    activeInteractionId: null,
    activityScrollFrame: null,
    interactionScrollFrame: null,
  };
  const media = window.matchMedia("(max-width: 760px)");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const watched = [
    "events",
    "interactions",
    "state",
    "draft_differs",
    "has_results",
    "export_choice",
    "include_full_transcript",
    "prepared_export_choice",
    "export_json",
    "export_filename",
    "export_error",
  ];

  function saveMany(values) {
    for (const [name, value] of Object.entries(values)) model.set(name, value);
    model.save_changes();
  }

  const root = element("section", "run-activity-card");
  const splitSurface = element("div", "split-surface");
  const activityPane = element("section", "run-activity-pane");
  activityPane.id = `run-activity-${Math.random().toString(36).slice(2)}`;
  activityPane.setAttribute("aria-label", "Run Activity");
  const activityHeader = element("header", "pane-header");
  activityHeader.appendChild(element("h3", "pane-title", "Run Activity"));
  const activityState = element("span", "activity-state");
  activityHeader.appendChild(activityState);
  const activityLive = element("div", "run-activity-live");
  activityLive.tabIndex = 0;
  activityLive.setAttribute("role", "region");
  activityLive.setAttribute("aria-label", "Run Activity events");
  activityLive.setAttribute("aria-live", "polite");
  const eventList = element("ol", "activity-event-list");
  const activityEmpty = element(
    "p",
    "activity-empty",
    "No run events yet. Export is still available for current settings.",
  );
  activityLive.append(activityEmpty, eventList);
  activityPane.append(activityHeader, activityLive);

  const separator = element("button", "pane-separator");
  separator.type = "button";

  const interactionsPane = element("section", "llm-interactions-pane");
  interactionsPane.id = `llm-interactions-${Math.random().toString(36).slice(2)}`;
  interactionsPane.setAttribute("aria-label", "LLM Interactions");
  const interactionsHeader = element("header", "pane-header");
  interactionsHeader.appendChild(element("h3", "pane-title", "LLM Interactions"));
  const interactionsCount = element("span", "interaction-count");
  interactionsHeader.appendChild(interactionsCount);
  const jumpToLive = element("button", "jump-to-live", "↓ Live");
  jumpToLive.type = "button";
  jumpToLive.hidden = true;
  interactionsHeader.appendChild(jumpToLive);
  const interactionsLive = element("div", "llm-interactions-live");
  interactionsLive.tabIndex = 0;
  interactionsLive.setAttribute("role", "region");
  interactionsLive.setAttribute("aria-label", "LLM prompts and responses");
  interactionsLive.setAttribute("aria-live", "polite");
  const interactionList = element("div", "interaction-list");
  const interactionsEmpty = element(
    "p",
    "interaction-empty",
    "No LLM interaction occurred for this run.",
  );
  interactionsLive.append(interactionsEmpty, interactionList);
  interactionsPane.append(interactionsHeader, interactionsLive);
  splitSurface.append(activityPane, separator, interactionsPane);

  const exportPanel = element("section", "session-export-panel");
  root.append(splitSurface, exportPanel);
  el.replaceChildren(root);

  function applyPaneState() {
    state.pane = normalizePaneState(state.pane, media.matches);
    splitSurface.dataset.paneState = state.pane;
    splitSurface.className = `split-surface pane-${state.pane}`;
    const visible = state.pane !== "collapsed";
    separator.textContent = `LLM Interactions: ${state.pane}`;
    separator.setAttribute("aria-controls", interactionsPane.id);
    separator.setAttribute("aria-expanded", String(visible));
    separator.setAttribute(
      "aria-label",
      `LLM Interactions pane is ${state.pane}; activate to change pane size`,
    );
  }

  function applyFollowSnapshot(snapshot) {
    state.followLive = snapshot.following;
    state.unseen = snapshot.unseen;
    jumpToLive.hidden = snapshot.following;
    jumpToLive.textContent = snapshot.unseen
      ? `↓ Live (${snapshot.unseen} unseen)`
      : "↓ Live";
    jumpToLive.setAttribute(
      "aria-label",
      snapshot.unseen
        ? `Jump to live; ${snapshot.unseen} unseen LLM interaction updates`
        : "Jump to live",
    );
  }

  function beginProgrammaticScroll(viewport, source) {
    scrollGuard.begin(viewport, source);
  }

  function centerNode(node, viewport, source) {
    if (!node) return;
    beginProgrammaticScroll(viewport, source);
    node.scrollIntoView({ block: "center",
      inline: "nearest",
      behavior: reducedMotion.matches ? "auto" : "smooth",
    });
  }

  function linkedInteractionIds() {
    return (model.get("interactions") || [])
      .filter((interaction) => latestLinkedEventId(interaction))
      .map((interaction) => interaction.id);
  }

  function eventNodeForInteraction(interactionId) {
    const interaction = (model.get("interactions") || []).find(
      (candidate) => candidate.id === interactionId,
    );
    return eventNodes.get(latestLinkedEventId(interaction));
  }

  function highlightInteraction(interactionId) {
    for (const row of eventNodes.values()) {
      row.classList.toggle(
        "is-active-pair",
        row.dataset.interactionId === interactionId,
      );
    }
    for (const [id, interactionCard] of interactionNodes) {
      interactionCard.classList.toggle("is-active-pair", id === interactionId);
    }
  }

  function selectInteraction(interactionId, source = "selection") {
    const card = interactionNodes.get(interactionId);
    if (!card) return;
    state.activeInteractionId = interactionId;
    highlightInteraction(interactionId);
    if (!new Set(["interaction-click", "interaction-scroll", "resize"]).has(source)) {
      card.open = true;
    }
    if (source !== "activity-scroll") {
      centerNode(eventNodeForInteraction(interactionId), activityLive, source);
    }
    if (source !== "interaction-scroll") {
      centerNode(card, interactionsLive, source);
    }
  }

  function newestInteractionId() {
    const ids = linkedInteractionIds();
    return ids.length ? ids[ids.length - 1] : null;
  }

  function resumeLive(source) {
    applyFollowSnapshot(followState.onManualScroll(true));
    const newest = newestInteractionId();
    if (newest) {
      selectInteraction(newest, liveEdgeSelectionSource(source));
      return;
    }
    beginProgrammaticScroll(activityLive, "live-follow");
    activityLive.scrollTop = activityLive.scrollHeight;
  }

  jumpToLive.addEventListener("click", resumeLive);

  separator.addEventListener("click", () => {
    state.pane = nextPaneState(state.pane, media.matches);
    applyPaneState();
  });
  const handleMediaChange = () => applyPaneState();
  media.addEventListener("change", handleMediaChange);

  const resizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) {
      const interactionId = entry.target.dataset.interactionId;
      if (
        interactionId &&
        shouldRecenterOnResize(
          state.followLive,
          state.activeInteractionId,
          interactionId,
        )
      ) {
        selectInteraction(interactionId, "resize");
      }
    }
  });

  function activityInteractionAtCenter() {
    const viewport = activityLive.getBoundingClientRect();
    const viewportCenter = viewport.top + viewport.height / 2;
    const rows = [...eventNodes.values()];
    if (!rows.length) return null;
    const positions = rows.map((row) => {
      const rect = row.getBoundingClientRect();
      return {
        id: row.dataset.interactionId || null,
        center: rect.top + rect.height / 2,
      };
    });
    let centeredIndex = 0;
    let centeredDistance = Number.POSITIVE_INFINITY;
    positions.forEach((position, index) => {
      const distance = Math.abs(position.center - viewportCenter);
      if (distance < centeredDistance) {
        centeredDistance = distance;
        centeredIndex = index;
      }
    });
    for (let index = centeredIndex; index >= 0; index -= 1) {
      if (positions[index].id) return positions[index].id;
    }
    return nearestLinkedId(positions, viewportCenter);
  }

  function interactionAtCenter() {
    const viewport = interactionsLive.getBoundingClientRect();
    const viewportCenter = viewport.top + viewport.height / 2;
    return nearestLinkedId(
      [...interactionNodes].map(([id, card]) => {
        const rect = card.getBoundingClientRect();
        return { id, center: rect.top + rect.height / 2 };
      }),
      viewportCenter,
    );
  }

  function scheduleScrollSelection(source) {
    const frameName =
      source === "activity-scroll"
        ? "activityScrollFrame"
        : "interactionScrollFrame";
    if (state[frameName] !== null) return;
    state[frameName] = requestAnimationFrame(() => {
      state[frameName] = null;
      const interactionId =
        source === "activity-scroll"
          ? activityInteractionAtCenter()
          : interactionAtCenter();
      if (interactionId) selectInteraction(interactionId, source);
    });
  }

  function handleViewportScroll(event, viewport, source) {
    if (!event.isTrusted || scrollGuard.noteScroll(viewport)) return;
    const atLiveEdge = isAtLiveEdge(viewport);
    applyFollowSnapshot(followState.onManualScroll(atLiveEdge));
    if (atLiveEdge) {
      resumeLive(source);
      return;
    }
    scheduleScrollSelection(source);
  }

  activityLive.addEventListener("scroll", (event) =>
    handleViewportScroll(event, activityLive, "activity-scroll"),
  );
  interactionsLive.addEventListener("scroll", (event) =>
    handleViewportScroll(event, interactionsLive, "interaction-scroll"),
  );
  const endActivityScroll = () => scrollGuard.end(activityLive);
  const endInteractionScroll = () => scrollGuard.end(interactionsLive);
  activityLive.addEventListener("scrollend", endActivityScroll);
  interactionsLive.addEventListener("scrollend", endInteractionScroll);

  splitSurface.addEventListener("keydown", (event) => {
    const direction =
      event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
    if (!direction) return;
    const next = nextLinkedInteractionId(
      linkedInteractionIds(),
      state.activeInteractionId,
      direction,
    );
    if (!next) return;
    event.preventDefault();
    applyFollowSnapshot(followState.onManualScroll(false));
    selectInteraction(next, "keyboard");
  });

  function reconcileEvents() {
    const events = model.get("events") || [];
    const wanted = new Set(events.map((event) => event.id));
    for (const [id, node] of eventNodes) {
      if (!wanted.has(id)) {
        node.remove();
        eventNodes.delete(id);
      }
    }
    for (const event of events) {
      let row = eventNodes.get(event.id);
      if (!row) {
        row = element("li", "activity-event");
        row.addEventListener("click", () => {
          if (!row.dataset.interactionId) return;
          applyFollowSnapshot(followState.onManualScroll(false));
          selectInteraction(row.dataset.interactionId, "activity-click");
        });
        eventNodes.set(event.id, row);
      }
      updateEventRow(row, event);
      eventList.appendChild(row);
    }
    activityEmpty.hidden = events.length > 0;
    eventList.hidden = events.length === 0;
  }

  function reconcileInteractions() {
    const interactions = model.get("interactions") || [];
    const wanted = new Set(interactions.map((interaction) => interaction.id));
    for (const [id, node] of interactionNodes) {
      if (!wanted.has(id)) {
        resizeObserver.unobserve(node);
        node.remove();
        interactionNodes.delete(id);
      }
    }
    for (const interaction of interactions) {
      let card = interactionNodes.get(interaction.id);
      const isNew = !card;
      if (!card) {
        card = document.createElement("details");
        card.addEventListener("click", () => {
          applyFollowSnapshot(followState.onManualScroll(false));
          selectInteraction(card.dataset.interactionId, "interaction-click");
        });
        resizeObserver.observe(card);
        interactionNodes.set(interaction.id, card);
      }
      updateInteractionCard(card, interaction, isNew);
      interactionList.appendChild(card);
    }
    interactionsCount.textContent = String(interactions.length);
    interactionsEmpty.hidden = interactions.length > 0;
    interactionList.hidden = interactions.length === 0;
  }

  function renderExport() {
    if (currentExportUrl) {
      URL.revokeObjectURL(currentExportUrl);
      currentExportUrl = null;
    }
    exportPanel.replaceChildren();
    exportPanel.appendChild(element("h3", "session-export-title", "Export Session JSON"));
    const hasResults = Boolean(model.get("has_results"));
    const draftDiffers = Boolean(model.get("draft_differs"));
    if (hasResults && draftDiffers) {
      exportPanel.appendChild(
        element(
          "p",
          "draft-warning",
          "Draft settings do not match the settings used for the current results.",
        ),
      );
      const choiceGroup = element("div", "export-choice-group");
      choiceGroup.setAttribute("role", "radiogroup");
      choiceGroup.setAttribute("aria-label", "Export contents");
      for (const [value, labelText] of [
        ["original_with_results", "Original settings + results"],
        ["draft_settings_only", "Draft settings only"],
      ]) {
        const label = element("label", "export-choice");
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = "reasoning-export-choice";
        radio.value = value;
        radio.checked = model.get("export_choice") === value;
        radio.addEventListener("change", () => saveMany({ export_choice: value }));
        label.append(radio, element("span", "", labelText));
        choiceGroup.appendChild(label);
      }
      exportPanel.appendChild(choiceGroup);
    } else {
      exportPanel.appendChild(
        element(
          "p",
          "export-description",
          hasResults
            ? "Export the submitted settings with their corresponding results."
            : "Export the current settings. Results will be empty until an analysis completes.",
        ),
      );
    }
    const selectedExportChoice =
      hasResults && !draftDiffers ? "original_with_results" : model.get("export_choice");
    if (hasResults && selectedExportChoice === "original_with_results") {
      const transcriptLabel = element("label", "transcript-choice");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = Boolean(model.get("include_full_transcript"));
      checkbox.addEventListener("change", () =>
        saveMany({ include_full_transcript: checkbox.checked }),
      );
      transcriptLabel.append(
        checkbox,
        element("span", "", "Include Full LLM Transcript"),
      );
      exportPanel.appendChild(transcriptLabel);
      exportPanel.appendChild(
        element(
          "p",
          "transcript-disclosure",
          "Includes complete application prompts and provider-visible responses.",
        ),
      );
    }
    const exportReady =
      Boolean(model.get("export_json")) &&
      Boolean(model.get("export_filename")) &&
      model.get("prepared_export_choice") === selectedExportChoice;
    let exportButton;
    if (exportReady) {
      const blob = new Blob([model.get("export_json")], { type: "application/json" });
      currentExportUrl = URL.createObjectURL(blob);
      exportButton = element("a", "export-button", "Export JSON");
      exportButton.href = currentExportUrl;
      exportButton.download = model.get("export_filename");
    } else {
      exportButton = element("button", "export-button", "Preparing export…");
      exportButton.type = "button";
      exportButton.disabled = true;
    }
    exportPanel.appendChild(exportButton);
    if (model.get("export_error")) {
      exportPanel.appendChild(element("p", "export-error", model.get("export_error")));
    }
  }

  function updateAll(changedName = null) {
    const modelState = model.get("state");
    const analyzeStarted =
      previousModelState !== "running" && modelState === "running";
    if (analyzeStarted) {
      state.pane = paneStateOnAnalyze(media.matches);
      applyFollowSnapshot(followState.onAnalyze());
    } else if (changedName === "interactions") {
      applyFollowSnapshot(followState.onInteractionUpdate());
    }
    activityState.className = `activity-state activity-status-${modelState}`;
    activityState.textContent = modelState;
    reconcileEvents();
    reconcileInteractions();
    renderExport();
    applyPaneState();
    const newest = newestInteractionId();
    if (state.activeInteractionId && !interactionNodes.has(state.activeInteractionId)) {
      state.activeInteractionId = null;
    }
    if (!state.activeInteractionId && newest) {
      selectInteraction(newest, "initial-selection");
    } else if (state.activeInteractionId) {
      highlightInteraction(state.activeInteractionId);
    }
    if (
      analyzeStarted ||
      (state.followLive && ["events", "interactions", "state"].includes(changedName))
    ) {
      queueMicrotask(resumeLive);
    }
    previousModelState = modelState;
  }

  const watchHandlers = new Map();
  for (const name of watched) {
    const handler = () => updateAll(name);
    watchHandlers.set(name, handler);
    model.on(`change:${name}`, handler);
  }
  updateAll();
  return () => {
    for (const [name, handler] of watchHandlers) {
      model.off(`change:${name}`, handler);
    }
    media.removeEventListener("change", handleMediaChange);
    resizeObserver.disconnect();
    scrollGuard.clear();
    activityLive.removeEventListener("scrollend", endActivityScroll);
    interactionsLive.removeEventListener("scrollend", endInteractionScroll);
    if (state.activityScrollFrame !== null) {
      cancelAnimationFrame(state.activityScrollFrame);
    }
    if (state.interactionScrollFrame !== null) {
      cancelAnimationFrame(state.interactionScrollFrame);
    }
    if (currentExportUrl) URL.revokeObjectURL(currentExportUrl);
  };
}

export default { render };
