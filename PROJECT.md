# 🧟 Frankenstein Storage — Project Submission & Overview

> **Turn fragmented drives, external USB pendrives, and free cloud tiers into one unified, self-healing, encrypted storage mesh.**

---

## 📌 Project Links & Metadata

| Resource | Link / Detail |
| :--- | :--- |
| **Project Name** | Frankenstein Storage |
| **Live Web Application (Vercel)** | [https://zippy-pumice-qfzzlv8.tmp.now](https://zippy-pumice-qfzzlv8.tmp.now) |
| **Preview Deployment** | [https://zippy-pumice-qfzzlv8-kjlcvukf4-founders23.vercel.app](https://zippy-pumice-qfzzlv8-kjlcvukf4-founders23.vercel.app) |
| **GitHub Repository** | [https://github.com/shivanggupta1931-art/Frankenstein-Storage](https://github.com/shivanggupta1931-art/Frankenstein-Storage) |
| **Demo Master Password** | `iitr@123` |
| **Session Bearer Token** | `frankenstein-demo-token` |
| **Target Platforms** | Web, macOS, Linux (Docker) |

---

## 💡 The Problem It Solves

Every student, developer, and creative professional has fragmented storage:
- A drawer full of half-used 8GB and 16GB USB pendrives.
- An older external HDD with 40GB free.
- Free cloud tiers with tight quota limits (15GB on Google Drive, 5GB on iCloud, 2GB on Dropbox).

Right now, this storage is isolated, fragile, and inefficient:
1. **Capacity Silos**: You cannot store an 8GB file across two 4GB drives.
2. **Zero Fault Tolerance**: If a cheap USB pendrive suffers bit-rot or dies, your files are permanently lost.
3. **Privacy Vulnerability**: Storing sensitive files across free cloud providers exposes them to telemetry and scanning.
4. **Subscription Traps**: Big-tech cloud providers lock users into recurring monthly storage tiers for incremental gigabytes.

**Frankenstein Storage** aggregates disparate local directories, external USB pendrives, and free cloud storage tiers into a **single, secure, self-healing virtual volume**.

---

## 🌟 Key Capabilities & Features

### 1. 🧬 Unified Hybrid Storage Mesh
Aggregates heterogeneous storage media—internal SSD partitions, external USB sticks/hard drives, Apple iCloud, Google Drive, and S3-compatible buckets (Cloudflare R2, MinIO, AWS)—into one continuous logical volume with intelligent, load-balanced chunk allocation.

### 2. 🔐 Zero-Knowledge Authenticated Encryption
- Authenticated **AES-256-GCM** cipher with unique 12-byte random nonces per chunk.
- Master encryption keys derived using memory-hard **`scrypt`** ($N=16384, r=8, p=1$).
- Keys exist **exclusively in volatile RAM** while unlocked; locking the vault completely scrubs keys from memory.
- Chunks stored on disk or cloud tiers are indistinguishable from high-entropy random data—stealing a physical drive yields zero readable information.

### 3. 🛡️ Rotating XOR Parity ($2D + 1P$) & Autonomous Self-Healing
- Slices files into uniform chunks and computes rotating XOR parity across independent physical drives.
- **On-the-Fly Stream Reconstruction**: If a drive is unplugged or fails mid-transfer, Frankenstein reconstructs the missing byte stream during download with verified SHA-256 integrity.
- **1-Click Pool Healing**: Re-synthesizes missing chunks onto newly attached or remaining healthy drives to bring the pool back to 100% redundancy.

### 4. 🔌 Plug & Play Hot-Plug USB Support & Safe Hardware Eject
- Automatically detects connected external pendrives and provisions flat chunk layouts with human-readable manifest files (`FRANKENSTEIN_MANIFEST.txt`).
- Hardware safe eject flushes the OS write-buffer (`os.sync()`) followed by atomic unmount (`diskutil` on macOS / `umount` on Linux) to prevent filesystem corruption.

### 5. ⚡ Dual Storage Engine
- **Chunked Parity Mode**: High-throughput parallel striping with $N-1$ fault tolerance and bitwise self-healing.
- **Whole-Object Encrypted Mode**: Mirrors whole encrypted files across distinct physical media for critical documents requiring multi-drive resilience.

---

## 🛠️ Technologies Used

- **Backend Framework**: Python 3.11+, FastAPI, Uvicorn (ASGI)
- **Database & Metadata**: SQLite with Write-Ahead Logging (WAL) and atomic transactions
- **Cryptography & Security**: PyCA Cryptography (`AES-256-GCM`, `scrypt`, `HMAC-SHA256`)
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS tokens, Lucide Icons
- **Deployment & Cloud**: Vercel (Serverless Python + SPA rewrites), Docker, Multi-stage builds
- **Hardware Integration**: macOS `diskutil` / IOKit CLI, Linux block storage integration

---

## 🧗 Challenges We Ran Into & How We Overcame Them

### 1. On-the-Fly Bitwise Parity Reconstruction in Streaming Downloads
* **Challenge**: Rebuilding missing chunks dynamically during streaming download without caching multi-gigabyte files into server RAM.
* **Solution**: Implemented an async chunk generator pipeline. When an chunk in a stripe is detected as degraded or missing, the engine pulls the sibling data chunk and XOR parity chunk into memory, applies bitwise XOR matrix operations on the byte stream in real time, and streams the decrypted stream directly to the browser while verifying the original SHA-256 checksum.

### 2. Zero-Knowledge Key Security without Disk Leakage
* **Challenge**: Storing encryption keys or recovery tokens on disk defeats the security model if a physical USB stick is stolen.
* **Solution**: Engineered a memory-only session key lifecycle. Keys are derived strictly upon vault unlock via `scrypt` and held in RAM. Once locked, the memory pointers are cleared and all REST API endpoints immediately reject requests with `403 VAULT_LOCKED`.

### 3. Preventing USB Detach Corruption
* **Challenge**: Users frequently pull USB pendrives without ejecting, causing corrupted parity stripes due to unwritten OS write buffers.
* **Solution**: Built an automated synchronization workflow that triggers kernel-level `os.sync()` to flush all dirty page buffers before invoking atomic unmount commands.

### 4. Serverless Cloud Deployment (Vercel) & Mixed-Content Prevention
* **Challenge**: Serving a modern React dashboard over HTTPS on Vercel while connecting to local Python backend engines triggered browser Mixed-Content / Private Network Access security blocks.
* **Solution**: Built dynamic same-origin resolution (`window.location.origin`) and a dedicated Vercel Python serverless entrypoint (`api/index.py`) so both frontend and backend communicate over the same domain with zero CORS or Mixed-Content restrictions.

---

## 🏆 Accomplishments We're Proud Of

- ✅ **True Hardware Fault Tolerance**: Demonstrated live drive unplugging with instant, zero-corruption XOR parity reconstruction.
- ✅ **Zero-Knowledge Privacy**: Verified that no plain-text filenames, directory structures, or keys ever touch disks or third-party cloud quotas.
- ✅ **Single-Port Simplicity**: Unified FastAPI backend serving the pre-compiled Vite React dashboard and REST APIs on a single port (`http://localhost:8765`).
- ✅ **Cross-Platform Readiness**: 1-line installation script for macOS & Linux, Docker container distribution, and 1-click cloud deployment on Vercel, Render, and Railway.

---

## 📚 What We Learned

- High-performance binary operations in Python using bytearrays and bitwise XOR arithmetic.
- Zero-knowledge encryption architectures and secure key derivation standards (`scrypt` parameter tuning).
- Designing resilient distributed storage engines that gracefully handle asynchronous disk failures and hot-plug hardware events.
- Bridging low-level OS storage calls (`diskutil`, `umount`, `os.sync`) with reactive modern web frontends.

---

## 🔮 What's Next for Frankenstein Storage

- 📱 **Mobile Companion App**: iOS/Android client to browse and stream files from your storage mesh over local Wi-Fi.
- 🌐 **P2P Encrypted LAN Mesh**: Peer-to-peer storage clustering between friends and lab mates using WebRTC/libp2p.
- 🧬 **Reed-Solomon ($M+N$) Parity**: Upgrade parity calculation to allow configurable multi-drive failure tolerance ($3D + 2P$).
- 📦 **Automated Background Bit-Rot Scrubbing**: Periodic silent integrity audits that detect and repair bit-level corruption before drives fail.

---

## 🚀 Quickstart: Run Frankenstein Locally

```bash
# Clone the repository
git clone https://github.com/shivanggupta1931-art/Frankenstein-Storage.git
cd Frankenstein-Storage

# Setup and run with virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Launch unified server
python -m backend.app.main
```
Open **`http://localhost:8765`** in your browser and enter master password **`iitr@123`**!
