import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import * as controls from "./workbench_controls.js";
import {
  buildSubmittedRequest,
  runActionAvailability,
} from "./workbench_controls.js";

const source = readFileSync(new URL("./workbench_controls.js", import.meta.url), "utf8");

test("Run requires a usable config and complete Live selection", () => {
  assert.deepEqual(
    runActionAvailability({
      configEnabled: true,
      mode: "live",
      provider: "ollama",
      model: null,
      runActive: false,
    }),
    { enabled: false, reason: "live_selection_incomplete" },
  );
  assert.deepEqual(
    runActionAvailability({
      configEnabled: true,
      mode: "mock",
      provider: null,
      model: null,
      runActive: false,
    }),
    { enabled: true, reason: null },
  );
});

test("submitted state is an immutable explicit snapshot", () => {
  const state = {
    configId: "nxuskit-harness-basic.yaml",
    mode: "live",
    provider: "ollama",
    model: "qwen3.5:4b",
    includeTests: "ticket-routing, regression",
    excludeTests: "slow",
    allowExternal: false,
    writeReports: false,
  };
  const request = buildSubmittedRequest(state);
  state.model = "changed-later";

  assert.equal(request.model, "qwen3.5:4b");
  assert.deepEqual(request.include_tests, ["ticket-routing", "regression"]);
  assert.deepEqual(request.exclude_tests, ["slow"]);
});

test("configuration controls explain fixture, filters, and the submitted action", () => {
  assert.match(source, /Fixture — deterministic synthetic evidence/);
  assert.match(source, /Blank runs all configured tests/);
  assert.match(source, /Run Evaluation/);
  assert.doesNotMatch(source, /Run evaluation/);
});

test("external acknowledgement is enabled only for external adapter configs", () => {
  assert.equal(typeof controls.contextualControlState, "function");
  assert.equal(
    controls.contextualControlState("safe-built-in").allowExternal.disabled,
    true,
  );
  assert.equal(
    controls.contextualControlState("external-adapter").allowExternal.disabled,
    false,
  );
});

test("checkbox help is a description instead of duplicated label text", () => {
  assert.match(source, /checkbox\.setAttribute\("aria-describedby", helpId\)/);
  assert.match(source, /info\.setAttribute\("aria-hidden", "true"\)/);
  assert.doesNotMatch(source, /info\.setAttribute\("aria-label", help\)/);
});

test("engine cards distinguish availability from configured use", () => {
  assert.equal(typeof controls.engineUsageState, "function");
  assert.deepEqual(controls.engineUsageState({ id: "solver", enabled: true }, []), {
    code: "available_not_used",
    label: "Available, Not Used",
  });
  assert.equal(
    controls.engineUsageState({ id: "clips", enabled: true }, ["clips"]).label,
    "Used by This Configuration",
  );
  assert.equal(
    controls.engineUsageState({ id: "bn", enabled: false }, ["bn"]).label,
    "Unavailable",
  );
});
