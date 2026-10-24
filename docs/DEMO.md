# 60-Second Frankenstein Storage Demo Script

Follow this step-by-step 60-second walkthrough to demonstrate pooled encrypted storage, rotating XOR parity redundancy, and graceful degradation.

---

### Step 0: Launch Backend & Frontend

1. **Terminal 1 (Backend)**:
   ```bash
   source .venv/bin/activate
   python -m backend.app.main
   ```
   *Copy the printed `SESSION TOKEN: <token>` from the console banner.*

2. **Terminal 2 (Frontend)**:
   ```bash
   cd frontend
   npm run dev
   ```
   *Open browser at `http://127.0.0.1:5173`.*

---

### Step 1: Configure Token & Unlock Vault (10 seconds)
1. On first load, if prompted for token, click **Token** in the top bar and paste the session token printed on backend startup. Click **Save Settings**.
2. Click **Unlock Vault** in the top right.
3. Enter master password: `iitr@123` and click **Unlock Vault**.
4. The status pill transitions from Locked to **Unlocked (Green)**.

---

### Step 2: Register 3 Storage Drives (15 seconds)
*You can use the folders created by `python scripts/seed-demo.py`:*
1. In the **Storage Drives** panel, click **Add Drive**.
   - Name: `Drive Alpha`
   - Path: `<absolute-path>/demo_drives/drive_alpha`
   - Click **Register Drive**.
2. Repeat for **Drive Beta**:
   - Path: `<absolute-path>/demo_drives/drive_beta`
3. Repeat for **Drive Gamma**:
   - Path: `<absolute-path>/demo_drives/drive_gamma`
4. Notice the **Pool Overview** immediately updates:
   - Pooled Capacity: sums total reported disk capacity.
   - Drives Online: shows **3 of 3 (Healthy)**.
   - Each drive receives a distinct color tag (Cyan, Amber, Purple).

---

### Step 3: Upload a File and Inspect the Chunk Map (15 seconds)
1. In the **Pooled Files** panel, drag & drop `demo_document.txt` (or click **Upload File** to pick a file/PDF).
2. Watch the upload progress bar complete.
3. In the file row, observe:
   - **Health Badge**: `Healthy` (Green checkmark).
   - **Chunk Map**: Visual grid of squares, each colored by its assigned physical drive.
   - **Parity Chips**: Squares with letter **"P"** denote rotating XOR parity chunks. Hover over any chunk square to see:
     `Stripe 0, Slot 1 (Data) • Drive: Drive Beta [ONLINE] • Hash: ab34cd...`
4. Click **Details** to see the full plaintext SHA-256 and chunk distribution across drives.

---

### Step 4: Take ONE Drive Offline & Download with Parity Rebuild (10 seconds)
1. In the **Storage Drives** panel, find **Drive Alpha** and click **Take Offline**.
2. Status updates to **Simulated offline** (Pink badge).
3. In the **Pooled Files** panel:
   - All chunks located on Drive Alpha immediately dim and grey out in the chunk map.
   - File health badge updates to: **`Rebuilt from parity` (Amber badge)**.
4. Click **Download** on `demo_document.txt`.
5. The backend streams the file, detects missing chunks from Drive Alpha, reconstructs them on-the-fly via byte-wise XOR of the remaining data and parity chunks, verifies the SHA-256 hash, and saves the file to your computer.
6. Verify byte identity:
   ```bash
   # Compare downloaded file with original
   shasum -a 256 ~/Downloads/demo_document.txt demo_document.txt
   ```
   *Hashes match 100% byte-for-byte!*

---

### Step 5: Take a SECOND Drive Offline & Show Clear 503 Failure (10 seconds)
1. In the **Storage Drives** panel, find **Drive Beta** and click **Take Offline**.
2. Now 2 of 3 drives are offline!
3. In the **Pooled Files** panel:
   - File health badge switches to **`Unavailable` (Red badge)**.
   - The Download button is disabled with explanatory tooltip.
4. If an external client attempts `GET /api/v1/files/{id}/download`:
   - Returns **HTTP 503 Service Unavailable** with standard error envelope:
     ```json
     {
       "error": {
         "code": "PARITY_RECOVERY_FAILED",
         "message": "Stripe 0 unrecoverable: 2 chunks unavailable (Drive Alpha offline; Drive Beta offline)",
         "details": { "stripe_index": 0 }
       }
     }
     ```
5. Click **Bring Online** on Drive Alpha and Drive Beta to restore the system to **Healthy**.
