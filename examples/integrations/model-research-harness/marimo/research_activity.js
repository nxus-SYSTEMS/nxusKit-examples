const LIVE_EDGE_THRESHOLD = 32;

export function paneLayoutState(pane, narrow) {
  if (narrow) {
    return pane === "collapsed"
      ? { activity: "100%", interactions: "0%" }
      : { activity: "0%", interactions: "100%" };
  }
  return {
    collapsed: { activity: "100%", interactions: "0%" },
    normal: { activity: "42%", interactions: "58%" },
    expanded: { activity: "24%", interactions: "76%" },
  }[pane] || { activity: "42%", interactions: "58%" };
}

export function nextPaneState(pane, narrow) {
  if (narrow) return pane === "collapsed" ? "expanded" : "collapsed";
  if (pane === "collapsed") return "normal";
  if (pane === "normal") return "expanded";
  return "collapsed";
}

export function liveEdgeState({ atBottom, running }) {
  const following = Boolean(atBottom && running);
  return { following, shouldCenter: following };
}

export function linkedPairSelection(events, interactions, interactionId) {
  const interaction = interactions.find((item) => item.id === interactionId);
  if (!interaction) return null;
  const links = interaction.linked_event_ids || [];
  const eventId = [...links].reverse().find((id) =>
    events.some((event) => event.id === id && event.interaction_id === interactionId),
  );
  return eventId ? { eventId, interactionId } : null;
}

export function scrollGuard({ trusted, programmatic }) {
  return !trusted || programmatic;
}

function isAtBottom(viewport) {
  return (
    viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight <=
    LIVE_EDGE_THRESHOLD
  );
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function timestamp(value) {
  return String(value || "").split("T")[1] || String(value || "");
}

function appendText(parent, label, content, className = "") {
  const section = element("section", `interaction-section ${className}`.trim());
  section.appendChild(element("h4", "interaction-section-title", label));
  section.appendChild(element("pre", "interaction-text", String(content ?? "")));
  parent.appendChild(section);
}

function updateEventRow(row, event) {
  row.className = `activity-event status-${event.status}`;
  row.dataset.eventId = event.id;
  if (event.interaction_id) {
    row.dataset.interactionId = event.interaction_id;
    row.tabIndex = 0;
  } else {
    delete row.dataset.interactionId;
    row.tabIndex = -1;
  }
  row.setAttribute(
    "aria-label",
    `${event.summary}; ${event.interaction_id ? "linked model interaction" : "no model interaction"}`,
  );
  row.replaceChildren(
    element("time", "activity-time", timestamp(event.timestamp)),
    element("span", "activity-status", event.status),
    element(
      "span",
      event.interaction_id ? "activity-link" : "activity-unlinked",
      event.interaction_id ? event.interaction_id.replace("interaction-", "Model ") : "No model call",
    ),
    element("span", "activity-phase", event.phase),
    element("span", "activity-summary", event.summary),
  );
}

function updateInteractionCard(card, interaction, isNew) {
  const wasOpen = card.open;
  card.className = `interaction-card status-${interaction.status}`;
  card.dataset.interactionId = interaction.id;
  const summary = element("summary", "interaction-summary");
  summary.append(
    element(
      "span",
      "interaction-title",
      `${interaction.id.replace("interaction-", "Model Interaction ")} · ${interaction.test_id}`,
    ),
    element("span", "interaction-status", interaction.status),
  );
  const body = element("div", "interaction-body");
  body.appendChild(
    element(
      "p",
      "interaction-provenance",
      `${interaction.provenance_label} · ${interaction.provider} / ${interaction.model}`,
    ),
  );
  if (interaction.system_prompt) {
    appendText(body, "System Prompt", interaction.system_prompt);
  }
  appendText(body, "User Prompt", interaction.user_prompt);
  if (interaction.status === "requested") {
    appendText(body, "Response", "Waiting for response…", "interaction-waiting");
  } else if (interaction.status === "error") {
    appendText(body, "Safe Error", interaction.error || "Provider interaction failed.");
  } else {
    appendText(body, "Response", interaction.response || "");
  }
  if (interaction.status === "evaluated") {
    appendText(body, "Parsed Result", JSON.stringify(interaction.parsed, null, 2));
    const assertions = element("ul", "assertion-list");
    for (const assertion of interaction.assertions || []) {
      assertions.appendChild(
        element(
          "li",
          `status-${assertion.status}`,
          `${assertion.type}: ${assertion.status}${assertion.detail ? ` — ${assertion.detail}` : ""}`,
        ),
      );
    }
    const assertionSection = element("section", "interaction-section");
    assertionSection.append(
      element("h4", "interaction-section-title", "Assertions"),
      assertions,
    );
    body.appendChild(assertionSection);
    appendText(body, "Policy", JSON.stringify(interaction.policy || {}, null, 2));
  }
  card.replaceChildren(summary, body);
  card.open = isNew || wasOpen || interaction.status === "requested";
}

function render({ model, el }) {
  const eventNodes = new Map();
  const interactionNodes = new Map();
  const state = {
    pane: "normal",
    following: true,
    activeInteractionId: null,
    programmatic: new WeakSet(),
  };
  const media = window.matchMedia("(max-width: 760px)");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  const root = element("section", "research-activity-card");
  const split = element("div", "research-split");
  const activityPane = element("section", "activity-pane");
  const activityHeader = element("header", "pane-header");
  activityHeader.append(
    element("h3", "pane-title", "Run Activity"),
    element("span", "run-state"),
  );
  const activityViewport = element("div", "activity-viewport");
  activityViewport.tabIndex = 0;
  activityViewport.setAttribute("role", "region");
  activityViewport.setAttribute("aria-label", "Run Activity events");
  activityViewport.setAttribute("aria-live", "polite");
  const activityEmpty = element("p", "empty-state", "No submitted evaluation yet.");
  const eventList = element("ol", "event-list");
  activityViewport.append(activityEmpty, eventList);
  activityPane.append(activityHeader, activityViewport);

  const separator = element("button", "pane-separator");
  separator.type = "button";

  const interactionPane = element("section", "interaction-pane");
  const interactionHeader = element("header", "pane-header");
  interactionHeader.append(
    element("h3", "pane-title", "Model Interactions"),
    element("span", "interaction-count"),
  );
  const jumpToLive = element("button", "jump-live", "↓ Live");
  jumpToLive.type = "button";
  jumpToLive.hidden = true;
  interactionHeader.appendChild(jumpToLive);
  const interactionViewport = element("div", "interaction-viewport");
  interactionViewport.tabIndex = 0;
  interactionViewport.setAttribute("role", "region");
  interactionViewport.setAttribute("aria-label", "Model prompts and responses");
  interactionViewport.setAttribute("aria-live", "polite");
  const interactionEmpty = element(
    "p",
    "empty-state",
    "No model interaction occurred for this evaluation.",
  );
  const interactionList = element("div", "interaction-list");
  interactionViewport.append(interactionEmpty, interactionList);
  interactionPane.append(interactionHeader, interactionViewport);
  split.append(activityPane, separator, interactionPane);
  root.appendChild(split);
  el.replaceChildren(root);

  function running() {
    return model.get("run_state") === "running";
  }

  function applyPane() {
    if (media.matches && state.pane === "normal") state.pane = "expanded";
    const layout = paneLayoutState(state.pane, media.matches);
    split.style.setProperty("--activity-width", layout.activity);
    split.style.setProperty("--interaction-width", layout.interactions);
    split.dataset.pane = state.pane;
    const visible = layout.interactions !== "0%";
    separator.textContent = `Model Interactions: ${state.pane}`;
    separator.setAttribute("aria-expanded", String(visible));
    separator.setAttribute(
      "aria-label",
      `Model Interactions pane is ${state.pane}; activate to change pane size`,
    );
  }

  function markProgrammatic(viewport) {
    state.programmatic.add(viewport);
    setTimeout(() => state.programmatic.delete(viewport), 360);
  }

  function center(node, viewport) {
    if (!node) return;
    markProgrammatic(viewport);
    node.scrollIntoView({
      block: "center",
      inline: "nearest",
      behavior: reducedMotion.matches ? "auto" : "smooth",
    });
  }

  function highlight(interactionId) {
    state.activeInteractionId = interactionId;
    for (const row of eventNodes.values()) {
      row.classList.toggle("active-pair", row.dataset.interactionId === interactionId);
    }
    for (const [id, card] of interactionNodes) {
      card.classList.toggle("active-pair", id === interactionId);
    }
  }

  function selectPair(interactionId, source) {
    const pair = linkedPairSelection(
      model.get("events") || [],
      model.get("interactions") || [],
      interactionId,
    );
    if (!pair) return;
    highlight(interactionId);
    const card = interactionNodes.get(interactionId);
    if (card && !["interaction-scroll", "interaction-click"].includes(source)) {
      card.open = true;
      center(card, interactionViewport);
    }
    if (!["activity-scroll", "activity-click"].includes(source)) {
      center(eventNodes.get(pair.eventId), activityViewport);
    }
  }

  function newestInteractionId() {
    const interactions = model.get("interactions") || [];
    return interactions.length ? interactions[interactions.length - 1].id : null;
  }

  function jumpLive() {
    if (!running()) return;
    state.following = true;
    jumpToLive.hidden = true;
    const newest = newestInteractionId();
    if (newest) selectPair(newest, "live");
    markProgrammatic(activityViewport);
    activityViewport.scrollTop = activityViewport.scrollHeight;
    markProgrammatic(interactionViewport);
    interactionViewport.scrollTop = interactionViewport.scrollHeight;
  }

  function nearestInteraction(viewport, nodes) {
    const bounds = viewport.getBoundingClientRect();
    const centerPoint = bounds.top + bounds.height / 2;
    let selected = null;
    let distance = Number.POSITIVE_INFINITY;
    for (const [id, node] of nodes) {
      const rect = node.getBoundingClientRect();
      const candidate = Math.abs(rect.top + rect.height / 2 - centerPoint);
      if (candidate < distance) {
        selected = id;
        distance = candidate;
      }
    }
    return selected;
  }

  function handleScroll(event, viewport, source) {
    if (scrollGuard({
      trusted: event.isTrusted,
      programmatic: state.programmatic.has(viewport),
    })) return;
    const edge = liveEdgeState({ atBottom: isAtBottom(viewport), running: running() });
    state.following = edge.following;
    jumpToLive.hidden = state.following || !running();
    if (edge.shouldCenter) {
      jumpLive();
      return;
    }
    if (!running() && isAtBottom(viewport)) return;
    const selected =
      source === "activity-scroll"
        ? nearestInteraction(
            viewport,
            [...eventNodes]
              .filter(([, node]) => node.dataset.interactionId)
              .map(([, node]) => [node.dataset.interactionId, node]),
          )
        : nearestInteraction(viewport, interactionNodes);
    if (selected) selectPair(selected, source);
  }

  activityViewport.addEventListener("scroll", (event) =>
    handleScroll(event, activityViewport, "activity-scroll"),
  );
  interactionViewport.addEventListener("scroll", (event) =>
    handleScroll(event, interactionViewport, "interaction-scroll"),
  );
  jumpToLive.addEventListener("click", jumpLive);
  separator.addEventListener("click", () => {
    state.pane = nextPaneState(state.pane, media.matches);
    applyPane();
  });
  media.addEventListener("change", applyPane);

  split.addEventListener("keydown", (event) => {
    const direction = event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
    if (!direction) return;
    const ids = [...interactionNodes.keys()];
    if (!ids.length) return;
    const current = ids.indexOf(state.activeInteractionId);
    const next = Math.max(0, Math.min(ids.length - 1, (current < 0 ? 0 : current) + direction));
    event.preventDefault();
    state.following = false;
    selectPair(ids[next], "keyboard");
  });

  function reconcileEvents() {
    const events = model.get("events") || [];
    const wanted = new Set(events.map((item) => item.id));
    for (const [id, node] of eventNodes) {
      if (!wanted.has(id)) {
        node.remove();
        eventNodes.delete(id);
      }
    }
    for (const item of events) {
      let row = eventNodes.get(item.id);
      if (!row) {
        row = element("li", "activity-event");
        row.addEventListener("click", () => {
          if (row.dataset.interactionId) {
            state.following = false;
            selectPair(row.dataset.interactionId, "activity-click");
          }
        });
        eventNodes.set(item.id, row);
      }
      updateEventRow(row, item);
      eventList.appendChild(row);
    }
    activityEmpty.hidden = events.length > 0;
    eventList.hidden = events.length === 0;
  }

  function reconcileInteractions() {
    const interactions = model.get("interactions") || [];
    const wanted = new Set(interactions.map((item) => item.id));
    for (const [id, node] of interactionNodes) {
      if (!wanted.has(id)) {
        node.remove();
        interactionNodes.delete(id);
      }
    }
    for (const item of interactions) {
      let card = interactionNodes.get(item.id);
      const isNew = !card;
      if (!card) {
        card = document.createElement("details");
        card.addEventListener("click", () => {
          state.following = false;
          selectPair(card.dataset.interactionId, "interaction-click");
        });
        card.addEventListener("toggle", () => {
          if (card.open && state.activeInteractionId === card.dataset.interactionId) {
            selectPair(card.dataset.interactionId, "interaction-click");
          }
        });
        interactionNodes.set(item.id, card);
      }
      updateInteractionCard(card, item, isNew);
      interactionList.appendChild(card);
    }
    interactionHeader.querySelector(".interaction-count").textContent = String(interactions.length);
    interactionEmpty.hidden = interactions.length > 0;
    interactionList.hidden = interactions.length === 0;
  }

  function update(changedName) {
    if (changedName === "generation") {
      state.following = true;
      state.activeInteractionId = null;
      state.pane = media.matches ? "expanded" : "normal";
      jumpToLive.hidden = true;
    }
    const stateLabel = activityHeader.querySelector(".run-state");
    stateLabel.textContent = model.get("run_state");
    stateLabel.className = `run-state status-${model.get("run_state")}`;
    reconcileEvents();
    reconcileInteractions();
    applyPane();
    if (running() && state.following && ["events", "interactions", "run_state"].includes(changedName)) {
      queueMicrotask(jumpLive);
    }
    if (!running()) jumpToLive.hidden = true;
  }

  const watched = ["events", "interactions", "run_state", "generation", "final_status", "safe_message"];
  const handlers = new Map();
  for (const name of watched) {
    const handler = () => update(name);
    handlers.set(name, handler);
    model.on(`change:${name}`, handler);
  }
  update(null);

  return () => {
    for (const [name, handler] of handlers) model.off(`change:${name}`, handler);
    media.removeEventListener("change", applyPane);
  };
}

export default { render };
