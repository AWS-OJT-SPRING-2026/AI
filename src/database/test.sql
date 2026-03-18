select * from questions
select * from content_blocks
select * from subjects
select * from question_bank
select * from books
select * from students
select * from chapters
select * from lessons
select * from subsections
select * from users
select * from teachers
select * from answers

-- reset index
SELECT setval('questions_id_seq', (SELECT MAX(id) FROM questions));

-- xóa tất cả bảng
DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'public'
    )
    LOOP
        EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END $$;

-- tạo user ảo
-- Thêm users
INSERT INTO users (userid, roleid) VALUES
(1, 1),  -- student 1
(2, 1),  -- student 2
(3, 1),  -- student 3
(4, 2);  -- teacher

-- Thêm students
INSERT INTO students (studentid, userid) VALUES
(101, 1),
(102, 2),
(103, 3);

-- Thêm teacher
INSERT INTO teachers (teacherid, userid) VALUES
(201, 4);

--xóa các bảng chỉ định
DROP TABLE IF EXISTS 
    submission_answers,
    submissions,
    assignment_questions,
    assignments,
CASCADE;