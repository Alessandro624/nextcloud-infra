# Forgejo Actions

Optional. Keep Actions disabled until a dedicated disposable runner VM and its network policy have been validated. Never mount the production server Docker socket into a runner.

Follow the [official runner installation](https://forgejo.org/docs/latest/admin/actions/runner-installation/) for the chosen supported version. Pin the runner and job images; create a repository-scoped runner. Permit only trusted workflows, no privileged jobs, host networking, arbitrary host volumes or job access to the Docker socket.

Allow only Forgejo and reviewed dependency/registry endpoints from the runner VM, including forwarded IPv4/IPv6 traffic. Test clone/build, rejection of LAN/admin/metadata destinations, and absence of production credentials before enabling workflows. Keep runner registration secrets private. Revoke and recreate them during disaster recovery; caches are disposable.

Runner installation is not automated or covered by the core module tests.
