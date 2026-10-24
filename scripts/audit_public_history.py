"""Read-only bounded public-history audit; never prints matched secret values.

Patterns + path/magic checks are a review aid, not proof that all secrets are absent.
Scans every reachable commit tree/blob, including subsequently deleted files.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

PATTERNS = {
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----'),
    'mnemonic_assignment': re.compile(r'''(?:mnemonic|seed[-_]?phrase)\s*["']?\s*[:=]\s*["']([a-z]+(?: [a-z]+){11,23})["']''', re.I),
    'wallet_secret_array': re.compile(r'(?:private[-_]?key|secret[-_]?key|keypair)\s*["\x27]?\s*[:=]\s*(?:new Uint8Array\()?\[(?:\s*\d{1,3},){31,}\s*\d{1,3}\s*\]', re.I),
    'github_token': re.compile(r'(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{30,})'),
    'aws_key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'slack_token': re.compile(r'xox[baprs]-[A-Za-z0-9-]{20,}'),
    'credential_assignment': re.compile(r'''(?:api[-_]?key|private[-_]?key|secret[-_]?key|seed[-_]?phrase|mnemonic)\s*["']?\s*[:=]\s*["']?([A-Za-z0-9_/-]{24,})''', re.I),
    'url_userinfo': re.compile(r'''(?:https?|wss?)://[^/\s"']+:[^/@\s"']+@''', re.I),
    'provider_path_key': re.compile(r'(?:alchemy\.com/v2/|rpc\.ankr\.com/solana/|quiknode\.pro/)[A-Za-z0-9_-]{16,}', re.I),
    'rpc_url_credential': re.compile(r'''(?:api[-_]?key|token)=[A-Za-z0-9_-]{24,}''', re.I),
}


def sensitive_path(path):
    p = Path(path)
    if p.name == '.env.example':
        return False  # CONTENT is still scanned.
    if p.name == '.env' or p.name.startswith('.env.') or p.name == '.envrc':
        return True
    if re.search(r'\.(?:db(?:[-.]|$)|sqlite(?:3)?(?:[-.]|$)|pem$|key$|p12$)', p.name, re.I):
        return True
    if any(part in {'.aws', '.codex', 'node_modules', '.venv', 'private', 'secrets'} for part in p.parts):
        return True
    if p.parts and p.parts[0] in {'data', 'logs'} and p.name != '.gitkeep':
        return True
    return p.name in {'id_rsa', 'id_ed25519', 'credentials', 'keypair.json', 'wallet.json'}


def audit(repo, ref='HEAD'):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args])
    head = git('rev-parse', '--verify', ref+'^{commit}').decode().strip()
    commits = git('rev-list', head).decode().splitlines()
    if len(commits) > 2000:
        raise ValueError('Bounded audit commits exceeded; no clean result')
    paths: dict[str, set[str]] = {}
    findings: list[dict] = []
    for commit in commits:
        for row in git('ls-tree', '-r', '-z', commit).split(b'\0'):
            if not row:
                continue
            header, path = row.split(b'\t', 1)
            _, kind, oid = header.decode().split()
            if kind == 'blob':
                paths.setdefault(oid, set()).add(path.decode('utf-8', errors='replace'))
                if len(paths) > 20000:
                    raise ValueError('Bounded audit objects exceeded; no clean result')
    if len(commits) > 2000 or len(paths) > 20000:
        raise ValueError('Bounded audit scope exceeded; no clean result')
    total = 0
    for oid, names in paths.items():
        size = int(git('cat-file', '-s', oid))
        total += size
        if size > 2*1024*1024 or total > 64*1024*1024:
            raise ValueError('Bounded audit bytes exceeded; no clean result')
        raw = git('cat-file', 'blob', oid)
        if raw.startswith(b'SQLite format 3\0'):
            findings.append(dict(blob=oid, paths=sorted(names), category='sqlite_database'))
        try:
            content = raw.decode('utf-8')
        except UnicodeDecodeError:
            findings.append(dict(blob=oid, paths=sorted(names), category='binary_requires_review'))
            continue
        for number, line in enumerate(content.splitlines(), 1):
            for label, pattern in PATTERNS.items():
                for match in pattern.finditer(line):
                    findings.append(dict(blob=oid, paths=sorted(names), line=number, category=label,
                        match_sha256=hashlib.sha256(match.group().encode()).hexdigest()))
    for commit in commits:
        message = git('show', '-s', '--format=%B', commit).decode()
        for label, pattern in PATTERNS.items():
            if pattern.search(message):
                findings.append(dict(commit=commit, category=label, location='commit_message'))
    restricted = sorted({p for names in paths.values() for p in names if sensitive_path(p)})
    return dict(head=head, commits=len(commits), blobs=len(paths), blob_bytes=total,
        sensitive_paths=restricted, findings=findings,
        verdict='REVIEW_REQUIRED' if restricted or findings else 'PATTERN_AND_PATH_SCAN_CLEAR',
        limitations='No scanner guarantees absence of every secret. Manual publication review remains required; values suppressed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.repo, args.ref)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as file:
        json.dump(result, file, indent=2)
    print(json.dumps(result, indent=2))
    if result['verdict'] != 'PATTERN_AND_PATH_SCAN_CLEAR':
        raise SystemExit(1)
