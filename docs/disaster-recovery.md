# Disaster recovery

Scenario: the server and its storage are lost.

Recovery requires this repository, a complete off-site backup, the Borg password and credentials accessible without the failed server. Assign a primary operator and a backup operator. Record secret locations, never their values, in the internal operations inventory.

1. Prepare a replacement Linux host and storage, install Docker and retrieve this repository.
2. Retrieve the off-site backup and verify its date, completeness and integrity.
3. Follow [restore](restore.md) in an isolated environment.
4. Validate administrator login, users, files, shares and collaborative DOCX/XLSX editing.
5. Restore DNS and user access, then verify sync clients.
6. Confirm a new local backup and off-site copy.
7. Record actual recovery time and data loss relative to the backup timestamp; update this procedure.

Complete the first drill before migrating business data. Git contains configuration and procedures, not the application state or recovery secrets.
