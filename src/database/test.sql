select * from questions
select * from content_blocks
select * from subjects
select * from question_bank
select* from books
select * from lessons
select * from students
select * from question_bank
select * from questions
select * from topics
select * from chapters
select * from lessons
select * from topics
select * from subsections

DELETE FROM answers
WHERE question_id IN(
    SELECT id
    FROM questions
    ORDER BY id
    OFFSET 10
);


DELETE FROM questions
WHERE id NOT IN (
    SELECT id
    FROM questions
    ORDER BY id
    LIMIT 10
);

SELECT setval('questions_id_seq', (SELECT MAX(id) FROM questions));

SELECT last_value FROM answers_id_seq;

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