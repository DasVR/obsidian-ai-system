import json, base64

settings = {
    'couchDB_URI': 'https://obsidian-sync.dasdev.net',
    'couchDB_USER': 'admin',
    'couchDB_PASSWORD': 'obsidian_secret_2026',
    'couchDB_DBNAME': 'obsidian-livesync',
    'passphrase': '',
    'disable_encryption': True
}

encoded = base64.b64encode(json.dumps(settings).encode()).decode()
uri = f'obsidian://setuplivesync?settings={encoded}'

print('=== LiveSync Setup URI ===')
print()
# Print in chunks to avoid truncation
chunk_size = 50
for i in range(0, len(uri), chunk_size):
    print(uri[i:i+chunk_size], end='')
print()
print()
print(f'Total length: {len(uri)} characters')
