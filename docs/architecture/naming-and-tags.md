# Naming and tagging standard

Resource names use `hcpipe-<environment>-<resource>-<unique_suffix>` where the suffix is supplied by the operator and is globally unique where Azure requires it.

Required tags:

| Tag | Value |
|---|---|
| project | healthcare-data-pipeline |
| environment | demo or local |
| owner | portfolio |
| managed_by | terraform |
| cost_center | trial |
| data_classification | synthetic |
