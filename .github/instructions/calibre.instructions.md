---
applyTo: "calibre/**"
---

# Calibre Expert Instructions

You are an expert in Calibre ebook library management and the LinuxServer.io Docker image.

## Service Overview
Calibre is a powerful ebook management application with format conversion, metadata editing, and a built-in content server. The LinuxServer.io image provides a web-accessible GUI.

## Technical Configuration

### Docker Compose Patterns
```yaml
image: lscr.io/linuxserver/calibre:latest
container_name: calibre
security_opt:
  - seccomp:unconfined  # Required for GUI apps
environment:
  - PUID=${PUID}
  - PGID=${PGID}
  - TZ=${TZ}
  - PASSWORD=${CALIBRE_PASSWORD}
ports:
  - 8090:8080   # Desktop GUI (HTTP)
  - 8091:8181   # Desktop GUI (HTTPS)
  - 8092:8081   # Content Server
volumes:
  - ./config:/config
  - /path/to/books:/books
```

### Port Mapping (Critical)
| External | Internal | Purpose |
|----------|----------|---------|
| 8090 | 8080 | Calibre Desktop GUI (HTTP) |
| 8091 | 8181 | Calibre Desktop GUI (HTTPS) |
| 8092 | 8081 | Calibre Content Server |

**Important**: For Docker network communication (Uptime Kuma, etc.), use **internal ports**:
- Content Server: `http://calibre:8081` (NOT 8092)

### Critical Files
- `config/` - Calibre configuration and library
- `config/metadata.db` - Library database

## Content Server

### Authentication
Content Server uses **Digest Authentication** (not Basic Auth).
- Username: Set in Calibre preferences
- Password: Set in Calibre preferences

**Note**: Uptime Kuma doesn't support Digest Auth. Monitor by accepting 401 as valid:
- URL: `http://calibre:8081`
- Accepted Status Codes: `200-299, 401`

### Enable Content Server
1. Open Calibre GUI (port 8090)
2. Preferences → Sharing → Sharing over the net
3. Enable "Run server automatically"
4. Set username/password
5. Apply

## Format Conversion

### Supported Formats
- Input: EPUB, MOBI, AZW3, PDF, FB2, DJVU, CBZ, CBR, and more
- Output: EPUB, MOBI, AZW3, PDF, and more

### Conversion via CLI
```bash
docker exec calibre ebook-convert input.epub output.mobi
```

### Bulk Conversion
1. Select books in GUI
2. Convert books → Choose output format
3. Jobs panel shows progress

## Integration Points

### Bookshelf Integration
Bookshelf can send downloads to Calibre library:
- Configure Calibre Content Server credentials in Bookshelf
- Or share the same `/books` volume

### Kavita Integration
Kavita can read from the same library:
- Mount same `/books` volume to Kavita
- Kavita prefers EPUB format

### Homepage Labels
```yaml
labels:
  - homepage.group=Media
  - homepage.name=Calibre
  - homepage.icon=calibre.png
  - homepage.href=https://calibre.benlawson.dev/
  - homepage.description=Ebook library management
```

Note: Calibre doesn't have an official Homepage widget.

## Common Tasks

### Add Books to Library
1. Open GUI (port 8090)
2. Add books button or drag-and-drop
3. Edit metadata as needed

### Edit Metadata
1. Select book
2. Edit metadata (Ctrl+E)
3. Download metadata from internet sources

### Send to Kindle
1. Preferences → Sharing → Email
2. Configure SMTP
3. Right-click book → Connect/Share → Email

## Troubleshooting

### GUI Not Loading
1. Ensure `seccomp:unconfined` is set
2. Check container logs: `docker logs calibre`
3. Verify port 8090 is accessible

### Content Server 401 Errors
This is normal - Digest Auth requires authentication.
For monitoring, accept 401 as valid status code.

### Conversion Failures
1. Check input file isn't corrupted
2. Review job logs in GUI
3. Try different conversion settings

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| PUID | User ID | 1000 |
| PGID | Group ID | 1000 |
| TZ | Timezone | UTC |
| PASSWORD | GUI password | (required) |
| CLI_ARGS | Additional CLI args | (empty) |

## Best Practices

1. **Library organization**: Let Calibre manage folder structure
2. **Backups**: Regular backups of `config/` directory
3. **Format preferences**: Store in EPUB, convert to MOBI/AZW3 on demand
4. **Metadata**: Use Calibre's metadata download for consistency
5. **Content Server**: Enable for remote access and API integration
