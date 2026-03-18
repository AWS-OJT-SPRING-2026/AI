CREATE TABLE roadmaps (
    roadmapid SERIAL PRIMARY KEY,
    studentid INTEGER,
    total_time INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (studentid) REFERENCES students(studentid)
);

CREATE TABLE roadmap_chapters (
    id SERIAL PRIMARY KEY,
    roadmapid INTEGER,
    chapterid INTEGER,
    chapter_order INTEGER,

    FOREIGN KEY (roadmapid) REFERENCES roadmaps(roadmapid) ON DELETE CASCADE,
    FOREIGN KEY (chapterid) REFERENCES chapters(chapterid)
);

CREATE TABLE roadmap_lessons (
    id SERIAL PRIMARY KEY,
    roadmap_chapter_id INTEGER,
    lessonid INTEGER,

    time INTEGER,
    explain TEXT,

    wrong_question_count INTEGER,
    priority_score FLOAT,

    FOREIGN KEY (roadmap_chapter_id) REFERENCES roadmap_chapters(id) ON DELETE CASCADE,
    FOREIGN KEY (lessonid) REFERENCES lessons(lessonid)
);

CREATE TABLE question_content_blocks (
    id SERIAL PRIMARY KEY,

    questionid INTEGER NOT NULL,
    content_block_id INTEGER NOT NULL,

    similarity_score FLOAT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_qcb_question
        FOREIGN KEY (questionid)
        REFERENCES questions(questionid)
        ON DELETE CASCADE,

    CONSTRAINT fk_qcb_content_block
        FOREIGN KEY (content_block_id)
        REFERENCES content_blocks(id)
        ON DELETE CASCADE,

    CONSTRAINT unique_question_content UNIQUE (questionid, content_block_id)
);