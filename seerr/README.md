# Seerr book availability

The `Rubiss/seerr` book-support fork is based on the official Seerr v3.5.0
release. Compose pins its image by digest. Source and upgrade validation:
[Seerr PR #1](https://github.com/Rubiss/seerr/pull/1).

## Import notifications

Each Bookshelf instance has a **Seerr Book Availability** webhook under
**Settings → Connect**, with **On Release Import** and **On Upgrade** enabled.

| Bookshelf instance | Webhook URL |
| --- | --- |
| `bookshelf` (ebooks) | `http://seerr:5055/api/v1/webhook/readarr/0` |
| `bookshelf-audio` (audiobooks) | `http://seerr:5055/api/v1/webhook/readarr/1` |

Use **POST**, username `seerr`, and the **Seerr API key** as the password.
Credentials are stored in the applications' live configuration, outside Git.
If the Seerr key changes, update both connections and test them again.
Keep **Sync** enabled on both Readarr entries in Seerr. Server IDs in the URL
refer to those entries; recheck them if a server is removed and recreated.

Seerr reads the imported book back from Bookshelf before changing availability.
Ebook and audiobook status are independent. Completed imports finish approved
requests through Seerr's normal notification path. Repeated events are safe;
connection tests do not change library state.

Scheduled scans remain a fallback for missed events and older library items.
Their schedules have not been increased.

## Upgrade and recovery

Before upgrading, save `config/settings.json`, a consistent SQLite backup of
`config/db/db.sqlite3`, and the current image digest outside the checkout. Use
SQLite's backup API while Seerr is running so committed WAL data is included.
Test migrations against a copy before changing the production pin.

After deployment, test both Bookshelf connections and confirm a completed import
shows **Available** in Seerr. Callback failures are logged as `Readarr Webhook`.
Check credentials, server ID, the Sync setting, and Seerr's access to Bookshelf
if a connection or import fails.

To roll back an upgrade, stop Seerr, restore the matching database/settings backup,
and deploy the prior image digest. Account for requests created since the backup
before restoring it. Keep the Bookshelf webhooks disabled while an older image
without the callback endpoint is running.
