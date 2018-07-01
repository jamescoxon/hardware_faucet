import getpass
import random
from simplecrypt import encrypt, decrypt

def write_encrypted(password, filename, plaintext):
    with open(filename, 'wb') as output:
        ciphertext = encrypt(password, plaintext)
        output.write(ciphertext)

password = getpass.getpass('Enter password: ')
password_confirm = getpass.getpass('Confirm password: ')
if password == password_confirm:
    print("Generating Wallet Seed")
    full_wallet_seed = hex(random.SystemRandom().getrandbits(256))
    wallet_seed = full_wallet_seed[2:].upper()
    print("Wallet Seed (make a copy of this in a safe place!): ", wallet_seed)
    print(len(wallet_seed))
    print(str(wallet_seed))
#    write_encrypted(password, 'seed.txt', wallet_seed)
else:
    print("Password Mismatch! Try again")
