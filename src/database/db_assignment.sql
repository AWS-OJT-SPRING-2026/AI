CREATE TABLE assignments (
    assignmentid SERIAL PRIMARY KEY,
    classid INTEGER,
    teacherid INTEGER,
    title VARCHAR(255),
    type VARCHAR(100),
    status VARCHAR(50),
    created_at TIMESTAMP(6),
    updated_at TIMESTAMP(6),
    deadline TIMESTAMP(6)
);

CREATE TABLE assignment_questions (
    assignmentid INTEGER,
    questionid INTEGER,

    PRIMARY KEY (assignmentid, questionid),

    FOREIGN KEY (assignmentid)
        REFERENCES assignments(assignmentid)
        ON DELETE CASCADE,

    FOREIGN KEY (questionid)
        REFERENCES questions(id)
        ON DELETE CASCADE
);

CREATE TABLE submissions (
    submissionid SERIAL PRIMARY KEY,
    assignmentid INTEGER,
    studentid INTEGER,
    score NUMERIC(5,2),
    time_taken INTEGER,
    submit_time TIMESTAMP(6),

    FOREIGN KEY (assignmentid)
        REFERENCES assignments(assignmentid)
        ON DELETE CASCADE,

    FOREIGN KEY (studentid)
        REFERENCES students(studentid)
        ON DELETE CASCADE
);

CREATE TABLE submission_answers (
    answerid SERIAL PRIMARY KEY,
    submissionid INTEGER,
    questionid INTEGER,
    selected_answer VARCHAR(255),
    is_correct BOOLEAN,

    FOREIGN KEY (submissionid)
        REFERENCES submissions(submissionid)
        ON DELETE CASCADE,

    FOREIGN KEY (questionid)
        REFERENCES questions(id)
        ON DELETE CASCADE,

    FOREIGN KEY (answerid)
        REFERENCES answers(id)
        ON DELETE CASCADE
);