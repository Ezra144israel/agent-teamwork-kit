use change_guardian::{
    GuardError, check_receipt, evaluate_contract, evaluate_envelope, read_contract,
    run_verification, seal_contract,
};
use serde_json::Value;
use std::env;
use std::io::{self, Read};
use std::path::PathBuf;

const USAGE: &str = "usage:\n  change-guardian seal --contract PATH --repository PATH\n  change-guardian check --contract PATH --repository PATH\n  change-guardian verify --contract PATH --receipt PATH --repository PATH -- COMMAND [ARG...]\n  change-guardian check-receipt --contract PATH --receipt PATH --repository PATH\n  change-guardian envelope --contract PATH [--repository PATH]";

fn option(args: &[String], name: &str) -> Result<Option<PathBuf>, GuardError> {
    let mut found = None;
    let mut index = 0;
    while index < args.len() {
        if args[index] == name {
            let value = args
                .get(index + 1)
                .ok_or_else(|| GuardError(format!("{name} needs a value")))?;
            if found.is_some() {
                return Err(GuardError(format!("{name} was supplied more than once")));
            }
            found = Some(PathBuf::from(value));
            index += 2;
        } else {
            index += 1;
        }
    }
    Ok(found)
}

fn required(args: &[String], name: &str) -> Result<PathBuf, GuardError> {
    option(args, name)?.ok_or_else(|| GuardError(format!("missing {name}")))
}

fn run() -> Result<i32, GuardError> {
    let args = env::args().skip(1).collect::<Vec<_>>();
    let command = args
        .first()
        .map(String::as_str)
        .ok_or_else(|| GuardError(USAGE.to_owned()))?;
    let tail = &args[1..];
    match command {
        "seal" => {
            let contract = required(tail, "--contract")?;
            let repository = required(tail, "--repository")?;
            let sealed = seal_contract(&contract, &repository)?;
            println!("{}", sealed.contract_hash.expect("sealed contract"));
            Ok(0)
        }
        "check" => {
            let contract = read_contract(&required(tail, "--contract")?)?;
            let evaluation = evaluate_contract(&contract, &required(tail, "--repository")?)?;
            println!("{}", serde_json::to_string_pretty(&evaluation)?);
            Ok(if evaluation.violations.is_empty() {
                0
            } else {
                10
            })
        }
        "verify" => {
            let separator = tail
                .iter()
                .position(|argument| argument == "--")
                .ok_or_else(|| GuardError("verify needs -- before the command".to_owned()))?;
            let options = &tail[..separator];
            let verification_command = tail[separator + 1..].to_vec();
            if verification_command.is_empty() {
                return Err(GuardError("verification command is empty".to_owned()));
            }
            let receipt = run_verification(
                &required(options, "--contract")?,
                &required(options, "--receipt")?,
                &required(options, "--repository")?,
                &verification_command,
            )?;
            println!("{}", serde_json::to_string_pretty(&receipt)?);
            Ok(if receipt.exit_status == 0 { 0 } else { 10 })
        }
        "check-receipt" => {
            let receipt = check_receipt(
                &required(tail, "--contract")?,
                &required(tail, "--receipt")?,
                &required(tail, "--repository")?,
            )?;
            println!("{}", serde_json::to_string_pretty(&receipt)?);
            Ok(0)
        }
        "envelope" => {
            let contract = read_contract(&required(tail, "--contract")?)?;
            let repository = option(tail, "--repository")?;
            let mut input = Vec::new();
            io::stdin().read_to_end(&mut input)?;
            let payload: Value = serde_json::from_slice(&input)?;
            let output = evaluate_envelope(&contract, &payload, repository.as_deref())?;
            println!("{}", serde_json::to_string(&output)?);
            Ok(0)
        }
        _ => Err(GuardError(USAGE.to_owned())),
    }
}

fn main() {
    match run() {
        Ok(code) => std::process::exit(code),
        Err(error) => {
            eprintln!("change-guardian: {error}");
            std::process::exit(2);
        }
    }
}
