from passlib.context import CryptContext

# Create a password hashing context
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# The plain text password you want to hash
plain_password = input("Enter the password to hash: ")

# Generate the hash
hashed_password = pwd_ctx.hash(plain_password)

print("\nPlain Password: ", plain_password)
print("Hashed Password:", hashed_password)
