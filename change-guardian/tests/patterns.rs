use change_guardian::pattern_matches;

#[test]
fn glob_semantics_keep_single_and_double_star_distinct() {
    assert!(pattern_matches("src/**", "src/main.rs"));
    assert!(pattern_matches("tests/**/*.rs", "tests/known.rs"));
    assert!(pattern_matches("tests/**/*.rs", "tests/unit/known.rs"));
    assert!(pattern_matches("**/*.test.ts", "deep/path/x.test.ts"));
    assert!(pattern_matches("src/?.rs", "src/x.rs"));
    assert!(!pattern_matches("src/*.rs", "src/deep/x.rs"));
    assert!(!pattern_matches("tests/**/*.rs", "tests/known.py"));
}

#[test]
fn long_nonmatch_is_bounded_and_does_not_recurse() {
    let pattern = format!("{}z", "**a".repeat(512));
    let path = "a".repeat(2048);
    assert!(!pattern_matches(&pattern, &path));
}
