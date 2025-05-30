from Cryptodome.PublicKey import RSA
from Cryptodome.Cipher    import PKCS1_OAEP, AES
from Cryptodome.Random    import get_random_bytes
import struct, base64

# ───────── chiffrement hybride RSA-OAEP + AES-GCM ─────────
def hybrid_encrypt(pub_pem: bytes, plaintext: str) -> str:
    pub_key   = RSA.import_key(pub_pem)
    sess      = get_random_bytes(32)                           # clef AES-256
    enc_sess  = PKCS1_OAEP.new(pub_key).encrypt(sess)
    cipher    = AES.new(sess, AES.MODE_GCM)
    ct, tag   = cipher.encrypt_and_digest(plaintext.encode())
    blob      = struct.pack(">H", len(enc_sess)) + enc_sess + cipher.nonce + tag + ct
    return base64.b64encode(blob).decode()

def hybrid_decrypt(priv_pem: bytes, b64blob: str) -> str:
    data    = base64.b64decode(b64blob)
    klen    = struct.unpack(">H", data[:2])[0]
    enc_key = data[2:2+klen]
    nonce, tag, ct = data[2+klen:18+klen], data[18+klen:34+klen], data[34+klen:]
    sess    = PKCS1_OAEP.new(RSA.import_key(priv_pem)).decrypt(enc_key)
    plain   = AES.new(sess, AES.MODE_GCM, nonce).decrypt_and_verify(ct, tag)
    return plain.decode()