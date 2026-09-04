from __future__ import annotations

import hashlib

import numpy as np

from dayahead.frozen_mapping_authority import hash_bool_array, hash_string_sequence


def test_frozen_semantic_hashes_follow_original_authority_serialization() -> None:
    values = ["1", "150r", "9r"]
    expected = hashlib.sha256(b"1\x00150r\x009r\x00").hexdigest()
    assert hash_string_sequence(values) == expected

    mask = np.asarray([[True, False, True], [False, True, False]], dtype=bool)
    expected_mask = hashlib.sha256(b"(2, 3)" + mask.astype(np.uint8).tobytes(order="C")).hexdigest()
    assert hash_bool_array(mask) == expected_mask
