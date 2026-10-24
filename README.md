# 🧟 Frankenstein Storage

**Pooled • Encrypted • Fault-Tolerant Local Storage Volume**

Frankenstein Storage pools several independent storage drives (folders, external SSDs, USB keys) into one unified logical drive. Files are chunked, encrypted with AES-256-GCM, protected with rotating XOR parity, and distributed across distinct physical drives.

If any **ONE** drive goes offline or suffers silent bit rot, files are reconstructed on-the-fly from parity during download without data loss.

---

## 📦 Dependency Justifications

### Backend Dependencies (`pyproject.toml`)
- `fastapi`: High-performance asynchronous REST API framework for streaming endpoints and request handling.
- `uvicorn`: Lightweight ASGI server binding strictly to `127.0.0.1:8765`.
- `pydantic`: Strict request and payload schema validation (v2).
- `cryptography`: Provides authenticated AES-256-GCM encryption with 12-byte random nonces and 16-byte authentication tags.
- `python-multipart`: Streaming form data handling for file uploads.
- `pytest`: Automated test runner for engine, security, and integrity assertions.
- `pytest-asyncio`: Async test runner support for FastAPI endpoints and streams.
- `httpx`: Full HTTP client for asynchronous API integration tests.
- `ruff`: Ultra-fast Python code linter and formatter.

### Frontend Dependencies (`frontend/package.json`)
- `react` & `react-dom`: Component-based reactive UI library (v19).
- `vite`: Fast developer server and production bundler binding strictly to `127.0.0.1:5173`.
- `typescript`: Type safety across all data structures, API contracts, and UI components.
- `lucide-react`: Lightweight, accessible icon set for drives, chunks, and status indicators.

---

## 🚀 Quickstart & Running the App

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm

### 1. macOS & Linux (Bash / Zsh)

```bash
# Clone and enter workspace
cd /path/to/IITR_Drive_Manager

# Backend Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
# Or pip install fastapi uvicorn "pydantic>=2.0" cryptography python-multipart pytest pytest-asyncio httpx ruff

# Seed demo folders and sample test file
python scripts/seed-demo.py

# Start Backend Server (Terminal 1)
python -m backend.app.main
```
*Observe the console output banner and copy the `SESSION TOKEN: <token>`.*

```bash
# Frontend Setup (Terminal 2)
cd frontend
npm install
npm run dev
```
*Open your browser at `http://127.0.0.1:5173`.*

---

### 2. Windows (PowerShell)

```powershell
# In PowerShell (Run as Administrator or standard user)
cd C:\path\to\IITR_Drive_Manager

# Backend Setup
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .

# Seed demo folders and sample test file
python scripts\seed-demo.py

# Start Backend Server (Terminal 1)
python -m backend.app.main
```
*Copy the `SESSION TOKEN: <token>` displayed in the terminal.*

```powershell
# Frontend Setup (Terminal 2)
cd frontend
npm install
npm run dev
```
*Navigate to `http://127.0.0.1:5173`.*

---

## 🧪 Running the Automated Test Suite

All 8 hackathon test suites run against an isolated temporary environment (`tmp_path`) and never touch real user files:

```bash
# Run backend pytest suite
source .venv/bin/activate
pytest -v

# Run Python linter (ruff)
ruff check backend

# Run Frontend typecheck and build
cd frontend
npm run build
```

### Verified Test Cases:
1. **Round Trip**: Chunk, encrypt, pad, and reassemble round-trip for 0-byte, 1-byte, 1-stripe, and multi-MB files.
2. **Crypto Security**: Wrong password rejection via scrypt verifier; tampered ciphertext detection via AES-GCM tags.
3. **Single Drive Offline**: Downloading with each individual drive offline is 100% byte-identical (hash match).
4. **Double Drive Offline**: Two drives offline produces a clear HTTP 503 `PARITY_RECOVERY_FAILED` with zero corrupted output.
5. **Disk Bit Rot Recovery**: Flipping a byte directly on disk is caught by hash verification and rebuilt from XOR parity.
6. **Path Traversal & Security**: Rejection of path traversal (`../`) and symlink escapes; missing/invalid token returns 401; bad Host/Origin returns 403.
7. **Mid-Stream Rollback**: Upload failure mid-stream leaves no `.tmp` debris and deletes all written chunks.
8. **Application Restart**: New app instance pointing to the same SQLite database re-authenticates and streams files.

---

## 🏛️ Architecture & Storage Design

1. **Provider Layer (`providers/base.py`, `providers/local.py`)**:
   - Chunks stored strictly under `<drive_root>/.frankenstein/chunks/ab/cd/<chunk_id>`.
   - Atomic writes via `.frankenstein/tmp/<uuid>.tmp`, `fsync`, and atomic rename (`Path.replace`).
   - Strict path traversal prevention: all targets must resolve within `.frankenstein`.
2. **Key Derivation & In-Memory Encryption (`crypto/`)**:
   - Master password derived via `scrypt` (N=16384, r=8, p=1, dklen=32) with a random 32-byte salt stored in DB.
   - Master key kept exclusively in memory when unlocked; never logged or saved to disk.
   - AES-256-GCM authenticated encryption per chunk with a 12-byte random nonce prefixed to ciphertext + 16-byte tag.
3. **Rotating XOR Parity (`redundancy/parity.py`)**:
   - Stripe configuration: 2 data chunks + 1 XOR parity chunk ($2D + 1P$).
   - Parity position rotates across drives per stripe index ($s \pmod 3$).
   - Equal-length chunk padding ensures exact byte-for-byte XOR parity computation:
     $P = C_0 \oplus C_1$
     $C_0 = P \oplus C_1$
     $C_1 = P \oplus C_0$
4. **Integrity & Streaming (`services/storage_engine.py`)**:
   - Stored chunk SHA-256 verified on disk read.
   - Whole plaintext SHA-256 verified after reassembly.
   - Zero-memory-buffering streaming download through FastAPI `StreamingResponse`.

---

## ⚠️ Known Limitations

1. **Single User / Local Vault**: Designed as a single-user local storage pool; multi-user permissions and roles are non-goals.
2. **Loopback Only**: Security middleware enforces loopback binding (`127.0.0.1` / `localhost`) and rejects external hosts.
3. **XOR Parity Tolerance**: 1 parity chunk per stripe can survive at most **one** drive failure per stripe. If two or more drives holding chunks for the same stripe are offline, recovery fails with HTTP 503.
4. **No Cloud Providers in Core**: Storage providers in this version are local folders and mounted filesystem volumes.
5. **No Password Recovery**: If the master password is lost, data cannot be decrypted or recovered as keys are never stored.
