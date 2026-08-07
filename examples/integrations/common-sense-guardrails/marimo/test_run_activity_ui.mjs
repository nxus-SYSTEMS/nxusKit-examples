import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("./run_activity.js", import.meta.url), "utf8");
const encoded = Buffer.from(source).toString("base64");
const ui = await import(`data:text/javascript;base64,${encoded}`);

const {
  createFollowState,
  createProgrammaticScrollGuard,
  isAtLiveEdge,
  latestLinkedEventId,
  liveEdgeSelectionSource,
  nearestLinkedId,
  nextLinkedInteractionId,
  nextPaneState,
  normalizePaneState,
  paneStateOnAnalyze,
  shouldRecenterOnResize,
} = ui;

assert.equal(
  isAtLiveEdge({ scrollTop: 680, clientHeight: 300, scrollHeight: 1000 }),
  true,
);
assert.equal(
  isAtLiveEdge({ scrollTop: 620, clientHeight: 300, scrollHeight: 1000 }),
  false,
);
assert.equal(nextPaneState("collapsed", false), "normal");
assert.equal(nextPaneState("normal", false), "expanded");
assert.equal(nextPaneState("expanded", false), "collapsed");
assert.equal(nextPaneState("collapsed", true), "expanded");
assert.equal(nextPaneState("expanded", true), "collapsed");
assert.equal(normalizePaneState("normal", true), "expanded");
assert.equal(normalizePaneState("collapsed", true), "collapsed");
assert.equal(normalizePaneState("unknown", false), "normal");
assert.equal(
  latestLinkedEventId({ linked_event_ids: ["event-0002", "event-0004"] }),
  "event-0004",
);
assert.equal(latestLinkedEventId({ linked_event_ids: [] }), null);
assert.equal(liveEdgeSelectionSource("activity-scroll"), "activity-scroll");
assert.equal(liveEdgeSelectionSource("interaction-scroll"), "interaction-scroll");
assert.equal(liveEdgeSelectionSource("keyboard"), "live-follow");
assert.equal(liveEdgeSelectionSource(), "live-follow");
assert.equal(shouldRecenterOnResize(true, "llm-0004", "llm-0004"), false);
assert.equal(shouldRecenterOnResize(false, "llm-0004", "llm-0004"), true);
assert.equal(shouldRecenterOnResize(false, "llm-0003", "llm-0004"), false);

const follow = createFollowState();
assert.deepEqual(follow.onAnalyze(), { following: true, unseen: 0 });
assert.deepEqual(follow.onManualScroll(false), { following: false, unseen: 0 });
assert.deepEqual(follow.onInteractionUpdate(), { following: false, unseen: 1 });
assert.deepEqual(follow.onManualScroll(false), { following: false, unseen: 1 });
assert.deepEqual(follow.onManualScroll(true), { following: true, unseen: 0 });

assert.equal(
  nearestLinkedId(
    [
      { id: "llm-0001", center: 120 },
      { id: "llm-0002", center: 310 },
    ],
    280,
  ),
  "llm-0002",
);
assert.equal(nearestLinkedId([], 280), null);
assert.equal(paneStateOnAnalyze(false), "normal");
assert.equal(paneStateOnAnalyze(true), "expanded");
assert.equal(
  nextLinkedInteractionId(["llm-0001", "llm-0002", "llm-0004"], "llm-0002", 1),
  "llm-0004",
);
assert.equal(
  nextLinkedInteractionId(["llm-0001", "llm-0002", "llm-0004"], "llm-0002", -1),
  "llm-0001",
);
assert.equal(
  nextLinkedInteractionId(["llm-0001", "llm-0002"], "llm-0002", 1),
  "llm-0002",
);

let nextTimerId = 1;
const pendingTimers = new Map();
const canceledTimers = [];
const scrollGuard = createProgrammaticScrollGuard({
  schedule(callback) {
    const id = nextTimerId;
    nextTimerId += 1;
    pendingTimers.set(id, callback);
    return id;
  },
  cancel(id) {
    canceledTimers.push(id);
    pendingTimers.delete(id);
  },
});
scrollGuard.begin("interactions", "live-follow");
assert.equal(scrollGuard.isActive("interactions"), true);
assert.equal(scrollGuard.noteScroll("interactions"), true);
assert.deepEqual(canceledTimers, [1]);
assert.equal(scrollGuard.noteScroll("activity"), false);
scrollGuard.end("interactions");
assert.equal(scrollGuard.isActive("interactions"), true);
assert.deepEqual(canceledTimers, [1, 2]);
assert.equal(pendingTimers.size, 1);
for (const callback of pendingTimers.values()) callback();
assert.equal(scrollGuard.isActive("interactions"), false);

console.log("run_activity UI state helpers: PASS");
