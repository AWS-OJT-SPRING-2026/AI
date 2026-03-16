CREATE TABLE question_bank (
    id SERIAL PRIMARY KEY,
    bank_name TEXT NOT NULL,
    subject_id INT REFERENCES subjects(subject_id) ON DELETE CASCADE
);

CREATE TABLE questions (
    id SERIAL PRIMARY KEY,
    question_text TEXT NOT NULL,
    image_url TEXT,
    explanation TEXT,
    difficulty_level TEXT NOT NULL,
    embedding vector(3072),
    is_ai BOOLEAN NOT NULL DEFAULT FALSE,
    bank_id INT REFERENCES question_bank(id) ON DELETE CASCADE
);

CREATE TABLE questions_link (
    id SERIAL PRIMARY KEY,
    question_id INT REFERENCES questions(id) ON DELETE CASCADE,
    lesson_id INT REFERENCES lessons(id) ON DELETE CASCADE,
    keyword_id INT REFERENCES keywords(id) ON DELETE CASCADE
);

CREATE TABLE answers (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    label TEXT NOT NULL,
    is_correct BOOLEAN NOT NULL,
    question_id INT NOT NULL,
    FOREIGN KEY (question_id) REFERENCES questions(id)
);
-- ============================================================
-- INDEXES
-- ============================================================
 
-- question_bank
CREATE INDEX idx_question_bank_bank_name ON question_bank(bank_name);
 
-- question
CREATE INDEX idx_question_bank_id ON questions(bank_id);
CREATE INDEX idx_question_difficulty_level ON questions(difficulty_level);
CREATE INDEX idx_question_embedding ON questions USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
 
-- answer
CREATE INDEX idx_answer_question_id ON answers(question_id);
CREATE INDEX idx_answer_is_correct ON answer(is_correct);