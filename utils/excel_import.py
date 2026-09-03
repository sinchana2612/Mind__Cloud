from datetime import datetime

import pandas as pd

from utils.password import generate_default_password_from_dob, hash_password


def _read_excel(file, required_columns):
    dataframe = pd.read_excel(file)
    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    missing = [column for column in required_columns if column not in dataframe.columns]
    if missing:
        return None, {"success": False, "errors": [f"Missing required columns: {', '.join(missing)}"]}
    if dataframe.empty:
        return None, {"success": False, "errors": ["The spreadsheet is empty."]}
    return dataframe, None


def _value(row, column, row_number):
    value = row[column]
    if pd.isna(value) or not str(value).strip():
        raise ValueError(f"Row {row_number}: {column} is required.")
    return str(value).strip()


def import_students(file, cursor):
    required = ["Student Name", "USN", "DOB", "Department", "Class", "Email", "Gender", "Phone", "Parent Name", "Parent Phone", "Address", "Semester", "Section", "Batch", "Admission Year", "CGPA", "Attendance", "Career Goal", "Interest Domain"]
    dataframe, error = _read_excel(file, required)
    if error:
        return error
    errors = []; imported = 0; seen = set()
    for index, row in dataframe.iterrows():
        row_number = index + 2
        try:
            usn = _value(row, "USN", row_number)
            if usn in seen:
                raise ValueError(f"Row {row_number}: duplicate USN in spreadsheet: {usn}.")
            seen.add(usn); cursor.execute("SELECT id FROM users WHERE USN=%s", (usn,))
            if cursor.fetchone():
                raise ValueError(f"Row {row_number}: USN already exists: {usn}.")
            dob = pd.to_datetime(row["DOB"], errors="raise").date()
            for column in required:
                _value(row, column, row_number)
            cursor.execute("INSERT INTO users (UserName, USN, password, role) VALUES (%s,%s,%s,'student')", (_value(row, "Student Name", row_number), usn, hash_password(generate_default_password_from_dob(dob))))
            cursor.execute("""INSERT INTO students (user_id, department, class, email, gender, dob, phone, parent_name, parent_phone, address, semester, section, batch, admission_year, cgpa, attendance, career_goal, interest_domain)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (cursor.lastrowid, _value(row,"Department",row_number), _value(row,"Class",row_number), _value(row,"Email",row_number), _value(row,"Gender",row_number), dob, _value(row,"Phone",row_number), _value(row,"Parent Name",row_number), _value(row,"Parent Phone",row_number), _value(row,"Address",row_number), _value(row,"Semester",row_number), _value(row,"Section",row_number), _value(row,"Batch",row_number), _value(row,"Admission Year",row_number), row["CGPA"], row["Attendance"], _value(row,"Career Goal",row_number), _value(row,"Interest Domain",row_number)))
            imported += 1
        except (ValueError, KeyError) as exc:
            errors.append(str(exc))
    return {"success": not errors, "imported": imported, "errors": errors}


def import_teachers(file, cursor):
    required = ["Teacher Name", "Employee ID", "DOB", "Department", "Email", "Designation", "Gender", "Phone", "Qualification", "Experience", "Office Room"]
    dataframe, error = _read_excel(file, required)
    if error:
        return error
    errors = []; imported = 0; seen = set()
    for index, row in dataframe.iterrows():
        row_number = index + 2
        try:
            employee_id = _value(row, "Employee ID", row_number)
            if employee_id in seen:
                raise ValueError(f"Row {row_number}: duplicate Employee ID in spreadsheet: {employee_id}.")
            seen.add(employee_id); cursor.execute("SELECT id FROM users WHERE USN=%s", (employee_id,))
            if cursor.fetchone():
                raise ValueError(f"Row {row_number}: Employee ID already exists: {employee_id}.")
            dob = pd.to_datetime(row["DOB"], errors="raise").date()
            for column in required:
                _value(row, column, row_number)
            cursor.execute("INSERT INTO users (UserName, USN, password, role) VALUES (%s,%s,%s,'teacher')", (_value(row,"Teacher Name",row_number), employee_id, hash_password(generate_default_password_from_dob(dob))))
            cursor.execute("""INSERT INTO teachers (user_id, department, email, designation, employee_id, gender, dob, phone, qualification, experience, office_room)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (cursor.lastrowid, _value(row,"Department",row_number), _value(row,"Email",row_number), _value(row,"Designation",row_number), employee_id, _value(row,"Gender",row_number), dob, _value(row,"Phone",row_number), _value(row,"Qualification",row_number), _value(row,"Experience",row_number), _value(row,"Office Room",row_number)))
            imported += 1
        except (ValueError, KeyError) as exc:
            errors.append(str(exc))
    return {"success": not errors, "imported": imported, "errors": errors}
