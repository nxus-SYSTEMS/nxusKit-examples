import assert from "node:assert/strict";

import * as reasoningControls from "./reasoning_controls.js";

const {
  buildSubmittedRequest,
  hasSelectedApplicableEngine,
  modeDisabledForState,
  modeOptionPresentation,
  providerControlPresentation,
  scenarioModePresentation,
} = reasoningControls;

const engines = [
  { id: "clips", enabled: true, applicable: true },
  { id: "bn", enabled: true, applicable: false },
  { id: "solver", enabled: false, applicable: true },
];

assert.equal(hasSelectedApplicableEngine(engines, []), false);
assert.equal(hasSelectedApplicableEngine(engines, ["bn"]), false);
assert.equal(hasSelectedApplicableEngine(engines, ["solver"]), false);
assert.equal(hasSelectedApplicableEngine(engines, ["clips"]), true);
assert.equal(hasSelectedApplicableEngine(engines, ["clips", "bn"]), true);

const compatibilityCode =
  "coupon_live_strict_schema_transport_unavailable_v1_0_5";
const couponModes = [
  { id: "fixture", label: "Fixture", enabled: true, resolved_mode: "fixture" },
  {
    id: "auto",
    label: "Auto",
    enabled: true,
    resolved_mode: "fixture",
    message: "Coupon stack Auto uses fixtures.",
  },
  {
    id: "live",
    label: "Live",
    enabled: false,
    compatibility_code: compatibilityCode,
    message:
      "Unavailable for Coupon stack with nxusKit v1.0.5: strict schema transport is unavailable.",
  },
];
const globalProvider = {
  id: "claude",
  enabled: true,
  selectable: false,
  applicable: false,
  status: "available",
  reason: "Credential name detected.",
  applicability_reason: "Coupon stack does not contact providers on v1.0.5.",
};

assert.deepEqual(
  couponModes.map((mode) => modeOptionPresentation(mode)),
  [
    { label: "Fixture", disabled: false, title: "" },
    { label: "Auto — Fixture", disabled: false, title: "Coupon stack Auto uses fixtures." },
    {
      label: "Live — unavailable (v1.0.5 strict schema)",
      disabled: true,
      title:
        "Unavailable for Coupon stack with nxusKit v1.0.5: strict schema transport is unavailable.",
    },
  ],
);
assert.equal(modeDisabledForState(couponModes[1], "coupon-stack", true), false);
assert.equal(modeDisabledForState(couponModes[2], "coupon-stack", false), true);
assert.equal(
  modeDisabledForState(
    { id: "auto", label: "Auto", enabled: true },
    "car-wash",
    true,
  ),
  true,
);
assert.deepEqual(scenarioModePresentation("coupon-stack", couponModes), {
  badge: "v1.0.5 · Fixture-backed",
  summary: "Coupon stack Auto uses fixtures.",
});
assert.deepEqual(providerControlPresentation(globalProvider), {
  disabled: true,
  scenarioInapplicable: true,
  globallyUnavailable: false,
  title:
    "Credential name detected. Coupon stack does not contact providers on v1.0.5.",
});
assert.equal(
  providerControlPresentation({ ...globalProvider, applicable: true, selectable: true })
    .disabled,
  false,
);

const analyzeAvailability = (overrides = {}) =>
  reasoningControls.analyzeActionAvailability?.({
    scenario: "coupon-stack",
    mode: "auto",
    modes: couponModes,
    fixtureLlmOverride: true,
    hasApplicableEngine: true,
    runActive: false,
    provider: null,
    model: null,
    ...overrides,
  });

assert.equal(
  analyzeAvailability()?.enabled,
  true,
  "coupon Auto must remain analyzable when the fixture LLM override is active",
);
assert.equal(
  analyzeAvailability({ mode: "fixture" })?.enabled,
  true,
  "coupon Fixture must remain analyzable",
);
assert.equal(
  analyzeAvailability({
    mode: "live",
    provider: "claude",
    model: "claude-sonnet-4-6",
  })?.enabled,
  false,
  "coupon Live must remain unavailable",
);
assert.equal(
  analyzeAvailability({
    scenario: "car-wash",
    mode: "auto",
    modes: [
      { id: "fixture", enabled: true },
      { id: "auto", enabled: true },
      { id: "live", enabled: true },
    ],
  })?.enabled,
  false,
  "noncoupon Auto must remain disabled under the fixture LLM override",
);
assert.equal(
  analyzeAvailability({
    scenario: "car-wash",
    mode: "live",
    modes: [
      { id: "fixture", enabled: true },
      { id: "auto", enabled: true },
      { id: "live", enabled: true },
    ],
    provider: "claude",
    model: "claude-sonnet-4-6",
  })?.enabled,
  false,
  "noncoupon Live must remain disabled under the fixture LLM override",
);
assert.equal(
  analyzeAvailability({ hasApplicableEngine: false })?.enabled,
  false,
  "Analyze still requires an applicable selected engine",
);
assert.equal(
  analyzeAvailability({ runActive: true })?.enabled,
  false,
  "Analyze must remain disabled while a run is active",
);
assert.equal(
  analyzeAvailability({
    scenario: "car-wash",
    mode: "live",
    modes: [
      { id: "fixture", enabled: true },
      { id: "auto", enabled: true },
      { id: "live", enabled: true },
    ],
    fixtureLlmOverride: false,
  })?.enabled,
  false,
  "Live still requires a selected provider and model",
);
assert.equal(
  analyzeAvailability({
    scenario: "car-wash",
    mode: "live",
    modes: [
      { id: "fixture", enabled: true },
      { id: "auto", enabled: true },
      { id: "live", enabled: true },
    ],
    fixtureLlmOverride: false,
    provider: "claude",
    model: "claude-sonnet-4-6",
  })?.enabled,
  true,
  "Live remains analyzable when its existing provider/model requirements are met",
);
assert.deepEqual(
  buildSubmittedRequest({
    scenario: "coupon-stack",
    mode: "auto",
    provider: "claude",
    model: "claude-sonnet-4-6",
    mechanisms: ["clips"],
    maxRepairAttempts: 3,
  }),
  {
    scenario: "coupon-stack",
    mode: "auto",
    provider: null,
    model: null,
    mechanisms: ["clips"],
    max_repair_attempts: 3,
  },
);

console.log("reasoning controls selection helpers: PASS");
