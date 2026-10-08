# Security

Before production use:

- Configure valid HTTPS and DNS resolution for browsers and containers; decide between LAN/VPN-only and public access.
- Enable administrator 2FA, define user policy and store recovery codes.
- Use SSH keys, restrict administrative access and verify firewall behavior for Docker-published ports.
- Keep database and Redis ports private. Restrict Docker access to administrators: a read-only socket mount still allows privileged API operations.
- Schedule OS and AIO updates with a verified backup available first.
- Use a dedicated backup account and test recovery without the primary account or server.
- Monitor free space and backup health; periodically test a full restore.
- Check staged files before committing. Ignore rules do not protect secrets already tracked by Git.

The administration interface is bound to loopback in this repository. Review access to every published port, including AIO-created containers, before deployment.

The stable image tag can change. Record deployed image versions or digests and review the supported AIO update workflow before introducing stricter image pinning.
