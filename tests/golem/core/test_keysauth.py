import os
from random import random, randint
from unittest import TestCase
from unittest.mock import patch

from freezegun import freeze_time
from golem_messages import message
from golem_messages.cryptography import ECCx

from golem import testutils
from golem.core.keysauth import EllipticalKeysAuth, get_random, \
    get_random_float, sha2
from golem.core.simpleserializer import CBORSerializer
from golem.utils import decode_hex
from golem.utils import encode_hex


class TestKeysAuth(TestCase, testutils.PEP8MixIn):
    PEP8_FILES = ['golem/core/keysauth.py']

    def test_sha(self):
        """ Test sha2 function"""
        test_str = "qaz123WSX"
        expected_sha2 = int("0x47b151cede6e6a05140af0da56cb889c40adaf4fddd9f1"
                            "7435cdeb5381be0a62", 16)
        self.assertEqual(sha2(test_str), expected_sha2)

    def test_random_number_generator(self):
        with self.assertRaises(ArithmeticError):
            get_random(30, 10)
        self.assertEqual(10, get_random(10, 10))
        for _ in range(10):
            a = randint(10, 100)
            b = randint(a + 1, 2 * a)
            r = get_random(a, b)
            self.assertGreaterEqual(r, a)
            self.assertGreaterEqual(b, r)

        for _ in range(10):
            r = get_random_float()
            self.assertGreater(r, 0)
            self.assertGreater(1, r)


class TestEllipticalKeysAuth(testutils.TempDirFixture):

    def test_init(self):
        for _ in range(100):
            ek = EllipticalKeysAuth(os.path.join(self.path),
                                    private_key_name=str(random()))
            self.assertEqual(len(ek._private_key),
                             EllipticalKeysAuth.PRIV_KEY_LEN)
            self.assertEqual(len(ek.public_key), EllipticalKeysAuth.PUB_KEY_LEN)
            self.assertEqual(len(ek.key_id), EllipticalKeysAuth.KEY_ID_LEN)

    @patch('golem.core.keysauth.logger')
    def test_init_priv_key_wrong_length(self, logger):
        keys_dir = os.path.join(self.path, 'keys')
        private_key_name = "priv_key"
        private_key_path = os.path.join(keys_dir, private_key_name)

        # given
        os.makedirs(keys_dir)
        with open(private_key_path, 'wb') as f:
            f.write(b'123')

        # when
        EllipticalKeysAuth(self.path, private_key_name)

        # then
        assert logger.error.called
        with open(private_key_path, 'rb') as f:
            new_priv_key = f.read()
        assert len(new_priv_key) == EllipticalKeysAuth.PRIV_KEY_LEN

    @patch('golem.core.keysauth.logger')
    def test_key_recreate_on_increased_difficulty(self, logger):
        old_difficulty = 0
        new_difficulty = 8

        assert old_difficulty < new_difficulty  # just in case

        # create key that has difficulty lower than new_difficulty
        ek = EllipticalKeysAuth(self.path, difficulty=old_difficulty)
        while ek.is_difficult(new_difficulty):
            ek.generate_new(old_difficulty)

        assert ek.get_difficulty() >= old_difficulty
        assert ek.get_difficulty() < new_difficulty
        logger.reset_mock()  # just in case

        ek = EllipticalKeysAuth(self.path, difficulty=new_difficulty)

        assert ek.get_difficulty() >= new_difficulty
        assert logger.warning.called

    @patch('golem.core.keysauth.logger')
    def test_key_successful_load(self, logger):
        # given
        ek = EllipticalKeysAuth(self.path)
        private_key = ek._private_key
        public_key = ek.public_key
        del ek
        logger.reset_mock()  # just in case

        # when
        ek2 = EllipticalKeysAuth(self.path)

        # then
        assert private_key == ek2._private_key
        assert public_key == ek2.public_key
        assert not logger.warning.called

    @freeze_time("2017-11-23 11:40:27.767804")
    def test_backup_keys_with_no_keys(self):
        # given
        assert os.listdir(self.path) == []  # empty dir
        priv_key_name = 'priv'

        # when
        EllipticalKeysAuth(self.path, priv_key_name)

        # then
        assert os.listdir(self.path) == ['keys']
        assert os.listdir(os.path.join(self.path, 'keys')) == [priv_key_name]

    @freeze_time("2017-11-23 11:40:27.767804")
    def test_backup_keys(self):
        # given
        priv_key_name = 'priv'
        private_key_dir = os.path.join(self.path, 'keys')
        os.mkdir(private_key_dir)
        private_key_path = os.path.join(private_key_dir, priv_key_name)
        with open(private_key_path, 'w') as f:
            f.write("foo")

        # when
        EllipticalKeysAuth(self.path, priv_key_name)

        # then
        assert os.listdir(self.path) == ['keys']
        assert os.listdir(os.path.join(self.path, 'keys')) == [
            "%s_2017-11-23_11-40-27_767804.bak" % priv_key_name,
            priv_key_name,
        ]

    def test_sign_verify_elliptical(self):
        ek = EllipticalKeysAuth(self.path)
        data = b"abcdefgh\nafjalfa\rtajlajfrlajl\t" * 100
        signature = ek.sign(data)
        self.assertTrue(ek.verify(signature, data))
        self.assertTrue(ek.verify(signature, data, ek.key_id))
        ek2 = EllipticalKeysAuth(os.path.join(self.path, str(random())))
        self.assertTrue(ek2.verify(signature, data, ek.key_id))
        data2 = b"23103"
        sig = ek2.sign(data2)
        self.assertTrue(ek.verify(sig, data2, ek2.key_id))

    def test_sign_fail_elliptical(self):
        """ Test incorrect signature or data """
        ek = EllipticalKeysAuth(self.path)
        data1 = b"qaz123WSX./;'[]"
        data2 = b"qaz123WSY./;'[]"
        sig1 = ek.sign(data1)
        sig2 = ek.sign(data2)
        self.assertTrue(ek.verify(sig1, data1))
        self.assertTrue(ek.verify(sig2, data2))
        self.assertFalse(ek.verify(sig1, data2))
        self.assertFalse(ek.verify(sig1, [data1]))
        self.assertFalse(ek.verify(sig2, None))
        self.assertFalse(ek.verify(sig2, data1))
        self.assertFalse(ek.verify(None, data1))

    def test_fixed_sign_verify_elliptical(self):
        public_key = b"cdf2fa12bef915b85d94a9f210f2e432542f249b8225736d923fb0" \
                     b"7ac7ce38fa29dd060f1ea49c75881b6222d26db1c8b0dd1ad4e934" \
                     b"263cc00ed03f9a781444"
        private_key = b"1aab847dd0aa9c3993fea3c858775c183a588ac328e5deb9ceeee" \
                      b"3b4ac6ef078"

        ek = EllipticalKeysAuth(self.path)

        ek.public_key = decode_hex(public_key)
        ek._private_key = decode_hex(private_key)
        ek.key_id = encode_hex(ek.public_key)
        ek.ecc = ECCx(ek._private_key)

        msg = message.WantToComputeTask(node_name='node_name',
                                        task_id='task_id',
                                        perf_index=2200,
                                        price=5 * 10 ** 18,
                                        max_resource_size=250000000,
                                        max_memory_size=300000000,
                                        num_cores=4)

        data = msg.get_short_hash()
        signature = ek.sign(data)

        dumped_s = CBORSerializer.dumps(signature)
        loaded_s = CBORSerializer.loads(dumped_s)

        self.assertEqual(signature, loaded_s)

        dumped_d = CBORSerializer.dumps(data)
        loaded_d = CBORSerializer.loads(dumped_d)

        self.assertEqual(data, loaded_d)

        dumped_k = CBORSerializer.dumps(ek.key_id)
        loaded_k = CBORSerializer.loads(dumped_k)

        self.assertEqual(ek.key_id, loaded_k)
        self.assertTrue(ek.verify(loaded_s, loaded_d, ek.key_id))

        dumped_l = msg.serialize(ek.sign, lambda x: ek.encrypt(x, public_key))
        loaded_l = message.Message.deserialize(dumped_l, ek.decrypt)

        self.assertEqual(msg.get_short_hash(), loaded_l.get_short_hash())
        self.assertTrue(ek.verify(msg.sig, msg.get_short_hash(), ek.key_id))

    def test_encrypt_decrypt_elliptical(self):
        """ Test encryption and decryption with EllipticalKeysAuth """
        ek = EllipticalKeysAuth(os.path.join(self.path, str(random())))
        data = b"abcdefgh\nafjalfa\rtajlajfrlajl\t" * 1000
        enc = ek.encrypt(data)
        self.assertEqual(ek.decrypt(enc), data)
        ek2 = EllipticalKeysAuth(os.path.join(self.path, str(random())))
        self.assertEqual(ek2.decrypt(ek.encrypt(data, ek2.key_id)), data)
        data2 = b"23103"
        self.assertEqual(ek.decrypt(ek2.encrypt(data2, ek.key_id)), data2)
        data3 = b"\x00" + os.urandom(1024)
        ek.generate_new(2)
        self.assertEqual(ek2.decrypt(ek2.encrypt(data3)), data3)
        with self.assertRaises(TypeError):
            ek2.encrypt(None)

    def test_difficulty(self):
        difficulty = 8
        ek = EllipticalKeysAuth(self.path, difficulty=difficulty)
        # first 8 bits of digest must be 0
        assert sha2(ek.public_key).to_bytes(256, 'big')[0] == 0
        assert ek.get_difficulty() >= difficulty
        assert EllipticalKeysAuth.is_pubkey_difficult(ek.public_key, difficulty)
        assert EllipticalKeysAuth.is_pubkey_difficult(ek.key_id, difficulty)
