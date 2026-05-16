//! CLI auth helper — credential management via terminal commands.
//!
//! Usage:
//!   cargo run -- status              # List all providers and auth status
//!   cargo run -- set <provider>      # Set credential (interactive key entry)
//!   cargo run -- remove <provider>   # Remove stored credential
//!   cargo run -- dashboard <provider> # Open provider dashboard in browser

use auth_helper_core::{
    format_status_line, list_providers, open_dashboard, remove_credential, set_credential,
};
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(
    name = "auth-helper",
    about = "nxusKit credential management helper",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// List all providers and their authentication status
    Status,
    /// Set (store) an API key for a provider
    Set {
        /// Provider identifier (e.g., openai, claude, groq, xai)
        provider: String,
    },
    /// Remove a stored API key for a provider
    Remove {
        /// Provider identifier
        provider: String,
    },
    /// Open the provider's credential management dashboard in a browser
    Dashboard {
        /// Provider identifier
        provider: String,
    },
}

fn main() {
    let cli = Cli::parse();

    let result = match cli.command {
        Command::Status => cmd_status(),
        Command::Set { provider } => cmd_set(&provider),
        Command::Remove { provider } => cmd_remove(&provider),
        Command::Dashboard { provider } => cmd_dashboard(&provider),
    };

    if let Err(e) = result {
        eprintln!("Error: {e}");
        std::process::exit(1);
    }
}

fn cmd_status() -> Result<(), Box<dyn std::error::Error>> {
    let providers = list_providers()?;
    println!("Provider Auth Status:");
    for entry in &providers {
        println!("{}", format_status_line(entry));
    }
    Ok(())
}

fn cmd_set(provider: &str) -> Result<(), Box<dyn std::error::Error>> {
    eprint!("Enter API key for {provider}: ");
    let key = read_masked_input()?;

    if key.is_empty() {
        eprintln!("No key entered. Aborting.");
        return Ok(());
    }

    set_credential(provider, &key)?;
    println!("Credential stored successfully.");

    // Show updated status
    let providers = list_providers()?;
    if let Some(entry) = providers.iter().find(|p| p.id == provider) {
        println!(
            "Status: {} ({})",
            entry.status.label(),
            entry.masked_preview.as_deref().unwrap_or("-")
        );
    }

    Ok(())
}

fn cmd_remove(provider: &str) -> Result<(), Box<dyn std::error::Error>> {
    remove_credential(provider)?;
    println!("Credential removed for {provider}.");
    Ok(())
}

fn cmd_dashboard(provider: &str) -> Result<(), Box<dyn std::error::Error>> {
    open_dashboard(provider)?;
    println!("Opening dashboard for {provider} in default browser...");
    Ok(())
}

/// Read a line from stdin without echoing (best effort).
///
/// On Unix, disables echo via termios. Falls back to normal input on error.
fn read_masked_input() -> Result<String, Box<dyn std::error::Error>> {
    #[cfg(unix)]
    {
        use std::io::{BufRead, Write};
        use std::os::unix::io::AsRawFd;

        let stdin = std::io::stdin();
        let fd = stdin.as_raw_fd();

        // Save terminal settings
        let saved = unsafe {
            let mut t: libc::termios = std::mem::zeroed();
            libc::tcgetattr(fd, &mut t);
            t
        };

        // Disable echo
        unsafe {
            let mut t = saved;
            t.c_lflag &= !libc::ECHO;
            libc::tcsetattr(fd, libc::TCSANOW, &t);
        }

        let mut line = String::new();
        stdin.lock().read_line(&mut line)?;
        std::io::stderr().write_all(b"\n")?;

        // Restore terminal
        unsafe {
            libc::tcsetattr(fd, libc::TCSANOW, &saved);
        }

        Ok(line.trim().to_string())
    }

    #[cfg(not(unix))]
    {
        use std::io::BufRead;
        let mut line = String::new();
        std::io::stdin().lock().read_line(&mut line)?;
        Ok(line.trim().to_string())
    }
}
