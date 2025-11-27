---
applyTo: "kavita/**"
---

# Kavita Expert Instructions

You are an expert in Kavita, a fast cross-platform reading server for ebooks and comics.

## Service Overview
Kavita is a self-hosted digital library for reading ebooks, comics, and manga. It provides a beautiful web interface for reading directly in the browser, with support for EPUB, PDF, and comic formats.

## Technical Configuration

### Docker Compose Patterns
```yaml
image: lscr.io/linuxserver/kavita:latest
container_name: kavita
ports:
  - "5000:5000"
volumes:
  - ./config:/config
  - /path/to/books:/books
env_file:
  - .env
```

### Critical Files
- `config/config/kavita.db` - Main database
- `config/config/appsettings.json` - Configuration

### Default Port
- 5000 - Web UI and API

## Supported Formats

### Ebooks
- **EPUB** (preferred)
- **PDF**

### Comics/Manga
- **CBZ** (Comic Book ZIP)
- **CBR** (Comic Book RAR)
- **CB7** (Comic Book 7-Zip)

### Not Supported
- **MOBI** - Not supported (use Calibre to convert)
- **AZW3** - Not supported (use Calibre to convert)

**Tip**: Use Calibre to convert MOBI/AZW3 to EPUB before importing to Kavita.

## Integration Points

### Homepage Widget
```yaml
labels:
  - homepage.widget.type=kavita
  - homepage.widget.url=http://kavita:5000
  - homepage.widget.key=${KAVITA_KEY}
```

### Get API Key
1. Login to Kavita
2. User Settings → 3rd Party Clients
3. Generate API Key

### OPDS Feed
Kavita provides OPDS for e-reader apps:
- URL: `http://kavita:5000/api/opds/{apikey}`
- Compatible with: Moon+ Reader, KOReader, etc.

### Kindle Browser Access
Access Kavita directly from Kindle's experimental browser:
- URL: `https://kavita.yourdomain.com`
- Login and read EPUBs directly

## Common Tasks

### Initial Setup
1. Access `http://localhost:5000`
2. Create admin account
3. Add library: Settings → Libraries → Add
4. Point to `/books` folder
5. Scan library

### Library Structure
Kavita expects organized folders:
```
/books/
├── Author Name/
│   ├── Book Title/
│   │   └── Book Title.epub
│   └── Series Name/
│       ├── Series Name v01.epub
│       └── Series Name v02.epub
```

### Series Detection
Kavita auto-detects series from:
- Folder structure
- Filename patterns (v01, v02, etc.)
- Metadata in EPUB files

### User Management
Settings → Users:
- Create accounts for friends/family
- Set library access per user
- Age ratings and restrictions

## Troubleshooting

### Books Not Appearing
1. Check library path is correct
2. Verify file format is supported (EPUB, PDF)
3. Manual library scan: Libraries → Scan
4. Check logs for errors

### MOBI Files Not Working
Kavita doesn't support MOBI. Convert with Calibre:
```bash
docker exec calibre ebook-convert book.mobi book.epub
```

### Slow Performance
1. Large libraries take time to scan
2. Enable background scanning
3. Consider SSD storage for library

### Cover Images Missing
1. Kavita extracts covers from files
2. Manual refresh: Book → Refresh Metadata
3. Check EPUB has embedded cover

## Best Practices

1. **File format**: Use EPUB for best compatibility
2. **Organization**: Maintain consistent folder structure
3. **Metadata**: Ensure EPUBs have proper metadata
4. **Users**: Create separate accounts for each user
5. **OPDS**: Use for e-reader app integration
6. **Backups**: Regular backups of `config/` directory

## Comparison with Calibre

| Feature | Kavita | Calibre |
|---------|--------|---------|
| Web reading | ✅ Excellent | ❌ Limited |
| Format support | EPUB, PDF, CBZ | Many formats |
| Conversion | ❌ No | ✅ Yes |
| Metadata editing | Limited | ✅ Extensive |
| User management | ✅ Multi-user | Single user |

**Recommended setup**: Use Calibre for library management/conversion, Kavita for reading.
