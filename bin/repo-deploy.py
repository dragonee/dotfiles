#!/usr/bin/env python3
"""Setup GitHub Actions deployment for a repository.

Generates an ED25519 SSH key, sets GitHub secrets, and configures the remote server.

Usage:
    repo-deploy.py [options]
    repo-deploy.py -h | --help

Options:
    -h --help           Show this help message.
    -i --no-interactive Skip interactive prompts, use defaults/provided values.
    -k --key FILE       Use existing private key instead of generating a new one.
    -p --path PATH      Deploy path on remote server [default: /home/sites/vhosts/{repo}/].
    -u --user USER      SSH user for deployment [default: sites].
    -H --host HOST      SSH host for deployment [default: lambdadelta.pl].
    -P --port PORT      SSH port for deployment [default: 22].
"""

import os
import subprocess
import sys
from docopt import docopt


def run(cmd, input_data=None, capture=False):
    """Run a command and optionally capture output."""
    result = subprocess.run(
        cmd,
        input=input_data,
        capture_output=capture,
        text=True,
        check=True,
    )
    return result.stdout.strip() if capture else None


def get_repo_name():
    """Get the repository name from git remote origin."""
    repo_url = run(["git", "config", "--get", "remote.origin.url"], capture=True)
    repo_name = os.path.basename(repo_url)
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    return repo_name


def prompt(label, default):
    """Prompt for input with a default value."""
    value = input(f"{label} [{default}]: ").strip()
    return value if value else default


def parse_secrets_file(path):
    """Parse .secrets file and return list of (key, default) tuples."""
    secrets = []
    if not os.path.exists(path):
        return secrets

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, default = line.split("=", 1)
                secrets.append((key.strip(), default.strip()))
            else:
                secrets.append((line, ""))
    return secrets


def main():
    args = docopt(__doc__)

    repo_name = get_repo_name()
    print(f"Repository name: {repo_name}")

    deploy_path = args["--path"].replace("{repo}", repo_name)
    deploy_user = args["--user"]
    deploy_host = args["--host"]
    deploy_port = args["--port"]

    key_file = args["--key"]

    # Parse additional secrets from .secrets file
    extra_secrets = parse_secrets_file(".secrets")
    extra_secret_values = {key: default for key, default in extra_secrets}

    if not args["--no-interactive"]:
        print()
        key_file = prompt("Existing key file (empty to generate new)", key_file or "")
        deploy_path = prompt("Deploy path", deploy_path)
        deploy_user = prompt("Deploy user", deploy_user)
        deploy_host = prompt("Deploy host", deploy_host)
        deploy_port = prompt("Deploy port", deploy_port)

        if extra_secrets:
            print("\nAdditional secrets from .secrets:")
            for key, default in extra_secrets:
                extra_secret_values[key] = prompt(f"  {key}", default)

        print()

    # Get or generate SSH key
    if key_file:
        print(f"Using existing key: {key_file}")
        with open(key_file, "r") as f:
            private_key = f.read()
        public_key = run(["ssh-keygen", "-y", "-f", key_file], capture=True)
    else:
        print(f"Generating SSH key: {repo_name}")
        run([
            "ssh-keygen",
            "-t", "ed25519",
            "-C", f"github-actions@{repo_name}",
            "-f", repo_name,
            "-N", "",
        ])
        with open(repo_name, "r") as f:
            private_key = f.read()
        with open(f"{repo_name}.pub", "r") as f:
            public_key = f.read()

    # Set GitHub secrets
    print("Setting GitHub secrets...")
    run(["gh", "secret", "set", "DEPLOY_KEY"], input_data=private_key)
    run(["gh", "secret", "set", "DEPLOY_PATH", "-b", deploy_path])
    run(["gh", "secret", "set", "DEPLOY_USER", "-b", deploy_user])
    run(["gh", "secret", "set", "DEPLOY_HOST", "-b", deploy_host])
    run(["gh", "secret", "set", "DEPLOY_PORT", "-b", deploy_port])

    # Set additional secrets from .secrets file
    for key, value in extra_secret_values.items():
        run(["gh", "secret", "set", key, "-b", value])

    # Configure remote server
    ssh_target = f"{deploy_user}@{deploy_host}"
    ssh_opts = ["-p", deploy_port]

    print(f"Creating deploy path on remote: {deploy_path}")
    run(["ssh", ssh_target] + ssh_opts + [f"mkdir -p {deploy_path}"])

    print("Adding public key to authorized_keys...")
    run(["ssh", ssh_target] + ssh_opts + ["cat >> ~/.ssh/authorized_keys"], input_data=public_key)

    print("Done!")


if __name__ == "__main__":
    main()
