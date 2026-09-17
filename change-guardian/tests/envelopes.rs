use change_guardian::{evaluate_envelope, seal_contract};
use serde_json::json;
use std::fs;
use std::process::Command;
use tempfile::TempDir;

fn setup() -> (TempDir, TempDir, change_guardian::Contract) {
    let repo = TempDir::new().unwrap();
    let evidence = TempDir::new().unwrap();
    assert!(
        Command::new("git")
            .current_dir(repo.path())
            .args(["init", "-q"])
            .status()
            .unwrap()
            .success()
    );
    assert!(
        Command::new("git")
            .current_dir(repo.path())
            .args(["config", "user.email", "test@example.invalid"])
            .status()
            .unwrap()
            .success()
    );
    assert!(
        Command::new("git")
            .current_dir(repo.path())
            .args(["config", "user.name", "Test"])
            .status()
            .unwrap()
            .success()
    );
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
    let path = evidence.path().join("contract.json");
    let value = json!({
        "schema":"change-guardian-contract/v1","repository_id":null,"baseline":null,
        "rules":[{"class":"implementation","patterns":["allowed.txt"],"allow_staged":true,"allow_unstaged":true,"allow_kinds":["file"],"allow_test_suppression":false}],
        "dependency_patterns":[],"generated":[],"test_ecosystems":[],"unknown_test_patterns":["tests/**"],
        "verification_commands":[["git","diff","--check"]],"contract_hash":null
    });
    fs::write(&path, serde_json::to_vec_pretty(&value).unwrap()).unwrap();
    let contract = seal_contract(&path, repo.path()).unwrap();
    (repo, evidence, contract)
}

#[test]
fn claude_codex_and_antigravity_envelopes_report_denial() {
    let (repo, _evidence, contract) = setup();
    fs::write(repo.path().join("surprise.txt"), "no\n").unwrap();
    let claude = json!({"hook_event_name":"PostToolUse","cwd":repo.path(),"tool_input":{"command":"touch surprise.txt"}});
    let claude_output = evaluate_envelope(&contract, &claude, None).unwrap();
    assert_eq!(
        claude_output["hookSpecificOutput"]["permissionDecision"],
        "deny"
    );
    assert_eq!(
        claude_output["changeContainmentGuard"]["surface"],
        "claude_codex"
    );

    let antigravity = json!({"toolCall":{"name":"run_command","args":{"CommandLine":"touch surprise.txt","Cwd":repo.path()}}});
    let antigravity_output = evaluate_envelope(&contract, &antigravity, None).unwrap();
    assert_eq!(antigravity_output["decision"], "deny");
    assert_eq!(
        antigravity_output["changeContainmentGuard"]["surface"],
        "antigravity"
    );
}

#[test]
fn malformed_or_unknown_envelope_fails_closed() {
    let (_repo, _evidence, contract) = setup();
    assert!(evaluate_envelope(&contract, &json!({"unknown":true}), None).is_err());
    assert!(evaluate_envelope(&contract, &json!({"tool_input":{}}), None).is_err());
}
