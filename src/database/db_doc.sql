CREATE TABLE books (
    id SERIAL PRIMARY KEY,
    book_name TEXT NOT NULL,
    create_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    subject_id INT REFERENCES subjects(subject_id) ON DELETE CASCADE
);

CREATE TABLE chapters (
    id SERIAL PRIMARY KEY,
    book_id INT REFERENCES books(id) ON DELETE CASCADE,
    chapter_number VARCHAR(10),
    title TEXT
);

CREATE TABLE lessons (
    id SERIAL PRIMARY KEY,
    chapter_id INT REFERENCES chapters(id) ON DELETE CASCADE,   
    lesson_number VARCHAR(10),
    title TEXT
);


CREATE TABLE sections (
    id SERIAL PRIMARY KEY,
    lesson_id INT REFERENCES lessons(id) ON DELETE CASCADE,
    section_number VARCHAR(10),
    section_title TEXT
);

CREATE TABLE subsections (
    id SERIAL PRIMARY KEY,
    section_id INT REFERENCES sections(id) ON DELETE CASCADE,
    subsection_number VARCHAR(10),
    subsection_title TEXT
);

CREATE TABLE content_blocks (
    id SERIAL PRIMARY KEY,
    subsection_id INT REFERENCES subsections(id) ON DELETE CASCADE,
    content TEXT,
    embedding vector(3072)
);
-- ============================================================
-- INDEXES
-- ============================================================
 
-- books
CREATE INDEX idx_books_book_name ON books(book_name);
 
-- chapters
CREATE INDEX idx_chapters_book_id ON chapters(book_id);
CREATE INDEX idx_chapters_chapter_number ON chapters(chapter_number);
 
-- lessons
CREATE INDEX idx_lessons_chapter_id ON lessons(chapter_id);
CREATE INDEX idx_lessons_lesson_number ON lessons(lesson_number);
 
-- sections
CREATE INDEX idx_sections_lesson_id ON sections(lesson_id);
CREATE INDEX idx_sections_section_number ON sections(section_number);
 
-- subsections
CREATE INDEX idx_subsections_section_id ON subsections(section_id);
CREATE INDEX idx_subsections_subsection_number ON subsections(subsection_number);
 
-- content_blocks
CREATE INDEX idx_content_blocks_subsection_id ON content_blocks(subsection_id);
CREATE INDEX idx_content_blocks_embedding ON content_blocks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);