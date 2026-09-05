# Phase 0 workstation setup

The project requires Python 3.10+ (3.11 recommended), Git, Docker, Terraform,
Azure CLI, Databricks CLI v1+, and Snowflake CLI. Install tools using the
vendor-supported installer for your operating system; do not place credentials
in shell history or repository files.

On macOS with Homebrew, the typical commands are:

```bash
brew update
brew install terraform azure-cli
brew tap databricks/tap && brew install databricks
brew install snowflake-cli
```

The existing Databricks CLI may already be installed. Verify each executable:

```bash
bash scripts/preflight/check_local_tools.sh
```

Use `/usr/local/bin/python3.11` (or another Python 3.10+) for this repository:

```bash
/usr/local/bin/python3.11 -m venv .venv311
.venv311/bin/python -m pip install -e '.[dev]'
```

Azure authentication is deferred until the deployment phase:

```bash
az login
az account list --output table
az account set --subscription '<TRIAL_SUBSCRIPTION_ID>'
az account show --output table
```

Do not run `az login` or Terraform apply until the subscription is confirmed as
the intended trial subscription.
