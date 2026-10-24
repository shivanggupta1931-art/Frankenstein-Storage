"""XOR Parity calculation and rotating stripe layout."""



def xor_bytes(a: bytes, b: bytes) -> bytes:
    """Computes byte-wise XOR of two equal-length byte strings."""
    if len(a) != len(b):
        raise ValueError(f"Cannot XOR byte strings of differing lengths: {len(a)} vs {len(b)}")
    if len(a) == 0:
        return b""
    ia = int.from_bytes(a, "big")
    ib = int.from_bytes(b, "big")
    return (ia ^ ib).to_bytes(len(a), "big")


def compute_xor_parity(chunk_a: bytes, chunk_b: bytes) -> bytes:
    """Computes XOR parity chunk P = A ^ B."""
    return xor_bytes(chunk_a, chunk_b)


def rebuild_missing_chunk(available_chunk: bytes, parity_chunk: bytes) -> bytes:
    """Rebuilds missing chunk from the remaining data chunk and parity chunk.
    
    Since P = A ^ B, A = B ^ P and B = A ^ P.
    """
    return xor_bytes(available_chunk, parity_chunk)


def get_stripe_layout(stripe_index: int) -> dict[str, int]:
    """Returns rotating slot assignments for a 3-chunk stripe (2 data, 1 parity).
    
    Returns a dictionary mapping:
        'parity': slot_index (0, 1, or 2)
        'data0': slot_index
        'data1': slot_index
    """
    parity_pos = stripe_index % 3
    data_slots = [i for i in (0, 1, 2) if i != parity_pos]
    return {
        "parity": parity_pos,
        "data0": data_slots[0],
        "data1": data_slots[1],
    }
