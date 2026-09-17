use change_guardian::{ChangeClass, RepositorySnapshot, evaluate_contract, seal_contract};
use serde_json::{Value, json};
use std::fs;
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::process::Command;
use tempfile::TempDir;

fn git(repo: &TempDir, args: &[&str]) {
    let output = Command::new("git")
        .current_dir(repo.path())
        .args(args)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "git {args:?}: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}

fn repo() -> TempDir {
    let repo = TempDir::new().unwrap();
    git(&repo, &["init", "-q"]);
    git(&repo, &["config", "user.email", "test@example.invalid"]);
    git(&repo, &["config", "user.name", "Test"]);
    repo
}

#[cfg(unix)]
fn make_file_symlink(target: &str, link: &std::path::Path) {
    std::os::unix::fs::symlink(target, link).unwrap();
}

fn rule(class: &str, patterns: &[&str], kinds: &[&str]) -> Value {
    json!({
        "class": class,
        "patterns": patterns,
        "allow_staged": true,
        "allow_unstaged": true,
        "allow_kinds": kinds,
        "allow_test_suppression": false
    })
}

fn seal(
    repository: &TempDir,
    rules: Vec<Value>,
    dependency_patterns: Vec<&str>,
    generated: Vec<Value>,
    ecosystems: Vec<Value>,
) -> (TempDir, change_guardian::Contract) {
    let evidence = TempDir::new().unwrap();
    let path = evidence.path().join("contract.json");
    let contract = json!({
        "schema": "change-guardian-contract/v1",
        "repository_id": null,
        "baseline": null,
        "rules": rules,
        "dependency_patterns": dependency_patterns,
        "generated": generated,
        "test_ecosystems": ecosystems,
        "unknown_test_patterns": ["tests/**", "test/**", "**/*_test.*", "**/*.test.*", "**/*.spec.*"],
        "verification_commands": [["git", "diff", "--check"]],
        "contract_hash": null
    });
    fs::write(&path, serde_json::to_vec_pretty(&contract).unwrap()).unwrap();
    let sealed = seal_contract(&path, repository.path()).unwrap();
    (evidence, sealed)
}

#[test]
fn possibly_dirty_baseline_is_stable_and_new_delta_is_detected() {
    let repository = repo();
    fs::write(repository.path().join("dirty.txt"), "baseline dirty\n").unwrap();
    let (_evidence, contract) = seal(
        &repository,
        vec![rule("implementation", &["dirty.txt"], &["file"])],
        vec![],
        vec![],
        vec![],
    );
    assert!(
        evaluate_contract(&contract, repository.path())
            .unwrap()
            .changes
            .is_empty()
    );
    fs::write(repository.path().join("dirty.txt"), "new delta\n").unwrap();
    let result = evaluate_contract(&contract, repository.path()).unwrap();
    assert_eq!(result.changes.len(), 1);
    assert!(result.changes[0].unstaged);
}

#[test]
fn staged_and_unstaged_are_reported_separately() {
    let repository = repo();
    fs::write(repository.path().join("both.txt"), "base\n").unwrap();
    git(&repository, &["add", "."]);
    git(&repository, &["commit", "-qm", "base"]);
    let (_evidence, contract) = seal(
        &repository,
        vec![rule("implementation", &["both.txt"], &["file"])],
        vec![],
        vec![],
        vec![],
    );
    fs::write(repository.path().join("both.txt"), "staged\n").unwrap();
    git(&repository, &["add", "both.txt"]);
    let staged = evaluate_contract(&contract, repository.path()).unwrap();
    assert!(staged.changes[0].staged);
    assert!(!staged.changes[0].unstaged);
    fs::write(repository.path().join("both.txt"), "staged plus unstaged\n").unwrap();
    let both = evaluate_contract(&contract, repository.path()).unwrap();
    assert!(both.changes[0].staged && both.changes[0].unstaged);
}

#[test]
#[cfg(unix)]
fn mode_only_change_is_not_silently_ignored() {
    let repository = repo();
    fs::write(repository.path().join("script.sh"), "echo ok\n").unwrap();
    git(&repository, &["add", "."]);
    git(&repository, &["commit", "-qm", "base"]);
    let (_evidence, contract) = seal(
        &repository,
        vec![rule("implementation", &["script.sh"], &["file"])],
        vec![],
        vec![],
        vec![],
    );
    fs::set_permissions(
        repository.path().join("script.sh"),
        fs::Permissions::from_mode(0o755),
    )
    .unwrap();
    let result = evaluate_contract(&contract, repository.path()).unwrap();
    assert_eq!(result.changes.len(), 1);
    assert!(result.changes[0].unstaged);
}

#[test]
fn rename_is_delete_plus_add() {
    let repository = repo();
    fs::write(repository.path().join("old.txt"), "same\n").unwrap();
    git(&repository, &["add", "."]);
    git(&repository, &["commit", "-qm", "base"]);
    let (_evidence, contract) = seal(
        &repository,
        vec![rule("implementation", &["old.txt", "new.txt"], &["file"])],
        vec![],
        vec![],
        vec![],
    );
    fs::rename(
        repository.path().join("old.txt"),
        repository.path().join("new.txt"),
    )
    .unwrap();
    let result = evaluate_contract(&contract, repository.path()).unwrap();
    assert!(result.violations.is_empty(), "{:?}", result.violations);
    assert!(
        result
            .changes
            .iter()
            .any(|change| change.path == "old.txt" && change.operation == "delete")
    );
    assert!(
        result
            .changes
            .iter()
            .any(|change| change.path == "new.txt" && change.operation == "add")
    );
}

#[test]
fn protected_git_files_need_exact_rules() {
    for path in [
        ".gitignore",
        ".gitattributes",
        ".gitmodules",
        "sub/.gitignore",
        "sub/.gitattributes",
        "sub/.gitmodules",
    ] {
        let repository = repo();
        if path.starts_with("sub/") {
            fs::create_dir(repository.path().join("sub")).unwrap();
        }
        fs::write(repository.path().join(path), "base\n").unwrap();
        git(&repository, &["add", "."]);
        git(&repository, &["commit", "-qm", "base"]);
        let (_evidence, contract) = seal(
            &repository,
            vec![rule("implementation", &["**"], &["file"])],
            vec![],
            vec![],
            vec![],
        );
        let (_exact_evidence, exact_contract) = seal(
            &repository,
            vec![rule("implementation", &[path], &["file"])],
            vec![],
            vec![],
            vec![],
        );
        fs::write(repository.path().join(path), "changed\n").unwrap();
        let result = evaluate_contract(&contract, repository.path()).unwrap();
        assert!(
            result
                .violations
                .iter()
                .any(|message| message.contains("exact rule")),
            "{path}: {:?}",
            result.violations
        );
        assert!(
            evaluate_contract(&exact_contract, repository.path())
                .unwrap()
                .violations
                .is_empty()
        );
    }
}

#[test]
fn nested_gitignore_cannot_hide_an_unclassified_file_without_an_exact_rule() {
    let repository = repo();
    fs::write(repository.path().join("base.txt"), "base\n").unwrap();
    git(&repository, &["add", "."]);
    git(&repository, &["commit", "-qm", "base"]);
    let (_broad_evidence, broad_contract) = seal(
        &repository,
        vec![rule("implementation", &["**/.gitignore"], &["file"])],
        vec![],
        vec![],
        vec![],
    );
    let (_exact_evidence, exact_contract) = seal(
        &repository,
        vec![rule("implementation", &["sub/.gitignore"], &["file"])],
        vec![],
        vec![],
        vec![],
    );

    fs::create_dir(repository.path().join("sub")).unwrap();
    fs::write(repository.path().join("sub/.gitignore"), "smuggled.txt\n").unwrap();
    fs::write(
        repository.path().join("sub/smuggled.txt"),
        "unclassified but ignored\n",
    )
    .unwrap();

    let broad = evaluate_contract(&broad_contract, repository.path()).unwrap();
    assert_eq!(broad.changes.len(), 1, "{:?}", broad.changes);
    assert_eq!(broad.changes[0].path, "sub/.gitignore");
    assert!(
        broad
            .violations
            .iter()
            .any(|message| message.contains("protected Git control file needs an exact rule")),
        "{:?}",
        broad.violations
    );

    let exact = evaluate_contract(&exact_contract, repository.path()).unwrap();
    assert_eq!(exact.changes.len(), 1, "{:?}", exact.changes);
    assert!(exact.violations.is_empty(), "{:?}", exact.violations);
}

#[test]
fn ignored_worktree_files_are_excluded_by_git() {
    let repository = repo();
    fs::write(repository.path().join(".gitignore"), "*.log\n").unwrap();
    fs::write(repository.path().join("kept.txt"), "base\n").unwrap();
    fs::write(repository.path().join("ignored.log"), "baseline\n").unwrap();
    git(&repository, &["add", "."]);
    git(&repository, &["commit", "-qm", "base"]);
    let (_evidence, contract) = seal(
        &repository,
        vec![rule("implementation", &["kept.txt"], &["file"])],
        vec![],
        vec![],
        vec![],
    );
    fs::write(repository.path().join("ignored.log"), "changed\n").unwrap();
    assert!(
        evaluate_contract(&contract, repository.path())
            .unwrap()
            .changes
            .is_empty()
    );
}

#[test]
#[cfg(unix)]
fn symlink_kind_needs_explicit_permission() {
    let repository = repo();
    fs::write(repository.path().join("target"), "content\n").unwrap();
    git(&repository, &["add", "."]);
    git(&repository, &["commit", "-qm", "base"]);
    let (_evidence, contract) = seal(
        &repository,
        vec![rule("implementation", &["link"], &["file"])],
        vec![],
        vec![],
        vec![],
    );
    let (_allowed_evidence, allowed_contract) = seal(
        &repository,
        vec![rule("implementation", &["link"], &["symlink"])],
        vec![],
        vec![],
        vec![],
    );
    make_file_symlink("target", &repository.path().join("link"));
    let result = evaluate_contract(&contract, repository.path()).unwrap();
    assert!(
        result
            .violations
            .iter()
            .any(|message| message.contains("symlink"))
    );
    assert!(
        evaluate_contract(&allowed_contract, repository.path())
            .unwrap()
            .violations
            .is_empty()
    );
}

#[test]
fn submodule_pointer_needs_explicit_kind_permission() {
    let source = repo();
    fs::write(source.path().join("lib.txt"), "one\n").unwrap();
    git(&source, &["add", "."]);
    git(&source, &["commit", "-qm", "one"]);
    let first = Command::new("git")
        .current_dir(source.path())
        .args(["rev-parse", "HEAD"])
        .output()
        .unwrap();
    let first = String::from_utf8(first.stdout).unwrap();
    fs::write(source.path().join("lib.txt"), "two\n").unwrap();
    git(&source, &["commit", "-qam", "two"]);
    let second = Command::new("git")
        .current_dir(source.path())
        .args(["rev-parse", "HEAD"])
        .output()
        .unwrap();
    let second = String::from_utf8(second.stdout).unwrap();

    let repository = repo();
    let source_path = source.path().to_str().unwrap();
    git(
        &repository,
        &[
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            source_path,
            "vendor/sub",
        ],
    );
    let submodule = repository.path().join("vendor/sub");
    assert!(
        Command::new("git")
            .current_dir(&submodule)
            .args(["checkout", "-q", first.trim()])
            .status()
            .unwrap()
            .success()
    );
    git(&repository, &["add", "."]);
    git(&repository, &["commit", "-qm", "base"]);
    let (_evidence, contract) = seal(
        &repository,
        vec![rule("implementation", &["vendor/sub"], &["file"])],
        vec![],
        vec![],
        vec![],
    );
    let (_allowed_evidence, allowed_contract) = seal(
        &repository,
        vec![rule("implementation", &["vendor/sub"], &["submodule"])],
        vec![],
        vec![],
        vec![],
    );
    assert!(
        Command::new("git")
            .current_dir(&submodule)
            .args(["checkout", "-q", second.trim()])
            .status()
            .unwrap()
            .success()
    );
    let result = evaluate_contract(&contract, repository.path()).unwrap();
    assert!(
        result
            .violations
            .iter()
            .any(|message| message.contains("submodule")),
        "{:?}",
        result.violations
    );
    assert!(
        evaluate_contract(&allowed_contract, repository.path())
            .unwrap()
            .violations
            .is_empty()
    );
}

#[test]
fn dirty_submodule_content_is_rejected_at_the_snapshot_boundary() {
    let source = repo();
    fs::write(source.path().join("lib.txt"), "base\n").unwrap();
    git(&source, &["add", "."]);
    git(&source, &["commit", "-qm", "base"]);

    let repository = repo();
    git(
        &repository,
        &[
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            source.path().to_str().unwrap(),
            "vendor/sub",
        ],
    );
    git(&repository, &["add", "."]);
    git(&repository, &["commit", "-qm", "base"]);
    let submodule = repository.path().join("vendor/sub");

    fs::write(submodule.join("lib.txt"), "dirty tracked\n").unwrap();
    let tracked = RepositorySnapshot::capture(repository.path())
        .unwrap_err()
        .to_string();
    assert!(tracked.contains("dirty initialized submodule"), "{tracked}");

    assert!(
        Command::new("git")
            .current_dir(&submodule)
            .args(["checkout", "-q", "--", "lib.txt"])
            .status()
            .unwrap()
            .success()
    );
    fs::write(submodule.join("untracked.txt"), "dirty untracked\n").unwrap();
    let untracked = RepositorySnapshot::capture(repository.path())
        .unwrap_err()
        .to_string();
    assert!(
        untracked.contains("dirty initialized submodule"),
        "{untracked}"
    );
}

#[test]
fn nested_dirty_submodule_content_is_rejected_at_the_snapshot_boundary() {
    let inner = repo();
    fs::write(inner.path().join("inner.txt"), "base\n").unwrap();
    git(&inner, &["add", "."]);
    git(&inner, &["commit", "-qm", "base"]);

    let middle = repo();
    git(
        &middle,
        &[
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            inner.path().to_str().unwrap(),
            "nested/inner",
        ],
    );
    git(&middle, &["add", "."]);
    git(&middle, &["commit", "-qm", "middle"]);

    let repository = repo();
    git(
        &repository,
        &[
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            middle.path().to_str().unwrap(),
            "vendor/middle",
        ],
    );
    git(
        &repository,
        &[
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "update",
            "--init",
            "--recursive",
        ],
    );
    git(&repository, &["add", "."]);
    git(&repository, &["commit", "-qm", "outer"]);

    fs::write(
        repository
            .path()
            .join("vendor/middle/nested/inner/inner.txt"),
        "nested dirty\n",
    )
    .unwrap();
    let error = RepositorySnapshot::capture(repository.path())
        .unwrap_err()
        .to_string();
    assert!(error.contains("dirty initialized submodule"), "{error}");
}

#[test]
fn dependency_and_generated_contracts_are_enforced() {
    let repository = repo();
    fs::create_dir_all(repository.path().join("src")).unwrap();
    fs::create_dir_all(repository.path().join("dist")).unwrap();
    fs::write(repository.path().join("src/input.txt"), "base\n").unwrap();
    fs::write(repository.path().join("dist/output.txt"), "base\n").unwrap();
    fs::write(repository.path().join("Cargo.lock"), "base\n").unwrap();
    git(&repository, &["add", "."]);
    git(&repository, &["commit", "-qm", "base"]);
    let generated =
        json!({"patterns":["dist/**"],"source_patterns":["src/**"],"requires_source_change":true});
    let (_evidence, contract) = seal(
        &repository,
        vec![
            rule("implementation", &["src/**"], &["file"]),
            rule("implementation", &["Cargo.lock"], &["file"]),
            rule("generated", &["dist/**"], &["file"]),
        ],
        vec!["Cargo.lock"],
        vec![generated],
        vec![],
    );
    let (_allowed_evidence, allowed_contract) = seal(
        &repository,
        vec![
            rule("implementation", &["src/**"], &["file"]),
            rule("dependency", &["Cargo.lock"], &["file"]),
            rule("generated", &["dist/**"], &["file"]),
        ],
        vec!["Cargo.lock"],
        vec![
            json!({"patterns":["dist/**"],"source_patterns":["src/**"],"requires_source_change":true}),
        ],
        vec![],
    );
    fs::write(repository.path().join("Cargo.lock"), "changed\n").unwrap();
    fs::write(repository.path().join("dist/output.txt"), "changed\n").unwrap();
    let denied = evaluate_contract(&contract, repository.path()).unwrap();
    assert!(
        denied
            .violations
            .iter()
            .any(|message| message.contains("dependency class"))
    );
    assert!(
        denied
            .violations
            .iter()
            .any(|message| message.contains("no declared source"))
    );
    fs::write(repository.path().join("src/input.txt"), "changed\n").unwrap();
    assert!(
        evaluate_contract(&allowed_contract, repository.path())
            .unwrap()
            .violations
            .is_empty()
    );
}

#[test]
fn evaluator_is_kept_separate_from_implementation() {
    let repository = repo();
    fs::create_dir(repository.path().join("evaluator")).unwrap();
    fs::write(repository.path().join("evaluator/oracle.txt"), "base\n").unwrap();
    git(&repository, &["add", "."]);
    git(&repository, &["commit", "-qm", "base"]);
    let (_evidence, contract) = seal(
        &repository,
        vec![rule("evaluator", &["evaluator/**"], &["file"])],
        vec![],
        vec![],
        vec![],
    );
    fs::write(repository.path().join("evaluator/oracle.txt"), "changed\n").unwrap();
    let result = evaluate_contract(&contract, repository.path()).unwrap();
    assert!(result.violations.is_empty());
    assert_eq!(result.changes[0].class, Some(ChangeClass::Evaluator));
}

#[test]
fn test_suppression_and_unknown_ecosystems_need_human_approval() {
    let repository = repo();
    fs::create_dir(repository.path().join("tests")).unwrap();
    fs::write(
        repository.path().join("tests/known.rs"),
        "#[test]\nfn works() {}\n",
    )
    .unwrap();
    fs::write(repository.path().join("tests/unknown.xyz"), "test\n").unwrap();
    git(&repository, &["add", "."]);
    git(&repository, &["commit", "-qm", "base"]);
    let rust =
        json!({"name":"rust","patterns":["tests/**/*.rs"],"suppression_markers":["#[ignore]"]});
    let (_evidence, contract) = seal(
        &repository,
        vec![rule("test", &["tests/**"], &["file"])],
        vec![],
        vec![],
        vec![rust],
    );
    let mut allowed_rule = rule("test", &["tests/**"], &["file"]);
    allowed_rule["allow_test_suppression"] = json!(true);
    let (_allowed_evidence, allowed_contract) = seal(
        &repository,
        vec![allowed_rule],
        vec![],
        vec![],
        vec![
            json!({"name":"rust","patterns":["tests/**/*.rs"],"suppression_markers":["#[ignore]"]}),
        ],
    );
    fs::write(
        repository.path().join("tests/known.rs"),
        "#[test]\n#[ignore]\nfn works() {}\n",
    )
    .unwrap();
    let allowed_known = evaluate_contract(&allowed_contract, repository.path()).unwrap();
    assert!(
        allowed_known.violations.is_empty(),
        "{:?}",
        allowed_known.violations
    );
    fs::write(repository.path().join("tests/unknown.xyz"), "changed\n").unwrap();
    let result = evaluate_contract(&contract, repository.path()).unwrap();
    assert!(
        result
            .violations
            .iter()
            .any(|message| message.contains("suppression marker")),
        "{:?}",
        result.violations
    );
    assert!(
        result
            .violations
            .iter()
            .any(|message| message.contains("unknown ecosystem")),
        "{:?}",
        result.violations
    );
}

#[test]
#[cfg(unix)]
fn overlapping_same_class_rules_are_order_independent_and_fail_closed() {
    let repository = repo();
    fs::create_dir(repository.path().join("tests")).unwrap();
    fs::write(
        repository.path().join("tests/narrow.rs"),
        "#[test]\nfn works() {}\n",
    )
    .unwrap();
    git(&repository, &["add", "."]);
    git(&repository, &["commit", "-qm", "base"]);

    let broad = json!({
        "class": "test",
        "patterns": ["tests/**"],
        "allow_staged": true,
        "allow_unstaged": true,
        "allow_kinds": ["file", "symlink"],
        "allow_test_suppression": true
    });
    let narrow = json!({
        "class": "test",
        "patterns": ["tests/narrow*"],
        "allow_staged": false,
        "allow_unstaged": false,
        "allow_kinds": ["file"],
        "allow_test_suppression": false
    });
    let ecosystem =
        json!({"name":"rust","patterns":["tests/**/*.rs"],"suppression_markers":["#[ignore]"]});
    let (_first_evidence, broad_first) = seal(
        &repository,
        vec![broad.clone(), narrow.clone()],
        vec![],
        vec![],
        vec![ecosystem.clone()],
    );
    let (_second_evidence, narrow_first) = seal(
        &repository,
        vec![narrow, broad],
        vec![],
        vec![],
        vec![ecosystem],
    );

    fs::write(
        repository.path().join("tests/narrow.rs"),
        "#[test]\n#[ignore]\nfn works() { assert!(true); }\n",
    )
    .unwrap();
    git(&repository, &["add", "tests/narrow.rs"]);
    fs::write(
        repository.path().join("tests/narrow.rs"),
        "#[test]\n#[ignore]\nfn works() { assert!(true); }\n// unstaged\n",
    )
    .unwrap();
    make_file_symlink("narrow.rs", &repository.path().join("tests/narrow-link.rs"));

    let broad_first_result = evaluate_contract(&broad_first, repository.path()).unwrap();
    let narrow_first_result = evaluate_contract(&narrow_first, repository.path()).unwrap();
    assert_eq!(
        broad_first_result.violations, narrow_first_result.violations,
        "same rules in reverse order must produce identical violations"
    );
    assert!(
        broad_first_result
            .violations
            .iter()
            .any(|message| message == "tests/narrow.rs: staged changes are not allowed")
    );
    assert!(
        broad_first_result
            .violations
            .iter()
            .any(|message| message.contains("unstaged changes are not allowed"))
    );
    assert!(
        broad_first_result
            .violations
            .iter()
            .any(|message| message.contains("entry kind symlink is not explicitly allowed"))
    );
    assert!(
        broad_first_result
            .violations
            .iter()
            .any(|message| message.contains("suppression marker"))
    );
}
