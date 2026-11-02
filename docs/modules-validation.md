# Clean-machine module validation

Use a disposable Debian VM, a new Tailscale identity, test users and separate backup prefixes. Do not copy production bot tokens, ping URLs, node identity or backup writer configuration into the test VM.

1. Clone a reviewed revision and follow [the installation order](modules.md). Record OS/package versions and image digests privately. Every required script must come from the checkout.
2. Verify Nextcloud upload/download, sharing and simultaneous Office editing. Install Forgejo; verify login, permissions, HTTPS/SSH clone and push, and any enabled LFS/packages features.
3. Create test documents and commits. Run both local/external backups, then restore each application on another isolated VM. Compare recovered data; keep production writers and restored writers separate.
4. Run the [Forgejo recovery scenarios](forgejo-recovery.md#acceptance-on-a-disposable-deployment): interrupted upload, reboot, abrupt VM power loss during the snapshot, failed verification and concurrent requests. Require pending state, healthy application recovery and no pruning after failure.
5. Verify bot allowlists, expired/replayed confirmation, rolling daily/weekly quotas and persistence across restart. Send only test identities through the discovery command. Test each bot independently.
6. Stop test network access and restore it. Check service monitoring recovers; backup success remains distinct from service health. Confirm external alerts arrive when the VM cannot send.
7. Check homepage links, authorized and unauthorized tailnet users, LAN denial, reboot and Office callbacks. Run positive/negative host and container tests over IPv4/IPv6 against the actual egress policy.

## Repository checks

```bash
python3 -m unittest discover -s tests
python3 -m unittest discover -s modules/forgejo/automation -p 'test_*.py'
python3 -m unittest discover -s modules/forgejo/bot -p 'test_*.py'
python3 -m unittest discover -s modules/forgejo/scripts -p 'test_*.py'
python3 -m unittest discover -s modules/homepage -p 'test_*.py'
git diff --check
```
