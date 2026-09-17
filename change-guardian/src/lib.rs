use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::OsStr;
use std::fmt;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, mpsc};
use std::thread;
use std::time::Duration;

pub const CONTRACT_SCHEMA: &str = "change-guardian-contract/v1";
pub const RECEIPT_SCHEMA: &str = "change-guardian-receipt/v1";
pub const MAX_VERIFICATION_OUTPUT_BYTES: usize = 16 * 1024 * 1024;

#[derive(Debug)]
pub struct GuardError(pub String);

impl fmt::Display for GuardError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for GuardError {}

impl From<std::io::Error> for GuardError {
    fn from(error: std::io::Error) -> Self {
        Self(error.to_string())
    }
}

impl From<serde_json::Error> for GuardError {
    fn from(error: serde_json::Error) -> Self {
        Self(error.to_string())
    }
}

pub type GuardResult<T> = Result<T, GuardError>;

pub fn hash_bytes(bytes: &[u8]) -> String {
    let mut digest = Sha256::new();
    digest.update(bytes);
    format!("sha256:{:x}", digest.finalize())
}

fn run_git<I, S>(repository: &Path, args: I) -> GuardResult<Vec<u8>>
where
    I: IntoIterator<Item = S>,
    S: AsRef<OsStr>,
{
    let output = Command::new("git")
        .current_dir(repository)
        .args(args)
        .output()
        .map_err(|error| GuardError(format!("cannot execute git: {error}")))?;
    if !output.status.success() {
        return Err(GuardError(format!(
            "git failed with {}: {}",
            output.status,
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    Ok(output.stdout)
}

fn git_text<I, S>(repository: &Path, args: I) -> GuardResult<String>
where
    I: IntoIterator<Item = S>,
    S: AsRef<OsStr>,
{
    let bytes = run_git(repository, args)?;
    Ok(String::from_utf8_lossy(&bytes).trim().to_owned())
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct SnapshotEntry {
    pub index_mode: Option<String>,
    pub index_oid: Option<String>,
    pub work_kind: String,
    pub work_digest: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct RepositorySnapshot {
    pub repository_id: String,
    pub root: String,
    pub branch: String,
    pub head: String,
    pub entries: BTreeMap<String, SnapshotEntry>,
    pub staged_paths: BTreeSet<String>,
    pub unstaged_paths: BTreeSet<String>,
    pub untracked_paths: BTreeSet<String>,
    pub state_hash: String,
}

#[derive(Serialize)]
struct SnapshotIdentity<'a> {
    repository_id: &'a str,
    branch: &'a str,
    head: &'a str,
    entries: &'a BTreeMap<String, SnapshotEntry>,
    staged_paths: &'a BTreeSet<String>,
    unstaged_paths: &'a BTreeSet<String>,
    untracked_paths: &'a BTreeSet<String>,
}

impl RepositorySnapshot {
    pub fn capture(repository: &Path) -> GuardResult<Self> {
        let root_text = git_text(repository, ["rev-parse", "--show-toplevel"])?;
        let root = fs::canonicalize(&root_text)
            .map_err(|error| GuardError(format!("cannot canonicalize repository root: {error}")))?;
        let root_string = root.to_string_lossy().into_owned();
        let git_common = git_text(&root, ["rev-parse", "--git-common-dir"])?;
        let git_common_path = if Path::new(&git_common).is_absolute() {
            PathBuf::from(git_common)
        } else {
            root.join(git_common)
        };
        let git_common_canonical = fs::canonicalize(&git_common_path).map_err(|error| {
            GuardError(format!("cannot canonicalize Git common directory: {error}"))
        })?;
        let origin = git_text(&root, ["config", "--get", "remote.origin.url"])
            .unwrap_or_else(|_| "NO_ORIGIN".to_owned());
        let repository_id = hash_bytes(
            format!(
                "root\0{}\0git-common\0{}\0origin\0{}",
                root_string,
                git_common_canonical.to_string_lossy(),
                origin
            )
            .as_bytes(),
        );
        let branch = git_text(&root, ["symbolic-ref", "--short", "HEAD"])
            .or_else(|_| git_text(&root, ["rev-parse", "--abbrev-ref", "HEAD"]))?;
        let head = git_text(&root, ["rev-parse", "HEAD"]).unwrap_or_else(|_| "UNBORN".to_owned());

        let mut index = BTreeMap::<String, (String, String)>::new();
        for record in run_git(&root, ["ls-files", "--stage", "-z"])?.split(|byte| *byte == 0) {
            if record.is_empty() {
                continue;
            }
            let tab = record
                .iter()
                .position(|byte| *byte == b'\t')
                .ok_or_else(|| GuardError("malformed git ls-files --stage record".to_owned()))?;
            let metadata = String::from_utf8_lossy(&record[..tab]);
            let mut fields = metadata.split_ascii_whitespace();
            let mode = fields
                .next()
                .ok_or_else(|| GuardError("missing index mode".to_owned()))?;
            let oid = fields
                .next()
                .ok_or_else(|| GuardError("missing index oid".to_owned()))?;
            let stage = fields
                .next()
                .ok_or_else(|| GuardError("missing index stage".to_owned()))?;
            if stage != "0" {
                return Err(GuardError(
                    "unmerged index entries require human resolution".to_owned(),
                ));
            }
            let path = String::from_utf8(record[tab + 1..].to_vec())
                .map_err(|_| GuardError("non-UTF-8 repository paths are unsupported".to_owned()))?;
            index.insert(path, (mode.to_owned(), oid.to_owned()));
        }

        let mut paths = index.keys().cloned().collect::<BTreeSet<_>>();
        let mut untracked_paths = BTreeSet::new();
        for record in run_git(&root, ["ls-files", "--others", "--exclude-standard", "-z"])?
            .split(|byte| *byte == 0)
        {
            if record.is_empty() {
                continue;
            }
            let path = String::from_utf8(record.to_vec())
                .map_err(|_| GuardError("non-UTF-8 repository paths are unsupported".to_owned()))?;
            untracked_paths.insert(path.clone());
            paths.insert(path);
        }

        let staged_paths = nul_path_set(run_git(
            &root,
            ["diff", "--cached", "--name-only", "-z", "--no-ext-diff"],
        )?)?;
        let unstaged_paths = nul_path_set(run_git(
            &root,
            ["diff", "--name-only", "-z", "--no-ext-diff"],
        )?)?;

        let mut entries = BTreeMap::new();
        for path in paths {
            let absolute = root.join(&path);
            let indexed = index.get(&path);
            let (work_kind, work_digest) = work_identity(&root, &absolute, indexed)?;
            entries.insert(
                path,
                SnapshotEntry {
                    index_mode: indexed.map(|(mode, _)| mode.clone()),
                    index_oid: indexed.map(|(_, oid)| oid.clone()),
                    work_kind,
                    work_digest,
                },
            );
        }
        let identity = SnapshotIdentity {
            repository_id: &repository_id,
            branch: &branch,
            head: &head,
            entries: &entries,
            staged_paths: &staged_paths,
            unstaged_paths: &unstaged_paths,
            untracked_paths: &untracked_paths,
        };
        let state_hash = hash_bytes(&serde_json::to_vec(&identity)?);
        Ok(Self {
            repository_id,
            root: root_string,
            branch,
            head,
            entries,
            staged_paths,
            unstaged_paths,
            untracked_paths,
            state_hash,
        })
    }
}

#[derive(Clone, Debug)]
struct ObservedRepositoryState {
    snapshot: RepositorySnapshot,
    suppression_counts: BTreeMap<String, u64>,
}

impl ObservedRepositoryState {
    fn capture(contract: &Contract, repository: &Path) -> GuardResult<Self> {
        let mut snapshot = RepositorySnapshot::capture(repository)?;
        let mut suppression_counts = BTreeMap::new();
        let root = Path::new(&snapshot.root);
        for (path, entry) in &mut snapshot.entries {
            if entry.work_kind != "file" {
                continue;
            }
            let ecosystems = contract
                .test_ecosystems
                .iter()
                .filter(|ecosystem| {
                    ecosystem
                        .patterns
                        .iter()
                        .any(|pattern| pattern_matches(pattern, path))
                })
                .collect::<Vec<_>>();
            if ecosystems.is_empty() {
                continue;
            }
            let bytes = fs::read(root.join(path)).map_err(|error| {
                GuardError(format!(
                    "cannot capture test file bytes for {path}: {error}"
                ))
            })?;
            entry.work_digest = hash_bytes(&bytes);
            let text = std::str::from_utf8(&bytes).map_err(|_| {
                GuardError(format!(
                    "test suppression scan requires UTF-8 text in {path}"
                ))
            })?;
            for ecosystem in ecosystems {
                for marker in &ecosystem.suppression_markers {
                    suppression_counts.insert(
                        suppression_key(&ecosystem.name, path, marker),
                        text.matches(marker).count() as u64,
                    );
                }
            }
        }
        snapshot.state_hash = snapshot_state_hash(&snapshot)?;
        Ok(Self {
            snapshot,
            suppression_counts,
        })
    }
}

fn snapshot_state_hash(snapshot: &RepositorySnapshot) -> GuardResult<String> {
    let identity = SnapshotIdentity {
        repository_id: &snapshot.repository_id,
        branch: &snapshot.branch,
        head: &snapshot.head,
        entries: &snapshot.entries,
        staged_paths: &snapshot.staged_paths,
        unstaged_paths: &snapshot.unstaged_paths,
        untracked_paths: &snapshot.untracked_paths,
    };
    Ok(hash_bytes(&serde_json::to_vec(&identity)?))
}

fn nul_path_set(bytes: Vec<u8>) -> GuardResult<BTreeSet<String>> {
    bytes
        .split(|byte| *byte == 0)
        .filter(|record| !record.is_empty())
        .map(|record| {
            String::from_utf8(record.to_vec())
                .map_err(|_| GuardError("non-UTF-8 repository paths are unsupported".to_owned()))
        })
        .collect()
}

#[derive(Clone, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ChangeClass {
    Implementation,
    Test,
    Evaluator,
    Dependency,
    Generated,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Rule {
    pub class: ChangeClass,
    pub patterns: Vec<String>,
    pub allow_staged: bool,
    pub allow_unstaged: bool,
    #[serde(default = "default_file_kind")]
    pub allow_kinds: Vec<String>,
    #[serde(default)]
    pub allow_test_suppression: bool,
}

#[derive(Debug)]
struct EffectiveRule {
    allow_staged: bool,
    allow_unstaged: bool,
    allow_kinds: BTreeSet<String>,
    allow_test_suppression: bool,
    exact_path_rule: bool,
}

fn default_file_kind() -> Vec<String> {
    vec!["file".to_owned()]
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GeneratedDeclaration {
    pub patterns: Vec<String>,
    #[serde(default)]
    pub source_patterns: Vec<String>,
    #[serde(default)]
    pub requires_source_change: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TestEcosystem {
    pub name: String,
    pub patterns: Vec<String>,
    pub suppression_markers: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Baseline {
    pub snapshot: RepositorySnapshot,
    pub suppression_counts: BTreeMap<String, u64>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Contract {
    pub schema: String,
    pub repository_id: Option<String>,
    pub baseline: Option<Baseline>,
    pub rules: Vec<Rule>,
    pub dependency_patterns: Vec<String>,
    pub generated: Vec<GeneratedDeclaration>,
    pub test_ecosystems: Vec<TestEcosystem>,
    pub unknown_test_patterns: Vec<String>,
    pub verification_commands: Vec<Vec<String>>,
    pub contract_hash: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct Change {
    pub path: String,
    pub operation: String,
    pub staged: bool,
    pub unstaged: bool,
    pub entry_kind: String,
    pub class: Option<ChangeClass>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct Evaluation {
    pub state_hash: String,
    pub changes: Vec<Change>,
    pub violations: Vec<String>,
}

const PROTECTED_GIT_FILES: &[&str] = &[".gitignore", ".gitattributes", ".gitmodules"];

fn is_protected_git_control_file(path: &str) -> bool {
    path.rsplit('/')
        .next()
        .is_some_and(|name| PROTECTED_GIT_FILES.contains(&name))
}

pub fn read_contract(path: &Path) -> GuardResult<Contract> {
    let contract: Contract = serde_json::from_slice(&fs::read(path)?)?;
    validate_contract_shape(&contract)?;
    Ok(contract)
}

pub fn seal_contract(path: &Path, repository: &Path) -> GuardResult<Contract> {
    let mut contract = read_contract(path)?;
    if contract.baseline.is_some()
        || contract.repository_id.is_some()
        || contract.contract_hash.is_some()
    {
        return Err(GuardError("seal requires an unsealed contract".to_owned()));
    }
    let observation = ObservedRepositoryState::capture(&contract, repository)?;
    let snapshot = observation.snapshot;
    let suppression_counts = observation.suppression_counts;
    contract.repository_id = Some(snapshot.repository_id.clone());
    contract.baseline = Some(Baseline {
        snapshot,
        suppression_counts,
    });
    contract.contract_hash = Some(compute_contract_hash(&contract)?);
    fs::write(path, serde_json::to_vec_pretty(&contract)?)?;
    let readback = read_contract(path)?;
    verify_contract_hash(&readback)?;
    Ok(readback)
}

fn validate_contract_shape(contract: &Contract) -> GuardResult<()> {
    if contract.schema != CONTRACT_SCHEMA {
        return Err(GuardError(format!(
            "unsupported contract schema: {}",
            contract.schema
        )));
    }
    if contract.rules.is_empty() {
        return Err(GuardError(
            "contract must declare at least one rule".to_owned(),
        ));
    }
    if contract.verification_commands.is_empty()
        || contract
            .verification_commands
            .iter()
            .any(|command| command.is_empty())
    {
        return Err(GuardError(
            "contract must declare nonempty verification commands".to_owned(),
        ));
    }
    for rule in &contract.rules {
        if rule.patterns.is_empty() || rule.allow_kinds.is_empty() {
            return Err(GuardError(
                "each rule needs patterns and allowed entry kinds".to_owned(),
            ));
        }
    }
    let mut patterns = Vec::new();
    for rule in &contract.rules {
        patterns.extend(rule.patterns.iter());
    }
    patterns.extend(contract.dependency_patterns.iter());
    patterns.extend(contract.unknown_test_patterns.iter());
    for declaration in &contract.generated {
        if declaration.patterns.is_empty()
            || (declaration.requires_source_change && declaration.source_patterns.is_empty())
        {
            return Err(GuardError(
                "generated declarations need output patterns and any required source patterns"
                    .to_owned(),
            ));
        }
        patterns.extend(declaration.patterns.iter());
        patterns.extend(declaration.source_patterns.iter());
    }
    let mut ecosystem_names = BTreeSet::new();
    for ecosystem in &contract.test_ecosystems {
        if ecosystem.name.is_empty()
            || ecosystem.patterns.is_empty()
            || ecosystem.suppression_markers.is_empty()
            || !ecosystem_names.insert(ecosystem.name.as_str())
        {
            return Err(GuardError(
                "test ecosystems need a unique name, patterns, and suppression markers".to_owned(),
            ));
        }
        patterns.extend(ecosystem.patterns.iter());
        if ecosystem
            .suppression_markers
            .iter()
            .any(|marker| marker.is_empty() || marker.len() > 256 || marker.contains('\0'))
        {
            return Err(GuardError("invalid test suppression marker".to_owned()));
        }
    }
    if patterns.into_iter().any(|pattern| {
        pattern.is_empty()
            || pattern.len() > 1024
            || pattern.starts_with('/')
            || pattern.contains('\0')
            || pattern.split('/').any(|segment| segment == "..")
    }) {
        return Err(GuardError(
            "patterns must be relative, nonempty, at most 1024 bytes, and contain no NUL or parent segment"
                .to_owned(),
        ));
    }
    if contract
        .verification_commands
        .iter()
        .flatten()
        .any(|argument| argument.is_empty() || argument.contains('\0'))
    {
        return Err(GuardError(
            "verification command arguments must be nonempty and contain no NUL".to_owned(),
        ));
    }
    Ok(())
}

pub fn compute_contract_hash(contract: &Contract) -> GuardResult<String> {
    let mut canonical = contract.clone();
    canonical.contract_hash = None;
    Ok(hash_bytes(&serde_json::to_vec(&canonical)?))
}

pub fn verify_contract_hash(contract: &Contract) -> GuardResult<String> {
    let expected = contract
        .contract_hash
        .as_ref()
        .ok_or_else(|| GuardError("contract is not sealed".to_owned()))?;
    let observed = compute_contract_hash(contract)?;
    if expected != &observed {
        return Err(GuardError(format!(
            "contract hash mismatch: expected {expected}, observed {observed}"
        )));
    }
    Ok(observed)
}

pub fn evaluate_contract(contract: &Contract, repository: &Path) -> GuardResult<Evaluation> {
    let observation = ObservedRepositoryState::capture(contract, repository)?;
    evaluate_observation(contract, &observation)
}

fn evaluate_observation(
    contract: &Contract,
    observation: &ObservedRepositoryState,
) -> GuardResult<Evaluation> {
    validate_contract_shape(contract)?;
    verify_contract_hash(contract)?;
    let baseline = contract
        .baseline
        .as_ref()
        .ok_or_else(|| GuardError("contract has no sealed baseline".to_owned()))?;
    let current = &observation.snapshot;
    let mut violations = Vec::new();
    if contract.repository_id.as_deref() != Some(current.repository_id.as_str()) {
        violations.push("repository identity differs from the sealed contract".to_owned());
    }
    if current.branch != baseline.snapshot.branch {
        violations.push(format!(
            "branch changed from {} to {}",
            baseline.snapshot.branch, current.branch
        ));
    }
    if current.head != baseline.snapshot.head {
        violations.push(format!(
            "HEAD changed from {} to {}",
            baseline.snapshot.head, current.head
        ));
    }

    let mut paths = baseline
        .snapshot
        .entries
        .keys()
        .chain(current.entries.keys())
        .cloned()
        .collect::<BTreeSet<_>>();
    let mut changes = Vec::new();
    for path in std::mem::take(&mut paths) {
        let before = baseline.snapshot.entries.get(&path);
        let after = current.entries.get(&path);
        let stage_markers_same = baseline.snapshot.staged_paths.contains(&path)
            == current.staged_paths.contains(&path)
            && baseline.snapshot.unstaged_paths.contains(&path)
                == current.unstaged_paths.contains(&path)
            && baseline.snapshot.untracked_paths.contains(&path)
                == current.untracked_paths.contains(&path);
        if before == after && stage_markers_same {
            continue;
        }
        let operation = match (before, after) {
            (None, Some(entry)) if entry.work_kind != "absent" => "add",
            (Some(entry), None) if entry.work_kind != "absent" => "delete",
            (Some(before), Some(after))
                if before.work_kind != "absent" && after.work_kind == "absent" =>
            {
                "delete"
            }
            (Some(before), Some(after))
                if before.work_kind == "absent" && after.work_kind != "absent" =>
            {
                "add"
            }
            _ => "modify",
        };
        let entry_kind = if operation == "delete" {
            before.map(|entry| entry.work_kind.clone())
        } else {
            after.map(|entry| entry.work_kind.clone())
        }
        .or_else(|| before.map(|entry| entry.work_kind.clone()))
        .unwrap_or_else(|| "absent".to_owned());
        let staged = current.staged_paths.contains(&path)
            || before.and_then(|entry| entry.index_oid.as_ref())
                != after.and_then(|entry| entry.index_oid.as_ref());
        let unstaged =
            current.unstaged_paths.contains(&path) || current.untracked_paths.contains(&path);
        let (class, rule) = matching_rule(contract, &path, &mut violations);
        if let Some(rule) = rule.as_ref() {
            if staged && !rule.allow_staged {
                violations.push(format!("{path}: staged changes are not allowed"));
            }
            if unstaged && !rule.allow_unstaged {
                violations.push(format!("{path}: unstaged changes are not allowed"));
            }
            if !rule.allow_kinds.contains(&entry_kind) {
                violations.push(format!(
                    "{path}: entry kind {entry_kind} is not explicitly allowed"
                ));
            }
            if is_protected_git_control_file(&path) && !rule.exact_path_rule {
                violations.push(format!(
                    "{path}: protected Git control file needs an exact rule"
                ));
            }
        }
        enforce_class_contracts(
            contract,
            baseline,
            observation,
            &path,
            class.as_ref(),
            rule.as_ref(),
            &mut violations,
        )?;
        changes.push(Change {
            path,
            operation: operation.to_owned(),
            staged,
            unstaged,
            entry_kind,
            class,
        });
    }
    enforce_generated_sources(contract, &changes, &mut violations);
    violations.sort();
    violations.dedup();
    Ok(Evaluation {
        state_hash: current.state_hash.clone(),
        changes,
        violations,
    })
}

fn matching_rule(
    contract: &Contract,
    path: &str,
    violations: &mut Vec<String>,
) -> (Option<ChangeClass>, Option<EffectiveRule>) {
    let matches = contract
        .rules
        .iter()
        .filter(|rule| {
            rule.patterns
                .iter()
                .any(|pattern| pattern_matches(pattern, path))
        })
        .collect::<Vec<_>>();
    if matches.is_empty() {
        violations.push(format!("{path}: unclassified change"));
        return (None, None);
    }
    let classes = matches
        .iter()
        .map(|rule| &rule.class)
        .collect::<BTreeSet<_>>();
    if classes.len() != 1 {
        violations.push(format!("{path}: ambiguous change classes"));
        return (None, None);
    }
    let allow_kinds = matches
        .iter()
        .map(|rule| rule.allow_kinds.iter().cloned().collect::<BTreeSet<_>>())
        .reduce(|left, right| left.intersection(&right).cloned().collect())
        .unwrap_or_default();
    let effective = EffectiveRule {
        allow_staged: matches.iter().all(|rule| rule.allow_staged),
        allow_unstaged: matches.iter().all(|rule| rule.allow_unstaged),
        allow_kinds,
        allow_test_suppression: matches.iter().all(|rule| rule.allow_test_suppression),
        exact_path_rule: matches
            .iter()
            .any(|rule| rule.patterns.iter().any(|pattern| pattern == path)),
    };
    (Some(matches[0].class.clone()), Some(effective))
}

fn enforce_class_contracts(
    contract: &Contract,
    baseline: &Baseline,
    observation: &ObservedRepositoryState,
    path: &str,
    class: Option<&ChangeClass>,
    rule: Option<&EffectiveRule>,
    violations: &mut Vec<String>,
) -> GuardResult<()> {
    let current = &observation.snapshot;
    let dependency = contract
        .dependency_patterns
        .iter()
        .any(|pattern| pattern_matches(pattern, path));
    if dependency && class != Some(&ChangeClass::Dependency) {
        violations.push(format!(
            "{path}: dependency or lockfile change needs dependency class"
        ));
    }
    if class == Some(&ChangeClass::Dependency) && !dependency {
        violations.push(format!(
            "{path}: dependency class is not declared in dependency_patterns"
        ));
    }
    let generated = contract.generated.iter().any(|declaration| {
        declaration
            .patterns
            .iter()
            .any(|pattern| pattern_matches(pattern, path))
    });
    if generated && class != Some(&ChangeClass::Generated) {
        violations.push(format!("{path}: generated path needs generated class"));
    }
    if class == Some(&ChangeClass::Generated) && !generated {
        violations.push(format!(
            "{path}: generated class has no generated declaration"
        ));
    }

    let known = contract
        .test_ecosystems
        .iter()
        .filter(|ecosystem| {
            ecosystem
                .patterns
                .iter()
                .any(|pattern| pattern_matches(pattern, path))
        })
        .collect::<Vec<_>>();
    let looks_like_test = contract
        .unknown_test_patterns
        .iter()
        .any(|pattern| pattern_matches(pattern, path));
    if looks_like_test && known.is_empty() {
        violations.push(format!(
            "{path}: changed test belongs to an unknown ecosystem; human classification required"
        ));
    }
    if !known.is_empty()
        && class != Some(&ChangeClass::Test)
        && class != Some(&ChangeClass::Evaluator)
    {
        violations.push(format!(
            "{path}: known test path needs test or evaluator class"
        ));
    }
    if current
        .entries
        .get(path)
        .is_some_and(|entry| entry.work_kind == "file")
    {
        for ecosystem in known {
            for marker in &ecosystem.suppression_markers {
                let key = suppression_key(&ecosystem.name, path, marker);
                let before = baseline.suppression_counts.get(&key).copied().unwrap_or(0);
                let after = observation
                    .suppression_counts
                    .get(&key)
                    .copied()
                    .unwrap_or(0);
                if after > before && !rule.is_some_and(|rule| rule.allow_test_suppression) {
                    violations.push(format!(
                        "{path}: new {} suppression marker {:?} needs explicit approval",
                        ecosystem.name, marker
                    ));
                }
            }
        }
    }
    Ok(())
}

fn enforce_generated_sources(
    contract: &Contract,
    changes: &[Change],
    violations: &mut Vec<String>,
) {
    for declaration in &contract.generated {
        let generated_changed = changes.iter().any(|change| {
            declaration
                .patterns
                .iter()
                .any(|pattern| pattern_matches(pattern, &change.path))
        });
        if generated_changed && declaration.requires_source_change {
            let source_changed = changes.iter().any(|change| {
                declaration
                    .source_patterns
                    .iter()
                    .any(|pattern| pattern_matches(pattern, &change.path))
            });
            if !source_changed {
                violations.push(format!(
                    "generated change matching {:?} has no declared source change",
                    declaration.patterns
                ));
            }
        }
    }
}

fn suppression_key(ecosystem: &str, path: &str, marker: &str) -> String {
    format!("{ecosystem}\0{path}\0{marker}")
}

pub fn pattern_matches(pattern: &str, path: &str) -> bool {
    let pattern = pattern.as_bytes();
    let path = path.as_bytes();
    let mut table = vec![vec![false; path.len() + 1]; pattern.len() + 1];
    table[pattern.len()][path.len()] = true;
    for pattern_index in (0..pattern.len()).rev() {
        for path_index in (0..=path.len()).rev() {
            let double_star =
                pattern[pattern_index] == b'*' && pattern.get(pattern_index + 1) == Some(&b'*');
            table[pattern_index][path_index] = if double_star {
                let slash = pattern.get(pattern_index + 2) == Some(&b'/');
                let skip = pattern_index + if slash { 3 } else { 2 };
                table[skip][path_index]
                    || (path_index < path.len() && table[pattern_index][path_index + 1])
            } else {
                match pattern[pattern_index] {
                    b'*' => {
                        table[pattern_index + 1][path_index]
                            || (path_index < path.len()
                                && path[path_index] != b'/'
                                && table[pattern_index][path_index + 1])
                    }
                    b'?' => {
                        path_index < path.len()
                            && path[path_index] != b'/'
                            && table[pattern_index + 1][path_index + 1]
                    }
                    byte => {
                        path_index < path.len()
                            && byte == path[path_index]
                            && table[pattern_index + 1][path_index + 1]
                    }
                }
            };
        }
    }
    table[0][0]
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Receipt {
    pub schema: String,
    pub repository_id: String,
    pub branch: String,
    pub contract_hash: String,
    pub final_state_hash: String,
    pub verification_command: Vec<String>,
    pub exit_status: i32,
    pub output_digest: String,
    pub receipt_hash: Option<String>,
}

struct BoundedOutput {
    status: ExitStatus,
    stdout: Vec<u8>,
    stderr: Vec<u8>,
}

fn drain_stream<R: Read + Send + 'static>(
    mut stream: R,
    total: Arc<AtomicUsize>,
    error_tx: mpsc::Sender<GuardError>,
) -> thread::JoinHandle<Vec<u8>> {
    thread::spawn(move || {
        let mut output = Vec::new();
        let mut buffer = [0_u8; 64 * 1024];
        loop {
            let count = match stream.read(&mut buffer) {
                Ok(0) => break,
                Ok(count) => count,
                Err(error) => {
                    let _ = error_tx.send(GuardError(format!(
                        "cannot read verification output: {error}"
                    )));
                    break;
                }
            };
            let previous = total.fetch_add(count, Ordering::SeqCst);
            if previous.saturating_add(count) > MAX_VERIFICATION_OUTPUT_BYTES {
                let _ = error_tx.send(GuardError(format!(
                    "verification output exceeds the {} byte receipt limit",
                    MAX_VERIFICATION_OUTPUT_BYTES
                )));
                break;
            }
            output.extend_from_slice(&buffer[..count]);
        }
        output
    })
}

fn run_bounded_command(
    executable: &str,
    args: &[String],
    repository: &Path,
) -> GuardResult<BoundedOutput> {
    let mut child = Command::new(executable)
        .args(args)
        .current_dir(repository)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| GuardError(format!("cannot spawn verification command: {error}")))?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| GuardError("verification stdout pipe is unavailable".to_owned()))?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| GuardError("verification stderr pipe is unavailable".to_owned()))?;
    let total = Arc::new(AtomicUsize::new(0));
    let (error_tx, error_rx) = mpsc::channel();
    let stdout_thread = drain_stream(stdout, Arc::clone(&total), error_tx.clone());
    let stderr_thread = drain_stream(stderr, total, error_tx);

    let status = loop {
        if let Ok(error) = error_rx.try_recv() {
            let _ = child.kill();
            let _ = child.wait();
            let _ = stdout_thread.join();
            let _ = stderr_thread.join();
            return Err(error);
        }
        if let Some(status) = child
            .try_wait()
            .map_err(|error| GuardError(format!("cannot wait for verification child: {error}")))?
        {
            break status;
        }
        thread::sleep(Duration::from_millis(5));
    };
    let stdout = stdout_thread
        .join()
        .map_err(|_| GuardError("verification stdout reader panicked".to_owned()))?;
    let stderr = stderr_thread
        .join()
        .map_err(|_| GuardError("verification stderr reader panicked".to_owned()))?;
    if let Ok(error) = error_rx.try_recv() {
        return Err(error);
    }
    Ok(BoundedOutput {
        status,
        stdout,
        stderr,
    })
}

pub fn run_verification(
    contract_path: &Path,
    receipt_path: &Path,
    repository: &Path,
    command: &[String],
) -> GuardResult<Receipt> {
    let contract = read_contract(contract_path)?;
    verify_contract_hash(&contract)?;
    if !contract
        .verification_commands
        .iter()
        .any(|allowed| allowed == command)
    {
        return Err(GuardError(
            "verification command is not sealed in the contract".to_owned(),
        ));
    }
    let before = evaluate_contract(&contract, repository)?;
    if !before.violations.is_empty() {
        return Err(GuardError(format!(
            "containment rejected before verification: {}",
            before.violations.join("; ")
        )));
    }
    let executable = command
        .first()
        .ok_or_else(|| GuardError("verification command is empty".to_owned()))?;
    let output = run_bounded_command(executable, &command[1..], repository)?;
    let after = ObservedRepositoryState::capture(&contract, repository)?;
    let after_evaluation = evaluate_observation(&contract, &after)?;
    if !after_evaluation.violations.is_empty() {
        return Err(GuardError(format!(
            "containment rejected after verification: {}",
            after_evaluation.violations.join("; ")
        )));
    }
    let snapshot = after.snapshot;
    let contract_hash = contract
        .contract_hash
        .clone()
        .expect("verified sealed contract");
    let exit_status = output.status.code().unwrap_or(-1);
    let output_digest = verification_output_digest(&output.stdout, &output.stderr);
    let mut receipt = Receipt {
        schema: RECEIPT_SCHEMA.to_owned(),
        repository_id: snapshot.repository_id,
        branch: snapshot.branch,
        contract_hash,
        final_state_hash: snapshot.state_hash,
        verification_command: command.to_vec(),
        exit_status,
        output_digest,
        receipt_hash: None,
    };
    receipt.receipt_hash = Some(compute_receipt_hash(&receipt)?);
    fs::write(receipt_path, serde_json::to_vec_pretty(&receipt)?)?;
    let readback: Receipt = serde_json::from_slice(&fs::read(receipt_path)?)?;
    if readback != receipt {
        return Err(GuardError(
            "receipt readback differs from written bytes".to_owned(),
        ));
    }
    Ok(receipt)
}

pub fn check_receipt(
    contract_path: &Path,
    receipt_path: &Path,
    repository: &Path,
) -> GuardResult<Receipt> {
    let contract = read_contract(contract_path)?;
    let contract_hash = verify_contract_hash(&contract)?;
    let receipt: Receipt = serde_json::from_slice(&fs::read(receipt_path)?)?;
    if receipt.schema != RECEIPT_SCHEMA {
        return Err(GuardError(format!(
            "unsupported receipt schema: {}",
            receipt.schema
        )));
    }
    let expected_receipt_hash = receipt
        .receipt_hash
        .as_ref()
        .ok_or_else(|| GuardError("receipt hash is missing".to_owned()))?;
    let observed_receipt_hash = compute_receipt_hash(&receipt)?;
    if expected_receipt_hash != &observed_receipt_hash {
        return Err(GuardError("receipt hash mismatch".to_owned()));
    }
    if receipt.contract_hash != contract_hash {
        return Err(GuardError(
            "receipt belongs to a different contract".to_owned(),
        ));
    }
    if !contract
        .verification_commands
        .iter()
        .any(|command| command == &receipt.verification_command)
    {
        return Err(GuardError(
            "receipt command is not sealed in the contract".to_owned(),
        ));
    }
    if receipt.exit_status != 0 {
        return Err(GuardError(format!(
            "verification command was not green: exit {}",
            receipt.exit_status
        )));
    }
    if !receipt.output_digest.starts_with("sha256:") || receipt.output_digest.len() != 71 {
        return Err(GuardError(
            "verification output digest is malformed".to_owned(),
        ));
    }
    let current = ObservedRepositoryState::capture(&contract, repository)?;
    let evaluation = evaluate_observation(&contract, &current)?;
    if !evaluation.violations.is_empty() {
        return Err(GuardError(format!(
            "current repository violates containment: {}",
            evaluation.violations.join("; ")
        )));
    }
    if receipt.repository_id != current.snapshot.repository_id {
        return Err(GuardError(
            "receipt belongs to a different repository".to_owned(),
        ));
    }
    if receipt.branch != current.snapshot.branch {
        return Err(GuardError(
            "receipt belongs to a different branch".to_owned(),
        ));
    }
    if receipt.final_state_hash != current.snapshot.state_hash {
        return Err(GuardError(
            "receipt is stale for the current repository state".to_owned(),
        ));
    }
    Ok(receipt)
}

pub fn compute_receipt_hash(receipt: &Receipt) -> GuardResult<String> {
    let mut canonical = receipt.clone();
    canonical.receipt_hash = None;
    Ok(hash_bytes(&serde_json::to_vec(&canonical)?))
}

fn verification_output_digest(stdout: &[u8], stderr: &[u8]) -> String {
    let mut digest = Sha256::new();
    digest.update((stdout.len() as u64).to_be_bytes());
    digest.update(stdout);
    digest.update((stderr.len() as u64).to_be_bytes());
    digest.update(stderr);
    format!("sha256:{:x}", digest.finalize())
}

pub fn evaluate_envelope(
    contract: &Contract,
    payload: &Value,
    repository_override: Option<&Path>,
) -> GuardResult<Value> {
    let object = payload
        .as_object()
        .ok_or_else(|| GuardError("envelope must be a JSON object".to_owned()))?;
    let (surface, repository, event) = if let Some(tool_call) = object.get("toolCall") {
        let args = tool_call
            .get("args")
            .and_then(Value::as_object)
            .ok_or_else(|| {
                GuardError("Antigravity envelope is missing toolCall.args".to_owned())
            })?;
        let repository = repository_override
            .map(PathBuf::from)
            .or_else(|| args.get("Cwd").and_then(Value::as_str).map(PathBuf::from))
            .ok_or_else(|| GuardError("Antigravity envelope has no repository Cwd".to_owned()))?;
        ("antigravity", repository, "PostToolUse".to_owned())
    } else if object
        .get("tool_input")
        .and_then(Value::as_object)
        .is_some()
    {
        let repository = repository_override
            .map(PathBuf::from)
            .or_else(|| object.get("cwd").and_then(Value::as_str).map(PathBuf::from))
            .ok_or_else(|| GuardError("Claude/Codex envelope has no repository cwd".to_owned()))?;
        let event = object
            .get("hook_event_name")
            .and_then(Value::as_str)
            .unwrap_or("PostToolUse")
            .to_owned();
        ("claude_codex", repository, event)
    } else {
        return Err(GuardError("unrecognized public agent envelope".to_owned()));
    };

    let evaluation = evaluate_contract(contract, &repository)?;
    let denied = !evaluation.violations.is_empty();
    let reason = evaluation.violations.join("; ");
    let details = json!({
        "surface": surface,
        "decision": if denied { "deny" } else { "allow" },
        "stateHash": evaluation.state_hash,
        "changes": evaluation.changes,
        "violations": evaluation.violations,
    });
    if surface == "antigravity" {
        if denied {
            Ok(json!({"decision":"deny","reason":reason,"changeContainmentGuard":details}))
        } else {
            Ok(json!({"changeContainmentGuard":details}))
        }
    } else if denied {
        Ok(json!({
            "hookSpecificOutput": {
                "hookEventName": event,
                "permissionDecision": "deny",
                "permissionDecisionReason": reason
            },
            "changeContainmentGuard": details
        }))
    } else {
        Ok(json!({"changeContainmentGuard":details}))
    }
}

fn work_identity(
    repository: &Path,
    absolute: &Path,
    indexed: Option<&(String, String)>,
) -> GuardResult<(String, String)> {
    let metadata = match fs::symlink_metadata(absolute) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(("absent".to_owned(), hash_bytes(b"absent")));
        }
        Err(error) => return Err(error.into()),
    };
    if metadata.file_type().is_symlink() {
        let target = fs::read_link(absolute)?;
        return Ok(("symlink".to_owned(), hash_bytes(&path_bytes(&target))));
    }
    if metadata.is_file() {
        return Ok(("file".to_owned(), hash_file(absolute)?));
    }
    if metadata.is_dir() && indexed.is_some_and(|(mode, _)| mode == "160000") {
        let status = run_git(
            absolute,
            [
                "status",
                "--porcelain=v2",
                "-z",
                "--untracked-files=all",
                "--ignore-submodules=none",
            ],
        )?;
        if !status.is_empty() {
            let relative = absolute.strip_prefix(repository).unwrap_or(absolute);
            return Err(GuardError(format!(
                "dirty initialized submodule is not accepted: {}",
                relative.display()
            )));
        }
        let pointer = git_text(absolute, ["rev-parse", "--verify", "HEAD"])?;
        if pointer.len() != 40 || !pointer.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return Err(GuardError("submodule HEAD is malformed".to_owned()));
        }
        return Ok(("submodule".to_owned(), hash_bytes(pointer.as_bytes())));
    }
    let relative = absolute.strip_prefix(repository).unwrap_or(absolute);
    Err(GuardError(format!(
        "unsupported working-tree entry type: {}",
        relative.display()
    )))
}

#[cfg(unix)]
fn path_bytes(path: &Path) -> Vec<u8> {
    use std::os::unix::ffi::OsStrExt as _;
    path.as_os_str().as_bytes().to_vec()
}

#[cfg(windows)]
fn path_bytes(path: &Path) -> Vec<u8> {
    use std::os::windows::ffi::OsStrExt as _;
    path.as_os_str()
        .encode_wide()
        .flat_map(u16::to_le_bytes)
        .collect()
}

fn hash_file(path: &Path) -> GuardResult<String> {
    let mut file = fs::File::open(path)?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(format!("sha256:{:x}", digest.finalize()))
}

#[cfg(test)]
mod unit_tests {
    use super::{hash_bytes, pattern_matches};

    #[test]
    fn sha256_matches_published_abc_vector() {
        assert_eq!(
            hash_bytes(b"abc"),
            "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }

    #[test]
    fn a_single_star_does_not_cross_a_directory_boundary() {
        assert!(pattern_matches("src/*.rs", "src/main.rs"));
        assert!(!pattern_matches("src/*.rs", "src/deep/main.rs"));
    }
}
