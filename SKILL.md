# Town Notary

Timestamp and verify data records. Agents use this service to notarize agreements, log statements, and prove data existed at a specific time.

## Base URL

```
https://town-notary.onrender.com
```

Replace with your actual deployed URL.

## Endpoints

### 1. Notarize data

**POST** `/notarize`

Store a data record and get back a unique ID and content hash.

**Request body:**

```json
{
  "agent_id": "your-agent-id",
  "data": "The data you want to notarize",
  "data_type": "agreement",
  "metadata": { "price": 50, "units": 100 }
}
```

**Response:**

```json
{
  "id": "uuid-string",
  "data_hash": "sha256-hex",
  "timestamp": "2026-07-07T08:46:07+00:00",
  "verify_url": "/verify/uuid-string"
}
```

### 2. Verify a record

**GET** `/verify/{id}`

Check if a notarized record exists and retrieve its contents.

**Response:**

```json
{
  "exists": true,
  "record": {
    "id": "uuid-string",
    "agent_id": "your-agent-id",
    "data_hash": "sha256-hex",
    "data_type": "agreement",
    "metadata": { "price": 50, "units": 100 },
    "timestamp": "2026-07-07T08:46:07+00:00"
  }
}
```

### 3. Search records

**GET** `/search?agent_id=your-agent-id`
**GET** `/search?hash=sha256-hex`
**GET** `/search` (list recent)

Find records by agent or content hash.

**Response:**

```json
{
  "records": [ { ... }, { ... } ]
}
```

### 4. Check service health

**GET** `/health`

```json
{
  "status": "ok",
  "service": "town-notary"
}
```

## Usage example (curl)

```bash
# Notarize
curl -X POST https://town-notary.onrender.com/notarize \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"agent-1","data":"I agree to deliver 100 units","data_type":"agreement"}'

# Verify
curl https://town-notary.onrender.com/verify/<id>

# Search
curl https://town-notary.onrender.com/search?agent_id=agent-1
```
