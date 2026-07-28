import hashlib
import struct
import unittest

from solders.keypair import Keypair
from solders.pubkey import Pubkey

from nosana_bootstrap import (
    CONFIDENTIAL_STUB_CID,
    JOBS_PROGRAM,
    build_authorization,
    build_list_instruction,
    decode_confidential_stub_cid,
)


MARKET = "7AtiXMSH6R1jjBxrcYjehCkkSF7zvYWte63gwEDBcGHq"


class NosanaInstructionTests(unittest.TestCase):
    def setUp(self):
        self.payer = Keypair.from_seed(bytes(range(32)))
        self.job = Keypair.from_seed(bytes(range(32, 64)))
        self.run = Keypair.from_seed(bytes(range(64, 96)))

    def test_confidential_stub_cid_is_the_known_sha256_digest(self):
        self.assertEqual(
            decode_confidential_stub_cid(CONFIDENTIAL_STUB_CID).hex(),
            "924301b36fefe50cd83c93a0686d2e25ce05da34b50cd79d04328ef3d0ec8cf6",
        )

    def test_list_instruction_matches_official_account_contract(self):
        instruction = build_list_instruction(
            payer=self.payer.pubkey(),
            job=self.job.pubkey(),
            run=self.run.pubkey(),
            market=Pubkey.from_string(MARKET),
            timeout_sec=600,
            cid=CONFIDENTIAL_STUB_CID,
        )
        self.assertEqual(str(instruction.program_id), JOBS_PROGRAM)
        self.assertEqual(
            instruction.data,
            hashlib.sha256(b"global:list").digest()[:8]
            + decode_confidential_stub_cid(CONFIDENTIAL_STUB_CID)
            + struct.pack("<q", 600),
        )
        self.assertEqual(
            [
                (str(meta.pubkey), meta.is_signer, meta.is_writable)
                for meta in instruction.accounts
            ],
            [
                ("3ogUn1GNXoASaRbxPNeVJnVv5rG4EPBtmQmX61jVorUe", True, True),
                (MARKET, False, True),
                ("3WTypo2uYrwMHJ5yFFwUPX6T25n39PwNwke7pz22P4Ut", True, True),
                ("CiuGyhh6szsputL7MahWqvfRteFdL8WFhv64dgYmCrBu", False, True),
                ("EYZESGGY1rn2mEqMkzokKP4fxHcFePqhgwxp3ruacU5V", False, True),
                ("FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF", True, True),
                ("6tjbAfNHnUusWLZqFznMKyBrjs1ZX92eyKwiUi2Bsg3x", False, True),
                ("37xZ4jY3bSMBgxwekwdALRZK1kAUCh7YkkPabA4P2tq8", False, True),
                ("FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF", True, False),
                ("nosRB8DUV67oLNrL45bo2pFLrmsWPiewe2Lk2DRNYCp", False, False),
                ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", False, False),
                ("11111111111111111111111111111111", False, False),
            ],
        )

    def test_authorization_matches_official_tweetnacl_vector(self):
        self.assertEqual(
            build_authorization(
                CONFIDENTIAL_STUB_CID,
                bytes(self.payer),
                now_ms=1785144000123,
            ),
            "QmYBbVdWFgfoTEdPT7mnaXJz6zQzfKb1Pts4A5B9kDMBph:"
            "cWRPrV6oeYwMNkkXX4AafPQ3z5B1neGPnaKqVaTDH8o6KoaCQVAHSG7zWHfbZz5ueS2YC16dMtr2V7feWYoBCNr:"
            "1785144000123",
        )

    def test_matches_live_official_sdk_instruction_only_capture(self):
        """Captured from @nosana/sdk Jobs.list(..., instructionOnly=true)."""
        instruction = build_list_instruction(
            payer=self.payer.pubkey(),
            job=Pubkey.from_string("DjEAwhtbJ3xNmahLtyNGnuX5ZcL9jpkGEnU1JTTCvzYV"),
            run=Pubkey.from_string("739ng1zBYzr8ZxopuvtGMU3QFzoYZbDgkruphhXgm4D5"),
            market=Pubkey.from_string(MARKET),
            timeout_sec=600,
        )
        self.assertEqual(
            instruction.data.hex(),
            "36aec14311298426924301b36fefe50cd83c93a0686d2e25ce05da34b50cd79"
            "d04328ef3d0ec8cf65802000000000000",
        )
        self.assertEqual(
            [str(meta.pubkey) for meta in instruction.accounts],
            [
                "DjEAwhtbJ3xNmahLtyNGnuX5ZcL9jpkGEnU1JTTCvzYV",
                MARKET,
                "739ng1zBYzr8ZxopuvtGMU3QFzoYZbDgkruphhXgm4D5",
                "CiuGyhh6szsputL7MahWqvfRteFdL8WFhv64dgYmCrBu",
                "EYZESGGY1rn2mEqMkzokKP4fxHcFePqhgwxp3ruacU5V",
                "FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF",
                "6tjbAfNHnUusWLZqFznMKyBrjs1ZX92eyKwiUi2Bsg3x",
                "37xZ4jY3bSMBgxwekwdALRZK1kAUCh7YkkPabA4P2tq8",
                "FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF",
                "nosRB8DUV67oLNrL45bo2pFLrmsWPiewe2Lk2DRNYCp",
                "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                "11111111111111111111111111111111",
            ],
        )

    def test_invalid_cid_and_timeout_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "CID"):
            decode_confidential_stub_cid("not-a-cid")
        with self.assertRaisesRegex(ValueError, "timeout"):
            build_list_instruction(
                payer=self.payer.pubkey(),
                job=self.job.pubkey(),
                run=self.run.pubkey(),
                market=Pubkey.from_string(MARKET),
                timeout_sec=0,
                cid=CONFIDENTIAL_STUB_CID,
            )


if __name__ == "__main__":
    unittest.main()
