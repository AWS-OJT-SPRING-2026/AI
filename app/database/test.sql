select * from questions
select * from content_blocks
select * from subjects
select * from question_bank
select* from books
select * from lessons

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