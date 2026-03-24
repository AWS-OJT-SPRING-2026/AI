## assignment_generator.py
--title <bắt buộc>
--subject-id <bắt buộc>
--chapter-ids <bắt buộc>
--total-questions <bắt buộc>
--num-ai-questions <tùy chọn>
--class-id <tùy chọn>
--userid <bắt buộc>
--deadline <tùy chọn>
* Ví dụ:
python src/assignment_gen/assignment_generator.py --title "Bài tập Toán" --subject-id 1 --chapter-ids 1 2 3 --total-questions 10 --num-ai-questions 5 --class-id 1 --userid 1 --deadline "2022-12-31 23:59:59"

## quiz_generator.py
--userid <bắt buộc>
--subject-id <bắt buộc>
--chapter-id <bắt buộc>
--lesson-id <tùy chọn>
--total-questions <bắt buộc>
--level-1 <tùy chọn>
--level-2 <tùy chọn>
--level-3 <tùy chọn>
* Ví dụ:
python src/quiz_gen/quiz_generator.py --userid 1 --subject-id 1 --book-id 1 --chapter-id 1 --lesson-id 1 --total-questions 10 --level-1 5 --level-2 3 --level-3 2

## roadmap_generator.py
--student-id <bắt buộc>
--subject-id <bắt buộc>
--total-time <bắt buộc> (giờ)
* Ví dụ:
python src/roadmap_gen/roadmap_generator.py --student-id 1 --subject-id 1 --total-time 10
>>>>>>> c96ace531ad17fe949d51a09c44f3ba84daa3dd0
