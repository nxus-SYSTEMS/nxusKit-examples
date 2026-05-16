//go:build nxuskit

// Example: LLM-Solver Hybrid — LLM Constraint Extraction + Solver Optimization
//
// ## nxusKit Features Demonstrated
// - LLM provider Chat API for structured constraint extraction
// - SolverSession lifecycle (create, add variables/constraints/objective, solve)
// - Mock LLM mode for offline/deterministic testing
// - Retry logic for LLM JSON parsing failures
// - Pipeline: natural language -> structured constraints -> solver optimization
//
// ## Interactive Modes
// - `--verbose` or `-v`: Show raw LLM responses and solver details
// - `--step` or `-s`: Pause at each pipeline stage with explanations
//
// ## Scenario Selection
// - `--scenario <name>`: Load a problem from ../scenarios/<name>/problem.json
// - Available scenarios: seating, dungeon, road-trip
//
// ## LLM Mode
// - `--mock` (default): Use pre-defined mock LLM response from problem.json
// - `--no-mock`: Call a live LLM provider for constraint extraction
// - `--provider <name>`: LLM provider to use (default: ollama; supported: ollama, lmstudio, openai, claude, groq, xai)
// - `--model <name>`: Model to use (default: llama3.2)
//
// Usage:
//
//	go run . --scenario seating
//	go run . --scenario dungeon --verbose
//	go run . --scenario road-trip --step
//	go run . --scenario seating --no-mock --provider ollama --model llama3.2
//
// See the solver Go example for solver-only patterns.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/nxus-SYSTEMS/nxusKit/examples/shared/go/interactive"
	"github.com/nxus-SYSTEMS/nxusKit/packages/nxuskit-go"
)

// Problem represents the JSON structure of a scenario problem file.
type Problem struct {
	Description                string          `json:"description"`
	NaturalLanguageConstraints []string        `json:"natural_language_constraints"`
	SystemPrompt               string          `json:"system_prompt"`
	SolverConfig               json.RawMessage `json:"solver_config"`
	Objective                  json.RawMessage `json:"objective"`
	MockLLMResponse            MockLLMResponse `json:"mock_llm_response"`
}

// MockLLMResponse holds the pre-defined structured response for mock mode.
type MockLLMResponse struct {
	Variables   []json.RawMessage `json:"variables"`
	Constraints []json.RawMessage `json:"constraints"`
}

// stageResult holds the outcome of a pipeline stage for the final summary.
type stageResult struct {
	name   string
	status string
	detail string
}

const maxLLMRetries = 3

func main() {
	// Parse interactive mode flags (consumes --verbose/-v and --step/-s)
	config := interactive.FromArgs()

	// Parse custom flags manually (flag package already parsed by FromArgs)
	scenario := flagValue("--scenario")
	if scenario == "" {
		scenario = flagValue("-scenario")
	}
	if scenario == "" {
		fmt.Fprintln(os.Stderr, "Error: --scenario <name> is required")
		fmt.Fprintln(os.Stderr)
		listAvailableScenarios()
		os.Exit(1)
	}

	useMock := !flagPresent("--no-mock")
	providerName := flagValue("--provider")
	if providerName == "" {
		providerName = "ollama"
	}
	model := flagValue("--model")
	if model == "" {
		model = "llama3.2"
	}

	// Resolve scenario path relative to the binary location
	scenarioDir := filepath.Join("..", "scenarios", scenario)
	problemPath := filepath.Join(scenarioDir, "problem.json")

	// Load and parse the problem file
	data, err := os.ReadFile(problemPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: cannot load scenario %q: %v\n", scenario, err)
		fmt.Fprintln(os.Stderr)
		listAvailableScenarios()
		os.Exit(1)
	}

	var problem Problem
	if err := json.Unmarshal(data, &problem); err != nil {
		fmt.Fprintf(os.Stderr, "Error: invalid problem.json: %v\n", err)
		os.Exit(1)
	}

	var results []stageResult
	pipelineStart := time.Now()

	// ══════════════════════════════════════════════════════════════
	// Pipeline Header
	// ══════════════════════════════════════════════════════════════
	fmt.Println("========================================")
	fmt.Printf("  LLM-Solver Hybrid: %s\n", scenario)
	fmt.Println("========================================")
	fmt.Println()
	fmt.Println(problem.Description)
	fmt.Println()
	fmt.Println("Pipeline stages:")
	fmt.Println("  1. Load Problem     - Parse problem definition and NL constraints")
	fmt.Println("  2. Get Constraints  - Extract structured constraints (mock or LLM)")
	fmt.Println("  3. Validate         - Check variables and constraints are well-formed")
	fmt.Println("  4. Solve            - Run constraint solver optimization")
	fmt.Println("  5. Interpret        - Human-readable result interpretation")
	fmt.Println("  6. Summary          - Pipeline statistics")
	fmt.Println()

	if useMock {
		fmt.Println("Mode: MOCK (using pre-defined LLM response)")
	} else {
		fmt.Printf("Mode: LIVE (provider=%s, model=%s)\n", providerName, model)
	}
	fmt.Println()

	if config.StepPause("Starting LLM-Solver hybrid pipeline...", []string{
		"Stage 1 loads the problem definition with natural language constraints",
		"Stage 2 converts NL constraints to structured solver format via LLM",
		"Stage 3 validates the structured output before solving",
		"Stages 4-5 run the Z3 constraint solver and interpret results",
	}) == interactive.ActionQuit {
		return
	}

	// ══════════════════════════════════════════════════════════════
	// Stage 1: Load Problem
	// ══════════════════════════════════════════════════════════════
	fmt.Println("========================================")
	fmt.Println("  Stage 1: Load Problem")
	fmt.Println("========================================")
	fmt.Println()

	if config.StepPause("Displaying problem definition and natural language constraints...", []string{
		"The problem.json defines the scenario description",
		"Natural language constraints describe requirements in plain English",
		"The LLM will convert these into structured solver constraints",
	}) == interactive.ActionQuit {
		return
	}

	fmt.Printf("Scenario: %s\n", scenario)
	fmt.Printf("Description: %s\n", problem.Description)
	fmt.Printf("NL constraints: %d\n", len(problem.NaturalLanguageConstraints))
	fmt.Println()

	fmt.Println("Natural Language Constraints:")
	for i, c := range problem.NaturalLanguageConstraints {
		fmt.Printf("  %d. %s\n", i+1, c)
	}
	fmt.Println()

	if config.IsVerbose() {
		fmt.Println("[nxusKit] System prompt:")
		fmt.Printf("  %s\n", problem.SystemPrompt)
		fmt.Println()
	}

	results = append(results, stageResult{
		name:   "Load Problem",
		status: "[OK]",
		detail: fmt.Sprintf("%d NL constraints loaded", len(problem.NaturalLanguageConstraints)),
	})

	// ══════════════════════════════════════════════════════════════
	// Stage 2: Get Structured Constraints
	// ══════════════════════════════════════════════════════════════
	fmt.Println("========================================")
	fmt.Println("  Stage 2: Get Structured Constraints")
	fmt.Println("========================================")
	fmt.Println()

	var variablesJSON []json.RawMessage
	var constraintsJSON []json.RawMessage

	if useMock {
		if config.StepPause("Using mock LLM response from problem.json...", []string{
			"Mock mode uses the pre-defined mock_llm_response from the scenario",
			"This enables deterministic, offline testing of the pipeline",
			"Use --no-mock to call a live LLM provider instead",
		}) == interactive.ActionQuit {
			return
		}

		variablesJSON = problem.MockLLMResponse.Variables
		constraintsJSON = problem.MockLLMResponse.Constraints

		fmt.Printf("Mock response: %d variables, %d constraints\n",
			len(variablesJSON), len(constraintsJSON))
		fmt.Println()

		results = append(results, stageResult{
			name:   "Get Constraints",
			status: "[OK]",
			detail: fmt.Sprintf("mock: %d variables, %d constraints", len(variablesJSON), len(constraintsJSON)),
		})
	} else {
		if config.StepPause("Calling LLM provider for constraint extraction...", []string{
			fmt.Sprintf("nxusKit: Creating %s provider", providerName),
			"Sending system prompt + NL constraints to LLM",
			"Parsing JSON response with retry logic (max 3 attempts)",
		}) == interactive.ActionQuit {
			return
		}

		// Create LLM provider
		provider, err := createProvider(providerName, model)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error creating %s provider: %v\n", providerName, err)
			fmt.Fprintln(os.Stderr, "Falling back to mock mode...")
			fmt.Println()
			variablesJSON = problem.MockLLMResponse.Variables
			constraintsJSON = problem.MockLLMResponse.Constraints

			results = append(results, stageResult{
				name:   "Get Constraints",
				status: "[FB]",
				detail: fmt.Sprintf("fallback to mock: %d variables, %d constraints", len(variablesJSON), len(constraintsJSON)),
			})
		} else {
			// Build constraint text from NL constraints
			var constraintText strings.Builder
			constraintText.WriteString("Convert the following natural language constraints into structured solver variables and constraints.\n\n")
			constraintText.WriteString("Constraints:\n")
			for i, c := range problem.NaturalLanguageConstraints {
				fmt.Fprintf(&constraintText, "%d. %s\n", i+1, c)
			}
			constraintText.WriteString("\nRespond with JSON only, containing 'variables' and 'constraints' arrays.")

			// Retry loop for LLM calls
			var llmErr error
			for attempt := 1; attempt <= maxLLMRetries; attempt++ {
				fmt.Printf("LLM attempt %d/%d...\n", attempt, maxLLMRetries)

				req := &nxuskit.ChatRequest{
					Model: model,
					Messages: []nxuskit.Message{
						nxuskit.SystemMessage(problem.SystemPrompt),
						nxuskit.UserMessage(constraintText.String()),
					},
					JSONMode: true,
				}

				resp, err := provider.Chat(context.Background(), req)
				if err != nil {
					llmErr = fmt.Errorf("LLM request failed: %w", err)
					fmt.Fprintf(os.Stderr, "  Attempt %d failed: %v\n", attempt, err)
					continue
				}

				if config.IsVerbose() {
					fmt.Println("[nxusKit] Raw LLM response:")
					fmt.Printf("  %s\n", truncate(resp.Content, config.GetVerboseLimit()))
					fmt.Println()
				}

				// Parse response JSON
				var llmResult struct {
					Variables   []json.RawMessage `json:"variables"`
					Constraints []json.RawMessage `json:"constraints"`
				}
				if err := json.Unmarshal([]byte(resp.Content), &llmResult); err != nil {
					llmErr = fmt.Errorf("failed to parse LLM JSON: %w", err)
					fmt.Fprintf(os.Stderr, "  Attempt %d: JSON parse error: %v\n", attempt, err)
					continue
				}

				if len(llmResult.Variables) == 0 {
					llmErr = fmt.Errorf("LLM returned 0 variables")
					fmt.Fprintf(os.Stderr, "  Attempt %d: empty variables array\n", attempt)
					continue
				}

				// Success
				variablesJSON = llmResult.Variables
				constraintsJSON = llmResult.Constraints
				llmErr = nil
				fmt.Printf("LLM extracted: %d variables, %d constraints\n",
					len(variablesJSON), len(constraintsJSON))
				break
			}

			if llmErr != nil {
				fmt.Fprintf(os.Stderr, "\nAll %d LLM attempts failed: %v\n", maxLLMRetries, llmErr)
				fmt.Fprintln(os.Stderr, "Falling back to mock mode...")
				fmt.Println()
				variablesJSON = problem.MockLLMResponse.Variables
				constraintsJSON = problem.MockLLMResponse.Constraints

				results = append(results, stageResult{
					name:   "Get Constraints",
					status: "[FB]",
					detail: fmt.Sprintf("fallback after %d retries: %d vars, %d constraints",
						maxLLMRetries, len(variablesJSON), len(constraintsJSON)),
				})
			} else {
				results = append(results, stageResult{
					name:   "Get Constraints",
					status: "[OK]",
					detail: fmt.Sprintf("live LLM: %d variables, %d constraints",
						len(variablesJSON), len(constraintsJSON)),
				})
			}
		}
		fmt.Println()
	}

	// ══════════════════════════════════════════════════════════════
	// Stage 3: Validate
	// ══════════════════════════════════════════════════════════════
	fmt.Println("========================================")
	fmt.Println("  Stage 3: Validate")
	fmt.Println("========================================")
	fmt.Println()

	if config.StepPause("Validating structured variables and constraints...", []string{
		"Parse each variable and constraint from JSON into typed structs",
		"Check that variables have names, types, and valid domains",
		"Check that constraints reference existing variable names",
	}) == interactive.ActionQuit {
		return
	}

	// Parse variables
	var variables []nxuskit.VariableDef
	for i, raw := range variablesJSON {
		var v nxuskit.VariableDef
		if err := json.Unmarshal(raw, &v); err != nil {
			fmt.Fprintf(os.Stderr, "Error: invalid variable at index %d: %v\n", i, err)
			os.Exit(1)
		}
		if v.Name == "" {
			fmt.Fprintf(os.Stderr, "Error: variable at index %d has no name\n", i)
			os.Exit(1)
		}
		if v.VarType == "" {
			v.VarType = nxuskit.VariableTypeInteger
		}
		variables = append(variables, v)
	}

	// Parse constraints
	var constraints []nxuskit.ConstraintDef
	for i, raw := range constraintsJSON {
		var c nxuskit.ConstraintDef
		if err := json.Unmarshal(raw, &c); err != nil {
			fmt.Fprintf(os.Stderr, "Error: invalid constraint at index %d: %v\n", i, err)
			os.Exit(1)
		}
		// Ensure parameters field is non-nil (C ABI requires it)
		if c.Parameters == nil {
			c.Parameters = map[string]any{}
		}
		constraints = append(constraints, c)
	}

	// Parse objective
	var objective nxuskit.ObjectiveDef
	if len(problem.Objective) > 0 {
		if err := json.Unmarshal(problem.Objective, &objective); err != nil {
			fmt.Fprintf(os.Stderr, "Error: invalid objective: %v\n", err)
			os.Exit(1)
		}
	}

	// Build variable name set for cross-reference checking
	varNames := make(map[string]bool)
	for _, v := range variables {
		varNames[v.Name] = true
	}

	// Check constraint variable references
	var warnings []string
	for _, c := range constraints {
		for _, vName := range c.Variables {
			if !varNames[vName] {
				warnings = append(warnings, fmt.Sprintf(
					"constraint %q references unknown variable %q", c.Name, vName))
			}
		}
	}

	fmt.Printf("Variables:   %d (all valid)\n", len(variables))
	fmt.Printf("Constraints: %d (all valid)\n", len(constraints))
	if len(warnings) > 0 {
		fmt.Printf("Warnings:    %d\n", len(warnings))
		for _, w := range warnings {
			fmt.Printf("  - %s\n", w)
		}
	}
	fmt.Println()

	if config.IsVerbose() {
		fmt.Println("[nxusKit] Parsed variables:")
		for _, v := range variables {
			label := v.Label
			if label == "" {
				label = string(v.VarType)
			}
			domainStr := ""
			if v.Domain != nil {
				if v.Domain.Min != nil && v.Domain.Max != nil {
					domainStr = fmt.Sprintf(" [%.0f..%.0f]", *v.Domain.Min, *v.Domain.Max)
				}
			}
			fmt.Printf("  - %s (%s%s): %s\n", v.Name, v.VarType, domainStr, label)
		}
		fmt.Println()

		fmt.Println("[nxusKit] Parsed constraints:")
		for _, c := range constraints {
			label := c.Label
			if label == "" {
				label = c.Name
			}
			fmt.Printf("  - %s [%s] vars=%v\n", label, c.ConstraintType, c.Variables)
		}
		fmt.Println()
	}

	results = append(results, stageResult{
		name:   "Validate",
		status: "[OK]",
		detail: fmt.Sprintf("%d variables, %d constraints, %d warnings", len(variables), len(constraints), len(warnings)),
	})

	// ══════════════════════════════════════════════════════════════
	// Stage 4: Solve
	// ══════════════════════════════════════════════════════════════
	fmt.Println("========================================")
	fmt.Println("  Stage 4: Solve")
	fmt.Println("========================================")
	fmt.Println()

	if config.StepPause("Creating solver session and optimizing...", []string{
		"nxusKit: NewSolverSession() creates a Z3 constraint solver session",
		"Variables, constraints, and objective are added from the LLM output",
		"The solver finds optimal assignments respecting all constraints",
	}) == interactive.ActionQuit {
		return
	}

	// Parse solver config
	var solverConfig *nxuskit.SolverConfig
	if len(problem.SolverConfig) > 0 {
		var sc nxuskit.SolverConfig
		if err := json.Unmarshal(problem.SolverConfig, &sc); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: invalid solver_config, using defaults: %v\n", err)
		} else {
			solverConfig = &sc
		}
	}

	// Create solver session
	// TODO(v0.8.1): Migrate to FFI solver when available
	session, err := nxuskit.NewSolverSession(solverConfig)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error creating solver session: %v\n", err)
		os.Exit(1)
	}
	defer session.Close()

	// Add variables
	if err := session.AddVariables(variables); err != nil {
		fmt.Fprintf(os.Stderr, "Error adding variables: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("Added %d variables\n", len(variables))

	// Add constraints
	if err := session.AddConstraints(constraints); err != nil {
		fmt.Fprintf(os.Stderr, "Error adding constraints: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("Added %d constraints\n", len(constraints))

	// Set objective
	if objective.Name != "" {
		if err := session.SetObjective(objective); err != nil {
			fmt.Fprintf(os.Stderr, "Error setting objective: %v\n", err)
			os.Exit(1)
		}
		fmt.Printf("Objective: %s %s\n", objective.Direction, objective.Name)
		if objective.Label != "" {
			fmt.Printf("  %s\n", objective.Label)
		}
	}
	fmt.Println()

	// Solve
	solveStart := time.Now()
	solveResult, err := session.Solve(nil)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error solving: %v\n", err)
		os.Exit(1)
	}
	solveTime := time.Since(solveStart)

	fmt.Printf("Status: %s\n", solveResult.Status)
	if solveResult.ObjectiveValue != nil {
		fmt.Printf("Objective value: %.2f\n", *solveResult.ObjectiveValue)
	}

	solverOK := solveResult.Status == nxuskit.SolveStatusSat || solveResult.Status == nxuskit.SolveStatusOptimal
	if solverOK {
		printAssignments(solveResult.Assignments)
	}

	if config.IsVerbose() {
		fmt.Printf("[nxusKit] Solve time: %s\n", solveTime)
		fmt.Printf("[nxusKit] Solve stats: %dms, %d vars, %d constraints\n",
			solveResult.Stats.SolveTimeMs, solveResult.Stats.NumVariables, solveResult.Stats.NumConstraints)
	}
	fmt.Println()

	solverDetail := fmt.Sprintf("%s, %d assignments", solveResult.Status, len(solveResult.Assignments))
	if solveResult.ObjectiveValue != nil {
		solverDetail = fmt.Sprintf("%s, obj=%.2f, %d assignments", solveResult.Status, *solveResult.ObjectiveValue, len(solveResult.Assignments))
	}
	results = append(results, stageResult{
		name:   "Solve",
		status: statusIcon(solveResult.Status),
		detail: solverDetail,
	})

	// ══════════════════════════════════════════════════════════════
	// Stage 5: Interpret
	// ══════════════════════════════════════════════════════════════
	fmt.Println("========================================")
	fmt.Println("  Stage 5: Interpret Results")
	fmt.Println("========================================")
	fmt.Println()

	if !solverOK {
		fmt.Println("No feasible solution found. Cannot interpret results.")
		fmt.Println()
		results = append(results, stageResult{
			name:   "Interpret",
			status: "[--]",
			detail: "skipped (no feasible solution)",
		})
	} else {
		if config.StepPause("Interpreting solver assignments for this scenario...", []string{
			"Each scenario has a custom interpretation of variable assignments",
			"Assignments are grouped and presented in human-readable form",
		}) == interactive.ActionQuit {
			return
		}

		interpretResults(scenario, solveResult.Assignments)
		fmt.Println()

		results = append(results, stageResult{
			name:   "Interpret",
			status: "[OK]",
			detail: fmt.Sprintf("scenario=%s, %d assignments interpreted", scenario, len(solveResult.Assignments)),
		})
	}

	// ══════════════════════════════════════════════════════════════
	// Stage 6: Summary
	// ══════════════════════════════════════════════════════════════
	pipelineTime := time.Since(pipelineStart)

	fmt.Println("========================================")
	fmt.Println("  Pipeline Summary")
	fmt.Println("========================================")
	fmt.Println()
	for i, r := range results {
		fmt.Printf("  %d. %-5s %-25s %s\n", i+1, r.status, r.name, r.detail)
	}
	fmt.Printf("\nTotal pipeline time: %s\n", pipelineTime.Truncate(time.Millisecond))
	fmt.Println()
	fmt.Println("Done.")
}

// ── LLM Provider Factory ─────────────────────────────────────────

// createProvider creates an LLM provider by name.
func createProvider(name, model string) (nxuskit.LLMProvider, error) {
	switch strings.ToLower(name) {
	case "ollama":
		return nxuskit.NewOllamaFFIProvider()
	case "lmstudio":
		return nxuskit.NewLmStudioFFIProvider()
	case "openai":
		return nxuskit.NewOpenAIFFIProvider()
	case "claude":
		return nxuskit.NewClaudeFFIProvider()
	case "groq":
		return nxuskit.NewGroqFFIProvider()
	case "xai":
		return nxuskit.NewXaiFFIProvider()
	default:
		return nil, fmt.Errorf("unknown provider %q (supported: ollama, lmstudio, openai, claude, groq, xai)", name)
	}
}

// ── Result Interpretation ─────────────────────────────────────────

// interpretResults prints a human-readable interpretation of solver results.
func interpretResults(scenario string, assignments map[string]nxuskit.SolverValue) {
	switch scenario {
	case "seating":
		interpretSeating(assignments)
	case "dungeon":
		interpretDungeon(assignments)
	case "road-trip":
		interpretRoadTrip(assignments)
	default:
		fmt.Println("No custom interpretation for this scenario.")
		fmt.Println("Raw assignments:")
		printAssignments(assignments)
	}
}

// interpretSeating displays wedding seating assignments grouped by table.
func interpretSeating(assignments map[string]nxuskit.SolverValue) {
	fmt.Println("Wedding Seating Arrangement:")
	fmt.Println()

	// Group guests by table
	tables := make(map[int][]string)
	for name, val := range assignments {
		if strings.HasPrefix(name, "guest_") && strings.HasSuffix(name, "_table") {
			guest := strings.TrimPrefix(name, "guest_")
			guest = strings.TrimSuffix(guest, "_table")
			guest = strings.ReplaceAll(guest, "_", " ")
			table := toInt(val)
			tables[table] = append(tables[table], guest)
		}
	}

	// Print tables in order
	tableNums := sortedIntKeys(tables)
	for _, t := range tableNums {
		guests := tables[t]
		sort.Strings(guests)
		fmt.Printf("  Table %d: %s\n", t, strings.Join(guests, ", "))
	}
}

// interpretDungeon displays dungeon room layout.
func interpretDungeon(assignments map[string]nxuskit.SolverValue) {
	fmt.Println("Dungeon Layout:")
	fmt.Println()

	// Extract key assignments
	bossRoom := 0
	entryRoom := 0
	var treasureRooms []int
	difficulties := make(map[int]int)

	for name, val := range assignments {
		switch {
		case name == "boss_room":
			bossRoom = toInt(val)
		case name == "entry_room":
			entryRoom = toInt(val)
		case strings.HasPrefix(name, "treasure_room_"):
			treasureRooms = append(treasureRooms, toInt(val))
		case strings.HasPrefix(name, "room_") && strings.HasSuffix(name, "_difficulty"):
			roomStr := strings.TrimPrefix(name, "room_")
			roomStr = strings.TrimSuffix(roomStr, "_difficulty")
			room := 0
			for _, c := range roomStr {
				if c >= '0' && c <= '9' {
					room = room*10 + int(c-'0')
				}
			}
			if room > 0 {
				difficulties[room] = toInt(val)
			}
		}
	}

	sort.Ints(treasureRooms)

	for room := 1; room <= 5; room++ {
		label := ""
		switch {
		case room == entryRoom:
			label = " [ENTRY]"
		case room == bossRoom:
			label = " [BOSS]"
		}
		for _, tr := range treasureRooms {
			if tr == room {
				label += " [TREASURE]"
				break
			}
		}
		diff := difficulties[room]
		bar := strings.Repeat("#", diff)
		fmt.Printf("  Room %d: difficulty=%2d %s%s\n", room, diff, bar, label)
	}
}

// interpretRoadTrip displays road trip itinerary.
func interpretRoadTrip(assignments map[string]nxuskit.SolverValue) {
	fmt.Println("Road Trip Itinerary:")
	fmt.Println()

	// Extract park data
	type parkInfo struct {
		name  string
		days  int
		order int
	}

	parks := make(map[string]*parkInfo)
	parkNames := []string{"yosemite", "yellowstone", "zion", "glacier", "grand_canyon"}
	displayNames := map[string]string{
		"yosemite":     "Yosemite",
		"yellowstone":  "Yellowstone",
		"zion":         "Zion",
		"glacier":      "Glacier",
		"grand_canyon": "Grand Canyon",
	}

	for _, pn := range parkNames {
		parks[pn] = &parkInfo{name: displayNames[pn]}
	}

	for name, val := range assignments {
		if strings.HasPrefix(name, "days_at_") {
			park := strings.TrimPrefix(name, "days_at_")
			if info, ok := parks[park]; ok {
				info.days = toInt(val)
			}
		}
		if strings.HasPrefix(name, "visit_order_") {
			park := strings.TrimPrefix(name, "visit_order_")
			if info, ok := parks[park]; ok {
				info.order = toInt(val)
			}
		}
	}

	// Sort parks by visit order
	type orderedPark struct {
		info *parkInfo
	}
	var ordered []*parkInfo
	for _, pn := range parkNames {
		ordered = append(ordered, parks[pn])
	}
	sort.Slice(ordered, func(i, j int) bool {
		return ordered[i].order < ordered[j].order
	})

	totalDays := 0
	for i, p := range ordered {
		if p.order > 0 {
			bar := strings.Repeat("*", p.days)
			fmt.Printf("  Stop %d: %-15s %d days %s\n", i+1, p.name, p.days, bar)
			totalDays += p.days
		}
	}
	fmt.Printf("\n  Total: %d / 14 days allocated\n", totalDays)
}

// ── Display Helpers ───────────────────────────────────────────────

// printAssignments displays variable assignments in sorted order.
func printAssignments(assignments map[string]nxuskit.SolverValue) {
	if len(assignments) == 0 {
		return
	}
	fmt.Println("Assignments:")

	keys := make([]string, 0, len(assignments))
	for k := range assignments {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	for _, k := range keys {
		v := assignments[k]
		fmt.Printf("  %-30s = %v\n", k, formatValue(v))
	}
}

// formatValue renders a SolverValue for display.
func formatValue(v nxuskit.SolverValue) string {
	switch val := v.Value.(type) {
	case bool:
		if val {
			return "true"
		}
		return "false"
	case float64:
		if v.Type == "integer" || val == float64(int64(val)) {
			return fmt.Sprintf("%.0f", val)
		}
		return fmt.Sprintf("%.4f", val)
	case string:
		return val
	default:
		return fmt.Sprintf("%v", v.Value)
	}
}

// statusIcon returns a text indicator for the solve status.
func statusIcon(status nxuskit.SolveStatus) string {
	switch status {
	case nxuskit.SolveStatusSat, nxuskit.SolveStatusOptimal:
		return "[OK]"
	case nxuskit.SolveStatusUnsat:
		return "[!!]"
	case nxuskit.SolveStatusTimeout:
		return "[TO]"
	default:
		return "[??]"
	}
}

// toInt converts a SolverValue to an integer.
func toInt(v nxuskit.SolverValue) int {
	switch val := v.Value.(type) {
	case float64:
		return int(val)
	case int64:
		return int(val)
	case int:
		return val
	default:
		return 0
	}
}

// truncate limits a string to maxLen characters.
func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}

// sortedIntKeys returns the keys of a map[int]V in sorted order.
func sortedIntKeys[V any](m map[int]V) []int {
	keys := make([]int, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Ints(keys)
	return keys
}

// ── CLI Helpers ───────────────────────────────────────────────────

// flagValue extracts the value for a flag like "--scenario seating" from
// os.Args. Returns "" if not found.
func flagValue(name string) string {
	args := os.Args[1:]
	for i, arg := range args {
		if arg == name && i+1 < len(args) {
			return args[i+1]
		}
		if strings.HasPrefix(arg, name+"=") {
			return strings.TrimPrefix(arg, name+"=")
		}
	}
	return ""
}

// flagPresent checks if a boolean flag is present in os.Args.
func flagPresent(name string) bool {
	for _, arg := range os.Args[1:] {
		if arg == name {
			return true
		}
	}
	return false
}

// listAvailableScenarios prints the available scenario directories.
func listAvailableScenarios() {
	scenariosDir := filepath.Join("..", "scenarios")
	entries, err := os.ReadDir(scenariosDir)
	if err != nil {
		fmt.Fprintln(os.Stderr, "Available scenarios: seating, dungeon, road-trip")
		return
	}
	fmt.Fprintln(os.Stderr, "Available scenarios:")
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		// Verify problem.json exists
		pPath := filepath.Join(scenariosDir, e.Name(), "problem.json")
		if _, err := os.Stat(pPath); err == nil {
			fmt.Fprintf(os.Stderr, "  - %s\n", e.Name())
		}
	}
}
