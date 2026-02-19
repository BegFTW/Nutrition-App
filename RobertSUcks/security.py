from passlib.context import CryptContext

#creating a new CryptContext, just a helper for hashing/verifying passwords.
pwd_context = CryptContext(
  #using SHA256 as our default scheme, though more could be added
  schemes=["pbkdf2_sha256"],
  default="pbkdf2_sha256",
  #rounds are basic transformations that are repeated multiple times
  #the cipher basically iterates on itself n times, where n is the # of rounds
  #the algorithm takes longer depending on how many rounds, so this should be ~350ms, but we could go lower
  
  pbkdf2_sha256__default_rounds=30000
)

#self explanatory! hashing that password the password
def encrypt_password(password):
  return pwd_context.hash(password)

#basically just comparing the password plaintext the user enters with the hash we have stored
def decrypt_password(password, hashed):
  return pwd_context.verify(password, hashed)
