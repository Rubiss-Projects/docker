# Audiobookshelf Guidance

Use this guidance when working on Audiobookshelf configuration for audiobook and podcast library management.

## Service Overview
Audiobookshelf is a self-hosted audiobook and podcast server with a clean web interface. It provides audiobook library management, podcast subscriptions, user management, progress tracking, and mobile apps for iOS/Android.

## Technical Configuration

### Docker Compose Patterns
```yaml
ports:
  - "13378:80"
environment:
  - PUID=1000
  - PGID=1000
  - TZ=America/Chicago
volumes:
  - ./config:/config
  - ./metadata:/metadata
  - ../../Media/audiobooks:/audiobooks
  - ../../Media/podcasts:/podcasts
restart: unless-stopped
```

### Critical Files
- `config/config.json` - Application configuration
- `config/database/` - SQLite database
- `metadata/covers/` - Book cover cache
- `metadata/cache/` - Metadata cache

### Default Port
- 13378 (mapped to 80 internal)

## Common Tasks

### First-Time Setup
1. Access UI: `http://localhost:13378`
2. Create root user account
3. Configure libraries
4. Add audiobooks/podcasts
5. Create additional users (optional)

### Add Audiobook Library
Settings > Libraries > Add Library:
1. **Name**: Audiobooks
2. **Folder**: /audiobooks
3. **Library Type**: Audiobooks
4. **Provider**: Audible, Google Books, etc.
5. **Save**

Scanner automatically indexes audiobooks.

### Add Podcast Library
Settings > Libraries > Add Library:
1. **Name**: Podcasts
2. **Folder**: /podcasts
3. **Library Type**: Podcasts
4. **Save**

### Subscribe to Podcast
Podcasts > Add Podcast:
- Enter RSS feed URL
- Or search by name
- Select to subscribe
- Downloads episodes automatically

### Audiobook Organization
Recommended folder structure:
```
audiobooks/
├── Author Name/
│   ├── Book Title/
│   │   ├── Chapter 01.mp3
│   │   ├── Chapter 02.mp3
│   │   └── cover.jpg
```

Or single file per book:
```
audiobooks/
├── Author Name/
│   ├── Book Title.m4b  # Chapterized audiobook file
```

### Scan Library
Libraries > [Library] > Scan:
- Scans for new/changed files
- Updates metadata
- Finds missing covers

Or auto-scan: Settings > Libraries > Enable auto scan

### Edit Audiobook Metadata
Library > Book > Edit:
- Title, Author, Narrator
- Description, genres, tags
- Cover image
- ISBN, ASIN
- Series information

### Create User
Settings > Users > Add User:
1. Username, password
2. Permissions: Admin or User
3. Library access
4. Item tagging permissions

### Playback Features
- **Speed control**: 0.5x - 3.0x
- **Sleep timer**: 5min - 8 hours
- **Skip forward/back**: 15s (configurable)
- **Chapters**: Jump to chapter
- **Progress sync**: Cross-device sync

### Download for Offline (Mobile)
Mobile app:
- Tap book > Download
- Play offline without internet
- Syncs progress when online

## Integration Points

### Homepage Dashboard
```yaml
- Audiobookshelf:
    icon: audiobookshelf.png
    href: http://localhost:13378
    description: Audiobook and podcast server
```

### SWAG reverse proxy
```
Domain: audiobooks.benlawson.dev
Forward: http://audiobookshelf:80
Websockets: Yes
SSL: Let's Encrypt
```

### Mobile Apps
- **iOS**: App Store "Audiobookshelf"
- **Android**: Play Store "Audiobookshelf"

Server URL: `https://audiobooks.benlawson.dev`

### Plex Integration
No direct integration, but can coexist:
- Plex for video
- Audiobookshelf for audiobooks

### Podcast RSS
Each podcast has RSS feed for external clients.

## Troubleshooting

### Audiobooks Not Detected
1. Check folder structure matches expected format
2. Verify file permissions (PUID/PGID)
3. Supported formats: MP3, M4A, M4B, FLAC, OGG, OPUS, AAC, WMA
4. Trigger manual scan
5. Check logs for errors

### Metadata Not Found
1. Verify internet connectivity
2. Check provider API keys (if configured)
3. Manually edit metadata
4. Upload custom cover image

### Playback Issues
1. Check audio file codec support
2. Verify file not corrupted
3. Test in different player
4. Check browser console for errors

### Mobile App Won't Connect
1. Verify server URL is accessible
2. Check HTTPS certificate valid
3. Test in browser first
4. Verify firewall allows connection
5. Check user credentials

### Podcast Episodes Not Downloading
1. Check RSS feed URL is valid
2. Verify disk space available
3. Review episode download settings
4. Check podcast folder permissions

## Best Practices

1. **Folder Structure**: Organize by Author > Title
2. **Chapterized Files**: Use M4B for single-file audiobooks with chapters
3. **Metadata**: Complete metadata improves browsing
4. **Cover Images**: High-quality covers enhance experience
5. **Regular Scans**: Enable auto-scan or schedule periodic scans
6. **User Accounts**: Separate accounts for family members (progress tracking)
7. **Backups**: Backup config and metadata directories

## Security Considerations

- **User Accounts**: Strong passwords
- **HTTPS**: Use reverse proxy for SSL
- **Port Exposure**: Don't expose 13378 publicly without auth
- **Admin Account**: Protect admin access
- **Library Permissions**: Restrict user access per library
- **API Keys**: Protect API tokens

## Advanced Configuration

### Custom Providers
Settings > Providers:
- Audible
- Google Books
- Open Library
- Custom API keys (optional)

### Automatic Backups
Settings > Backups:
- Enable automatic backups
- Frequency: Daily, weekly
- Keep last X backups
- Backup location: /metadata/backups

### Notifications
Settings > Notifications:
- Apprise (supports many services)
- Discord, Slack, Email, Pushover
- Events: New episodes, failed downloads

### Collections
Organize books into collections:
- Create collection
- Add books manually
- Or auto-collections by genre, narrator, etc.

### User Listening Stats
Each user dashboard shows:
- Total listening time
- Books finished
- Currently reading
- Recently added

### Server Settings
Settings > Server:
- **Port**: Change listen port
- **Host**: Bind address
- **Base URL**: For reverse proxy
- **Authentication**: JWT settings

### Library Settings
Per-library configuration:
- **Auto scan**: Enable/disable
- **Metadata provider**: Preferred provider
- **Cover search**: Automatic cover fetching
- **Audio file management**: Chapter detection, merging

## Supported File Formats

**Audio**:
- MP3
- M4A, M4B (AAC, ALAC)
- FLAC
- OGG, OPUS
- AAC
- WMA
- WAV

**Metadata**:
- ID3 tags (MP3)
- MP4 tags (M4A/M4B)
- Vorbis comments (FLAC, OGG)

**Images**:
- JPG, JPEG
- PNG
- WEBP

## Audiobook File Types

### M4B (Chapterized)
Best for audiobooks:
- Single file per book
- Embedded chapters
- Artwork support
- Small file size (AAC)

### MP3 (Multi-file)
Common format:
- One file per chapter
- Easy to edit
- Universal compatibility

### FLAC (Lossless)
For audiophiles:
- Lossless quality
- Larger file size
- Full metadata support

## Podcast Features

### Episode Management
- Auto-download new episodes
- Download limits per podcast
- Episode retention rules
- Custom download schedules

### Playback Queue
- Add episodes to queue
- Rearrange queue
- Continue where left off

### Episode Filters
- Filter by played/unplayed
- Filter by date
- Search episodes

### OPML Import/Export
Import/export podcast subscriptions:
- Settings > Podcasts > Import OPML
- Export to backup subscriptions

## API Usage

### Get Libraries
```powershell
$headers = @{
    "Authorization" = "Bearer your-api-token"
}

Invoke-RestMethod -Uri "http://localhost:13378/api/libraries" -Headers $headers
```

### Get Library Items
```powershell
Invoke-RestMethod -Uri "http://localhost:13378/api/libraries/{library-id}/items" -Headers $headers
```

### Get User Progress
```powershell
Invoke-RestMethod -Uri "http://localhost:13378/api/me/progress" -Headers $headers
```

### Trigger Library Scan
```powershell
Invoke-RestMethod -Uri "http://localhost:13378/api/libraries/{library-id}/scan" -Method Post -Headers $headers
```

Get API token:
- Settings > Users > [User] > API Token

## Backup and Restore

### Backup Config
```powershell
docker compose stop
tar -czf "audiobookshelf-backup-$(Get-Date -Format 'yyyyMMdd').tar.gz" config/ metadata/
docker compose start
```

### Restore
```powershell
docker compose stop
tar -xzf audiobookshelf-backup-YYYYMMDD.tar.gz
docker compose start
```

### Backup Audiobooks
Audiobook files are media, back up separately to external drive.

## Mobile App Features

- **Offline listening**: Download books
- **Progress sync**: Cross-device sync
- **Sleep timer**: Auto-pause
- **Speed control**: Variable playback speed
- **Chapter navigation**: Quick chapter jumps
- **Bookmarks**: Mark favorite moments
- **Widgets**: Home screen widgets (iOS/Android)
- **CarPlay**: iOS CarPlay support
- **Android Auto**: Android Auto support

## User Management

### User Permissions
- **Admin**: Full access, settings management
- **User**: Library access, playback only
- **Guest**: Limited access, no progress tracking

### Library Access Control
Per-user library restrictions:
- User A: Audiobooks only
- User B: Podcasts only
- Admin: All libraries

### Item Tagging
Allow users to:
- Tag books as favorite
- Add personal notes
- Create custom shelves

## Performance Optimization

### Metadata Caching
Settings > Advanced:
- Cache covers locally
- Preload metadata
- Background scanning

### Database Maintenance
Periodically vacuum database:
```powershell
docker exec audiobookshelf sqlite3 /config/database/libraryItems.db "VACUUM;"
```

### Transcoding (Future Feature)
Currently serves original files. Transcoding planned for future releases.

## Common Configuration

### Base URL for Reverse Proxy
Settings > Server:
- Base URL: `/audiobooks`
- Nginx config: `location /audiobooks { proxy_pass http://audiobookshelf:80; }`

### Custom Metadata Folder
Change metadata location:
```yaml
volumes:
  - ../../Backups/audiobookshelf-metadata:/metadata
```

### Read-Only Audiobook Library
For shared network libraries:
```yaml
volumes:
  - ../../Media/audiobooks:/audiobooks:ro
```

Server can read but not modify source files.

This comprehensive audiobook and podcast server provides a Plex-like experience for audio content with robust library management, progress tracking, and multi-device support for the homelab media stack.
