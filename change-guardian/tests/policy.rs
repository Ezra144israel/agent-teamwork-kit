use change_guardian::{evaluate_contract, seal_contract};
use serde_json::json;
use std::fs;
use std::process::Command;
use tempfile::TempDir;

fn git(repo: &TempDir, args: &[&str]) {
    assert!(
        Command::new("git")
            .current_dir(repo.path())
            .args(args)
            .status()
            .unwrap()
            .success()
    );
}

fn repository() -> TempDir {
    let repo = TempDir::new().unwrap();
    git(&repo, &["init", "-q"]);
    git(&repo, &["config", "user.email", "test@example.invalid"]);
    git(&repo, &["config", "user.name", "Test"]);
    fs::create_dir(repo.path().join("src")).unwrap();
    fs::write(repo.path().join("src/main.rs"), "fn main() {}\n").unwrap();
    git(&repo, &["add", "."]);
    git(&repo, &["commit", "-qm", "base"]);
    repo
}

fn contract_json() -> serde_json::Value {
    json!({
        "schema": "change-guardian-contract/v1",
        "repository_id": null,
        "baseline": null,
        "rules": [{
            "class": "implementation",
            "patterns": ["src/**"],
            "allow_staged": true,
            "allow_unstaged": true,
            "allow_kinds": ["file"],
            "allow_test_suppression": false
        }],
        "dependency_patterns": [],
        "generated": [],
        "test_ecosystems": [],
        "unknown_test_patterns": ["tests/**", "**/*_test.*"],
        "verification_commands": [["cargo", "test"]],
        "contract_hash": null
    })
}

#[test]
fn allowed_path_passes_and_unclassified_path_fails() {
    let repo = repository();
    let contract_dir = TempDir::new().unwrap();
    let contract_path = contract_dir.path().join("contract.json");
    fs::write(
        &contract_path,
        serde_json::to_vec_pretty(&contract_json()).unwrap(),
    )
    .unwrap();
    let contract = seal_contract(&contract_path, repo.path()).unwrap();

    fs::write(
        repo.path().join("src/main.rs"),
        "fn main() { println!(\"ok\"); }\n",
    )
    .unwrap();
    let allowed = evaluate_contract(&contract, repo.path()).unwrap();
    assert!(allowed.violations.is_empty(), "{:?}", allowed.violations);

    fs::write(repo.path().join("surprise.txt"), "not allowed\n").unwrap();
    let denied = evaluate_contract(&contract, repo.path()).unwrap();
    assert!(
        denied
            .violations
            .iter()
            .any(|message| message.contains("surprise.txt"))
    );
}

#[test]
fn malformed_contract_fails_closed() {
    let repo = repository();
    let contract_dir = TempDir::new().unwrap();
    let contract_path = contract_dir.path().join("contract.json");
    fs::write(&contract_path, b"{not json").unwrap();
    assert!(seal_contract(&contract_path, repo.path()).is_err());
}

#[test]
fn distributed_example_contract_seals_and_reads_back() {
    let repo = repository();
    let contract_dir = TempDir::new().unwrap();
    let contract_path = contract_dir.path().join("contract.json");
    fs::copy(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("contract.example.json"),
        &contract_path,
    )
    .unwrap();
    let sealed = seal_contract(&contract_path, repo.path()).unwrap();
    assert!(
        sealed
            .contract_hash
            .as_deref()
            .is_some_and(|hash| hash.starts_with("sha256:"))
    );
}

#[test]
fn unknown_fields_and_parent_patterns_fail_closed() {
    let repo = repository();
    let contract_dir = TempDir::new().unwrap();
    let contract_path = contract_dir.path().join("contract.json");
    let mut unknown = contract_json();
    unknown["typo_field"] = json!(true);
    fs::write(&contract_path, serde_json::to_vec_pretty(&unknown).unwrap()).unwrap();
    assert!(seal_contract(&contract_path, repo.path()).is_err());

    let mut unsafe_pattern = contract_json();
    unsafe_pattern["rules"][0]["patterns"] = json!(["../outside"]);
    fs::write(
        &contract_path,
        serde_json::to_vec_pretty(&unsafe_pattern).unwrap(),
    )
    .unwrap();
    assert!(seal_contract(&contract_path, repo.path()).is_err());
}
