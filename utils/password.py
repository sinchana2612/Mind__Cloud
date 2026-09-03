from datetime import date, datetime

from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password):
    if not password:
        raise ValueError("Password cannot be empty.")
    return generate_password_hash(password)


def verify_password(password_hash, password):
    return bool(password_hash and password and check_password_hash(password_hash, password))


def generate_default_password_from_dob(dob):
    if isinstance(dob, str):
        try:
            dob = datetime.strptime(dob, "%Y-%m-%d").date()
        except ValueError as error:
            raise ValueError("Date of birth must use YYYY-MM-DD format.") from error
    if not isinstance(dob, (date, datetime)):
        raise ValueError("A valid date of birth is required.")
    return dob.strftime("%d%m%Y")
