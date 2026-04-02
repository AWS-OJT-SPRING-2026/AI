CREATE TABLE question_bank (
    id SERIAL PRIMARY KEY,
    bank_name TEXT NOT NULL,
    userid INT REFERENCES users(userid) ON DELETE CASCADE,
    subject_id INT REFERENCES subjects(subject_id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE questions (
    id SERIAL PRIMARY KEY,
    question_text TEXT NOT NULL,
    image_url TEXT,
    explanation TEXT,
    difficulty_level INT NOT NULL,
    embedding vector(3072),
    bank_id INT REFERENCES question_bank(id) ON DELETE CASCADE,
    is_ai BOOLEAN NOT NULL DEFAULT FALSE
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

-- topic
CREATE INDEX idx_topic_bank_id ON topic(bank_id);
CREATE INDEX idx_topic_topic_name ON topic(topic_name);

-- question
CREATE INDEX idx_question_topic_id ON question(topic_id);
CREATE INDEX idx_question_difficulty_level ON question(difficulty_level);
CREATE INDEX idx_question_embedding ON question USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- answer
CREATE INDEX idx_answer_question_id ON answer(question_id);
CREATE INDEX idx_answer_is_correct ON answer(is_correct);