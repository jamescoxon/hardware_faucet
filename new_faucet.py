import picamera
import dataset
from pyzbar.pyzbar import decode
from PIL import Image
import time, getpass, sys, json, settings
from simplecrypt import encrypt, decrypt
from websocket import create_connection

import binascii
from bitstring import BitArray
from pyblake2 import blake2b
from pure25519 import ed25519_oop as ed25519

from papirus import PapirusText
text = PapirusText()

def private_public(private):
    return ed25519.SigningKey(private).get_verifying_key().to_bytes()

def xrb_account(address):
    # Given a string containing an XRB address, confirm validity and
    # provide resulting hex address
    if len(address) == 64 and (address[:4] == 'xrb_'):
        # each index = binary value, account_lookup[0] == '1'
        account_map = "13456789abcdefghijkmnopqrstuwxyz"
        account_lookup = {}
        # populate lookup index with prebuilt bitarrays ready to append
        for i in range(32):
            account_lookup[account_map[i]] = BitArray(uint=i,length=5)

        # we want everything after 'xrb_' but before the 8-char checksum
        acrop_key = address[4:-8]
        # extract checksum
        acrop_check = address[-8:]

        # convert base-32 (5-bit) values to byte string by appending each
        # 5-bit value to the bitstring, essentially bitshifting << 5 and
        # then adding the 5-bit value.
        number_l = BitArray()
        for x in range(0, len(acrop_key)):
            number_l.append(account_lookup[acrop_key[x]])
        # reduce from 260 to 256 bit (upper 4 bits are never used as account
        # is a uint256)
        number_l = number_l[4:]

        check_l = BitArray()
        for x in range(0, len(acrop_check)):
            check_l.append(account_lookup[acrop_check[x]])

        # reverse byte order to match hashing format
        check_l.byteswap()
        result = number_l.hex.upper()

        # verify checksum
        h = blake2b(digest_size=5)
        h.update(number_l.bytes)
        if (h.hexdigest() == check_l.hex):
            return result
        else:
            return False
    else:
        return False

def account_xrb(account):
    # Given a string containing a hex address, encode to public address
    # format with checksum
    # each index = binary value, account_lookup['00001'] == '3'
    account_map = "13456789abcdefghijkmnopqrstuwxyz"
    account_lookup = {}
    # populate lookup index for binary string to base-32 string character
    for i in range(32):
        account_lookup[BitArray(uint=i,length=5).bin] = account_map[i]
    # hex string > binary
    account = BitArray(hex=account)

    # get checksum
    h = blake2b(digest_size=5)
    h.update(account.bytes)
    checksum = BitArray(hex=h.hexdigest())

    # encode checksum
    # swap bytes for compatibility with original implementation
    checksum.byteswap()
    encode_check = ''
    for x in range(0,int(len(checksum.bin)/5)):
        # each 5-bit sequence = a base-32 character from account_map
        encode_check += account_lookup[checksum.bin[x*5:x*5+5]]

    # encode account
    encode_account = ''
    while len(account.bin) < 260:
        # pad our binary value so it is 260 bits long before conversion
        # (first value can only be 00000 '1' or 00001 '3')
        account = '0b0' + account
    for x in range(0,int(len(account.bin)/5)):
        # each 5-bit sequence = a base-32 character from account_map
        encode_account += account_lookup[account.bin[x*5:x*5+5]]

    # build final address string
    return 'xrb_'+encode_account+encode_check

def seed_account(seed, index):
    # Given an account seed and index #, provide the account private and
    # public keys
    h = blake2b(digest_size=32)

    seed_data = BitArray(hex=seed)
    seed_index = BitArray(int=index,length=32)

    h.update(seed_data.bytes)
    h.update(seed_index.bytes)

    account_key = BitArray(h.digest())
    return account_key.bytes, private_public(account_key.bytes)

def get_previous(account):
    #Get account info
    accounts_list = [account]
    data = json.dumps({'action' : 'accounts_frontiers', 'accounts' : accounts_list})
    ws.send(data)
    result =  ws.recv()
    print(result)
    account_info = json.loads(str(result))

    if len(account_info['frontiers']) == 0:
       return ""
    else:
       previous = account_info['frontiers'][account]
       return previous

def get_pending():
    #Get pending blocks
    data = json.dumps({'action' : 'pending', 'account' : account, "count" : "1","source": "true" })

    ws.send(data)

    pending_blocks =  ws.recv()
    print("Received '%s'" % pending_blocks)

    rx_data = json.loads(str(pending_blocks))

    return rx_data['blocks']

def get_balance(hash):
    #Get pending blocks
    data = json.dumps({'action' : 'block', 'hash' : hash})

    ws.send(data)

    block =  ws.recv()
    print("Received '%s'" % block)

    rx_data = json.loads(str(block))
    new_rx = json.loads(str(rx_data['contents']))
    return new_rx['balance']

def send_xrb(dest_account):
    representative = 'xrb_1kd4h9nqaxengni43xy9775gcag8ptw8ddjifnm77qes1efuoqikoqy5sjq3'

    previous = get_previous(str(account))

    current_balance = get_balance(previous)
    print(current_balance)
    new_balance = int(current_balance) - 50000000000000000000000000000
    hex_balance = hex(new_balance)

    print(hex_balance)
    hex_final_balance = hex_balance[2:].upper().rjust(32, '0')
    print(hex_final_balance)

    priv_key, pub_key = seed_account(seed,0)
    public_key = ed25519.SigningKey(priv_key).get_verifying_key().to_ascii(encoding="hex")

    #print("Starting PoW Generation")
    work = get_pow(previous)
    #print("Completed PoW Generation")

    #Calculate signature
    bh = blake2b(digest_size=32)
    bh.update(BitArray(hex='0x0000000000000000000000000000000000000000000000000000000000000006').bytes)
    bh.update(BitArray(hex=xrb_account(account)).bytes)
    bh.update(BitArray(hex=previous).bytes)
    bh.update(BitArray(hex=xrb_account(account)).bytes)
    bh.update(BitArray(hex=hex_final_balance).bytes)
    bh.update(BitArray(hex=xrb_account(dest_account)).bytes)

    sig = ed25519.SigningKey(priv_key+pub_key).sign(bh.digest())
    signature = str(binascii.hexlify(sig), 'ascii')

    finished_block = '{ "type" : "state", "previous" : "%s", "representative" : "%s" , "account" : "%s", "balance" : "%s", "link" : "%s", \
            "work" : "%s", "signature" : "%s" }' % (previous, account, account, new_balance, dest_account, work, signature)

    print(finished_block)

    data = json.dumps({'action' : 'process', 'block' : finished_block})
    #print(data)
    ws.send(data)

    block_reply = ws.recv()

    print(block_reply)

def receive_xrb():
    representative = 'xrb_1kd4h9nqaxengni43xy9775gcag8ptw8ddjifnm77qes1efuoqikoqy5sjq3'
    #Get pending blocks

    rx_data = get_pending()
    for block in rx_data:
      print(block)
      block_hash = block
      print(rx_data[block])
      balance = int(rx_data[block]['amount'])
      source = rx_data[block]['source']

    previous = get_previous(str(account))

    current_balance = get_balance(previous)
    print(current_balance)
    new_balance = int(current_balance) + int(balance)
    hex_balance = hex(new_balance)
    print(hex_balance)
    hex_final_balance = hex_balance[2:].upper().rjust(32, '0')
    print(hex_final_balance)

    priv_key, pub_key = seed_account(seed,0)
    public_key = ed25519.SigningKey(priv_key).get_verifying_key().to_ascii(encoding="hex")

    #print("Starting PoW Generation")
    work = get_pow(previous)
    #print("Completed PoW Generation")

    #Calculate signature
    bh = blake2b(digest_size=32)
    bh.update(BitArray(hex='0x0000000000000000000000000000000000000000000000000000000000000006').bytes)
    bh.update(BitArray(hex=xrb_account(account)).bytes)
    bh.update(BitArray(hex=previous).bytes)
    bh.update(BitArray(hex=xrb_account(account)).bytes)
    bh.update(BitArray(hex=hex_final_balance).bytes)
    bh.update(BitArray(hex=block_hash).bytes)

    sig = ed25519.SigningKey(priv_key+pub_key).sign(bh.digest())
    signature = str(binascii.hexlify(sig), 'ascii')

    finished_block = '{ "type" : "state", "previous" : "%s", "representative" : "%s" , "account" : "%s", "balance" : "%s", "link" : "%s", \
            "work" : "%s", "signature" : "%s" }' % (previous, account, account, new_balance, block_hash, work, signature)

    print(finished_block)

    data = json.dumps({'action' : 'process', 'block' : finished_block})
    #print(data)
    ws.send(data)

    block_reply = ws.recv()

    print(block_reply)

def open_xrb():
    representative = 'xrb_1kd4h9nqaxengni43xy9775gcag8ptw8ddjifnm77qes1efuoqikoqy5sjq3'
    #Get pending blocks

    rx_data = get_pending()
    for block in rx_data:
      print(block)
      block_hash = block
      print(rx_data[block])
      balance = int(rx_data[block]['amount'])
      source = rx_data[block]['source']

    hex_balance = hex(balance)
    print(hex_balance)
    hex_final_balance = hex_balance[2:].upper().rjust(32, '0')
    print(hex_final_balance)

    priv_key, pub_key = seed_account(seed,0)
    public_key = ed25519.SigningKey(priv_key).get_verifying_key().to_ascii(encoding="hex")

    #print("Starting PoW Generation")
    work = get_pow(str(public_key, 'ascii'))
    #print("Completed PoW Generation")

    #Calculate signature
    bh = blake2b(digest_size=32)
    bh.update(BitArray(hex='0x0000000000000000000000000000000000000000000000000000000000000006').bytes)
    bh.update(BitArray(hex=xrb_account(account)).bytes)
    bh.update(BitArray(hex='0x0000000000000000000000000000000000000000000000000000000000000000').bytes)
    bh.update(BitArray(hex=xrb_account(account)).bytes)
    bh.update(BitArray(hex=hex_final_balance).bytes)
    bh.update(BitArray(hex=block_hash).bytes)

    sig = ed25519.SigningKey(priv_key+pub_key).sign(bh.digest())
    signature = str(binascii.hexlify(sig), 'ascii')

    finished_block = '{ "type" : "state", "previous" : "0000000000000000000000000000000000000000000000000000000000000000", "representative" : "%s" , "account" : "%s", "balance" : "%s", "link" : "%s", \
            "work" : "%s", "signature" : "%s" }' % (account, account, balance, block_hash, work, signature)

    print(finished_block)

    data = json.dumps({'action' : 'process', 'block' : finished_block})
    #print(data)
    ws.send(data)

    block_reply = ws.recv()

    print(block_reply)

def get_pow(hash):
    data = json.dumps({'action' : 'work_generate', 'hash' : hash})
    ws.send(data)
    block_work = json.loads(str(ws.recv()))
    work = block_work['work']
    return work

def read_encrypted(password, filename, string=True):
  with open(filename, 'rb') as input:
      ciphertext = input.read()
      plaintext = decrypt(password, ciphertext)
      if string:
          return plaintext.decode('utf8')
      else:
          return plaintext

#while True:
#  password = getpass.getpass('Enter password: ')
#  password_confirm = getpass.getpass('Confirm password: ')
#  if password == password_confirm:
#      break
#  print("Password Mismatch!")

#  print("Decoding wallet seed with your password")

try:
  print("Decoding Seed (this might take some time...")
  #seed = read_encrypted(password, 'seed.txt', string=True)
  seed = settings.seed
except:
  print('\nError decoding seed, check password and try again')
  sys.exit()

#Generate address
print("Generate Address")
priv_key, pub_key = seed_account(seed, 0)
public_key = str(binascii.hexlify(pub_key), 'ascii')
print("Public Key: ", str(public_key))

account = account_xrb(str(public_key))
print("Account Address: ", account)

ws = create_connection('ws://yapraiwallet.space:8000')

previous = get_previous(str(account))
print("Previous: ", previous)
if len(previous) == 0:
   pending = get_pending()
   print("Pending: ", pending)

   open_xrb()
else:
   pending = get_pending()
   print("Rx Pending: ", pending)
   print(len(pending))
   if len(pending) > 0:
       receive_xrb()

print("Done")

db = dataset.connect('sqlite:///users.db')
user_table = db['user']

camera = picamera.PiCamera()

camera.color_effects = (128, 128)

text.write("Nano Hardware Faucet    Waiting for QR Code")

loop_count = 0

while 1:

  camera.capture('image.jpg')

  #print("Picture taken")

  result = decode(Image.open('image.jpg'))

  if len(result) > 0:
    text.write("Found QR Code")

    qr_code = result[0].data.decode("utf-8")
    print(qr_code)

    if len(qr_code) > 0:
        if qr_code[3] == ":":
           qr_code = qr_code[4:]

    try:
        ws = create_connection('ws://yapraiwallet.space:8000')
    except:
        pass

    pending = get_pending()
    if len(pending) > 0:
       receive_xrb()
       text.write("Funds Received - Woooo")
       time.sleep(5)
       print("Rx complete")

    # Check DB
    user_details = user_table.find_one(address=qr_code)
    # If not in db, add
    if user_details == None:
        loop_count += 1

        print("Not in DB")
        #Now Send Nano to Address
        message = "Sending 0.05 Nano to %s..." % (qr_code[:9])
        text.write(message)

        #Create send block with destination address
        try:
            send_xrb(qr_code)

            user_table.insert(dict(address=qr_code, requests=0, time=int(time.time()), loop=loop_count, claim=1))

            text.write("Nano Hardware Faucet    Waiting for QR Code")
        except:
            text.write("Error couldn't connect to network")
            time.sleep(5)

    else:
        loop_count += 1
        print("Already in DB")
        #Check time
        print(user_details['time'])
        if int(user_details['claim']) > 4:
            text.write("Claim limit reached")
        else:
            if ((int(time.time()) - int(user_details['time'])) > 900) or ((loop_count - int(user_details['loop'])) > 10):
                message = "Sending 0.05 Nano to %s..." % (qr_code[:9])
                text.write(message)
                try:
                    send_xrb(qr_code)
                    user_table.update(dict(address=qr_code, time=int(time.time()), loop=loop_count, claim=(int(user_details['claim']) + 1)), ['address'])
                except:
                    text.write("Error couldn't connect to network")
                    time.sleep(5)

            else:
                claims_left = 10 - (int(loop_count) - int(user_details['loop']))
                mins_left = (int(time.time()) - int(user_details['time'])) / 60
                text.write("To quick, wait %d mins or %d claims" % ( mins_left, claims_left ))

            time.sleep(10)
            text.write("Nano Hardware Faucet    Waiting for QR Code")


