//! Riffer CLI - Music Sequence Analysis and Transformation Tool
//!
//! A command-line tool for analyzing and transforming music sequences.
//!
//! ## Interactive Modes
//! - `--verbose` or `-v`: Show detailed analysis progress and LLM request/response data
//! - `--step` or `-s`: Pause at each major operation for step-by-step learning

// Clippy allowances for example/demo code
#![allow(dead_code)]
#![allow(clippy::ptr_arg)]
#![allow(clippy::collapsible_if)]
#![allow(clippy::redundant_closure)]
#![allow(clippy::needless_borrow)]
#![allow(clippy::clone_on_copy)]
#![allow(clippy::wrong_self_convention)]
#![allow(clippy::too_many_arguments)]
#![allow(clippy::io_other_error)]
#![allow(clippy::manual_clamp)]
#![allow(clippy::should_implement_trait)]
#![allow(clippy::field_reassign_with_default)]
#![allow(clippy::unnecessary_cast)]
#![allow(clippy::manual_range_contains)]

use std::path::PathBuf;
use std::process;

use clap::{Parser, Subcommand};
use nxuskit_examples_interactive::{InteractiveConfig, StepAction};

mod engine;
mod errors;
mod formats;
mod llm;
mod theory;
mod types;

use crate::engine::{analyze_sequence, score_sequence, score_sequence_async};
use crate::errors::{ExitCode, Result};

/// Riffer - Music sequence analysis and transformation tool
#[derive(Parser)]
#[command(name = "riffer")]
#[command(about = "Analyze and transform music sequences", long_about = None)]
#[command(version)]
struct Cli {
    /// Enable verbose output showing detailed progress and LLM data
    #[arg(short, long, global = true)]
    verbose: bool,

    /// Enable step-through mode with pauses at major operations
    #[arg(short, long, global = true)]
    step: bool,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Analyze a music sequence
    Analyze {
        /// Input file (MIDI or MusicXML)
        #[arg(short, long)]
        input: PathBuf,

        /// Output format (json, markdown)
        #[arg(short, long, default_value = "json")]
        format: String,

        /// Include suggestions for improvement
        #[arg(long)]
        suggestions: bool,

        /// Use LLM for narrative analysis
        #[arg(long)]
        narrative: bool,
    },

    /// Score a music sequence
    Score {
        /// Input file (MIDI or MusicXML)
        #[arg(short, long)]
        input: PathBuf,

        /// Output format (json, markdown)
        #[arg(short, long, default_value = "json")]
        format: String,

        /// Custom scoring weights (JSON file)
        #[arg(long)]
        weights: Option<PathBuf>,

        /// Enable CLIPS rule engine for scoring adjustments
        #[arg(long)]
        clips: bool,

        /// Path to CLIPS rules directory (default: ./rules)
        #[arg(long)]
        rules_dir: Option<PathBuf>,
    },

    /// Transform a music sequence
    Transform {
        /// Input file (MIDI or MusicXML)
        #[arg(short, long)]
        input: PathBuf,

        /// Output file
        #[arg(short, long)]
        output: PathBuf,

        /// Transpose by semitones (-12 to +12)
        #[arg(long)]
        transpose: Option<i8>,

        /// Change tempo (BPM, 20-300)
        #[arg(long)]
        tempo: Option<u16>,

        /// Invert melody around pivot pitch (MIDI note number, default: first note)
        #[arg(long)]
        invert: Option<Option<u8>>,

        /// Reverse note order (retrograde)
        #[arg(long)]
        retrograde: bool,

        /// Augment durations by factor (0.125-8.0)
        #[arg(long)]
        augment: Option<f32>,

        /// Diminish durations by factor (0.125-8.0)
        #[arg(long)]
        diminish: Option<f32>,

        /// Change key (e.g., "C", "Am", "F#m")
        #[arg(long)]
        key: Option<String>,

        /// Natural language transformation prompt (requires LLM)
        #[arg(long)]
        prompt: Option<String>,
    },

    /// Convert between formats
    Convert {
        /// Input file (MIDI or MusicXML)
        #[arg(short, long)]
        input: PathBuf,

        /// Output file
        #[arg(short, long)]
        output: PathBuf,
    },
}

#[tokio::main]
async fn main() {
    let cli = Cli::parse();

    // Initialize interactive mode from CLI flags
    let mut interactive = InteractiveConfig::new(cli.verbose, cli.step);

    let result = match cli.command {
        Commands::Analyze {
            input,
            format,
            suggestions,
            narrative,
        } => run_analyze(&input, &format, suggestions, narrative, &mut interactive).await,
        Commands::Score {
            input,
            format,
            weights,
            clips,
            rules_dir,
        } => {
            run_score(
                &input,
                &format,
                weights.as_deref(),
                clips,
                rules_dir.as_deref(),
                &mut interactive,
            )
            .await
        }
        Commands::Transform {
            input,
            output,
            transpose,
            tempo,
            invert,
            retrograde,
            augment,
            diminish,
            key,
            prompt,
        } => {
            run_transform(
                &input,
                &output,
                transpose,
                tempo,
                invert,
                retrograde,
                augment,
                diminish,
                key.as_deref(),
                prompt.as_deref(),
                &mut interactive,
            )
            .await
        }
        Commands::Convert { input, output } => run_convert(&input, &output),
    };

    match result {
        Ok(_) => process::exit(ExitCode::Success as i32),
        Err(e) => {
            eprintln!("{}", e.user_message());
            process::exit(e.exit_code() as i32);
        }
    }
}

async fn run_analyze(
    input: &PathBuf,
    format: &str,
    _suggestions: bool,
    narrative: bool,
    interactive: &mut InteractiveConfig,
) -> Result<()> {
    // Step mode: explain analysis
    if interactive.step_pause(
        "Loading music sequence...",
        &[
            &format!("Input: {}", input.display()),
            "Supports MIDI and MusicXML formats",
            "Will extract notes, timing, and metadata",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    let sequence = formats::read_sequence(input)?;

    // Step mode: explain analysis
    if interactive.step_pause(
        "Analyzing sequence...",
        &[
            "Detecting key signature using Krumhansl-Schmuckler algorithm",
            "Analyzing intervals, contour, rhythm, and dynamics",
            "Computing scale coherence and melodic interest",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // Use the comprehensive analyzer
    let analysis = analyze_sequence(&sequence, true)?;

    if format == "markdown" {
        print_markdown_analysis(&analysis);
    } else {
        println!("{}", serde_json::to_string_pretty(&analysis).unwrap());
    }

    // Generate narrative if requested
    if narrative {
        // Step mode: explain LLM narrative
        if interactive.step_pause(
            "Generating narrative analysis...",
            &[
                "Sending analysis data to LLM",
                "LLM will describe musical characteristics",
                "Uses natural language for accessibility",
            ],
        ) == StepAction::Quit
        {
            return Ok(());
        }

        // Verbose mode: show LLM request
        let request = serde_json::json!({
            "analysis": analysis,
            "request": "generate_narrative"
        });
        interactive.print_request("POST", "llm://provider/chat", &request);

        println!("\n## Narrative Analysis\n");
        let start = std::time::Instant::now();
        match llm::generate_narrative(&analysis).await {
            Ok(narrative_text) => {
                let elapsed_ms = start.elapsed().as_millis() as u64;
                // Verbose mode: show LLM response
                let response = serde_json::json!({
                    "narrative": narrative_text
                });
                interactive.print_response(200, elapsed_ms, &response);
                println!("{}", narrative_text);
            }
            Err(e) => eprintln!(
                "Warning: Could not generate narrative: {}",
                e.user_message()
            ),
        }
    }

    Ok(())
}

fn print_markdown_analysis(analysis: &engine::AnalysisResult) {
    println!(
        "# Music Analysis: {}\n",
        analysis.name.as_deref().unwrap_or("Unknown")
    );

    println!("## Summary\n");
    println!("- **Notes**: {}", analysis.note_count);
    println!("- **Duration**: {} ticks", analysis.duration_ticks);

    println!("\n## Key Detection\n");
    println!("- **Detected Key**: {}", analysis.key_detection.key);
    println!(
        "- **Confidence**: {:.1}%",
        analysis.key_detection.confidence * 100.0
    );
    if !analysis.key_detection.alternatives.is_empty() {
        println!("- **Alternatives**:");
        for (key, corr) in analysis.key_detection.alternatives.iter().take(3) {
            println!("  - {} ({:.2})", key, corr);
        }
    }

    println!("\n## Scale Analysis\n");
    println!("- **Key**: {}", analysis.scale_analysis.key);
    println!(
        "- **In Scale**: {} notes",
        analysis.scale_analysis.in_scale_count
    );
    println!(
        "- **Out of Scale**: {} notes",
        analysis.scale_analysis.out_of_scale_count
    );
    println!(
        "- **Harmonic Coherence**: {:.1}%",
        analysis.scale_analysis.coherence_percentage
    );

    println!("\n## Interval Analysis\n");
    println!(
        "- **Total Intervals**: {}",
        analysis.interval_analysis.count
    );
    println!(
        "- Perfect Consonances: {}",
        analysis.interval_analysis.by_quality.perfect_consonance
    );
    println!(
        "- Imperfect Consonances: {}",
        analysis.interval_analysis.by_quality.imperfect_consonance
    );
    println!(
        "- Mild Dissonances: {}",
        analysis.interval_analysis.by_quality.mild_dissonance
    );
    println!(
        "- Strong Dissonances: {}",
        analysis.interval_analysis.by_quality.strong_dissonance
    );
    println!(
        "- **Interval Variety**: {} unique intervals",
        analysis.interval_analysis.interval_variety
    );

    println!("\n## Melodic Contour\n");
    println!(
        "- **Contour Type**: {:?}",
        analysis.contour_analysis.contour_type
    );
    println!(
        "- **Direction Changes**: {}",
        analysis.contour_analysis.direction_changes
    );
    println!(
        "- **Pitch Range**: {} semitones ({} to {})",
        analysis.contour_analysis.pitch_range,
        analysis.contour_analysis.lowest_pitch,
        analysis.contour_analysis.highest_pitch
    );

    println!("\n## Rhythm Analysis\n");
    println!(
        "- **Unique Durations**: {}",
        analysis.rhythm_analysis.unique_durations
    );
    println!(
        "- **Most Common Duration**: {} ticks",
        analysis.rhythm_analysis.most_common_duration
    );
    println!(
        "- **Duration Variety**: {:.2}",
        analysis.rhythm_analysis.duration_variety
    );

    println!("\n## Dynamics Analysis\n");
    println!(
        "- **Velocity Range**: {} - {}",
        analysis.dynamics_analysis.min_velocity, analysis.dynamics_analysis.max_velocity
    );
    println!(
        "- **Has Dynamics**: {}",
        if analysis.dynamics_analysis.has_dynamics {
            "Yes"
        } else {
            "No"
        }
    );
}

async fn run_score(
    input: &PathBuf,
    format: &str,
    _weights: Option<&std::path::Path>,
    use_clips: bool,
    rules_dir: Option<&std::path::Path>,
    interactive: &mut InteractiveConfig,
) -> Result<()> {
    // Step mode: explain scoring
    if interactive.step_pause(
        "Loading music sequence for scoring...",
        &[
            &format!("Input: {}", input.display()),
            if use_clips {
                "CLIPS rules enabled for scoring adjustments"
            } else {
                "Using basic scoring without CLIPS"
            },
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    let sequence = formats::read_sequence(input)?;

    // Determine rules directory - default to "./rules" relative to the example
    let default_rules = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("examples/riffer/rules");
    let rules_path = rules_dir.unwrap_or(&default_rules);

    // Step mode: explain scoring process
    if interactive.step_pause(
        "Computing music score...",
        &[
            "Evaluating harmonic coherence and melodic interest",
            "Analyzing rhythmic variety and resolution quality",
            "Computing dynamics expression and structural balance",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // Score with optional CLIPS integration
    let score = if use_clips {
        score_sequence_async(&sequence, Some(rules_path)).await?
    } else {
        score_sequence(&sequence, false)?
    };

    if format == "markdown" {
        print_markdown_score(&sequence.name, &score);
    } else {
        println!("{}", serde_json::to_string_pretty(&score).unwrap());
    }

    Ok(())
}

fn print_markdown_score(name: &Option<String>, score: &engine::MusicScore) {
    println!("# Music Score: {}\n", name.as_deref().unwrap_or("Unknown"));

    println!(
        "## Overall Score: {:.1}/100 ({})\n",
        score.overall, score.summary.rating
    );

    println!("## Dimension Scores\n");
    println!("| Dimension | Score | Rating |");
    println!("|-----------|-------|--------|");
    println!(
        "| Harmonic Coherence | {:.1} | {} |",
        score.dimensions.harmonic_coherence.score, score.dimensions.harmonic_coherence.rating
    );
    println!(
        "| Melodic Interest | {:.1} | {} |",
        score.dimensions.melodic_interest.score, score.dimensions.melodic_interest.rating
    );
    println!(
        "| Rhythmic Variety | {:.1} | {} |",
        score.dimensions.rhythmic_variety.score, score.dimensions.rhythmic_variety.rating
    );
    println!(
        "| Resolution Quality | {:.1} | {} |",
        score.dimensions.resolution_quality.score, score.dimensions.resolution_quality.rating
    );
    println!(
        "| Dynamics Expression | {:.1} | {} |",
        score.dimensions.dynamics_expression.score, score.dimensions.dynamics_expression.rating
    );
    println!(
        "| Structural Balance | {:.1} | {} |",
        score.dimensions.structural_balance.score, score.dimensions.structural_balance.rating
    );

    println!("\n## Summary\n");
    println!("- **Strongest**: {}", score.summary.strongest);
    println!("- **Weakest**: {}", score.summary.weakest);
    println!("\n{}", score.summary.summary);

    if !score.suggestions.is_empty() {
        println!("\n## Suggestions for Improvement\n");
        for suggestion in &score.suggestions {
            println!("- {}", suggestion);
        }
    }
}

async fn run_transform(
    input: &PathBuf,
    output_path: &PathBuf,
    transpose_semitones: Option<i8>,
    tempo_bpm: Option<u16>,
    invert_pivot: Option<Option<u8>>,
    do_retrograde: bool,
    augment_factor: Option<f32>,
    diminish_factor: Option<f32>,
    key_str: Option<&str>,
    prompt: Option<&str>,
    interactive: &mut InteractiveConfig,
) -> Result<()> {
    // Step mode: explain transformation
    if interactive.step_pause(
        "Loading music sequence for transformation...",
        &[
            &format!("Input: {}", input.display()),
            &format!("Output: {}", output_path.display()),
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    let mut sequence = formats::read_sequence(input)?;

    // If a prompt is provided, use LLM to interpret it
    if let Some(prompt_text) = prompt {
        // Step mode: explain LLM transformation
        if interactive.step_pause(
            "Using LLM for transformation...",
            &[
                "Natural language prompt will be interpreted",
                "LLM determines transformation parameters",
                "Supports complex musical transformations",
            ],
        ) == StepAction::Quit
        {
            return Ok(());
        }

        // Verbose mode: show LLM request
        let request = serde_json::json!({
            "prompt": prompt_text,
            "sequence_notes": sequence.notes.len()
        });
        interactive.print_request("POST", "llm://provider/chat", &request);

        let start = std::time::Instant::now();
        match llm::transform_with_prompt(&mut sequence, prompt_text).await {
            Ok(description) => {
                let elapsed_ms = start.elapsed().as_millis() as u64;
                // Verbose mode: show LLM response
                let response = serde_json::json!({
                    "description": description
                });
                interactive.print_response(200, elapsed_ms, &response);
                eprintln!("LLM transformation: {}", description);
            }
            Err(e) => {
                return Err(errors::RifferError::LlmUnavailable(e.user_message()));
            }
        }
    }

    // Apply explicit transformations (these can combine with or override LLM changes)

    // Apply transpose
    if let Some(semitones) = transpose_semitones {
        engine::transpose(&mut sequence, semitones)?;
        eprintln!("Transposed by {} semitones", semitones);
    }

    // Apply tempo change
    if let Some(bpm) = tempo_bpm {
        engine::change_tempo(&mut sequence, bpm)?;
        eprintln!("Set tempo to {} BPM", bpm);
    }

    // Apply invert
    if let Some(pivot) = invert_pivot {
        engine::invert(&mut sequence, pivot)?;
        if let Some(p) = pivot {
            eprintln!("Inverted around pitch {}", p);
        } else {
            eprintln!("Inverted around first note");
        }
    }

    // Apply retrograde
    if do_retrograde {
        engine::retrograde(&mut sequence)?;
        eprintln!("Applied retrograde (reversed notes)");
    }

    // Apply augment
    if let Some(factor) = augment_factor {
        engine::augment(&mut sequence, factor)?;
        eprintln!("Augmented durations by factor {}", factor);
    }

    // Apply diminish
    if let Some(factor) = diminish_factor {
        engine::diminish(&mut sequence, factor)?;
        eprintln!("Diminished durations by factor {}", factor);
    }

    // Apply key change
    if let Some(key) = key_str {
        if let Some(target_key) = parse_key(key) {
            engine::key_change(&mut sequence, &target_key)?;
            eprintln!("Changed key to {}", target_key);
        } else {
            return Err(errors::RifferError::InvalidArguments(format!(
                "Invalid key format: '{}'. Use format like 'C', 'Am', 'F#', 'Bbm'",
                key
            )));
        }
    }

    // Write output
    formats::write_sequence(&sequence, output_path)?;
    eprintln!("Written to {}", output_path.display());

    Ok(())
}

/// Parse a key string like "C", "Am", "F#", "Bbm" into a KeySignature
fn parse_key(s: &str) -> Option<types::KeySignature> {
    let s = s.trim();
    if s.is_empty() {
        return None;
    }

    // Check if it ends with 'm' or 'minor' for minor mode
    let (root_str, mode) = if s.ends_with('m') && !s.ends_with("ajor") {
        (&s[..s.len() - 1], types::Mode::Minor)
    } else if s.to_lowercase().ends_with("minor") {
        (&s[..s.len() - 5], types::Mode::Minor)
    } else if s.to_lowercase().ends_with("major") {
        (&s[..s.len() - 5], types::Mode::Major)
    } else {
        (s, types::Mode::Major)
    };

    // Parse the root pitch class
    let root = match root_str.to_uppercase().as_str() {
        "C" => types::PitchClass::C,
        "C#" | "DB" => types::PitchClass::Cs,
        "D" => types::PitchClass::D,
        "D#" | "EB" => types::PitchClass::Ds,
        "E" => types::PitchClass::E,
        "F" => types::PitchClass::F,
        "F#" | "GB" => types::PitchClass::Fs,
        "G" => types::PitchClass::G,
        "G#" | "AB" => types::PitchClass::Gs,
        "A" => types::PitchClass::A,
        "A#" | "BB" => types::PitchClass::As,
        "B" => types::PitchClass::B,
        _ => return None,
    };

    Some(types::KeySignature::new(root, mode))
}

fn run_convert(input: &PathBuf, output: &PathBuf) -> Result<()> {
    let sequence = formats::read_sequence(input)?;
    formats::write_sequence(&sequence, output)?;
    eprintln!("Converted {} to {}", input.display(), output.display());
    Ok(())
}
