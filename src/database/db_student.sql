CREATE TABLE students (
    studentid INTEGER PRIMARY KEY,
    userid INTEGER,
    full_name VARCHAR(255),
    date_of_birth DATE,
    gender VARCHAR(10),
    address TEXT,
    parent_name VARCHAR(255),
    parent_email VARCHAR(255),
    parent_phone VARCHAR(15),
    parent_relationship VARCHAR(50)
);