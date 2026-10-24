# 🧟 Frankenstein Storage

<div align="center">

![Frankenstein Storage](https://img.shields.io/badge/Frankenstein-Storage_v1.0.0-8b5cf6?style=for-the-badge&logo=ghost)
[![Live Site](https://img.shields.io/badge/Live_Site-Vercel-black?style=for-the-badge&logo=vercel)](https://zippy-pumice-qfzzlv8.tmp.now)
[![CI Pipeline](https://img.shields.io/github/actions/workflow/status/shivanggupta1931/Frankenstein-Storage/ci.yml?branch=main&label=CI&style=for-the-badge&logo=githubactions)](https://github.com/shivanggupta1931/Frankenstein-Storage/actions)
[![Docker Image](https://img.shields.io/badge/ghcr.io-frankenstein--storage-blue?style=for-the-badge&logo=docker)](https://github.com/shivanggupta1931/Frankenstein-Storage/pkgs/container/frankenstein-storage)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-3776AB?style=for-the-badge&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![Vite + React](https://img.shields.io/badge/Vite-React_19-646CFF?style=for-the-badge&logo=vite)](https://vitejs.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

**Turn fragmented drives, external USB pendrives, and free cloud tiers into one unified, self-healing, encrypted storage mesh.**

[🌐 Live Site (Vercel)](https://zippy-pumice-qfzzlv8.tmp.now) • [Quickstart](#-quickstart) • [1-Line Installer](#-1-line-terminal-installer-macos--linux) • [Docker Distribution](#-1-click-docker-distribution) • [Cloud Deployment](#-cloud-1-click-deployment) • [Architecture](#-architecture--storage-engine) • [REST API](#-rest-api-reference)

</div>

---

## 🌟 Key Capabilities

- 🧬 **Unified Hybrid Storage Pool**: Aggregates disparate local directories, external USB pendrives/SSDs, Apple iCloud Drive, Google Drive Desktop, Microsoft OneDrive, Dropbox, and S3-compatible object storage (Cloudflare R2, AWS S3, MinIO, Backblaze B2) into a single logical volume.
- 🔐 **Zero-Knowledge Authenticated Encryption**: AES-256-GCM authenticated cipher with 12-byte random nonces per chunk. Keys derived via `scrypt` (N=16384, r=8, p=1) and held exclusively in memory while the vault is unlocked.
- 🛡️ **Rotating XOR Parity ($2D + 1P$)**: Striped chunks rotate parity across independent physical drives. If any drive goes offline or suffers silent bit rot, files are reconstructed on-the-fly during streaming download.
- 🔌 **Plug & Play USB Storage**: Automatic hot-plug detection for USB pendrives and external hard drives. Writes flat chunk structure (`chunks/<chunk_id>`) with human-readable manifests (`FRANKENSTEIN_MANIFEST.txt`).
- ⏏️ **Safe Hardware Eject**: OS write-buffer flush (`os.sync()`) followed by atomic unmount via `diskutil` prevents filesystem corruption when detaching drives.
- ⚡ **Dual Storage Modes**: Switch seamlessly between **Chunked Parity** (high-speed parallel striping with self-healing) and **Whole-Object Encrypted** (whole files encrypted and mirrored across distinct media).
- 🚀 **Unified Single-Port Server**: FastAPI serves pre-compiled Vite React static assets and REST API endpoints simultaneously at `http://localhost:8765` with automated session bootstrapping.

---

## 🚀 Quickstart

### 🌐 Live Web Deployment (Vercel)

Frankenstein Storage is deployed and live on Vercel:

👉 **[Open Live Site on Vercel](https://zippy-pumice-qfzzlv8.tmp.now)**

| Resource | URL / Value |
| :--- | :--- |
| **Production Domain** | [`https://zippy-pumice-qfzzlv8.tmp.now`](https://zippy-pumice-qfzzlv8.tmp.now) |
| **Preview Deployment** | [`https://zippy-pumice-qfzzlv8-kjlcvukf4-founders23.vercel.app`](https://zippy-pumice-qfzzlv8-kjlcvukf4-founders23.vercel.app) |
| **Demo Master Password** | `iitr@123` (Use this password if the vault is locked) |
| **Session Bearer Token** | `frankenstein-demo-token` |

---

### 📦 1-Line Terminal Installer (macOS & Linux)

Install and run Frankenstein Storage in one command:

```bash
curl -fsSL https://raw.githubusercontent.com/shivanggupta1931/Frankenstein-Storage/main/scripts/install.sh | bash
```

The installer verifies Python 3.10+, provisions a virtual environment, checks out all dependencies, creates an authorized `.env` configuration, generates the desktop/terminal launcher (`frankenstein`), and outputs your ready-to-use session URL.

---

### 🐳 1-Click Docker Distribution

Run the production multi-stage container image directly from GitHub Container Registry:

```bash
docker run -d \
  --name frankenstein-storage \
  -p 8765:8765 \
  -v frankenstein_data:/data \
  -v ~/frankenstein_pool:/mnt/storage \
  ghcr.io/shivanggupta1931/frankenstein-storage:latest
```

Open **`http://localhost:8765`** in your browser.

#### Using Docker Compose:

```bash
# Clone the repository
git clone https://github.com/shivanggupta1931/Frankenstein-Storage.git
cd Frankenstein-Storage

# Launch the unified container
docker compose up -d
```

View `docker-compose.yml` to customize host storage volume mounts:
```yaml
services:
  frankenstein:
    build: .
    ports:
      - "8765:8765"
    volumes:
      - frankenstein_data:/data
      - ./storage_pool:/mnt/storage
      # Mount external USB drives on macOS:
      # - /Volumes:/Volumes:rw
      # Mount external USB drives on Linux:
      # - /media:/media:rw
```

---

### ☁️ Cloud 1-Click Deployment

Frankenstein Storage can be deployed to your favorite cloud container provider with zero extra configuration:

| Provider | Configuration File | Guide |
| :--- | :--- | :--- |
| **Vercel** | [`vercel.json`](vercel.json) | [Live Production Link](https://zippy-pumice-qfzzlv8.tmp.now) with Serverless API routing |
| **Render** | [`render.yaml`](render.yaml) | 1-click Docker web service with persistent 10GB disk mount at `/data` |
| **Railway** | [`railway.json`](railway.json) | Instant deploy with automatic restart policy and `/api/v1/health` checks |

---

### 💻 Manual Local Development

```bash
# 1. Clone repository
git clone https://github.com/shivanggupta1931/Frankenstein-Storage.git
cd Frankenstein-Storage

# 2. Setup backend virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx ruff

# 3. Setup and build frontend
cd frontend
npm install
npm run build
cd ..

# 4. Launch unified server
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765
```

Navigate to `http://127.0.0.1:8765` in your browser.

---

## 🏛️ Architecture & Storage Engine

```
                          ┌───────────────────────────┐
                          │   Client Web Dashboard    │
                          │   (React 19 + TypeScript) │
                          └─────────────┬─────────────┘
                                        │ HTTP / REST (Port 8765)
                                        ▼
                          ┌───────────────────────────┐
                          │     FastAPI Core Engine   │
                          │  (Auth, Streamer, Router) │
                          └──────┬─────────────┬──────┘
                                 │             │
        ┌────────────────────────┘             └────────────────────────┐
        ▼                                                               ▼
┌──────────────────────────┐                                  ┌──────────────────────────┐
│   Chunked 2D+1P Mode     │                                  │   Whole-Object Mode      │
│  AES-256-GCM + XOR Parity│                                  │ Direct Stream Encryption │
└─────────────┬────────────┘                                  └────────────┬─────────────┘
              │                                                            │
              ▼                                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                STORAGE MESH PROVIDERS                                  │
├─────────────────────┬─────────────────────┬────────────────────┬───────────────────────┤
│ Local / SSD Folders │ External USB Drives │ Apple iCloud Drive │ Cloudflare R2 / S3    │
│ (~/.frankenstein)   │ (/Volumes/Pendrive) │ (CloudStorage)     │ (Pure Python SigV4)   │
└─────────────────────┴─────────────────────┴────────────────────┴───────────────────────┘
```

### Rotating XOR Parity Striping ($2D + 1P$)

For every 2 data chunks ($C_0, C_1$), a byte-for-byte XOR parity chunk ($P$) is computed:

$$P = C_0 \oplus C_1$$

The parity position cycles across the storage drives per stripe index ($s \pmod 3$):
- **Stripe 0**: Drive A holds $C_0$, Drive B holds $C_1$, Drive C holds $P$
- **Stripe 1**: Drive A holds $C_0$, Drive B holds $P$, Drive C holds $C_1$
- **Stripe 2**: Drive A holds $P$, Drive B holds $C_0$, Drive C holds $C_1$

If any drive goes offline or its hash fails due to silent corruption:
$$C_0 = P \oplus C_1 \quad \text{or} \quad C_1 = P \oplus C_0$$

Reconstruction is executed on-the-fly and streamed directly to the download socket with zero intermediate disk footprint.

---

## 📡 REST API Reference

All requests must supply the session authorization token via `Authorization: Bearer <token>` or `?token=<token>` (for preview streams).

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Healthcheck returning `{ "status": "ok" }` |
| `GET` | `/api/v1/overview` | Pooled capacity, free space, drive health, and deduplicated totals |
| `GET` | `/api/v1/drives` | List all registered storage drives with status and health metrics |
| `POST` | `/api/v1/drives` | Register a new local directory, USB path, iCloud folder, or S3 bucket |
| `POST` | `/api/v1/drives/{id}/eject` | Safely flush OS buffers and unmount external USB device |
| `GET` | `/api/v1/drives/external` | Auto-detect all external USB and pendrive volumes mounted under `/Volumes` |
| `GET` | `/api/v1/files` | List all stored files with SHA-256, redundancy mode, and chunk breakdown |
| `POST` | `/api/v1/files/upload` | Stream file upload with query parameters `name`, `mode`, `overwrite` |
| `GET` | `/api/v1/files/{id}/download`| Stream decrypted file download with automated on-the-fly parity rebuild |
| `GET` | `/api/v1/files/{id}/preview` | Stream inline preview (image, PDF, text) |
| `DELETE`| `/api/v1/files/{id}` | Permanently delete file and purge all chunks across all drives |
| `POST` | `/api/v1/vault/lock` | Evict master decryption keys from memory |
| `POST` | `/api/v1/vault/unlock` | Re-derive keys with password and resume vault operations |

---

## 🧪 Automated Test Suite

Frankenstein Storage includes 54 automated unit, integration, and security tests:

```bash
# Run the complete test suite
.venv/bin/pytest -v
```

### Coverage Highlights:
- ✅ **Round-Trip Integrity**: Zero-byte, single-byte, multi-megabyte payloads.
- ✅ **Cryptographic Verification**: scrypt rejection of incorrect passwords, AES-GCM tag tampering detection.
- ✅ **Degraded Parity Rebuilds**: Individual drive offline simulations with byte-for-byte SHA-256 match.
- ✅ **USB Hot-Plugging**: Pendrive attach/detach resilience and safe eject verification.
- ✅ **Multi-Cloud Signer**: Pure-Python AWS SigV4 signer validation without third-party SDKs.
- ✅ **Security Hardening**: Path traversal rejection (`../../../etc/passwd`), symlink escape blocking, Host & Origin whitelist enforcement.
- ✅ **Single-Port Production**: Static SPA asset serving and automatic session token injection.

---

## ⚙️ Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `HOST` | `127.0.0.1` | Network interface to bind (`0.0.0.0` inside containers) |
| `PORT` | `8765` | Server port |
| `AUTH_TOKEN` | *Random 32-byte URL-safe string* | Fixed API and Web UI bearer authorization token |
| `DATABASE_PATH` | `frankenstein.db` | Absolute or relative path to persistent SQLite database |
| `STATIC_DIR` | `frontend/dist` | Path to pre-compiled Vite frontend distribution |
| `ALLOW_ALL_HOSTS` | `false` | Set to `true` in Docker or cloud deployments |
| `ALLOW_ALL_ORIGINS`| `false` | Set to `true` for public reverse proxy access |
| `ALLOWED_HOSTS` | *(empty)* | Comma-separated list of additional permitted Host headers |
| `MIN_DRIVES` | `3` | Minimum number of online drives required for chunk striping |

---

## 📄 License

Frankenstein Storage is released under the [MIT License](LICENSE).
