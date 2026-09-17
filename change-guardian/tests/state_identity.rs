use change_guardian::{RepositorySnapshot, hash_bytes};
use std::fs;
use std::process::Command;
use tempfile::TempDir;

fn git(repo: &TempDir, args: &[&str]) {
    let status = Command::new("git")
        .current_dir(repo.path())
        .args(args)
        .status()
        .expect("run git");
    assert!(status.success(), "git {args:?} failed");
}

#[test]
fn snapshot_changes_when_tracked_content_changes() {
    let repo = TempDir::new().unwrap();
    git(&repo, &["init", "-q"]);
    git(&repo, &["config", "user.email", "test@example.invalid"]);
    git(&repo, &["config", "user.name", "Test"]);
    fs::write(repo.path().join("main.txt"), "before\n").unwrap();
    git(&repo, &["add", "main.txt"]);
    git(&repo, &["commit", "-qm", "base"]);

    let before = RepositorySnapshot::capture(repo.path()).unwrap();
    fs::write(repo.path().join("main.txt"), "after\n").unwrap();
    let after = RepositorySnapshot::capture(repo.path()).unwrap();

    assert_ne!(before.state_hash, after.state_hash);
    assert_eq!(
        hash_bytes(b"abc"),
        "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
}
