use change_guardian::{check_receipt, run_verification, seal_contract};
use serde_json::json;
use std::fs;
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::process::Command;
use std::time::{Duration, Instant};
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

fn setup() -> (TempDir, TempDir, std::path::PathBuf) {
    setup_with_commands(json!([["git", "diff", "--check"]]))
}

fn setup_with_commands(
    verification_commands: serde_json::Value,
) -> (TempDir, TempDir, std::path::PathBuf) {
    let repo = TempDir::new().unwrap();
    let evidence = TempDir::new().unwrap();
    git(&repo, &["init", "-q"]);
    git(&repo, &["config", "user.email", "test@example.invalid"]);
    git(&repo, &["config", "user.name", "Test"]);
    fs::write(repo.path().join("main.txt"), "base\n").unwrap();
    git(&repo, &["add", "."]);
    git(&repo, &["commit", "-qm", "base"]);
    let contract_path = evidence.path().join("contract.json");
    let contract = json!({
        "schema": "change-guardian-contract/v1",
        "repository_id": null,
        "baseline": null,
        "rules": [{"class":"implementation","patterns":["main.txt"],"allow_staged":true,"allow_unstaged":true,"allow_kinds":["file"],"allow_test_suppression":false}],
        "dependency_patterns": [], "generated": [], "test_ecosystems": [],
        "unknown_test_patterns": ["tests/**"],
        "verification_commands": verification_commands,
        "contract_hash": null
    });
    fs::write(
        &contract_path,
        serde_json::to_vec_pretty(&contract).unwrap(),
    )
    .unwrap();
    seal_contract(&contract_path, repo.path()).unwrap();
    (repo, evidence, contract_path)
}

fn framed_digest(stdout: &[u8], stderr: &[u8]) -> String {
    let mut framed = Vec::new();
    framed.extend_from_slice(&(stdout.len() as u64).to_be_bytes());
    framed.extend_from_slice(stdout);
    framed.extend_from_slice(&(stderr.len() as u64).to_be_bytes());
    framed.extend_from_slice(stderr);
    change_guardian::hash_bytes(&framed)
}

#[test]
fn receipt_rejects_post_green_mutation_and_cross_repository_reuse() {
    let (repo, evidence, contract_path) = setup();
    fs::write(repo.path().join("main.txt"), "allowed\n").unwrap();
    let receipt_path = evidence.path().join("receipt.json");
    let receipt = run_verification(
        &contract_path,
        &receipt_path,
        repo.path(),
        &["git".into(), "diff".into(), "--check".into()],
    )
    .unwrap();
    assert_eq!(receipt.exit_status, 0);
    check_receipt(&contract_path, &receipt_path, repo.path()).unwrap();

    fs::write(repo.path().join("main.txt"), "mutated after green\n").unwrap();
    assert!(check_receipt(&contract_path, &receipt_path, repo.path()).is_err());

    let other = TempDir::new().unwrap();
    git(&other, &["init", "-q"]);
    assert!(check_receipt(&contract_path, &receipt_path, other.path()).is_err());
}

#[test]
fn unapproved_verification_command_is_rejected() {
    let (repo, evidence, contract_path) = setup();
    let receipt_path = evidence.path().join("receipt.json");
    assert!(
        run_verification(&contract_path, &receipt_path, repo.path(), &["true".into()],).is_err()
    );
}

#[test]
fn receipt_rejects_cross_branch_contract_replacement_and_receipt_corruption() {
    let (repo, evidence, contract_path) = setup();
    let receipt_path = evidence.path().join("receipt.json");
    run_verification(
        &contract_path,
        &receipt_path,
        repo.path(),
        &["git".into(), "diff".into(), "--check".into()],
    )
    .unwrap();

    let base_branch = Command::new("git")
        .current_dir(repo.path())
        .args(["branch", "--show-current"])
        .output()
        .unwrap();
    let base_branch = String::from_utf8(base_branch.stdout).unwrap();
    git(&repo, &["checkout", "-qb", "other"]);
    assert!(check_receipt(&contract_path, &receipt_path, repo.path()).is_err());
    git(&repo, &["checkout", "-q", base_branch.trim()]);

    let original_contract = fs::read(&contract_path).unwrap();
    let mut changed: serde_json::Value = serde_json::from_slice(&original_contract).unwrap();
    changed["verification_commands"] = json!([["true"]]);
    fs::write(&contract_path, serde_json::to_vec_pretty(&changed).unwrap()).unwrap();
    assert!(check_receipt(&contract_path, &receipt_path, repo.path()).is_err());
    fs::write(&contract_path, original_contract).unwrap();

    let mut receipt: serde_json::Value =
        serde_json::from_slice(&fs::read(&receipt_path).unwrap()).unwrap();
    receipt["output_digest"] =
        json!("sha256:0000000000000000000000000000000000000000000000000000000000000000");
    fs::write(&receipt_path, serde_json::to_vec_pretty(&receipt).unwrap()).unwrap();
    assert!(check_receipt(&contract_path, &receipt_path, repo.path()).is_err());
}

#[test]
fn verification_output_streams_concurrently_and_preserves_exact_limit_digest() {
    let exact_script = format!(
        "import sys; sys.stdout.buffer.write(b'a' * {})",
        change_guardian::MAX_VERIFICATION_OUTPUT_BYTES
    );
    let split_script = format!(
        "import sys; n={}; sys.stdout.buffer.write(b'o'*n); sys.stderr.buffer.write(b'e'*n)",
        change_guardian::MAX_VERIFICATION_OUTPUT_BYTES / 2
    );
    let commands = json!([
        ["python3", "-c", exact_script],
        ["python3", "-c", split_script]
    ]);
    let (repo, evidence, contract_path) = setup_with_commands(commands);
    let exact_receipt_path = evidence.path().join("exact.json");
    let exact_command = vec!["python3".into(), "-c".into(), exact_script];
    let exact = run_verification(
        &contract_path,
        &exact_receipt_path,
        repo.path(),
        &exact_command,
    )
    .unwrap();
    let exact_bytes = vec![b'a'; change_guardian::MAX_VERIFICATION_OUTPUT_BYTES];
    assert_eq!(exact.output_digest, framed_digest(&exact_bytes, b""));

    let split_receipt_path = evidence.path().join("split.json");
    let split_command = vec!["python3".into(), "-c".into(), split_script];
    let split = run_verification(
        &contract_path,
        &split_receipt_path,
        repo.path(),
        &split_command,
    )
    .unwrap();
    let half = change_guardian::MAX_VERIFICATION_OUTPUT_BYTES / 2;
    assert_eq!(
        split.output_digest,
        framed_digest(&vec![b'o'; half], &vec![b'e'; half])
    );
}

#[test]
fn limit_plus_one_kills_and_reaps_the_direct_child() {
    let pid_dir = TempDir::new().unwrap();
    let pid_path = pid_dir.path().join("child.pid");
    let script = format!(
        "import os,sys,time; open({:?},'w').write(str(os.getpid())); sys.stdout.buffer.write(b'x' * {}); sys.stdout.flush(); time.sleep(10)",
        pid_path,
        change_guardian::MAX_VERIFICATION_OUTPUT_BYTES + 1
    );
    let commands = json!([["python3", "-c", script]]);
    let (repo, evidence, contract_path) = setup_with_commands(commands);
    let receipt_path = evidence.path().join("too-large.json");
    let command = vec!["python3".into(), "-c".into(), script];
    let started = Instant::now();
    let error = run_verification(&contract_path, &receipt_path, repo.path(), &command)
        .unwrap_err()
        .to_string();
    assert!(
        started.elapsed() < Duration::from_secs(5),
        "guard waited for the oversized child instead of terminating it early"
    );
    assert!(
        error.contains("exceeds the 16777216 byte receipt limit"),
        "{error}"
    );
    assert!(!receipt_path.exists());
    let pid = fs::read_to_string(&pid_path).unwrap();
    assert!(
        !Command::new("kill")
            .args(["-0", pid.trim()])
            .output()
            .unwrap()
            .status
            .success(),
        "direct child {pid} was not reaped"
    );
}

#[test]
#[cfg(unix)]
fn receipt_uses_one_post_command_repository_observation() {
    let (repo, evidence, contract_path) = setup();
    let marker = evidence.path().join("verification-finished");
    let counter = evidence.path().join("post-command-observation-count");
    let wrapper_dir = evidence.path().join("bin");
    fs::create_dir(&wrapper_dir).unwrap();
    let wrapper = wrapper_dir.join("git");
    let real_git = Command::new("sh")
        .args(["-c", "command -v git"])
        .output()
        .unwrap();
    assert!(real_git.status.success());
    let real_git = String::from_utf8(real_git.stdout).unwrap();
    let script = format!(
        "#!/bin/sh\nif [ \"$1\" = diff ] && [ \"$2\" = --check ]; then\n  {git:?} \"$@\"\n  wrapper_status=$?\n  : > {marker:?}\n  exit $wrapper_status\nfi\nif [ -f {marker:?} ] && [ \"$1\" = rev-parse ] && [ \"$2\" = --show-toplevel ]; then\n  echo observation >> {counter:?}\nfi\nexec {git:?} \"$@\"\n",
        git = real_git.trim(),
        marker = marker,
        counter = counter,
    );
    fs::write(&wrapper, script).unwrap();
    fs::set_permissions(&wrapper, fs::Permissions::from_mode(0o755)).unwrap();
    let receipt_path = evidence.path().join("receipt.json");
    let output = Command::new(env!("CARGO_BIN_EXE_change-guardian"))
        .args([
            "verify",
            "--contract",
            contract_path.to_str().unwrap(),
            "--receipt",
            receipt_path.to_str().unwrap(),
            "--repository",
            repo.path().to_str().unwrap(),
            "--",
            "git",
            "diff",
            "--check",
        ])
        .env("PATH", format!("{}:/usr/bin:/bin", wrapper_dir.display()))
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let count = fs::read_to_string(counter).unwrap();
    assert_eq!(
        count.lines().count(),
        1,
        "post-command state was captured more than once"
    );
}

#[test]
#[cfg(unix)]
fn check_receipt_uses_one_current_repository_observation() {
    let (repo, evidence, contract_path) = setup();
    let receipt_path = evidence.path().join("receipt.json");
    run_verification(
        &contract_path,
        &receipt_path,
        repo.path(),
        &["git".into(), "diff".into(), "--check".into()],
    )
    .unwrap();

    let counter = evidence.path().join("check-receipt-observation-count");
    let wrapper_dir = evidence.path().join("check-bin");
    fs::create_dir(&wrapper_dir).unwrap();
    let wrapper = wrapper_dir.join("git");
    let real_git = Command::new("sh")
        .args(["-c", "command -v git"])
        .output()
        .unwrap();
    assert!(real_git.status.success());
    let real_git = String::from_utf8(real_git.stdout).unwrap();
    let script = format!(
        "#!/bin/sh\nif [ \"$1\" = rev-parse ] && [ \"$2\" = --show-toplevel ]; then\n  echo observation >> {counter:?}\nfi\nexec {git:?} \"$@\"\n",
        counter = counter,
        git = real_git.trim(),
    );
    fs::write(&wrapper, script).unwrap();
    fs::set_permissions(&wrapper, fs::Permissions::from_mode(0o755)).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_change-guardian"))
        .args([
            "check-receipt",
            "--contract",
            contract_path.to_str().unwrap(),
            "--receipt",
            receipt_path.to_str().unwrap(),
            "--repository",
            repo.path().to_str().unwrap(),
        ])
        .env("PATH", format!("{}:/usr/bin:/bin", wrapper_dir.display()))
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let count = fs::read_to_string(counter).unwrap();
    assert_eq!(
        count.lines().count(),
        1,
        "check-receipt captured current repository state more than once"
    );
}

#[test]
fn suppression_count_and_work_digest_match_one_captured_byte_set() {
    let repo = TempDir::new().unwrap();
    let evidence = TempDir::new().unwrap();
    git(&repo, &["init", "-q"]);
    git(&repo, &["config", "user.email", "test@example.invalid"]);
    git(&repo, &["config", "user.name", "Test"]);
    fs::create_dir(repo.path().join("tests")).unwrap();
    let test_bytes = b"#[allow(dead_code)]\n#[allow(unused_variables)]\n";
    fs::write(repo.path().join("tests/case.rs"), test_bytes).unwrap();
    git(&repo, &["add", "."]);
    git(&repo, &["commit", "-qm", "base"]);

    let contract_path = evidence.path().join("contract.json");
    let contract = json!({
        "schema": "change-guardian-contract/v1",
        "repository_id": null,
        "baseline": null,
        "rules": [{"class":"test","patterns":["tests/**"],"allow_staged":true,"allow_unstaged":true,"allow_kinds":["file"],"allow_test_suppression":false}],
        "dependency_patterns": [], "generated": [],
        "test_ecosystems": [{"name":"rust","patterns":["tests/**"],"suppression_markers":["#[allow("]}],
        "unknown_test_patterns": ["tests/**"],
        "verification_commands": [["git", "diff", "--check"]],
        "contract_hash": null
    });
    fs::write(
        &contract_path,
        serde_json::to_vec_pretty(&contract).unwrap(),
    )
    .unwrap();
    seal_contract(&contract_path, repo.path()).unwrap();

    let sealed: serde_json::Value =
        serde_json::from_slice(&fs::read(&contract_path).unwrap()).unwrap();
    let baseline = &sealed["baseline"];
    assert_eq!(
        baseline["snapshot"]["entries"]["tests/case.rs"]["work_digest"],
        json!(change_guardian::hash_bytes(test_bytes))
    );
    let counts = baseline["suppression_counts"].as_object().unwrap();
    assert_eq!(counts.len(), 1);
    assert_eq!(counts.values().next().unwrap(), &json!(2));
}
