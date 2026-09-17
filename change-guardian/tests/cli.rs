use serde_json::json;
use std::fs;
use std::io::Write;
use std::process::{Command, Stdio};
use tempfile::TempDir;

fn setup() -> (TempDir, TempDir, std::path::PathBuf) {
    let repo = TempDir::new().unwrap();
    let evidence = TempDir::new().unwrap();
    for args in [
        vec!["init", "-q"],
        vec!["config", "user.email", "test@example.invalid"],
        vec!["config", "user.name", "Test"],
    ] {
        assert!(
            Command::new("git")
                .current_dir(repo.path())
                .args(args)
                .status()
                .unwrap()
                .success()
        );
    }
    fs::write(repo.path().join("allowed.txt"), "base\n").unwrap();
    assert!(
        Command::new("git")
            .current_dir(repo.path())
            .args(["add", "."])
            .status()
            .unwrap()
            .success()
    );
    assert!(
        Command::new("git")
            .current_dir(repo.path())
            .args(["commit", "-qm", "base"])
            .status()
            .unwrap()
            .success()
    );
    let contract = evidence.path().join("contract.json");
    let value = json!({
        "schema":"change-guardian-contract/v1","repository_id":null,"baseline":null,
        "rules":[{"class":"implementation","patterns":["allowed.txt"],"allow_staged":true,"allow_unstaged":true,"allow_kinds":["file"],"allow_test_suppression":false}],
        "dependency_patterns":[],"generated":[],"test_ecosystems":[],"unknown_test_patterns":["tests/**"],
        "verification_commands":[["git","diff","--check"]],"contract_hash":null
    });
    fs::write(&contract, serde_json::to_vec_pretty(&value).unwrap()).unwrap();
    let seal = Command::new(env!("CARGO_BIN_EXE_change-guardian"))
        .args([
            "seal",
            "--contract",
            contract.to_str().unwrap(),
            "--repository",
            repo.path().to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(
        seal.status.success(),
        "{}",
        String::from_utf8_lossy(&seal.stderr)
    );
    (repo, evidence, contract)
}

#[test]
fn check_exit_code_distinguishes_contained_and_denied_state() {
    let (repo, _evidence, contract) = setup();
    let allowed = Command::new(env!("CARGO_BIN_EXE_change-guardian"))
        .args([
            "check",
            "--contract",
            contract.to_str().unwrap(),
            "--repository",
            repo.path().to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert_eq!(allowed.status.code(), Some(0));
    fs::write(repo.path().join("surprise.txt"), "no\n").unwrap();
    let denied = Command::new(env!("CARGO_BIN_EXE_change-guardian"))
        .args([
            "check",
            "--contract",
            contract.to_str().unwrap(),
            "--repository",
            repo.path().to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert_eq!(denied.status.code(), Some(10));
    assert!(String::from_utf8_lossy(&denied.stdout).contains("surprise.txt"));
}

#[test]
fn malformed_envelope_exits_fail_closed() {
    let (_repo, _evidence, contract) = setup();
    let mut child = Command::new(env!("CARGO_BIN_EXE_change-guardian"))
        .args(["envelope", "--contract", contract.to_str().unwrap()])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.take().unwrap().write_all(b"{bad json").unwrap();
    let output = child.wait_with_output().unwrap();
    assert_eq!(output.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&output.stderr).contains("change-guardian:"));
}
