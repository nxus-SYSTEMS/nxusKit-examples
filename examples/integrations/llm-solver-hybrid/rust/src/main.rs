//! LLM-Solver Hybrid Example (E4) — nxusKit SDK
//!
//! Demonstrates LLM -> structured constraints -> solver optimization with retry logic.
//! The pipeline can run in **mock mode** (pre-computed LLM responses from problem.json)
//! or **live mode** (calling a real LLM API via the nxusKit Rust SDK).
//!
//! Usage:
//!   cargo run -- --scenario seating [--verbose] [--step] [--no-mock --provider ollama --model llama3.2]
//!   Supported live providers include ollama, lmstudio, openai, claude, groq, and xai.

use std::collections::HashSet;
use std::path::PathBuf;
use std::time::Instant;

use clap::Parser;
use nxuskit::solver::SolverSession;
use nxuskit::solver_types::*;
use nxuskit::{ChatRequest, Message, NxuskitProvider, ProviderConfig, ResponseFormat};
use serde::Deserialize;

// ── CLI Arguments ───────────────────────────────────────────────────

#[derive(Parser, Debug)]
#[command(name = "llm-solver-hybrid-example")]
#[command(about = "Demonstrates LLM -> structured constraints -> solver optimization")]
struct Args {
    /// Scenario to run: seating, dungeon, or road-trip
    #[arg(short = 'S', long, default_value = "seating")]
    scenario: String,

    /// Enable verbose output showing raw JSON payloads
    #[arg(short, long)]
    verbose: bool,

    /// Enable step-through mode with explanations at each phase
    #[arg(short, long)]
    step: bool,

    /// Use mock LLM response from problem.json instead of calling real LLM
    /// Pass --mock false to use live LLM
    #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
    mock: bool,

    /// LLM provider name (e.g., "ollama", "claude", "openai", "groq", "xai")
    #[arg(long, default_value = "ollama")]
    provider: String,

    /// Model name for LLM provider
    #[arg(long, default_value = "llama3.2")]
    model: String,

    /// API key for the LLM provider (reads from env if not set)
    #[arg(long, env = "ANTHROPIC_API_KEY")]
    api_key: Option<String>,
}

// ── Problem JSON Schema ─────────────────────────────────────────────

#[derive(Deserialize)]
struct Problem {
    description: String,
    natural_language_constraints: Vec<String>,
    system_prompt: String,
    solver_config: serde_json::Value,
    objective: serde_json::Value,
    mock_llm_response: MockLlmResponse,
}

#[derive(Deserialize, Clone)]
struct MockLlmResponse {
    variables: Vec<serde_json::Value>,
    constraints: Vec<serde_json::Value>,
}

// ── Helpers ──────────────────────────────────────────────────────────

/// Discover available scenario directories (those containing problem.json).
fn available_scenarios(scenarios_dir: &std::path::Path) -> Vec<String> {
    let mut names = Vec::new();
    if let Ok(entries) = std::fs::read_dir(scenarios_dir) {
        for entry in entries.flatten() {
            if entry.file_type().is_ok_and(|ft| ft.is_dir()) {
                let dir = entry.path();
                if dir.join("problem.json").exists()
                    && let Some(name) = entry.file_name().to_str()
                {
                    names.push(name.to_string());
                }
            }
        }
    }
    names.sort();
    names
}

// ── LLM interaction ─────────────────────────────────────────────────

const MAX_LLM_ATTEMPTS: usize = 3;

/// Attempt to get structured variables + constraints from a live LLM.
/// Returns (variables, constraints) on success, or None after all retries fail.
fn call_llm_with_retry(
    problem: &Problem,
    provider_name: &str,
    model_name: &str,
    api_key: Option<&str>,
    verbose: bool,
) -> Option<(Vec<serde_json::Value>, Vec<serde_json::Value>)> {
    // Create the LLM provider using nxuskit
    // Local models (Ollama) may need longer timeouts for thinking-mode models
    let config = ProviderConfig {
        provider_type: provider_name.to_string(),
        api_key: api_key.map(String::from),
        model: Some(model_name.to_string()),
        timeout_ms: Some(300_000), // 5 minutes for local inference
        ..Default::default()
    };

    let provider = match NxuskitProvider::new(config) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("  Error: Failed to create LLM provider '{provider_name}': {e}");
            return None;
        }
    };

    let user_content = format!(
        "Convert these constraints into structured JSON with 'variables' and 'constraints' arrays:\n\n{}",
        problem
            .natural_language_constraints
            .iter()
            .enumerate()
            .map(|(i, c)| format!("{}. {c}", i + 1))
            .collect::<Vec<_>>()
            .join("\n")
    );

    let mut messages = vec![
        Message::system(&problem.system_prompt),
        Message::user(&user_content),
    ];

    for attempt in 1..=MAX_LLM_ATTEMPTS {
        println!("  LLM attempt {attempt}/{MAX_LLM_ATTEMPTS}...");

        let mut request = ChatRequest::new(model_name).with_messages(messages.clone());
        // Force JSON output — suppresses thinking-mode prose in models like qwen3.
        request.response_format = Some(ResponseFormat::Json);

        match provider.chat(request) {
            Ok(response) => {
                if verbose {
                    eprintln!("  [verbose] Raw LLM response (attempt {attempt}):");
                    eprintln!("    {}", response.content);
                }

                match parse_llm_content(&response.content) {
                    Ok((vars, constrs)) => return Some((vars, constrs)),
                    Err(parse_err) => {
                        eprintln!("  Parse error on attempt {attempt}: {parse_err}");
                        if attempt < MAX_LLM_ATTEMPTS {
                            let feedback = if response.content.starts_with('<')
                                || response.content.starts_with("<!")
                            {
                                "Please respond with valid JSON only, not HTML.".to_string()
                            } else if response.content.trim().is_empty() {
                                "Your response was empty. Please respond with a JSON object containing 'variables' and 'constraints' arrays.".to_string()
                            } else {
                                format!(
                                    "Your response could not be parsed: {parse_err}. Please respond with valid JSON containing 'variables' and 'constraints' arrays."
                                )
                            };
                            messages.push(Message::assistant(&response.content));
                            messages.push(Message::user(&feedback));
                        }
                    }
                }
            }
            Err(e) => {
                eprintln!("  LLM error on attempt {attempt}: {e}");
                if attempt < MAX_LLM_ATTEMPTS {
                    messages.push(Message::user(
                        "The previous request failed. Please respond with valid JSON only, containing 'variables' and 'constraints' arrays."
                    ));
                }
            }
        }
    }

    None
}

/// Parse LLM content string into (variables, constraints).
fn parse_llm_content(
    content: &str,
) -> Result<(Vec<serde_json::Value>, Vec<serde_json::Value>), String> {
    // Try to find JSON in the content (it may be wrapped in markdown code blocks)
    let json_str = extract_json_block(content);
    let val: serde_json::Value =
        serde_json::from_str(&json_str).map_err(|e| format!("Invalid JSON: {e}"))?;

    let variables = val
        .get("variables")
        .and_then(|v| v.as_array())
        .ok_or_else(|| "Missing 'variables' array".to_string())?
        .clone();

    let constraints = val
        .get("constraints")
        .and_then(|c| c.as_array())
        .ok_or_else(|| "Missing 'constraints' array".to_string())?
        .clone();

    if variables.is_empty() {
        return Err("'variables' array is empty".to_string());
    }

    Ok((variables, constraints))
}

/// Extract a JSON block from text that may contain markdown code fences.
fn extract_json_block(text: &str) -> String {
    let trimmed = text.trim();
    // Check for ```json ... ``` or ``` ... ```
    if let Some(start) = trimmed.find("```") {
        let after_fence = &trimmed[start + 3..];
        // Skip optional language tag on the same line
        let content_start = after_fence.find('\n').map_or(0, |i| i + 1);
        let inner = &after_fence[content_start..];
        if let Some(end) = inner.find("```") {
            return inner[..end].trim().to_string();
        }
    }
    trimmed.to_string()
}

// ── Validation ──────────────────────────────────────────────────────

/// Validate variables and constraints structurally, returning counts and warnings.
///
/// Normalization of constraint types, parameter keys, linear decomposition,
/// and domain coercion is handled by the SDK's normalization pipeline
/// (invoked automatically in `SolverSession::solve()`).
fn validate_and_normalize(
    variables: &[serde_json::Value],
    constraints: &[serde_json::Value],
) -> (usize, Vec<serde_json::Value>, Vec<String>) {
    let mut warnings = Vec::new();
    let mut valid_vars = 0;

    let var_names: HashSet<String> = variables
        .iter()
        .filter_map(|v| v.get("name").and_then(|n| n.as_str()).map(String::from))
        .collect();

    for v in variables {
        let has_name = v.get("name").and_then(|n| n.as_str()).is_some();
        let has_type = v.get("var_type").and_then(|t| t.as_str()).is_some();
        let has_domain = v.get("domain").is_some();
        if has_name && has_type && has_domain {
            valid_vars += 1;
        } else {
            let name = v
                .get("name")
                .and_then(|n| n.as_str())
                .unwrap_or("<unnamed>");
            if !has_type {
                warnings.push(format!("Variable '{name}' missing var_type"));
            }
            if !has_domain {
                warnings.push(format!("Variable '{name}' missing domain"));
            }
        }
    }

    // Lightweight variable-reference check on constraints
    let mut valid_constraints = Vec::new();
    for c in constraints {
        if let Some(vars) = c.get("variables").and_then(|v| v.as_array()) {
            let mut all_known = true;
            for var_ref in vars {
                if let Some(name) = var_ref.as_str()
                    && !var_names.contains(name)
                {
                    warnings.push(format!(
                        "Constraint '{}' references unknown variable '{name}' (skipped)",
                        c.get("name")
                            .and_then(|n| n.as_str())
                            .unwrap_or("<unnamed>")
                    ));
                    all_known = false;
                    break;
                }
            }
            if all_known {
                valid_constraints.push(c.clone());
            }
        } else {
            // Constraints without a top-level "variables" array (e.g., params-based)
            // are passed through — the SDK validates variable references internally.
            valid_constraints.push(c.clone());
        }
    }

    (valid_vars, valid_constraints, warnings)
}

// ── Result interpretation ───────────────────────────────────────────

fn get_assignment_value(
    assignments: &std::collections::HashMap<String, SolverValue>,
    key: &str,
) -> i64 {
    match assignments.get(key) {
        Some(SolverValue::Integer(v)) => *v,
        Some(SolverValue::Real(v)) => *v as i64,
        Some(SolverValue::Boolean(v)) => {
            if *v {
                1
            } else {
                0
            }
        }
        None => 0,
    }
}

fn interpret_result(scenario: &str, result: &SolveResult) {
    if result.assignments.is_empty() {
        println!("  (No assignments to interpret)");
        return;
    }

    let assignments = &result.assignments;

    println!("\n  Interpretation:");
    match scenario {
        "seating" => {
            let mut by_table: std::collections::BTreeMap<i64, Vec<String>> =
                std::collections::BTreeMap::new();
            for (name, val) in assignments {
                if name.starts_with("guest_") && name.ends_with("_table") {
                    let guest = name
                        .strip_prefix("guest_")
                        .unwrap_or(name)
                        .strip_suffix("_table")
                        .unwrap_or(name);
                    let guest = guest
                        .chars()
                        .next()
                        .map(|c| c.to_uppercase().to_string())
                        .unwrap_or_default()
                        + &guest[1..];
                    let table = match val {
                        SolverValue::Integer(v) => *v,
                        SolverValue::Real(v) => *v as i64,
                        _ => 0,
                    };
                    by_table.entry(table).or_default().push(guest);
                }
            }
            for (table, guests) in &by_table {
                println!("    Table {table}: {}", guests.join(", "));
            }
        }
        "dungeon" => {
            for room in 1..=5 {
                let diff = get_assignment_value(assignments, &format!("room_{room}_difficulty"));
                let role = if get_assignment_value(assignments, "entry_room") == room {
                    "Entry"
                } else if get_assignment_value(assignments, "boss_room") == room {
                    "Boss"
                } else if get_assignment_value(assignments, "treasure_room_1") == room
                    || get_assignment_value(assignments, "treasure_room_2") == room
                {
                    "Treasure"
                } else {
                    "Normal"
                };
                println!("    Room {room}: {role} (difficulty {diff})");
            }
        }
        "road-trip" => {
            let parks = [
                ("yosemite", "Yosemite"),
                ("yellowstone", "Yellowstone"),
                ("zion", "Zion"),
                ("glacier", "Glacier"),
                ("grand_canyon", "Grand Canyon"),
            ];
            let mut schedule: Vec<(i64, &str, i64)> = parks
                .iter()
                .map(|(key, name)| {
                    let order = get_assignment_value(assignments, &format!("visit_order_{key}"));
                    let days = get_assignment_value(assignments, &format!("days_at_{key}"));
                    (order, *name, days)
                })
                .collect();
            schedule.sort_by_key(|(order, _, _)| *order);
            let mut day = 1;
            for (_, name, days) in &schedule {
                let end = day + days - 1;
                if *days == 1 {
                    println!("    Day {day}: {name}");
                } else {
                    println!("    Day {day}-{end}: {name} ({days} days)");
                }
                day = end + 1;
            }
        }
        _ => {
            let mut entries: Vec<_> = assignments.iter().collect();
            entries.sort_by_key(|(k, _)| k.to_string());
            for (name, val) in &entries {
                let display = match val {
                    SolverValue::Integer(v) => format!("{v}"),
                    SolverValue::Real(v) => format!("{v}"),
                    SolverValue::Boolean(v) => format!("{v}"),
                };
                println!("    {name} = {display}");
            }
        }
    }
}

// ── Main ────────────────────────────────────────────────────────────

fn main() {
    let args = Args::parse();
    let mut interactive =
        nxuskit_examples_interactive::InteractiveConfig::new(args.verbose, args.step);
    let total_start = Instant::now();

    // ── Locate scenario directory ───────────────────────────────

    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()))
        .unwrap_or_else(|| PathBuf::from("."));

    let candidate_bases = [
        exe_dir.join("../scenarios"),
        PathBuf::from("../scenarios"),
        PathBuf::from("scenarios"),
        PathBuf::from("examples/integrations/llm-solver-hybrid/scenarios"),
    ];

    let scenarios_dir = candidate_bases
        .iter()
        .find(|p| p.exists())
        .cloned()
        .unwrap_or_else(|| {
            eprintln!("Error: Could not locate scenarios directory.");
            eprintln!(
                "Run from the llm-solver-hybrid/rust/ directory or pass --scenario with a valid name."
            );
            std::process::exit(1);
        });

    // Validate scenario (FR-031: list available on invalid)
    let scenario_dir = scenarios_dir.join(&args.scenario);
    let problem_path = scenario_dir.join("problem.json");

    if !problem_path.exists() {
        let available = available_scenarios(&scenarios_dir);
        eprintln!("Error: Unknown scenario '{}'.", args.scenario);
        if available.is_empty() {
            eprintln!("No scenarios found in {}", scenarios_dir.display());
        } else {
            eprintln!("Available scenarios: {}", available.join(", "));
        }
        std::process::exit(1);
    }

    // ── Step 1: Load Problem ────────────────────────────────────

    println!("=== LLM-Solver Hybrid Pipeline ===");
    println!("Scenario: {}\n", args.scenario);

    if interactive.step_pause(
        "Loading problem definition...",
        &[
            "Reads the problem description and natural language constraints",
            "Also contains the mock LLM response for offline testing",
        ],
    ) == nxuskit_examples_interactive::StepAction::Quit
    {
        return;
    }

    let problem_json_str = std::fs::read_to_string(&problem_path).unwrap_or_else(|e| {
        eprintln!("Error: Failed to read {}: {e}", problem_path.display());
        std::process::exit(1);
    });

    let problem: Problem = serde_json::from_str(&problem_json_str).unwrap_or_else(|e| {
        eprintln!("Error: Failed to parse {}: {e}", problem_path.display());
        std::process::exit(1);
    });

    println!("--- Step 1: Load Problem ---");
    println!("  Description: {}", problem.description);
    println!("  Natural language constraints:");
    for (i, c) in problem.natural_language_constraints.iter().enumerate() {
        println!("    {}. {c}", i + 1);
    }

    if args.verbose {
        eprintln!("\n  [verbose] System prompt:");
        eprintln!("    {}", problem.system_prompt);
    }

    // ── Step 2: Get Structured Constraints ──────────────────────

    println!("\n--- Step 2: Get Structured Constraints ---");

    if interactive.step_pause(
        "Converting natural language to structured constraints...",
        &[
            if args.mock {
                "Using pre-computed mock LLM response from problem.json"
            } else {
                "Calling live LLM API with retry logic (max 3 attempts)"
            },
            "Parses response into variables and constraints arrays",
            "Falls back to mock response if live LLM fails",
        ],
    ) == nxuskit_examples_interactive::StepAction::Quit
    {
        return;
    }

    let step2_start = Instant::now();
    let llm_attempts;
    let mut used_mock = args.mock;

    let (variables, constraints) = if args.mock {
        println!("  (Using mock LLM response)");
        llm_attempts = 0;
        (
            problem.mock_llm_response.variables.clone(),
            problem.mock_llm_response.constraints.clone(),
        )
    } else {
        println!(
            "  Calling LLM provider '{}' model '{}'...",
            args.provider, args.model
        );
        match call_llm_with_retry(
            &problem,
            &args.provider,
            &args.model,
            args.api_key.as_deref(),
            args.verbose,
        ) {
            Some((vars, constrs)) => {
                llm_attempts = MAX_LLM_ATTEMPTS; // upper bound; actual tracked inside
                (vars, constrs)
            }
            None => {
                eprintln!(
                    "  Warning: LLM failed after {MAX_LLM_ATTEMPTS} attempts. Falling back to mock response."
                );
                used_mock = true;
                llm_attempts = MAX_LLM_ATTEMPTS;
                (
                    problem.mock_llm_response.variables.clone(),
                    problem.mock_llm_response.constraints.clone(),
                )
            }
        }
    };

    let step2_elapsed = step2_start.elapsed();
    println!(
        "  Got {} variables, {} constraints ({}ms)",
        variables.len(),
        constraints.len(),
        step2_elapsed.as_millis()
    );

    // ── Step 3: Validate Parsed Constraints ─────────────────────

    println!("\n--- Step 3: Validate Parsed Constraints ---");

    if interactive.step_pause(
        "Validating structure and cross-references...",
        &[
            "Checks that each variable has name, var_type, and domain",
            "Verifies constraints reference existing variable names",
        ],
    ) == nxuskit_examples_interactive::StepAction::Quit
    {
        return;
    }

    let (valid_vars, valid_constraints, warnings) =
        validate_and_normalize(&variables, &constraints);
    println!("  Valid variables:   {valid_vars}/{}", variables.len());
    println!(
        "  Valid constraints: {}/{}",
        valid_constraints.len(),
        constraints.len()
    );

    if !warnings.is_empty() {
        println!("  Warnings:");
        for w in &warnings {
            println!("    - {w}");
        }
    } else {
        println!("  All checks passed.");
    }

    if args.verbose {
        eprintln!("\n  [verbose] Variables JSON:");
        eprintln!(
            "    {}",
            serde_json::to_string_pretty(&variables).unwrap_or_default()
        );
        eprintln!("  [verbose] Constraints JSON:");
        eprintln!(
            "    {}",
            serde_json::to_string_pretty(&valid_constraints).unwrap_or_default()
        );
    }

    // ── Step 4: Solver Optimization ─────────────────────────────

    println!("\n--- Step 4: Solver Optimization ---");

    if interactive.step_pause(
        "Running constraint solver...",
        &[
            "Creates a Z3 solver session via nxuskit",
            "Adds variables and constraints from the LLM/mock response",
            "Sets the optimization objective from problem.json",
        ],
    ) == nxuskit_examples_interactive::StepAction::Quit
    {
        return;
    }

    let step4_start = Instant::now();

    // Parse solver config
    let solver_config: Option<SolverConfig> =
        serde_json::from_value(problem.solver_config.clone()).ok();

    // Create solver session
    let mut session = match SolverSession::create(solver_config.clone()) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Error: Failed to create solver session: {e}");
            std::process::exit(1);
        }
    };

    // Add variables (deserialize from raw JSON)
    let vars_typed: Vec<VariableDef> = match serde_json::from_value(serde_json::json!(variables)) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("Error: Failed to parse variables: {e}");
            std::process::exit(1);
        }
    };

    if let Err(e) = session.add_variables(vars_typed) {
        eprintln!("Error: Failed to add variables: {e}");
        std::process::exit(1);
    }

    // Add constraints (deserialize from normalized JSON)
    let constrs_typed: Vec<ConstraintDef> =
        match serde_json::from_value(serde_json::json!(valid_constraints)) {
            Ok(c) => c,
            Err(e) => {
                eprintln!("Error: Failed to parse constraints: {e}");
                std::process::exit(1);
            }
        };

    if let Err(e) = session.add_constraints(constrs_typed) {
        eprintln!("Error: Failed to add constraints: {e}");
        std::process::exit(1);
    }

    // Set objective
    let obj_dir = problem
        .objective
        .get("direction")
        .and_then(|d| d.as_str())
        .unwrap_or("maximize");
    let obj_name = problem
        .objective
        .get("name")
        .and_then(|n| n.as_str())
        .unwrap_or("unnamed");
    println!("  Objective: {obj_dir} {obj_name}");

    let obj_ok = match serde_json::from_value::<ObjectiveDef>(problem.objective.clone()) {
        Ok(obj) => session.set_objective(obj).is_ok(),
        Err(_) => false,
    };

    if !obj_ok {
        println!("  Note: Objective not applicable ({obj_name}), solving for satisfiability.");
    }

    // Solve
    let solve_result = match session.solve(None) {
        Ok(r) => r,
        Err(e) => {
            if obj_ok {
                if args.verbose {
                    eprintln!("  [verbose] Solve with objective failed: {e}");
                    eprintln!("  [verbose] Retrying without objective...");
                }
                // Retry: create fresh session without objective
                let mut session2 = match SolverSession::create(solver_config) {
                    Ok(s) => s,
                    Err(e2) => {
                        eprintln!("Error: Failed to create retry session: {e2}");
                        std::process::exit(1);
                    }
                };
                let vars2: Vec<VariableDef> =
                    serde_json::from_value(serde_json::json!(variables)).unwrap();
                let constrs2: Vec<ConstraintDef> =
                    serde_json::from_value(serde_json::json!(valid_constraints)).unwrap();
                session2.add_variables(vars2).unwrap();
                session2.add_constraints(constrs2).unwrap();
                match session2.solve(None) {
                    Ok(r) => r,
                    Err(e2) => {
                        eprintln!("Error: Solver failed: {e2}");
                        std::process::exit(1);
                    }
                }
            } else {
                eprintln!("Error: Solver failed: {e}");
                std::process::exit(1);
            }
        }
    };

    let status = &solve_result.status;
    println!("\n  Solver status: {status:?}");

    if *status == SolveStatus::Unsat {
        println!("  No satisfying assignment found.");
        if let Some(core) = &solve_result.unsat_core {
            println!("  Conflicting constraints:");
            for name in core {
                println!("    - {name}");
            }
        }
    }

    // Print assignments
    if !solve_result.assignments.is_empty() {
        println!("  Assignments:");
        let mut entries: Vec<_> = solve_result.assignments.iter().collect();
        entries.sort_by_key(|(k, _)| k.to_string());
        for (name, val) in &entries {
            let display = match val {
                SolverValue::Integer(v) => format!("{v}"),
                SolverValue::Real(v) => format!("{v}"),
                SolverValue::Boolean(v) => format!("{v}"),
            };
            println!("    {name} = {display}");
        }
    }

    if let Some(obj_val) = solve_result.objective_value {
        println!("  Objective value: {obj_val}");
    }

    let step4_elapsed = step4_start.elapsed();
    println!("  Solver time: {}ms", step4_elapsed.as_millis());

    // ── Step 5: Result Interpretation ───────────────────────────

    println!("\n--- Step 5: Result Interpretation ---");
    if *status == SolveStatus::Sat || *status == SolveStatus::Optimal {
        interpret_result(&args.scenario, &solve_result);
    } else {
        println!("  (No solution to interpret — solver returned {status:?})");
    }

    // ── Pipeline Summary ────────────────────────────────────────

    let total_elapsed = total_start.elapsed();

    println!("\n=== Pipeline Summary ===");
    println!("Scenario:     {}", args.scenario);
    println!("LLM mode:     {}", if used_mock { "mock" } else { "live" });
    if !args.mock {
        println!("LLM attempts: {llm_attempts}");
    }
    println!("Solver:       {status:?}");
    println!(
        "Timing:       {}ms (constraints {}ms + solver {}ms)",
        total_elapsed.as_millis(),
        step2_elapsed.as_millis(),
        step4_elapsed.as_millis(),
    );
}
