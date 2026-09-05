# GitHub Actions OIDC setup (Phase 0 documentation)

CI uses short-lived GitHub OIDC tokens for Azure. No Azure client secret is
stored in GitHub. A repository administrator must create an Entra application
(or user-assigned managed identity), federated credential for the repository's
`main` branch and `demo` environment, and a separate protected `destroy`
environment. Grant only the resource-group scope needed by Terraform.

Recommended GitHub environments:

- `demo`: required reviewers; deployment branch restricted to `main`.
- `destroy`: required reviewers; manual approval; used only for teardown.

Required GitHub environment variables (non-secret identifiers):

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

Snowflake automation should use the strongest trial-supported short-lived
OAuth or key-pair method. Store private key material only as an environment
secret, rotate it after the demo, and never put it in `.env.example`.

OIDC is documented now but is not used until Terraform bootstrap and the
GitHub deployment workflows are implemented and reviewed.
