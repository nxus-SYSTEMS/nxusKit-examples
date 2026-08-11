import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("./research_activity.js", import.meta.url), "utf8");
const encoded = Buffer.from(source).toString("base64");
const ui = await import(`data:text/javascript;base64,${encoded}`);

const {
  linkedPairSelection,
  liveEdgeState,
  nextPaneState,
  paneLayoutState,
  scrollGuard,
} = ui;

assert.deepEqual(paneLayoutState("normal", false), {
  activity: "42%",
  interactions: "58%",
});
assert.deepEqual(paneLayoutState("expanded", false), {
  activity: "24%",
  interactions: "76%",
});
assert.deepEqual(paneLayoutState("collapsed", false), {
  activity: "100%",
  interactions: "0%",
});
assert.deepEqual(paneLayoutState("normal", true), {
  activity: "0%",
  interactions: "100%",
});
assert.equal(nextPaneState("collapsed", false), "normal");
assert.equal(nextPaneState("normal", false), "expanded");
assert.equal(nextPaneState("expanded", false), "collapsed");
assert.equal(nextPaneState("collapsed", true), "expanded");
assert.equal(nextPaneState("expanded", true), "collapsed");

assert.equal(liveEdgeState({ atBottom: false, running: true }).following, false);
assert.equal(liveEdgeState({ atBottom: true, running: true }).following, true);
assert.equal(liveEdgeState({ atBottom: true, running: false }).following, false);
assert.equal(liveEdgeState({ atBottom: true, running: false }).shouldCenter, false);

const events = [
  { id: "event-0001", interaction_id: "interaction-0001" },
  { id: "event-0002", interaction_id: "interaction-0001" },
  { id: "event-0003" },
];
const interactions = [
  {
    id: "interaction-0001",
    linked_event_ids: ["event-0001", "event-0002"],
  },
];
assert.deepEqual(
  linkedPairSelection(events, interactions, "interaction-0001"),
  { eventId: "event-0002", interactionId: "interaction-0001" },
);
assert.equal(linkedPairSelection(events, interactions, "missing"), null);

assert.equal(scrollGuard({ trusted: true, programmatic: false }), false);
assert.equal(scrollGuard({ trusted: true, programmatic: true }), true);
assert.equal(scrollGuard({ trusted: false, programmatic: false }), true);

console.log("research_activity UI state helpers: PASS");
